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
from agag.zulip import ZulipTimeout

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


def test_an_unanswered_anchor_lookup_is_not_a_cancellation(spec, zulip):
    """A lookup failure read as a ✔ would drop every watch on one hiccup."""
    watch_id = open_watch(zulip, "watch-a")
    made = make_worker(spec, zulip)
    made.reconcile()

    zulip.fail_next_message = ZulipTimeout("timed out")
    made.ticks = 1
    made.tick()
    assert made.looked == []                          # the attempt was skipped
    record = store.load(spec.local / "watches", f"w{watch_id}")
    assert record["state"] == anchor.ACTIVE           # and nothing was concluded

    made.ticks = 1
    made.tick()
    assert len(made.looked) == 1                      # the next tick just works


# --- the watch follows its own anchor (ex1 step 2) -------------------------


def rename(zulip, topic: str, to: str) -> None:
    """A rename that is not a resolve: the same conversation, a new name."""
    for (channel, name) in list(zulip.topics):
        if name == topic:
            zulip.topics[(channel, to)] = zulip.topics.pop((channel, topic))
            return


def test_a_renamed_watch_is_continued_under_its_new_name(spec, zulip):
    watch_id = open_watch(zulip, "watch-a")
    made = make_worker(spec, zulip)
    made.reconcile()
    rename(zulip, "watch-a", "watch-a-renamed")

    made.ticks = 1
    assert made.tick() == 1
    assert len(made.looked) == 1                      # still being watched
    record = store.load(spec.local / "watches", f"w{watch_id}")
    assert record["topic"] == "watch-a-renamed"       # and addressed correctly
    assert record["state"] == anchor.ACTIVE


def test_what_a_renamed_watch_says_goes_to_where_it_is_now(spec, zulip):
    """The failure report is the one thing a waiting watch ever posts."""
    open_watch(zulip, "watch-a")
    made = make_worker(spec, zulip, verdict=observe.UNABLE)
    made.reconcile()
    rename(zulip, "watch-a", "watch-a-renamed")
    zulip.post(CHANNEL, "watch-a", "unrelated work under the reused name", sender_id=8)

    for _ in range(3):
        made.ticks = 1
        made.tick()

    said = " ".join(e["content"] for e in zulip.topic_history(CHANNEL, "watch-a-renamed", 100))
    assert said.count("not been able to look") == 1
    reused = " ".join(e["content"] for e in zulip.topic_history(CHANNEL, "watch-a", 100))
    assert "not been able to look" not in reused


def test_a_renamed_then_resolved_watch_is_cancelled_without_a_look(spec, zulip):
    """Renaming before resolving used to hide the ✔ from the name comparison."""
    watch_id = open_watch(zulip, "watch-a")
    made = make_worker(spec, zulip)
    made.reconcile()
    rename(zulip, "watch-a", "watch-a-renamed")
    zulip.resolve_topic(0, "watch-a-renamed")

    made.ticks = 1
    made.tick()
    assert made.looked == []
    assert store.load(spec.local / "watches", f"w{watch_id}")["state"] == worker.CANCELLED
    assert made.scheduled() == []


def test_a_cancelled_watch_posts_nothing_into_its_reused_name(spec, zulip):
    watch_id = open_watch(zulip, "watch-a")
    delivered = []
    made = worker.Worker(
        spec, zulip, interval=60,
        evaluate=lambda *a: observe.Observation(observe.MET, evidence="stub"),
        deliver=lambda *args: delivered.append(args) or True,
    )
    made.reconcile()
    rename(zulip, "watch-a", "watch-a-renamed")
    zulip.resolve_topic(0, "watch-a-renamed")
    before = len(zulip.topic_history(CHANNEL, "watch-a", 100))
    zulip.post(CHANNEL, "watch-a", "somebody else's watch, same name", sender_id=8)

    made.ticks = 1
    made.tick()

    assert delivered == []
    assert len(zulip.topic_history(CHANNEL, "watch-a", 100)) == before + 1
    assert store.load(spec.local / "watches", f"w{watch_id}")["state"] == worker.CANCELLED


def test_a_deleted_anchor_ends_the_watch_locally(spec, zulip):
    watch_id = open_watch(zulip, "watch-a")
    made = make_worker(spec, zulip)
    made.reconcile()
    zulip.deleted.add(watch_id)

    made.ticks = 1
    made.tick()
    assert made.looked == []
    record = store.load(spec.local / "watches", f"w{watch_id}")
    assert record["state"] == worker.REMOVED
    assert made.scheduled() == []


def test_a_watch_pending_delivery_re_reads_its_own_location(spec, zulip):
    """The second check: a ✔ that lands inside the evaluation still cancels,
    and a rename that lands inside it still gets the completion post."""
    watch_id = open_watch(zulip, "watch-a")
    delivered = []

    def evaluate(_spec, watch, previous):
        rename(zulip, "watch-a", "watch-a-renamed")   # the rename lands mid-look
        return observe.Observation(observe.MET, evidence="stub")

    made = worker.Worker(
        spec, zulip, interval=60, evaluate=evaluate,
        deliver=lambda client, watch, record: delivered.append(watch) or True,
    )
    made.reconcile()
    made.ticks = 1
    made.tick()
    assert [watch.topic for watch in delivered] == ["watch-a-renamed"]
    assert store.load(spec.local / "watches", f"w{watch_id}")["topic"] == "watch-a-renamed"


def test_a_reconcile_refreshes_a_name_it_used_to_leave_stale(spec, zulip):
    """`reconcile` skipped any record whose state and acceptance matched,
    which is every renamed watch."""
    watch_id = open_watch(zulip, "watch-a")
    made = make_worker(spec, zulip)
    assert made.reconcile() == 1
    rename(zulip, "watch-a", "watch-a-renamed")
    assert made.reconcile() == 1                      # not skipped this time
    assert store.load(spec.local / "watches", f"w{watch_id}")["topic"] == "watch-a-renamed"
    assert made.reconcile() == 0                      # and nothing to do once current


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


# --- a watch owing a notification (ex1 step 3) -----------------------------


def test_an_undelivered_watch_is_not_re_judged_and_does_not_block_the_others(spec, zulip):
    """Two properties of one tick, because they share a cause.

    A met watch owes a notification, not another look — re-judging it would
    spend a model call on a question already answered, and could answer it
    differently. And a delivery that keeps failing must not take the tick
    down with it: the other watches are waiting on their own conditions.
    """
    first = open_watch(zulip, "watch-a")
    second = open_watch(zulip, "watch-b")
    verdicts = {f"w{first}": observe.MET, f"w{second}": observe.NOT_MET}
    looked = []

    def evaluate(_spec, watch, previous):
        looked.append(watch.name)
        return observe.Observation(verdicts[watch.name], evidence="stub")

    def deliver(client, watch, record):
        raise RuntimeError("the destination is unreachable")

    made = worker.Worker(spec, zulip, interval=60, evaluate=evaluate, deliver=deliver)
    made.reconcile()
    made.ticks = 1
    made.tick()
    assert sorted(looked) == sorted([f"w{first}", f"w{second}"])

    made.ticks = 1
    made.tick()
    # The met watch was not looked at again; the other one was.
    assert looked.count(f"w{first}") == 1
    assert looked.count(f"w{second}") == 2
    assert store.load(spec.local / "watches", f"w{first}")[worker.PENDING] is True
