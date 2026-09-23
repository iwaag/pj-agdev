"""robust_workflow p2 step 1: the gaps in the request monitor, reproduced.

Each test asserts the outcome p2 requires; step 1 committed them as
`xfail(strict=True)` and steps 2 and 3 removed each mark with the fix.
They run the p1 monitor over a fake realm and a real mirror, exactly like
`test_monitor.py`, whose `stalled_realm` (p3's F2 in miniature) they reuse.
"""

from __future__ import annotations

import pytest

from agag.mirror.store import bare_topic

from agobserver import monitor as monitoring

from test_monitor import (  # noqa: F401 - the fixture is used by name
    ACK, AUTOLAB, CHANNEL, DEV, FRONT, incident_posts, post, requests, settle, world,
)


def ask(world) -> int:
    """The request's first post: what the root notes are anchored by."""
    return min(i for i, m in world.realm.messages.items() if m["display_recipient"] == "front")


def task2(world) -> str:
    return f"workrun-task2-m{world.mission}"


def incident_records(watcher) -> list[dict]:
    return watcher.records()


def open_incident(world):
    watcher = world.make()
    touched = watcher.tick()
    settle(world, lambda: requests(world))
    assert [r["kind"] for r in touched] == ["unstarted"]
    return watcher


def rename(world, channel: str, old: str, new: str) -> None:
    ids = world.realm._topic_ids(channel, old)
    world.realm.move(ids, new)
    settle(world, lambda: world.mirror.live_name(channel, new) == new)


# --- R1: a target that cannot be read is reported as rescued ---------------------


def test_r1_an_unreadable_target_is_not_a_rescue(world):
    watcher = open_incident(world)
    real = world.mirror.history

    def history(channel, topic, *args, **kwargs):
        # What the mirror answers for a conversation it does not hold (a
        # channel it has not read, coverage lost, a failed hydrate): nothing.
        if bare_topic(topic) == task2(world):
            return []
        return real(channel, topic, *args, **kwargs)

    world.mirror.history = history
    world.clock.now += 120
    touched = watcher.tick()
    assert all(r["state"] != monitoring.RESCUED for r in touched), \
        "an unreadable task read as 'not started' with no identity, and the incident closed as rescued"


# --- R2: a change of failure kind is reported as rescued ------------------------------


def test_r2_a_different_blockage_is_not_a_rescue(world):
    watcher = open_incident(world)
    # Somebody posts into task 2; autolab's listener never picks it up.
    post(world.realm, "work-m1", task2(world), f"[selfnote][rootchat] front/front-a #{ask(world)}", FRONT)
    started = post(world.realm, "work-m1", task2(world), "Start task 2.", FRONT)
    settle(world, lambda: world.mirror.message(started) is not None)
    world.clock.now += 120
    touched = watcher.tick()
    assert all(r["state"] != monitoring.RESCUED for r in touched), \
        "the task is still not being worked on: queued and unacknowledged is not recovered"


# --- R3: a request that ages out of discovery is abandoned ---------------------------


def test_r3_an_open_incident_survives_the_discovery_window(world):
    watcher = open_incident(world)
    world.clock.now += 13 * 3600
    touched = watcher.tick()
    assert touched, "the request fell out of the 12-hour window and its open incident is never looked at again"


# --- R4: an origin resolved while its work remains ------------------------------------


def test_r4_a_resolved_origin_does_not_abandon_its_incident(world):
    watcher = open_incident(world)
    world.realm.resolve("front", "front-a")
    settle(world, lambda: any(t.resolved for t in world.mirror.topics("front")))
    world.clock.now += monitoring.RETRY_SECONDS + 5
    watcher.tick()
    (record,) = incident_records(watcher)
    assert record["state"] != monitoring.RECOVERING, \
        "a ✔ on the origin removed it from discovery; the incident stays 'recovering' with nobody told"


# --- R5: an origin renamed while its work remains -------------------------------------


def test_r5_a_renamed_origin_keeps_its_incident(world):
    watcher = open_incident(world)
    rename(world, "front", "front-a", "front-a-renamed")
    post(world.realm, "work-m1", task2(world), f"[selfnote][rootchat] front/front-a-renamed #{ask(world)}", FRONT)
    post(world.realm, "work-m1", task2(world), "Start task 2.", FRONT)
    acked = post(world.realm, "work-m1", task2(world), ACK, AUTOLAB)
    settle(world, lambda: world.mirror.message(acked) is not None)
    world.clock.now += 120
    watcher.tick()
    (record,) = incident_records(watcher)
    assert record["state"] == monitoring.RESCUED, \
        "the record's origin key is the old name, so the recovery is never verified"


# --- R6: the old origin name reused by another request ----------------------------------


def test_r6_a_reused_origin_name_does_not_capture_the_incident(world):
    watcher = open_incident(world)
    rename(world, "front", "front-a", "front-a-renamed")
    fresh = post(world.realm, "front", "front-a", "An unrelated new request.", DEV)
    post(world.realm, "front", "front-a", ACK, FRONT)
    settle(world, lambda: world.mirror.message(fresh) is not None)
    world.clock.now += 120
    watcher.tick()
    records = incident_records(watcher)
    assert all(r["state"] != monitoring.RESCUED for r in records), \
        "the new conversation under the old name was looked at as the incident's origin, and the stall closed"


# --- R7: the stalled conversation itself renamed --------------------------------------


def test_r7_a_renamed_stalled_conversation_is_one_incident(world):
    watcher = open_incident(world)
    rename(world, "work-m1", task2(world), f"{task2(world)}-renamed")
    world.clock.now += monitoring.RETRY_SECONDS + 5
    watcher.tick()
    settle(world)
    records = incident_records(watcher)
    assert len(records) == 1, "the candidate key carries the topic name: a rename opens a second incident"
    assert records[0]["state"] != monitoring.RESCUED
    assert len(requests(world)) <= monitoring.MAX_REQUESTS
    assert sum("Incident: unstarted" in text for text in incident_posts(world)) == 1


# --- R8: an unrelated reply at home consumes a delegated answer --------------------------


@pytest.fixture
def undelivered(world):
    """Task 1's answer names Front; Front's listener never served it."""
    mission = world.mission
    task1 = f"workrun-task1-m{mission}"
    # Undo the acceptance in stalled_realm: a fresh task 3 carries the case.
    topic = f"workrun-task3-m{mission}"
    post(world.realm, "work-m1", topic, f"[selfnote][task] {mission}#3", AUTOLAB)
    post(world.realm, "work-m1", topic, f"[selfnote][rootchat] pj-x/workplan-a #{mission}", AUTOLAB)
    post(world.realm, "work-m1", topic, f"[selfnote][rootchat] front/front-a #{ask(world)}", FRONT)
    post(world.realm, "work-m1", topic, "Start task 3.", FRONT)
    post(world.realm, "work-m1", topic, ACK, AUTOLAB)
    answer = post(world.realm, "work-m1", topic, "@**Front** task 3 done", AUTOLAB)
    settle(world, lambda: world.mirror.message(answer) is not None)
    world.clock.now = world.realm.messages[answer]["timestamp"] + 400
    del task1
    return answer


def test_r8_an_unrelated_home_reply_does_not_consume_an_answer(world, undelivered):
    watcher = world.make()
    kinds = [r["kind"] for r in watcher.tick()]
    assert "undelivered" in kinds
    # Front replies at home to something else — a serving whose input ended
    # before the answer arrived. It never read the answer.
    reply = post(world.realm, "front", "front-a", "@**Developer** about your other question: yes.", FRONT)
    settle(world, lambda: world.mirror.message(reply) is not None)
    world.clock.now += 120
    touched = watcher.tick()
    undelivered_records = [r for r in touched if r["kind"] == "undelivered"]
    assert all(r["state"] != monitoring.RESCUED for r in undelivered_records), \
        "later speech at home is taken as the answer being handled"


# --- R9: a served mark written before the remote conversation was renamed ------------


def test_r9_a_served_mark_survives_a_rename_of_the_answering_conversation(world, undelivered):
    topic = f"workrun-task3-m{world.mission}"
    mark = post(world.realm, "front", "front-a", f"[selfnote][served] work-m1/{topic} {undelivered}", FRONT)
    settle(world, lambda: world.mirror.message(mark) is not None)
    watcher = world.make()
    assert "undelivered" not in [r["kind"] for r in watcher.tick()], "served: nothing is owed"
    rename(world, "work-m1", topic, f"{topic}-renamed")
    world.clock.now += 120
    kinds = [r["kind"] for r in watcher.tick()]
    assert "undelivered" not in kinds, "the served mark names the old topic name and no longer matches"


# --- step 2: identity survives what used to re-key it ---------------------------------


def test_a_lost_store_adopts_a_renamed_incident_topic_with_its_requests(world, tmp_path):
    watcher = open_incident(world)
    settle(world, lambda: world.mirror.topics(CHANNEL))
    (record,) = watcher.records()
    rename(world, CHANNEL, record["topic"], f"{record['topic']}-by-hand")
    for path in (tmp_path / "local" / "incidents").glob("*.json"):
        path.unlink()
    world.clock.now += 60
    again = world.make()
    again.tick()
    settle(world)
    (adopted,) = again.records()
    assert adopted["adopted"] and adopted["topic"].endswith("-by-hand")
    assert len(adopted["requests"]) == 1, "the request already made is counted, not asked again"
    assert len(requests(world)) == 1
    assert sum("Incident: unstarted" in text for text in incident_posts(world)) == 1


def test_a_recovery_request_goes_where_the_origin_is_now(world):
    watcher = world.make()
    rename(world, "front", "front-a", "front-a-renamed")
    watcher.tick()
    settle(world, lambda: requests(world))
    assert [m["subject"] for m in requests(world)] == ["front-a-renamed"]


# --- step 3: recovery is a transition on record, not an absence ------------------------


def test_a_new_blockage_inside_its_grace_is_not_a_rescue(world):
    """R2 without the luck of timing: posted into, not yet overdue."""
    watcher = open_incident(world)
    posted = post(world.realm, "work-m1", task2(world), "Start task 2.", FRONT)
    settle(world, lambda: world.mirror.message(posted) is not None)
    world.clock.now = world.realm.messages[posted]["timestamp"] + 60
    watcher.tick()
    (record,) = watcher.records()
    assert record["state"] == monitoring.RECOVERING and record["waiting"] == "queued"


def test_a_cancelled_task_closes_the_incident_as_a_decision(world):
    watcher = open_incident(world)
    note = post(world.realm, "work-m1", task2(world), "[selfnote][state] cancelled", AUTOLAB)
    settle(world, lambda: world.mirror.message(note) is not None)
    world.clock.now += 120
    watcher.tick()
    (record,) = watcher.records()
    assert record["state"] == monitoring.CANCELLED
    assert not any("**Rescued**" in text for text in incident_posts(world))


def test_a_stale_mirror_asks_nobody_and_concludes_nothing(world):
    world.mirror.health = lambda: {"state": "stale"}
    watcher = world.make()
    touched = watcher.tick()
    settle(world)
    assert not requests(world) and not incident_posts(world)
    assert [r["state"] for r in touched] == ["unconfirmed"]


def test_unobservable_work_is_reported_once_after_the_bound_and_never_rescued(world):
    watcher = open_incident(world)
    real = world.mirror.history
    world.mirror.history = lambda channel, topic, *a, **k: [] if bare_topic(topic) == task2(world) \
        else real(channel, topic, *a, **k)
    for _ in range(3):
        world.clock.now += monitoring.UNOBSERVABLE_REPORT_SECONDS / 2 + 1
        watcher.tick()
    settle(world)
    (record,) = watcher.records()
    assert record["state"] == monitoring.REPORTED and "not been able to see" in record["why"]
    posts = incident_posts(world)
    assert sum("I cannot see" in text for text in posts) == 1
    assert sum("Stopped: I could not get this moving" in text for text in posts) == 1
    assert not any("**Rescued**" in text for text in posts)


def test_a_tracked_request_is_kept_past_the_window_and_across_a_restart(world, tmp_path):
    first = open_incident(world)
    assert "o" + str(ask(world)) in first.load_tracked()
    world.clock.now += 20 * 3600
    again = world.make()  # a restart, a day later: the window no longer finds it
    assert again.origins(world.clock.now) == []
    touched = again.tick()
    settle(world)
    assert touched and len(requests(world)) == 2, "the second request, once — not a fresh allowance"
    world.clock.now += monitoring.RETRY_SECONDS + 5
    again.tick()
    settle(world)
    assert len(requests(world)) == 2
    (record,) = again.records()
    assert record["state"] == monitoring.REPORTED


def test_a_request_with_nothing_outstanding_is_let_go(world):
    watcher = world.make()
    post(world.realm, "work-m1", task2(world), "[selfnote][state] completed", AUTOLAB)
    done = post(world.realm, "pj-x", "workplan-a", "[selfnote][state] done", AUTOLAB)
    settle(world, lambda: world.mirror.message(done) is not None)
    watcher.tick()
    assert watcher.load_tracked() == {}


def test_the_same_work_stalling_after_a_rescue_is_a_new_incident(world):
    watcher = open_incident(world)
    posted = post(world.realm, "work-m1", task2(world), "Start task 2.", FRONT)
    acked = post(world.realm, "work-m1", task2(world), ACK, AUTOLAB)
    settle(world, lambda: world.mirror.message(acked) is not None)
    world.clock.now += 120
    assert [r["state"] for r in watcher.tick()] == [monitoring.RESCUED]
    # …and then autolab goes quiet for longer than the silence threshold.
    world.clock.now = world.realm.messages[acked]["timestamp"] + 3 * 3600
    watcher.judge = lambda *args: {"verdict": "stall", "evidence": "no word in hours"}
    touched = watcher.tick()
    settle(world)
    assert [(r["kind"], r["episode"]) for r in touched] == [("silent", 2)]
    assert sum(text.startswith("**Incident:") for text in incident_posts(world)) == 2
    assert posted


def test_a_closed_origin_with_unfinished_work_is_reported_once(world):
    """A ✔ stops nothing, and Front does not deliver into a finished
    conversation: work still open under a ✔ request is said once, to the
    owners — never asked about there."""
    watcher = world.make()
    post(world.realm, "work-m1", task2(world), f"[selfnote][rootchat] front/front-a #{ask(world)}", FRONT)
    posted = post(world.realm, "work-m1", task2(world), "Start task 2.", FRONT)
    acked = post(world.realm, "work-m1", task2(world), ACK, AUTOLAB)
    settle(world, lambda: world.mirror.message(acked) is not None)
    world.clock.now = world.realm.messages[acked]["timestamp"] + 30
    watcher.tick()  # tracked: task 2 is executing
    world.realm.resolve("front", "front-a")
    settle(world, lambda: any(t.resolved for t in world.mirror.topics("front")))
    world.clock.now += 60
    assert watcher.tick() == [], "inside the grace"
    for _ in range(3):
        world.clock.now += monitoring.ORIGIN_CLOSED_GRACE
        watcher.tick()
    settle(world)
    reports = [t for t in incident_posts(world) if "Stopped: I could not get this moving" in t]
    assert len(reports) == 1 and "✔" in reports[0]
    assert not [m for m in requests(world) if m["subject"].startswith("✔")], "nobody asked in the ✔ origin"
    assert posted


def test_an_undelivered_answer_taken_up_on_request_is_verified_by_its_receipt(world, undelivered):
    """The request names the answer (`[selfnote][owed]`); the requester's
    listener marks it served after the serving that processed the request
    replies; the next look sees the mark and records the rescue."""
    watcher = world.make()
    assert "undelivered" in [r["kind"] for r in watcher.tick()]
    settle(world, lambda: requests(world))
    owed = [m for m in requests(world) if m["content"].startswith("[selfnote][owed]")]
    assert owed and str(undelivered) in owed[0]["content"]
    # What Front's listener does after its reply to that request is delivered.
    topic = f"workrun-task3-m{world.mission}"
    post(world.realm, "front", "front-a", "@**Developer** task 3 is done (relayed).", FRONT)
    mark = post(world.realm, "front", "front-a", f"[selfnote][served] work-m1/{topic} {undelivered}", FRONT)
    settle(world, lambda: world.mirror.message(mark) is not None)
    world.clock.now += 120
    rescued = [r for r in watcher.tick() if r["kind"] == "undelivered"]
    assert [r["state"] for r in rescued] == [monitoring.RESCUED]
