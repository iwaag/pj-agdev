"""Where a notification goes, and how that survives the conversation moving.

A requester names the destination in words. Two spellings are accepted:

- a **message link** (Zulip's *Copy link to message*), or `msg:<id>`;
- `<channel>/<topic>`.

They are no longer two qualities of destination. Since ex1 both are resolved
to **a message id in the intended conversation at intake**, and that id is
what is stored and what every later lookup uses. A name is how the requester
said it and how the topic explains it; the id is what it means. The reason is
the one the rest of the realm arrived at the hard way: a topic name is
reusable, so a destination remembered by name eventually delivers into work
it knows nothing about — and a rename is not a rare accident, it is what
resolving a topic does.

Resolution is three-valued, and the third value is the point:

- **open** — a conversation that can be posted into now;
- **absent** or **closed** — Zulip answered, and the answer is terminal;
- **failed** — the lookup never got an answer. Nothing may be concluded from
  it: not that the destination is gone, not that it is fine. Try again.

Flattening the third into the second is how a watch that was met loses its
notification to one bad minute of network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agag.selfnote import Conversation, parse_conversation
from agag.zulip import (
    RESOLVED_TOPIC_PREFIX,
    ZulipClient,
    ZulipError,
    ZulipRejected,
    conversation_of,
)

#: `.../near/5901` in a Zulip message link, and the bare spellings beside it.
_NEAR = re.compile(r"/near/(\d+)")
_EXPLICIT_ID = re.compile(r"^(?:msg:|message:|#)?(\d+)$", re.IGNORECASE)

#: A conversation that can be posted into now.
OPEN = "open"
#: Zulip says it is not there. Terminal.
ABSENT = "absent"
#: It is there and resolved (✔). Terminal: a watch is not important enough
#: to reopen somebody's finished work.
CLOSED = "closed"
#: The lookup did not answer. Not a fact about the destination.
FAILED = "failed"

__all__ = [
    "ABSENT",
    "CLOSED",
    "FAILED",
    "OPEN",
    "Destination",
    "Resolved",
    "anchored",
    "parse",
    "resolve",
]


@dataclass(frozen=True)
class Destination:
    """A destination as the requester wrote it, once it has been understood.

    Exactly one of `message_id` / `conversation` is set. `raw` is kept so the
    watch topic can say what it was told rather than what it inferred.
    """

    raw: str
    message_id: int | None = None
    conversation: Conversation | None = None

    @property
    def describes(self) -> str:
        if self.message_id is not None:
            return f"the conversation holding message {self.message_id}"
        return str(self.conversation)


@dataclass(frozen=True)
class Resolved:
    """Where the notification goes now, or why it does not go there yet.

    `outcome` is the whole answer; the properties below are only the readable
    spellings of it. `message_id` is the anchor the conversation was found
    from — at intake it is what gets persisted, so that every later lookup
    asks the same question of the same id.
    """

    outcome: str
    conversation: Conversation | None = None
    reason: str = ""
    message_id: int | None = None

    @property
    def deliverable(self) -> bool:
        return self.outcome == OPEN

    @property
    def closed(self) -> bool:
        return self.outcome == CLOSED

    @property
    def failed(self) -> bool:
        return self.outcome == FAILED

    @property
    def terminal(self) -> bool:
        """Answered, and the answer is no. The only ground for giving up."""
        return self.outcome in (ABSENT, CLOSED)


def parse(text: str) -> Destination | None:
    """The destination in `text`, or None when it is not one.

    A message link wins over anything else in the same string, because a
    link also contains a channel and a topic and the id is the better half.
    """
    candidate = (text or "").strip().strip("<>").strip()
    if not candidate:
        return None
    found = _NEAR.search(candidate)
    if found:
        return Destination(raw=candidate, message_id=int(found.group(1)))
    explicit = _EXPLICIT_ID.match(candidate)
    if explicit:
        return Destination(raw=candidate, message_id=int(explicit.group(1)))
    conversation = parse_conversation(candidate)
    if conversation is not None and "#narrow" not in candidate:
        return Destination(raw=candidate, conversation=conversation)
    return None


def resolve(client: ZulipClient, destination: Destination) -> Resolved:
    """Where the notification goes **now**, read from Zulip.

    An id is asked about strictly: `None` then means Zulip said the message
    is not there, and a lookup that never answered is raised and becomes
    `FAILED` rather than a deletion nobody witnessed.

    A name is resolved by reading the conversation it names — following the
    ✔ rename, because that is the same conversation under the name it can be
    read under — and the newest message there becomes the anchor. Nothing
    falls back to a topic of the remembered name once an id is known: that
    name may since have been taken over by work this watch knows nothing
    about.
    """
    if destination.message_id is not None:
        return _by_id(client, destination.message_id)
    named = destination.conversation
    if named is None:
        return Resolved(ABSENT, reason="no destination was understood")
    return _by_name(client, named)


def anchored(client: ZulipClient, text: str) -> tuple[Destination | None, Resolved]:
    """Parse and resolve in one step: what intake and delivery both need.

    Returned together because the pair is the answer — the `Destination` is
    what the requester wrote and the `Resolved` carries the id it means. A
    text that is not a destination at all is `(None, ABSENT)`: there is
    nothing to retry, and the requester has to be asked.
    """
    parsed = parse(text)
    if parsed is None:
        return None, Resolved(ABSENT, reason=f"{text!r} is not a destination")
    return parsed, resolve(client, parsed)


def _by_id(client: ZulipClient, message_id: int) -> Resolved:
    try:
        conversation = conversation_of(client, message_id, strict=True)
    except ZulipRejected as error:
        # Zulip answered and refused: the message is not there, or not ours
        # to read. Either way it is an answer, and answers are terminal.
        return Resolved(ABSENT, reason=f"message {message_id} cannot be read: {error}")
    except ZulipError as error:
        return Resolved(
            FAILED, reason=f"could not look up message {message_id}: {error}",
            message_id=message_id,
        )
    if conversation is None:
        return Resolved(ABSENT, reason=f"message {message_id} is gone", message_id=message_id)
    return Resolved(
        CLOSED if conversation.topic.startswith(RESOLVED_TOPIC_PREFIX) else OPEN,
        conversation=conversation,
        message_id=message_id,
    )


def _by_name(client: ZulipClient, named: Conversation) -> Resolved:
    """The conversation a `<channel>/<topic>` names, and a message in it.

    Read under the bare name and then under the ✔ one, strictly: an empty
    history must mean the conversation is empty, never that the read failed.
    A conversation with no messages at all has no anchor to offer and is
    treated as absent — there is nothing there to have meant.
    """
    for live in (named.topic, f"{RESOLVED_TOPIC_PREFIX}{named.topic}"):
        try:
            history = client.topic_history(named.channel, live, num_before=1)
        except ZulipRejected as error:
            return Resolved(ABSENT, reason=f"cannot read {named.channel}/{live}: {error}")
        except ZulipError as error:
            return Resolved(FAILED, reason=f"could not read {named.channel}/{live}: {error}")
        if history:
            return Resolved(
                CLOSED if live.startswith(RESOLVED_TOPIC_PREFIX) else OPEN,
                conversation=Conversation(named.channel, live),
                message_id=int(history[-1]["id"]),
            )
        if named.topic.startswith(RESOLVED_TOPIC_PREFIX):
            break
    return Resolved(ABSENT, reason=f"{named.channel}/{named.topic} has no messages")
