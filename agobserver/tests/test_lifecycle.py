"""Lifecycle: what a watch is, what recovers it, and what stops it.

These are the properties the topic is the record *for*. Each one is a
sentence somebody would otherwise have to take on trust: that a request
needing an answer is not scheduled, that a resolved topic stops the schedule,
that a lost store loses only memory, and that an unreadable channel is not
read as everybody cancelling at once.
"""

from __future__ import annotations

import pytest

from agag.agent import AgentSpec

from agobserver import anchor, observe, store, worker

CHANNEL = "agobserver-agstudio1"
ACCEPTED = {
    "condition": "the file is there",
    "target": "/tmp/thing",
    "destination": "front/front-x",
    "requester": "Front",
}


@pytest.fixture
def spec(tmp_path) -> AgentSpec:
    (tmp_path / ".local").mkdir()
    (tmp_path / ".local" / "instance.toml").write_text(f'name = "{CHANNEL}"\n')
    return AgentSpec("agobserver", tmp_path)


def open_watch(zulip, topic: str, *, state: str = anchor.ACTIVE, accepted=ACCEPTED) -> int:
    zulip.post(CHANNEL, topic, "please watch this", sender_id=8)
    watch_id = zulip.post(CHANNEL, topic, anchor.watch_note(topic), sender_id=zulip.self_id)
    zulip.post(CHANNEL, topic, anchor.accepted_note(accepted), sender_id=zulip.self_id)
    zulip.post(CHANNEL, topic, anchor.state_note(state), sender_id=zulip.self_id)
    return watch_id


def make_worker(spec, zulip, verdict="not_met", **kwargs):
    looked = []

    def evaluate(_spec, watch, previous):
        looked.append((watch.name, previous))
        return observe.Observation(verdict, evidence="stub")

    made = worker.Worker(spec, zulip, interval=60, evaluate=evaluate, **kwargs)
    made.looked = looked
    return made


# --- what a watch is -------------------------------------------------------


def test_the_anchor_id_is_the_identity(spec, zulip):
    watch_id = open_watch(zulip, "watch-a")
    watch = anchor.read_watch(zulip, CHANNEL, "watch-a", zulip.self_id)
    assert watch.name == f"w{watch_id}"
    assert watch.condition == ACCEPTED["condition"]
    assert watch.scheduled


def test_a_second_anchor_never_moves_the_identity(spec, zulip):
    """A repeat is a mistake, not a move — the earliest anchor wins."""
    watch_id = open_watch(zulip, "watch-a")
    zulip.post(CHANNEL, "watch-a", anchor.watch_note("watch-a"), sender_id=zulip.self_id)
    assert anchor.read_watch(zulip, CHANNEL, "watch-a", zulip.self_id).name == f"w{watch_id}"


def test_notes_written_by_somebody_else_are_not_ours(spec, zulip):
    """An anchor is identified by its sender: a copy must not become a watch."""
    zulip.post(CHANNEL, "watch-forged", "please watch this", sender_id=8)
    zulip.post(CHANNEL, "watch-forged", anchor.watch_note("watch-forged"), sender_id=8)
    zulip.post(CHANNEL, "watch-forged", anchor.state_note(anchor.ACTIVE), sender_id=8)
    watch = anchor.read_watch(zulip, CHANNEL, "watch-forged", zulip.self_id)
    assert watch.watch_id is None and not watch.scheduled


def test_a_request_awaiting_an_answer_is_not_scheduled(spec, zulip):
    zulip.post(CHANNEL, "watch-vague", "watch something", sender_id=8)
    zulip.post(CHANNEL, "watch-vague", anchor.state_note(anchor.NEEDS_INPUT), sender_id=zulip.self_id)
    made = make_worker(spec, zulip)
    made.reconcile()
    assert made.scheduled() == []
    assert made.tick() == 0 and made.looked == []


# --- recovery --------------------------------------------------------------


def test_a_lost_store_loses_memory_and_not_work(spec, zulip):
    watch_id = open_watch(zulip, "watch-a")
    made = make_worker(spec, zulip)
    made.tick()
    assert store.load(spec.local / "watches", f"w{watch_id}")["last_result"]["verdict"] == "not_met"

    for path in (spec.local / "watches").glob("*.json"):
        path.unlink()

    revived = make_worker(spec, zulip)
    assert revived.reconcile() == 1
    assert [record["watch"] for record in revived.scheduled()] == [f"w{watch_id}"]
    revived.tick()
    # Recovered with no previous observation: memory gone, the watch is not.
    assert revived.looked[0][1] is None


def test_recovery_needs_no_fresh_post(spec, zulip):
    """The channel is read; nothing waits for somebody to speak."""
    open_watch(zulip, "watch-a")
    made = make_worker(spec, zulip)
    assert made.reconcile() == 1
    assert made.tick() == 1


def test_a_finished_watch_is_not_recovered(spec, zulip):
    open_watch(zulip, "watch-done", state=anchor.MET)
    made = make_worker(spec, zulip)
    assert made.reconcile() == 0
    assert made.scheduled() == []


# --- cancellation ----------------------------------------------------------


def test_resolving_the_topic_stops_the_schedule(spec, zulip):
    watch_id = open_watch(zulip, "watch-a")
    made = make_worker(spec, zulip)
    made.reconcile()
    zulip.resolve_topic(0, "watch-a")

    made.ticks = 1                            # no reconcile: the store still holds it
    assert made.tick() == 1
    assert made.looked == []                  # cancelled before any model call
    assert store.load(spec.local / "watches", f"w{watch_id}")["state"] == "cancelled"
    assert made.scheduled() == []


def test_a_resolve_during_the_evaluation_still_cancels(spec, zulip):
    """The second check exists for exactly this window."""
    watch_id = open_watch(zulip, "watch-a")
    delivered = []

    def evaluate(_spec, watch, previous):
        zulip.resolve_topic(0, "watch-a")     # the ✔ lands mid-evaluation
        return observe.Observation(observe.MET, evidence="stub")

    made = worker.Worker(
        spec, zulip, interval=60, evaluate=evaluate,
        deliver=lambda *args: delivered.append(args) or True,
    )
    made.reconcile()
    made.ticks = 1
    made.tick()
    assert delivered == []
    assert store.load(spec.local / "watches", f"w{watch_id}")["state"] == "cancelled"


def test_an_unreadable_channel_is_not_a_cancellation(spec, zulip):
    """A lookup failure read as a ✔ would drop every watch on one hiccup."""
    open_watch(zulip, "watch-a")
    made = make_worker(spec, zulip)
    made.reconcile()

    def explode(_stream_id):
        raise RuntimeError("zulip is unreachable")

    zulip.channel_topics = explode
    assert made.cancelled(made.scheduled()[0]) is False


# --- the interval ----------------------------------------------------------


def test_an_empty_queue_costs_no_inference(spec, zulip):
    made = make_worker(spec, zulip)
    made.ticks = 1
    assert made.tick() == 0
    assert made.looked == []


def test_a_failed_look_keeps_the_watch_and_counts_the_streak(spec, zulip):
    watch_id = open_watch(zulip, "watch-a")
    made = make_worker(spec, zulip, verdict=observe.UNABLE)
    made.reconcile()
    for _ in range(3):
        made.ticks = 1
        made.tick()
    record = store.load(spec.local / "watches", f"w{watch_id}")
    assert record["state"] == anchor.ACTIVE           # still watching
    assert record["unable_streak"] == 3
    assert record.get("pending_notification") is not True
    said = " ".join(entry["content"] for entry in zulip.topic_history(CHANNEL, "watch-a", 100))
    assert said.count("not been able to look") == 1   # said once, at the third


def test_a_nonsense_interval_is_the_default_not_a_crash(monkeypatch):
    monkeypatch.setenv(worker.INTERVAL_ENV, "soon")
    assert worker.interval_seconds() == worker.DEFAULT_INTERVAL_SECONDS
    monkeypatch.setenv(worker.INTERVAL_ENV, "-5")
    assert worker.interval_seconds() == worker.DEFAULT_INTERVAL_SECONDS
    monkeypatch.setenv(worker.INTERVAL_ENV, "15")
    assert worker.interval_seconds() == 15
