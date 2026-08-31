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
# Zulip accepts an over-long message and *truncates* it silently: the send
# succeeds, the daemon logs "posted", and the receiving agent gets an
# unparseable JSON block with prompt_id/state/wall_s cut off the end. A
# 124-frame video graph lists 125 outputs (~27 000 characters) against a
# ~10 000-character cap, so the list is capped here and `outputs_total`
# carries the real count. The callback names the job; it is not a manifest.
MAX_OUTPUTS = int(os.environ.get("COMFYNOTIFY_MAX_OUTPUTS", "6"))


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
                ticket, state, elapsed, outputs=outputs[:MAX_OUTPUTS],
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


def message(record: dict[str, Any], mention: str | None = None) -> str:
    prefix = f"@**{mention}** " if mention else ""
    headline = f"{prefix}comfy {record['state']} {record['prompt_id'][:8]} in {record['wall_s']}s"
    return f"{headline}\n```json\n{json.dumps(record, indent=2, sort_keys=True)}\n```"


class Notifier:
    def __init__(self, tickets_dir: Path, log_path: Path, *, agentchat: str = "agentchat",
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.tickets_dir = tickets_dir
        self.log_path = log_path
        self.agentchat = agentchat
        self.clock = clock

    def log(self, text: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as output:
            output.write(text + "\n")

    def post(self, ticket: dict[str, Any], record: dict[str, Any]) -> None:
        subprocess.run(
            [self.agentchat, "send", str(ticket["channel"]), str(ticket["topic"]),
             message(record, ticket.get("mention"))],
            check=True, env={**os.environ, "AGENTCHAT_HOME": ""}, text=True,
        )

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
