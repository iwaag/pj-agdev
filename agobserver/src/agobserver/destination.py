"""Where a notification goes, and how that survives the conversation moving.

A requester names the destination in words. Two spellings are accepted and
they are not equal in quality:

- a **message link** (Zulip's *Copy link to message*), or `msg:<id>` — the
  good one. It carries a message id, and an id is the single identifier a
  rename, a ✔ or a reused topic name does not touch, so the notification
  follows the conversation instead of following its old name;
- `<channel>/<topic>` — accepted, and resolved through the ✔ rename at send
  time, but a topic that was renamed for any other reason is simply gone as
  far as this is concerned. It is *absent*, never "whatever holds that name
  now": the whole reason to prefer an id is that a freed name gets reused.

`resolve` is called when the notification is about to be sent, not when the
watch is accepted, because everything above can change while a watch waits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agag.selfnote import Conversation, parse_conversation
from agag.zulip import RESOLVED_TOPIC_PREFIX, ZulipClient, conversation_of, live_topic_name

#: `.../near/5901` in a Zulip message link, and the bare spellings beside it.
_NEAR = re.compile(r"/near/(\d+)")
_EXPLICIT_ID = re.compile(r"^(?:msg:|message:|#)?(\d+)$", re.IGNORECASE)

__all__ = ["Destination", "Resolved", "parse", "resolve"]


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
    """Where the notification goes now, or why it cannot go anywhere.

    `closed` is a conversation that exists but is resolved (✔). It is not a
    delivery target: posting into it would un-resolve somebody's finished
    work, and a watch is not important enough to reopen a conversation.
    """

    conversation: Conversation | None = None
    reason: str = ""
    closed: bool = False

    @property
    def deliverable(self) -> bool:
        return self.conversation is not None and not self.closed


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
    """Where the notification goes **now**.

    A deleted anchor is absent, and absent is a terminal answer rather than
    an invitation to guess: nothing falls back to a topic of the remembered
    name, because that name may since have been taken over by work this
    watch knows nothing about.
    """
    if destination.message_id is not None:
        conversation = conversation_of(client, destination.message_id)
        if conversation is None:
            return Resolved(reason=f"message {destination.message_id} is gone")
        return Resolved(
            conversation=conversation,
            closed=conversation.topic.startswith(RESOLVED_TOPIC_PREFIX),
        )
    named = destination.conversation
    if named is None:
        return Resolved(reason="no destination was understood")
    live = live_topic_name(client, named.channel, named.topic)
    try:
        history = client.topic_history(named.channel, live, num_before=1)
    except Exception as error:  # noqa: BLE001 - an unreadable target is a reason
        return Resolved(reason=f"cannot read {named.channel}/{live}: {error}")
    if not history:
        return Resolved(reason=f"{named.channel}/{named.topic} has no messages")
    return Resolved(
        conversation=Conversation(named.channel, live),
        closed=live.startswith(RESOLVED_TOPIC_PREFIX),
    )
