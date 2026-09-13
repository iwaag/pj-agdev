"""Delivering the one post a watch exists to produce, exactly once.

The hard part is not sending; it is not sending twice. A watch is met once,
and the requester must be told once, across restarts, retries and an
ambiguous send. Three things carry that, in order of how much they are relied
on:

1. **The store's `delivered` record is the fact.** A watch carrying one is
   never delivered again, and the worker stops scheduling it. Ordinary
   repeated polling therefore cannot notify twice, because polling never
   reaches this module for a delivered watch.
2. **The watch's own id is in the post.** After an ambiguous send — the
   request went out, the answer did not come back — the destination is read
   back for a message of ours naming `w6676`, and a delivery that did land is
   recognized instead of repeated.
3. **The Zulip state note is written after delivery**, so a crash between
   them leaves the watch *owed* rather than silently finished. Owed is the
   safe side: the read-back above turns the retry into a no-op.

The remaining crash window is small and named rather than engineered away: a
crash after Zulip accepted the post but before either the read-back could see
it or the store was written. The next attempt reads the destination back,
finds the post, and records it — so the window costs a duplicate only if the
post is also unreadable at that moment, which is a Zulip outage, not a race.

The destination is resolved from its anchor **at send time**, never from the
name it had when the watch was accepted, so a rename in between does not
redirect the notification into somebody else's conversation. A destination
that is gone, or that has been closed with a ✔, is a terminal `undeliverable`
outcome recorded in the watch topic. Observer does not open a conversation of
its own to deliver into: a notification nobody asked to receive there is
worse than a notification that did not arrive.
"""

from __future__ import annotations

from typing import Any

from agag.agent import AgentSpec
from agag.zulip import ZulipClient, log, topic_write

from . import anchor, destination as dest, store

#: How far back to look when checking whether a notification already landed.
READBACK_MESSAGES = 40
#: Kept short: the requester wants the answer, not the transcript of the look.
EVIDENCE_IN_POST = 600

__all__ = ["deliver", "message", "route"]


def message(watch: anchor.Watch, evidence: str) -> str:
    """The notification. The watch id is in it, and that is load-bearing.

    Not decoration: it is what makes a delivery recognizable on read-back
    after an ambiguous send, and what lets the requester find the watch that
    produced it. It names nobody — the post itself is the requester's turn,
    and Zulip's own topic route is what serves them.
    """
    body = " ".join(str(evidence or "").split())[:EVIDENCE_IN_POST]
    return (
        f"**Watch `{watch.name}` met** — {watch.condition}\n\n"
        f"{body or '(no evidence was recorded)'}\n\n"
        f"Observed at {watch.target or 'the target you named'}. "
        f"This watch is finished; nothing further will be posted for it."
    )


def already_delivered(client: ZulipClient, conversation, watch: anchor.Watch, self_id: int) -> int | None:
    """The id of a notification for this watch already in the destination.

    The read-back that makes an ambiguous send safe. Only our own messages
    count, and the marker is the watch's own name — which is a message id, so
    nothing else in the realm can produce it by coincidence.
    """
    try:
        history = client.topic_history(
            conversation.channel, conversation.topic, num_before=READBACK_MESSAGES
        )
    except Exception as error:  # noqa: BLE001 - unknown is not "no"
        log(f"could not read {conversation} back for {watch.name}: {error}")
        return None
    marker = f"`{watch.name}`"
    for entry in reversed(history):
        if entry.get("sender_id") == self_id and marker in str(entry.get("content", "")):
            return int(entry["id"])
    return None


def route(client: ZulipClient, watch: anchor.Watch) -> dest.Resolved:
    """Where this watch's notification goes now, resolved from its anchor.

    The stored id first and the written name only as the fallback for a watch
    accepted before destinations were anchored. A name is never consulted
    once an id exists — that is the whole of the fix: the id answers "which
    conversation", and the name only ever answered "which conversation is
    called that today".
    """
    anchored_id = watch.destination_id
    if anchored_id is not None:
        return dest.resolve(client, dest.Destination(raw=watch.destination, message_id=anchored_id))
    return dest.anchored(client, watch.destination)[1]


def deliver(spec: AgentSpec, client: ZulipClient, watch: anchor.Watch, record: dict[str, Any]) -> bool:
    """Notify, record it, and finish the watch. True when it is done with.

    False means *retry later* and nothing has been lost: the watch keeps
    `pending_notification`, stays out of judgment, and the next tick tries
    again. Terminal failure — a destination that is gone or closed — returns
    True, because there is nothing left to retry; it is recorded in the watch
    topic as `undeliverable` and nobody is told.
    """
    watches = spec.local / "watches"
    self_id = int(client.whoami()["user_id"])
    if record.get("delivered"):
        _finish(client, watch, watches, anchor.MET)
        return True

    resolved = route(client, watch)
    if resolved.conversation is None or resolved.closed:
        reason = "it is closed (✔)" if resolved.closed else (resolved.reason or "it is gone")
        topic_write(
            watch.topic,
            f"**Watch `{watch.name}` met, and could not be delivered.** The "
            f"conversation it was to notify (`{watch.destination}`) cannot be "
            f"reached: {reason}. Nobody has been told, and I have not opened a "
            f"conversation of my own to tell them in.\n\n"
            f"What I saw: {str(record.get('last_result', {}).get('evidence', ''))[:EVIDENCE_IN_POST]}",
            channel=watch.channel, client=client,
        )
        store.update(
            watches, watch.name, state=anchor.UNDELIVERABLE,
            pending_notification=False, undeliverable_reason=reason,
        )
        _finish(client, watch, watches, anchor.UNDELIVERABLE)
        log(f"{watch.name} undeliverable: {reason}")
        return True

    existing = already_delivered(client, resolved.conversation, watch, self_id)
    if existing is not None:
        log(f"{watch.name} was already delivered as message {existing}; not repeating")
        message_id = existing
    else:
        evidence = str((record.get("last_result") or {}).get("evidence", ""))
        try:
            message_id = client.send_to_channel(
                resolved.conversation.channel,
                resolved.conversation.topic,
                message(watch, evidence),
            )
        except Exception as error:  # noqa: BLE001 - a failed send is retried, not lost
            store.update(
                watches, watch.name,
                delivery_error=str(error), delivery_attempts=int(record.get("delivery_attempts", 0)) + 1,
            )
            log(f"{watch.name} delivery failed, will retry: {error}")
            return False

    store.update(
        watches, watch.name, state=anchor.MET, pending_notification=False,
        delivered={
            "at": store.now(),
            "channel": resolved.conversation.channel,
            "topic": resolved.conversation.topic,
            "message_id": message_id,
        },
        delivery_error="",
    )
    _finish(client, watch, watches, anchor.MET, resolved.conversation, message_id)
    log(f"{watch.name} delivered to {resolved.conversation} as message {message_id}")
    return True


def _finish(client, watch, watches, state, conversation=None, message_id=None) -> None:
    """Say in the watch topic that this is over, once.

    The state note is written *after* delivery on purpose: a crash between
    the post and this note leaves the watch owed, and owed is recoverable —
    the read-back recognizes the post that did land. The reverse order would
    leave a watch that looks finished and told nobody.
    """
    record = store.load(watches, watch.name)
    if record.get("finished_posted"):
        return
    if state == anchor.MET and conversation is not None:
        body = (
            f"**Done — `{watch.name}`.** I told {conversation} "
            f"(message {message_id}) and I am no longer watching this."
        )
    elif state == anchor.MET:
        body = f"**Done — `{watch.name}`.** The notification was already delivered."
    else:
        body = f"**Finished — `{watch.name}` ({state}).**"
    try:
        topic_write(watch.topic, anchor.state_note(state), channel=watch.channel, client=client)
        last = client.send_to_channel(watch.channel, watch.topic, body)
    except Exception as error:  # noqa: BLE001 - the delivery already happened
        log(f"could not finish {watch.name} visibly: {error}")
        return
    store.update(watches, watch.name, finished_posted=True)
    # A delivered watch is resolved; an undeliverable one is deliberately left
    # open, because it is the one outcome a human has to see and decide about.
    if state != anchor.MET:
        return
    try:
        client.resolve_topic(int(last), watch.topic)
    except Exception as error:  # noqa: BLE001
        log(f"could not resolve {watch.channel}/{watch.topic}: {error}")
