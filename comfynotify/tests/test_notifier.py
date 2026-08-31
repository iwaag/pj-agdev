from __future__ import annotations

import json

from datetime import UTC, datetime

from comfynotify import notifier
from comfynotify.notifier import LOST_POLLS, Notifier, terminal_record


def ticket(**overrides):
    return {
        "prompt_id": "prompt-12345678",
        "created_at": datetime.now(UTC).isoformat(),
        "timeout_s": 1200,
        **overrides,
    }


class FakeClient:
    base_url = "http://comfy.invalid"

    def __init__(self, entry=None, queue=(), unavailable=False):
        self.entry, self.queue, self.unavailable = entry, set(queue), unavailable

    def history(self, _prompt_id):
        if self.unavailable:
            from comfynotify.comfy import ComfyUnavailable
            raise ComfyUnavailable("offline")
        return self.entry

    def queue_ids(self):
        return self.queue

    def vram_free(self):
        return 123


def test_finished_ticket_has_outputs_and_view_url():
    entry = {"status": {"status_str": "success", "completed": True},
             "outputs": {"9": {"images": [{"filename": "still.png", "subfolder": "x", "type": "output"}]}}}
    result = terminal_record(ticket(), FakeClient(entry=entry))
    assert result["state"] == "success"
    assert result["outputs"][0]["url"] == "http://comfy.invalid/view?filename=still.png&subfolder=x&type=output"


def test_error_is_truncated_to_a_readable_callback_size():
    entry = {"status": {"status_str": "error", "messages": ["x" * 3000]}}
    result = terminal_record(ticket(), FakeClient(entry=entry))
    assert result["state"] == "error"
    assert len(result["error"]) == 2000


def test_running_ticket_is_not_terminal():
    assert terminal_record(ticket(), FakeClient(queue={"prompt-12345678"})) is None


def test_unknown_ticket_becomes_lost_after_three_polls():
    value = ticket()
    client = FakeClient()
    for _ in range(LOST_POLLS - 1):
        assert terminal_record(value, client) is None
    assert terminal_record(value, client)["state"] == "lost"


def test_unreachable_ticket_is_terminal_after_threshold(monkeypatch):
    import comfynotify.notifier as notifier
    monkeypatch.setattr(notifier, "UNREACHABLE_S", 0)
    assert terminal_record(ticket(), FakeClient(unavailable=True))["state"] == "unreachable"


def test_posted_ticket_is_archived_so_a_restart_cannot_post_twice(tmp_path, monkeypatch):
    from comfynotify import notifier as module
    from comfynotify.tickets import write_ticket
    tickets = tmp_path / "tickets"
    write_ticket(tickets, {**ticket(), "comfyui_url": "http://comfy.invalid", "channel": "general", "topic": "test"})
    monkeypatch.setattr(module, "ComfyClient", lambda _url: FakeClient(entry={"status": {"status_str": "success"}}))
    sent = []
    service = Notifier(tickets, tmp_path / "out.log")
    monkeypatch.setattr(service, "post", lambda value, record: sent.append(record))
    assert service.sweep_once() == 1
    assert service.sweep_once() == 0
    assert len(sent) == 1
    assert len(list((tickets / "done").glob("*.json"))) == 1


def test_the_callback_follows_a_topic_that_was_resolved_while_the_job_ran(tmp_path, monkeypatch):
    """A run that closes its own topic renames it mid-render. Posting the
    remembered name opens an empty topic beside the real conversation, and
    the callback then serves nobody (`zulip_command` step 4, task 2)."""
    from comfynotify import notifier as module
    from comfynotify.tickets import write_ticket
    tickets = tmp_path / "tickets"
    write_ticket(tickets, {**ticket(), "comfyui_url": "http://comfy.invalid",
                           "channel": "work-m-51", "topic": "workrun-task2-m-51"})
    monkeypatch.setattr(module, "ComfyClient", lambda _url: FakeClient(entry={"status": {"status_str": "success"}}))
    sent = []
    service = Notifier(tickets, tmp_path / "out.log",
                       live_topic=lambda channel, topic: f"\u2714 {topic}")
    monkeypatch.setattr(service, "send", lambda channel, topic, text: sent.append((channel, topic)))
    assert service.sweep_once() == 1
    assert sent == [("work-m-51", "\u2714 workrun-task2-m-51")]


def test_post_is_two_lines_however_many_outputs_the_job_has():
    """A 124-frame video graph lists 125 outputs; Zulip truncates long posts
    silently, so the post names the job and nothing else."""
    images = [{"filename": f"frame_{n:05d}.png", "subfolder": "", "type": "output"}
              for n in range(125)]
    entry = {"status": {"status_str": "success", "completed": True},
             "outputs": {"9": {"images": images}}}
    result = terminal_record(ticket(note="A jump"), FakeClient(entry=entry))
    assert result["outputs_total"] == 125 and len(result["outputs"]) == 125  # archived in full
    posted = notifier.message(result, mention="Someone")
    lines = posted.splitlines()
    assert len(lines) == 2 and len(posted) < 400
    assert lines[0].startswith("@**Someone** comfy success prompt-1 in ")
    assert "125 outputs" in lines[0] and "A jump" in lines[0]
    assert "prompt-12345678" in lines[1]


def test_error_post_carries_a_short_excerpt():
    entry = {"status": {"status_str": "error", "messages": ["x" * 3000]}}
    result = terminal_record(ticket(), FakeClient(entry=entry))
    posted = notifier.message(result)
    assert posted.startswith("comfy error prompt-1 in ") and len(posted) < 500
