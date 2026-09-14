"""Zulip mention intake: one posted line replaces the `comfynotify` handover.

Every agent can already post to Zulip; almost none of them reliably has this
project's CLI on its PATH. So the command *is* a Zulip post:

    @**Comfy Notifier** watch <prompt_id> [free text kept as the note]

The intake is an **event queue** registered for every public channel
(`better_zulip_call` p1 step 5): a command reaches the daemon the moment it
is posted, in a channel the bot never joined. The mention narrow
(`is:mentioned`) is read once at startup and after a queue expiry, because a
command posted while the daemon was down is still returned by it. Three rules
shape the rest of this module:

- **The ack is a reaction, never a post.** A bot message in a `workrun-` topic
  re-serves that topic's owner — it is the resume mechanism — so acking with
  "watching…" would wake the agent early and burn a paid run.
- **A malformed command is the one case that should post back**, because the
  poster has to learn it was not understood, and waking it is then correct —
  but **only once per topic**. That post wakes an agent, and an agent woken by
  it may answer by naming this bot again; `zulip_command` step 4 watched
  exactly that start between the notifier and Front, one paid run per lap.
  One line per topic is enough for a person and cannot become a loop.
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
# How many topics remember that they were already told. A bound, not a policy:
# the file should not grow forever, and a topic that fell out of it is one
# nobody has posted junk in for a very long time.
ERROR_TOPIC_MEMORY = 200
# `@**Name**`, and Zulip's silent `@_**Name**` form, anywhere in the line.
MENTION = re.compile(r"@_?\*\*[^*]+\*\*")
SELFNOTE_MARK = "[selfnote]"


class CommandError(ValueError):
    """A command that reached us but could not be read."""


def parse_line(line: str) -> tuple[str, str]:
    """`(prompt_id, note)` from one line that mentions us, or raise.

    The prompt id is unquoted on the way in: an agent that writes it inside
    backticks means the same job as one that does not.
    """
    words = MENTION.sub(" ", line).split()
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


def parse_command(content: str) -> tuple[str, str]:
    """`(prompt_id, note)` from a message, or raise CommandError.

    **The command is a line, not a message.** A poster is not always a bare
    command: agforge's listener answers its own run topic with a short report
    whose *second* line is the watch line, and reading the whole message as
    one command would both miss the verb and swallow the rest of the report
    into the note. So every line that mentions us is tried in turn, and the
    first one that parses is the command; when none do, the first mentioning
    line is the one whose complaint is reported, because that is the line the
    poster most likely meant as a command.
    """
    lines = [line for line in (content or "").splitlines() if MENTION.search(line)]
    if not lines:
        # No mention in the body at all (a `@_**silent**` form Zulip rendered
        # away, or a caller passing bare text). Read it as one command.
        return parse_line(content or "")
    first_error: CommandError | None = None
    for line in lines:
        try:
            return parse_line(line)
        except CommandError as error:
            first_error = first_error or error
    raise first_error  # noqa: RSE102 — always set: the loop ran at least once


def usage_line(bot_name: str) -> str:
    return (
        f"comfy command not understood: post `@**{bot_name}** watch <prompt_id> "
        "[note]` in a public-channel topic"
    )


def read_state(path: Path) -> dict[str, Any]:
    """The daemon's command memory: the high-water mark and who has been told.

    An empty dict means "never run here", which is what makes the first sweep
    seed itself instead of ticketing everything Zulip still remembers.
    """
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return state if isinstance(state, dict) else {}


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_ticket(path, {**state, "updated_at": now()})


def read_mark(path: Path) -> int | None:
    value = read_state(path).get("last_message_id")
    return int(value) if isinstance(value, int) else None


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
    """The daemon's command door: Zulip mentions in, tickets out."""

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

    def catch_up(self) -> int:
        """One `is:mentioned` read: what arrived while the daemon was down.

        Startup and queue-expiry recovery, and the only place the narrow is
        read any more — the steady state is the event queue in `run()`.
        `better_zulip_call` p1 step 1 measured the old five-second poll of
        this narrow at 696 calls an hour, 78 % of the realm's API traffic,
        every one of them reading the same answer.
        """
        state = read_state(self.state_path)
        messages = self.client.mentions()
        mark = state.get("last_message_id")
        if not isinstance(mark, int):
            # First run on this host: adopt the present as the past. Every
            # command Zulip still remembers predates this daemon, and
            # ticketing a month of history at once is not what anybody asked.
            highest = max((int(m.get("id") or 0) for m in messages), default=0)
            write_state(self.state_path, {**state, "last_message_id": highest})
            self.log(f"command mark seeded at {highest}")
            return 0
        handled = 0
        for message in commandable(messages, self.self_id, mark):
            # The mark advances *before* the work, not after. A crash between
            # the two loses one command; the other order posts one callback
            # twice, which serves an agent twice — the prohibition that
            # matters. Nothing here is expensive enough to be worth the risk.
            state["last_message_id"] = int(message["id"])
            write_state(self.state_path, state)
            self._handle(message, state)
            handled += 1
        return handled

    def run(self, stop=None, *, log_polls: bool = False) -> None:
        """Follow the event queue: a message that mentions this bot is a
        command the moment it lands. Blocks until `stop` is set.

        Registered for every public channel (`all_public_streams`), so a
        command in a channel the bot never joined reaches it — the same
        reach the narrow had. A dead queue is recovered by one narrow read
        (`catch_up`) and a fresh registration; a 429 is waited out with the
        queue kept.
        """
        import threading

        from agag.zulip import QueueExpired, RateLimited, ZulipError, ZulipTimeout, rate_limit_backoff

        stop = stop if stop is not None else threading.Event()
        queue_id = None
        last_event_id = -1
        strikes = 0
        while not stop.is_set():
            try:
                if queue_id is None:
                    self.catch_up()
                    queue_id, last_event_id = self.client.register(
                        ["message"], all_public_streams=True, fetch_event_types=[])
                    self.log(f"command intake on the event queue {queue_id}")
                events = self.client.poll(queue_id, last_event_id)
            except ZulipTimeout:
                continue
            except QueueExpired:
                self.log("command intake queue expired; catching up and re-registering")
                queue_id = None
                continue
            except RateLimited as limited:
                strikes += 1
                delay = rate_limit_backoff(limited.retry_after, strikes)
                self.log(f"command intake rate limited: {limited}; waiting {delay:.0f}s")
                stop.wait(delay)
                continue
            except ZulipError as error:
                self.log(f"command intake poll failed: {error}; retrying in 5s")
                queue_id = None
                stop.wait(5.0)
                continue
            strikes = 0
            for event in events:
                last_event_id = max(last_event_id, int(event.get("id", last_event_id)))
                if event.get("type") != "message":
                    continue
                message = event.get("message") or {}
                if not self.addressed(message, event.get("flags")):
                    continue
                self.handle_event_message(message)

    def addressed(self, message: dict[str, Any], flags=None) -> bool:
        """Whether this message names **this bot** — Zulip's `mentioned` flag
        on our own queue, or our own name in the text.

        The narrow answered only our mentions, so nothing had to ask *who*
        was mentioned. The queue carries every public message, and a post
        naming somebody else is not a command: reading it as one posted a
        refusal into Front's conversation and bought a paid run (met live,
        `better_zulip_call` p1 step 7, on the first request after the switch).
        """
        if "mentioned" in (flags or []):
            return True
        content = str(message.get("content") or "")
        return f"@**{self.bot_name}**" in content or f"@_**{self.bot_name}**" in content

    def handle_event_message(self, message: dict[str, Any]) -> int:
        """One message off the queue: a command if it is one and newer than
        the mark, handled exactly as the narrow's would be."""
        state = read_state(self.state_path)
        mark = state.get("last_message_id")
        if not isinstance(mark, int):
            mark = 0
        found = commandable([message], self.self_id, mark)
        for one in found:
            state["last_message_id"] = int(one["id"])
            write_state(self.state_path, state)
            self._handle(one, state)
        return len(found)

    def _handle(self, message: dict[str, Any], state: dict[str, Any]) -> None:
        channel = str(message.get("display_recipient") or "")
        topic = str(message.get("subject") or "")
        message_id = int(message["id"])
        try:
            prompt_id, note = parse_command(str(message.get("content") or ""))
        except CommandError as error:
            self._refuse(message_id, channel, topic, str(error), state)
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

    def _refuse(self, message_id: int, channel: str, topic: str, reason: str,
                state: dict[str, Any]) -> None:
        """Tell a topic once that it is not being understood, then stay quiet.

        The post is deliberate — the poster must learn its command did nothing
        — but it also *wakes* that poster, and a woken agent that answers by
        naming this bot again would be answered again. Step 4 watched that
        start with Front. The topic is told once and then left alone; the log
        keeps every refusal.
        """
        told = [str(name) for name in state.get("errored_topics") or []]
        key = f"{channel}/{topic}"
        if key in told:
            self.log(f"command {message_id} rejected: {reason} (already told {key}, staying quiet)")
            return
        state["errored_topics"] = (told + [key])[-ERROR_TOPIC_MEMORY:]
        write_state(self.state_path, state)
        self.log(f"command {message_id} rejected: {reason}")
        self.send(channel, topic, usage_line(self.bot_name))

    def _ack(self, message_id: int) -> None:
        try:
            self.client.add_reaction(message_id, ACK_EMOJI)
        except Exception as error:  # noqa: BLE001 — an ack is never worth the ticket
            self.log(f"command {message_id} ack failed: {error}")
