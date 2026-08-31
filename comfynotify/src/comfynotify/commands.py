"""Zulip mention intake: one posted line replaces the `comfynotify` handover.

Every agent can already post to Zulip; almost none of them reliably has this
project's CLI on its PATH. So the command *is* a Zulip post:

    @**Comfy Notifier** watch <prompt_id> [free text kept as the note]

The mention narrow (`is:mentioned`) is the intake because it reaches public
channels the bot never subscribed to, and because a command posted while the
daemon was down is still returned after a restart. Three rules shape the rest
of this module:

- **The ack is a reaction, never a post.** A bot message in a `workrun-` topic
  re-serves that topic's owner — it is the resume mechanism — so acking with
  "watching…" would wake the agent early and burn a paid run.
- **A malformed command is the one case that should post back**, because the
  poster has to learn it was not understood, and waking it is then correct.
- **The mention is never consumed.** Answering it does not remove it from the
  narrow, so a high-water mark on disk is what stops a restart re-ticketing
  every command a topic ever carried.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Iterable

from .tickets import DEFAULT_TIMEOUT_S, now, replace_ticket, write_ticket

# The braindump spelled it `watch_comfy`; the plan settled on `watch`. Both are
# accepted, because refusing a synonym teaches nothing.
WATCH_VERBS = ("watch", "watch_comfy")
ACK_EMOJI = "eyes"
# `@**Name**`, and Zulip's silent `@_**Name**` form, anywhere in the line.
MENTION = re.compile(r"@_?\*\*[^*]+\*\*")
SELFNOTE_MARK = "[selfnote]"


class CommandError(ValueError):
    """A command that reached us but could not be read."""


def parse_command(content: str) -> tuple[str, str]:
    """`(prompt_id, note)` from the text of a mention, or raise CommandError.

    The prompt id is unquoted on the way in: an agent that writes it inside
    backticks means the same job as one that does not.
    """
    text = MENTION.sub(" ", content or "").strip()
    words = text.split()
    if not words:
        raise CommandError("no command after the mention")
    verb = words[0].lower().strip("`")
    if verb not in WATCH_VERBS:
        raise CommandError(f"unknown command {verb!r}")
    if len(words) < 2:
        raise CommandError(f"{verb} needs a prompt_id")
    prompt_id = words[1].strip("`\"'")
    if not prompt_id:
        raise CommandError(f"{verb} needs a prompt_id")
    return prompt_id, " ".join(words[2:]).strip()


def usage_line(bot_name: str) -> str:
    return (
        f"comfy command not understood: post `@**{bot_name}** watch <prompt_id> "
        "[note]` in a public-channel topic"
    )


def read_mark(path: Path) -> int | None:
    """The highest message id already handled, or None when never run here."""
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = state.get("last_message_id") if isinstance(state, dict) else None
    return int(value) if isinstance(value, int) else None


def write_mark(path: Path, message_id: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_ticket(path, {"last_message_id": int(message_id), "updated_at": now()})


def commandable(messages: Iterable[dict[str, Any]], self_id: int, mark: int) -> list[dict[str, Any]]:
    """Mentions that are commands to consider, oldest first.

    Resolved (`✔ `) topics are deliberately *not* skipped: a command posted
    moments before somebody closed the conversation still deserves its
    callback, and the callback belongs where the command was posted.
    """
    keep = []
    for message in messages:
        if message.get("type") != "stream" or message.get("sender_id") == self_id:
            continue
        if SELFNOTE_MARK in str(message.get("content") or ""):
            continue
        if int(message.get("id") or 0) <= mark:
            continue
        if not str(message.get("subject") or "") or not str(message.get("display_recipient") or ""):
            continue
        keep.append(message)
    return sorted(keep, key=lambda message: int(message["id"]))


class CommandIntake:
    """The daemon's second sweep: Zulip mentions in, tickets out."""

    def __init__(
        self,
        client,
        *,
        tickets_dir: Path,
        state_path: Path,
        comfyui_url: str,
        bot_name: str,
        self_id: int,
        send: Callable[[str, str, str], None],
        log: Callable[[str], None],
        timeout_s: int = DEFAULT_TIMEOUT_S,
    ) -> None:
        self.client = client
        self.tickets_dir = tickets_dir
        self.state_path = state_path
        self.comfyui_url = comfyui_url
        self.bot_name = bot_name
        self.self_id = self_id
        self.send = send
        self.log = log
        self.timeout_s = timeout_s

    def sweep_once(self) -> int:
        mark = read_mark(self.state_path)
        messages = self.client.mentions()
        if mark is None:
            # First run on this host: adopt the present as the past. Every
            # command Zulip still remembers predates this daemon, and
            # ticketing a month of history at once is not what anybody asked.
            highest = max((int(m.get("id") or 0) for m in messages), default=0)
            write_mark(self.state_path, highest)
            self.log(f"command mark seeded at {highest}")
            return 0
        handled = 0
        for message in commandable(messages, self.self_id, mark):
            # The mark advances *before* the work, not after. A crash between
            # the two loses one command; the other order posts one callback
            # twice, which serves an agent twice — the prohibition that
            # matters. Nothing here is expensive enough to be worth the risk.
            write_mark(self.state_path, int(message["id"]))
            self._handle(message)
            handled += 1
        return handled

    def _handle(self, message: dict[str, Any]) -> None:
        channel = str(message.get("display_recipient") or "")
        topic = str(message.get("subject") or "")
        message_id = int(message["id"])
        try:
            prompt_id, note = parse_command(str(message.get("content") or ""))
        except CommandError as error:
            self.log(f"command {message_id} rejected: {error}")
            self.send(channel, topic, usage_line(self.bot_name))
            return
        ticket = {
            "prompt_id": prompt_id,
            "comfyui_url": self.comfyui_url,
            "channel": channel,
            "topic": topic,
            "mention": None,
            "note": note,
            "timeout_s": self.timeout_s,
            "created_at": now(),
            "command_message_id": message_id,
        }
        try:
            path = write_ticket(self.tickets_dir, ticket)
        except FileExistsError:
            self.log(f"command {message_id} ignored: {prompt_id} is already watched")
            self._ack(message_id)
            return
        self.log(f"command {message_id} watching {prompt_id} for {channel}/{topic} ({path.name})")
        self._ack(message_id)

    def _ack(self, message_id: int) -> None:
        try:
            self.client.add_reaction(message_id, ACK_EMOJI)
        except Exception as error:  # noqa: BLE001 — an ack is never worth the ticket
            self.log(f"command {message_id} ack failed: {error}")
