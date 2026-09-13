"""Delivery: once, recoverably, and never into a conversation nobody named."""

from __future__ import annotations

from dataclasses import replace

import pytest

from agag.agent import AgentSpec

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
