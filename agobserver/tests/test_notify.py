"""Delivery: once, recoverably, and never into a conversation nobody named."""

from __future__ import annotations

from dataclasses import replace

import pytest

from agag.agent import AgentSpec
from agag.zulip import ZulipRejected, ZulipTimeout

from agobserver import anchor, notify, store

WATCH = anchor.Watch(
    channel="agobserver-agstudio1",
    topic="watch-thing",
    watch_id=6676,
    state=anchor.ACTIVE,
    accepted={
        "condition": "the file is there",
        "target": "/tmp/thing",
        "destination": "front/front-x",
        "requester": "Front",
    },
)
RESULT = {"verdict": "met", "evidence": "the file is there", "at": "now"}


@pytest.fixture
def spec(tmp_path) -> AgentSpec:
    return AgentSpec("agobserver", tmp_path)


def record_for(spec, watch=WATCH, **fields):
    return store.update(
        spec.local / "watches", watch.name,
        watch=watch.name, channel=watch.channel, topic=watch.topic,
        state=anchor.ACTIVE, accepted=dict(watch.accepted),
        last_result=RESULT, pending_notification=True, **fields,
    )


def notifications(zulip, channel="front", topic="front-x"):
    return [
        entry for entry in zulip.topic_history(channel, topic, 100)
        if "Watch `w6676` met" in entry["content"]
    ]


def test_a_met_watch_is_delivered_once_and_finished(spec, zulip):
    zulip.post("front", "front-x", "the request that asked for it")
    zulip.post(WATCH.channel, WATCH.topic, "please watch this")
    record = record_for(spec)

    assert notify.deliver(spec, zulip, WATCH, record) is True

    delivered = store.load(spec.local / "watches", WATCH.name)
    assert delivered["state"] == anchor.MET
    assert delivered["pending_notification"] is False
    assert delivered["delivered"]["channel"] == "front"
    assert len(notifications(zulip)) == 1
    # Finished visibly, and the watch topic is resolved rather than left open.
    assert ("agobserver-agstudio1", "✔ watch-thing") in zulip.topics


def test_repeated_polling_never_notifies_twice(spec, zulip):
    zulip.post("front", "front-x", "the request")
    zulip.post(WATCH.channel, WATCH.topic, "please watch this")
    notify.deliver(spec, zulip, WATCH, record_for(spec))

    # What a restart or a stray tick would do: deliver again with the record
    # as it now stands.
    stored = store.load(spec.local / "watches", WATCH.name)
    assert notify.deliver(spec, zulip, WATCH, stored) is True
    assert len(notifications(zulip)) == 1


def test_a_failed_send_is_retried_and_stays_visible(spec, zulip):
    zulip.post("front", "front-x", "the request")
    zulip.post(WATCH.channel, WATCH.topic, "please watch this")
    zulip.fail_next_send = ConnectionError("zulip is down")

    assert notify.deliver(spec, zulip, WATCH, record_for(spec)) is False
    held = store.load(spec.local / "watches", WATCH.name)
    # Still owed: pending, still met, and the reason is written down.
    assert held["pending_notification"] is True
    assert "zulip is down" in held["delivery_error"]
    assert notifications(zulip) == []

    assert notify.deliver(spec, zulip, WATCH, held) is True
    assert len(notifications(zulip)) == 1


def test_an_ambiguous_send_is_recognized_on_the_next_attempt(spec, zulip):
    """The post landed; the answer did not come back.

    This is the case the watch id in the notification exists for. Without the
    read-back the retry would post a second notification for one watch.
    """
    zulip.post("front", "front-x", "the request")
    zulip.post(WATCH.channel, WATCH.topic, "please watch this")
    zulip.swallow_next_send = True

    assert notify.deliver(spec, zulip, WATCH, record_for(spec)) is False
    assert len(notifications(zulip)) == 1        # it really did land

    held = store.load(spec.local / "watches", WATCH.name)
    assert notify.deliver(spec, zulip, WATCH, held) is True
    assert len(notifications(zulip)) == 1        # and it was not repeated
    assert store.load(spec.local / "watches", WATCH.name)["state"] == anchor.MET


def test_a_deleted_destination_is_terminal_and_opens_nothing(spec, zulip):
    anchor_id = zulip.post("front", "front-x", "the request")
    zulip.post(WATCH.channel, WATCH.topic, "please watch this")
    watch = replace(WATCH, accepted={**WATCH.accepted, "destination": f"msg:{anchor_id}"})
    zulip.deleted.add(anchor_id)
    del zulip.topics[("front", "front-x")]

    assert notify.deliver(spec, zulip, watch, record_for(spec, watch)) is True
    stored = store.load(spec.local / "watches", watch.name)
    assert stored["state"] == anchor.UNDELIVERABLE
    assert stored["pending_notification"] is False
    # Nothing was created to deliver into, and the watch topic says so.
    assert ("front", "front-x") not in zulip.topics
    said = " ".join(entry["content"] for entry in zulip.topic_history(watch.channel, watch.topic, 100))
    assert "could not be delivered" in said
    # An undeliverable watch is left open: a human has to see it.
    assert (watch.channel, f"✔ {watch.topic}") not in zulip.topics


def test_a_closed_destination_is_not_reopened(spec, zulip):
    zulip.post("front", "✔ front-x", "the request, since finished")
    zulip.post(WATCH.channel, WATCH.topic, "please watch this")

    assert notify.deliver(spec, zulip, WATCH, record_for(spec)) is True
    assert store.load(spec.local / "watches", WATCH.name)["state"] == anchor.UNDELIVERABLE
    assert notifications(zulip, "front", "✔ front-x") == []


def test_the_destination_follows_a_rename(spec, zulip):
    """A message id, resolved at send time — not the name it was accepted under."""
    anchor_id = zulip.post("front", "front-x", "the request")
    zulip.post(WATCH.channel, WATCH.topic, "please watch this")
    watch = replace(WATCH, accepted={**WATCH.accepted, "destination": f"msg:{anchor_id}"})
    zulip.topics[("front", "front-renamed")] = zulip.topics.pop(("front", "front-x"))
    # Somebody else has since taken the freed name. It must not be notified.
    zulip.post("front", "front-x", "unrelated work under the reused name")

    assert notify.deliver(spec, zulip, watch, record_for(spec, watch)) is True
    assert len(notifications(zulip, "front", "front-renamed")) == 1
    assert notifications(zulip, "front", "front-x") == []


# --- uncertainty is retried, not concluded (ex1 step 3) --------------------


def anchored(zulip, channel="front", topic="front-x"):
    """A watch whose destination is an id, which is what intake now stores."""
    anchor_id = zulip.post(channel, topic, "the request")
    zulip.post(WATCH.channel, WATCH.topic, "please watch this")
    return replace(
        WATCH,
        accepted={**WATCH.accepted, "destination_id": anchor_id},
    ), anchor_id


def test_a_destination_that_cannot_be_read_is_retried_not_abandoned(spec, zulip):
    """The defect: one failed lookup threw the notification away for good."""
    watch, _ = anchored(zulip)
    zulip.fail_next_message = ZulipTimeout("timed out")

    assert notify.deliver(spec, zulip, watch, record_for(spec, watch)) is False
    held = store.load(spec.local / "watches", watch.name)
    assert held["state"] == anchor.ACTIVE            # not undeliverable
    assert held["pending_notification"] is True      # still owed
    assert "could not be read" in held["delivery_error"]
    assert notifications(zulip) == []
    # And nothing was said in the watch topic about being unable to deliver.
    said = " ".join(e["content"] for e in zulip.topic_history(watch.channel, watch.topic, 100))
    assert "could not be delivered" not in said

    assert notify.deliver(spec, zulip, watch, held) is True
    assert len(notifications(zulip)) == 1


def test_a_failed_read_back_does_not_send(spec, zulip):
    """A read-back that could not run is not proof that nothing is there.

    The ambiguous send already landed; treating the failed check as "no
    delivery found" is exactly how the requester gets told twice.
    """
    watch, _ = anchored(zulip)
    zulip.swallow_next_send = True
    assert notify.deliver(spec, zulip, watch, record_for(spec, watch)) is False
    assert len(notifications(zulip)) == 1            # it really did land

    zulip.fail_next_history = ZulipTimeout("timed out")
    held = store.load(spec.local / "watches", watch.name)
    assert notify.deliver(spec, zulip, watch, held) is False
    assert len(notifications(zulip)) == 1            # and was not repeated
    assert "could not check" in store.load(spec.local / "watches", watch.name)["delivery_error"]

    held = store.load(spec.local / "watches", watch.name)
    assert notify.deliver(spec, zulip, watch, held) is True
    assert len(notifications(zulip)) == 1
    assert store.load(spec.local / "watches", watch.name)["state"] == anchor.MET


def test_a_restart_while_delivery_is_pending_still_delivers_once(spec, zulip):
    """Nothing is held in memory: the store is the whole of what carries over."""
    watch, _ = anchored(zulip)
    zulip.fail_next_send = ConnectionError("zulip is down")
    assert notify.deliver(spec, zulip, watch, record_for(spec, watch)) is False

    # The process ends here. What a new one has is the file.
    revived = store.load(spec.local / "watches", watch.name)
    assert revived["pending_notification"] is True
    assert revived["last_result"] == RESULT             # the met result is intact
    assert notify.deliver(spec, zulip, watch, revived) is True
    assert len(notifications(zulip)) == 1


def test_a_deleted_destination_is_still_terminal(spec, zulip):
    """Retrying uncertainty must not make a real deletion retry forever."""
    watch, anchor_id = anchored(zulip)
    zulip.deleted.add(anchor_id)

    assert notify.deliver(spec, zulip, watch, record_for(spec, watch)) is True
    stored = store.load(spec.local / "watches", watch.name)
    assert stored["state"] == anchor.UNDELIVERABLE
    assert stored["pending_notification"] is False


def test_a_refused_destination_lookup_is_terminal_and_a_silent_one_is_not(spec, zulip):
    """The whole distinction, on one watch: Zulip's "no" ends it, silence does not."""
    watch, _ = anchored(zulip)
    zulip.fail_next_message = ZulipTimeout("timed out")
    assert notify.deliver(spec, zulip, watch, record_for(spec, watch)) is False

    zulip.fail_next_message = ZulipRejected("GET messages/1 -> HTTP 400: Invalid message(s)")
    held = store.load(spec.local / "watches", watch.name)
    assert notify.deliver(spec, zulip, watch, held) is True
    assert store.load(spec.local / "watches", watch.name)["state"] == anchor.UNDELIVERABLE
