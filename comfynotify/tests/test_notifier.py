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


def test_many_outputs_are_capped_so_the_post_survives_zulips_length_limit():
    """A 124-frame video graph lists 125 outputs; Zulip truncates silently."""
    images = [{"filename": f"frame_{n:05d}.png", "subfolder": "", "type": "output"}
              for n in range(125)]
    entry = {"status": {"status_str": "success", "completed": True},
             "outputs": {"9": {"images": images}}}
    result = terminal_record(ticket(), FakeClient(entry=entry))
    assert result["outputs_total"] == 125
    assert len(result["outputs"]) == notifier.MAX_OUTPUTS
    posted = notifier.message(result)
    assert len(posted) < 10000
    assert json.loads(posted.split("```json\n", 1)[1].rsplit("\n```", 1)[0])["prompt_id"]
