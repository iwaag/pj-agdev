"""Ticket state machine and the one-post terminal delivery boundary."""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .comfy import ComfyClient, ComfyUnavailable, output_references, view_url
from .tickets import archive, load_tickets, replace_ticket

LOST_POLLS = 3
UNREACHABLE_S = int(os.environ.get("COMFYNOTIFY_UNREACHABLE_S", "120"))
# The post is a notification, not a manifest. Zulip accepts an over-long
# message and *truncates* it silently (a 124-frame graph's output list ran to
# ~27 000 characters against a ~10 000 cap, and the receiving agent got an
# unparseable block), so the post carries two lines and nothing else; the
# full record, outputs included, is kept in the archived ticket. The
# receiving run reads `GET /history/<prompt_id>` itself.
ERROR_EXCERPT = 300


def _elapsed(ticket: dict[str, Any], clock: Callable[[], float]) -> int:
    created = datetime.fromisoformat(ticket["created_at"])
    return max(0, round(datetime.now(UTC).timestamp() - created.timestamp()))


def _record(ticket: dict[str, Any], state: str, elapsed: int, **extra: Any) -> dict[str, Any]:
    return {
        "state": state,
        "prompt_id": ticket["prompt_id"],
        "wall_s": elapsed,
        "note": ticket.get("note", ""),
        **extra,
    }


def _readable_error(status: dict[str, Any]) -> str:
    """History errors can contain tensors; callbacks need a bounded diagnosis."""
    try:
        rendered = json.dumps(status.get("messages", []), ensure_ascii=False)
    except (TypeError, ValueError):
        rendered = str(status.get("messages", ""))
    return rendered[:2000]


def terminal_record(ticket: dict[str, Any], client: ComfyClient, clock: Callable[[], float] = time.monotonic) -> dict[str, Any] | None:
    """Poll a ticket once, mutating its recovery counters but never posting."""
    elapsed = _elapsed(ticket, clock)
    try:
        entry = client.history(str(ticket["prompt_id"]))
        queue_ids = client.queue_ids()
    except ComfyUnavailable as error:
        first = ticket.setdefault("unreachable_since", clock())
        if clock() - float(first) >= UNREACHABLE_S:
            return _record(ticket, "unreachable", elapsed, error=str(error)[:500])
        return None
    ticket.pop("unreachable_since", None)
    prompt_id = str(ticket["prompt_id"])
    if entry:
        ticket["seen"] = True
        status = entry.get("status") or {}
        status_name = str(status.get("status_str") or "").lower()
        if status_name in {"success", "error"} or status.get("completed"):
            state = "error" if status_name == "error" else "success"
            outputs = output_references(entry)
            for reference in outputs:
                reference["url"] = view_url(client.base_url, reference)
            vram_free = None
            try:
                vram_free = client.vram_free()
            except ComfyUnavailable:
                pass
            return _record(
                ticket, state, elapsed, outputs=outputs,
                outputs_total=len(outputs), vram_free=vram_free,
                error=_readable_error(status) if state == "error" else None,
            )
    if elapsed >= int(ticket["timeout_s"]):
        return _record(ticket, "timeout", elapsed, in_queue=prompt_id in queue_ids)
    if prompt_id in queue_ids:
        ticket["missing_polls"] = 0
        return None
    ticket["missing_polls"] = int(ticket.get("missing_polls", 0)) + 1
    if ticket["missing_polls"] >= LOST_POLLS:
        return _record(ticket, "lost", elapsed, missing_polls=ticket["missing_polls"])
    return None


def _detail(record: dict[str, Any]) -> str:
    state = record["state"]
    if state == "success":
        return f"{record.get('outputs_total', 0)} outputs"
    if state == "error":
        return "error: " + " ".join(str(record.get("error") or "").split())[:ERROR_EXCERPT]
    if state == "timeout":
        return "timed out, " + ("still in queue" if record.get("in_queue") else "not in queue")
    if state == "lost":
        return "not in queue or history — ComfyUI probably restarted"
    if state == "unreachable":
        return "ComfyUI unreachable: " + str(record.get("error") or "")[:ERROR_EXCERPT]
    return ""


def message(record: dict[str, Any], mention: str | None = None) -> str:
    """Two lines: what happened, and the id to look it up with."""
    prefix = f"@**{mention}** " if mention else ""
    headline = f"{prefix}comfy {record['state']} {record['prompt_id'][:8]} in {record['wall_s']}s — {_detail(record)}"
    if record.get("note"):
        headline += f" · {record['note']}"
    return f"{headline}\nprompt_id `{record['prompt_id']}` — read `GET /history/<prompt_id>` for outputs"


class Notifier:
    def __init__(self, tickets_dir: Path, log_path: Path, *, agentchat: str = "agentchat",
                 clock: Callable[[], float] = time.monotonic,
                 live_topic: Callable[[str, str], str] | None = None) -> None:
        self.tickets_dir = tickets_dir
        self.log_path = log_path
        self.agentchat = agentchat
        self.clock = clock
        # Resolving a topic *renames* it to `✔ <topic>`. A ticket remembers the
        # name the job was commanded under, and a run that finishes by closing
        # its own topic renames it while its job is still rendering — so
        # posting the remembered name creates an empty topic beside the real
        # conversation and the callback serves nobody. Measured in
        # `zulip_command` step 4: the callback for task 2 landed in a fresh
        # `workrun-task2-m-51` while every other message sat in
        # `✔ workrun-task2-m-51`.
        self.live_topic = live_topic or (lambda _channel, topic: topic)

    def log(self, text: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as output:
            output.write(text + "\n")

    def send(self, channel: str, topic: str, text: str) -> None:
        """The one delivery boundary — the callback and the command's own
        error line leave through the same door."""
        subprocess.run(
            [self.agentchat, "send", channel, topic, text],
            check=True, env={**os.environ, "AGENTCHAT_HOME": ""}, text=True,
        )

    def post(self, ticket: dict[str, Any], record: dict[str, Any]) -> None:
        channel = str(ticket["channel"])
        topic = self.live_topic(channel, str(ticket["topic"]))
        self.send(channel, topic, message(record, ticket.get("mention")))

    def sweep_once(self) -> int:
        completed = 0
        for path, ticket in load_tickets(self.tickets_dir):
            client = ComfyClient(str(ticket["comfyui_url"]))
            record = terminal_record(ticket, client, self.clock)
            if record is None:
                replace_ticket(path, ticket)
                continue
            try:
                self.post(ticket, record)
            except (OSError, subprocess.SubprocessError) as error:
                self.log(f"{ticket['prompt_id']} post_failed {error}")
                replace_ticket(path, ticket)
                continue
            archive(path, {"ticket": ticket, "record": record})
            self.log(f"{ticket['prompt_id']} {record['state']} posted")
            completed += 1
        return completed
