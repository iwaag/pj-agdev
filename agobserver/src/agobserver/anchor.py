"""The watch record, which is the Zulip topic.

Observer keeps no database of requests. A watch **is** a topic in this
instance's own channel, and what a program must resolve without guessing is
written into it as `[selfnote]` lines — invisible in every chatlog, and never
counted as somebody speaking, so nothing here buys the requester a run.

    [selfnote][watch] <slug>          the anchor; its own message id IS the
                                      watch id, so `w5901` names this request
                                      through a rename, a ✔ and a reused name
    [selfnote][accepted] {json}       the accepted request: condition, target,
                                      destination as written, requester
    [selfnote][state] <word>          where the lifecycle stands

Identity is a message id for the reason the rest of the realm learned it the
hard way (`refactor` p1–p3): a topic name is reusable and a resolve renames
it, so anything that remembers a name eventually reads somebody else's
conversation. The anchor's id is the one identifier nothing touches.

The visible half is an ordinary post saying the same thing in words. That is
not duplication: the notes are for this process, the post is for the human
scrolling the channel, and neither can be derived from the other by a reader
that only has one of them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agag import selfnote
from agag.zulip import ZulipClient, topic_history_across_resolve

#: The anchor. Its own message id is the watch's identity.
WATCH_TAG = "watch"
#: The accepted request, as JSON, written once when the watch becomes active.
ACCEPTED_TAG = "accepted"
#: The lifecycle word, appended; the newest one wins.
STATE_TAG = "state"

#: Waiting to be evaluated on every interval.
ACTIVE = "active"
#: Something concrete was asked in the topic; not evaluated until answered.
NEEDS_INPUT = "needs-input"
#: The condition held, the notification was delivered, the watch is finished.
MET = "met"
#: The condition held but the destination is gone; nobody was told.
UNDELIVERABLE = "undeliverable"

#: The states a watch is scheduled in. Everything else is finished or waiting.
SCHEDULED = (ACTIVE,)

HISTORY = 200

__all__ = [
    "ACCEPTED_TAG",
    "ACTIVE",
    "MET",
    "NEEDS_INPUT",
    "SCHEDULED",
    "STATE_TAG",
    "UNDELIVERABLE",
    "WATCH_TAG",
    "Watch",
    "accepted_note",
    "read_watch",
    "state_note",
    "watch_note",
]


def watch_note(slug: str) -> str:
    return selfnote.note(WATCH_TAG, slug)


def accepted_note(accepted: dict[str, Any]) -> str:
    """The accepted request as one note. JSON, because a program reads it."""
    return selfnote.note(ACCEPTED_TAG, json.dumps(accepted, ensure_ascii=False, sort_keys=True))


def state_note(state: str) -> str:
    return selfnote.note(STATE_TAG, state)


@dataclass(frozen=True)
class Watch:
    """One watch, read out of its own topic.

    `watch_id` is the anchor note's message id — `None` when the topic holds
    no anchor, which is what an ordinary question in this channel looks like
    and is not an error.
    """

    channel: str
    topic: str
    watch_id: int | None = None
    slug: str = ""
    state: str = ""
    accepted: dict[str, Any] = field(default_factory=dict)
    #: The newest message id seen when this was read. What "no new evidence"
    #: is measured against.
    last_message_id: int = 0

    @property
    def name(self) -> str:
        """`w5901` — how a watch is named to a human and in a notification."""
        return f"w{self.watch_id}" if self.watch_id else f"{self.channel}/{self.topic}"

    @property
    def scheduled(self) -> bool:
        return self.state in SCHEDULED

    @property
    def condition(self) -> str:
        return str(self.accepted.get("condition") or "")

    @property
    def target(self) -> str:
        return str(self.accepted.get("target") or "")

    @property
    def destination(self) -> str:
        return str(self.accepted.get("destination") or "")

    @property
    def requester(self) -> str:
        return str(self.accepted.get("requester") or "")


def read_watch(
    client: ZulipClient, channel: str, topic: str, self_id: int, *, history: list[dict] | None = None
) -> Watch:
    """The watch a topic holds, as it stands now.

    Only notes written by this bot are read: an anchor is identified by its
    sender, so a copy somebody else wrote would make the record lie about who
    accepted what. Reading follows Zulip's `✔ ` rename, because the post that
    cancels a watch is very often the one that renames its topic.
    """
    messages = history if history is not None else topic_history_across_resolve(
        client, channel, topic, HISTORY
    )
    ours = [m for m in messages if m.get("sender_id") == self_id]
    watch_id: int | None = None
    slug = ""
    accepted: dict[str, Any] = {}
    state = ""
    for message in ours:
        content = message.get("content")
        anchor = selfnote.parse_note(content, WATCH_TAG)
        # The *earliest* anchor wins: a second one is a mistake, never a move.
        if anchor is not None and watch_id is None:
            watch_id, slug = int(message["id"]), anchor
        payload = selfnote.parse_note(content, ACCEPTED_TAG)
        if payload is not None:
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                accepted = parsed
        word = selfnote.parse_note(content, STATE_TAG)
        if word is not None:
            state = word
    return Watch(
        channel=channel,
        topic=topic,
        watch_id=watch_id,
        slug=slug,
        state=state,
        accepted=accepted,
        last_message_id=max((int(m.get("id", 0)) for m in messages), default=0),
    )
