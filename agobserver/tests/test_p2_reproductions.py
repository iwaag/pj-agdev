"""robust_workflow p2 step 1: the gaps in the request monitor, reproduced.

Each test asserts the outcome p2 requires and is marked `xfail(strict=True)`
while the defect stands, so the fix that removes it has to remove the mark.
They run the p1 monitor over a fake realm and a real mirror, exactly like
`test_monitor.py`, whose `stalled_realm` (p3's F2 in miniature) they reuse.
"""

from __future__ import annotations

import pytest

from agag.mirror.store import bare_topic

from agobserver import monitor as monitoring

#: A reproduced defect: the test states the required outcome and fails today.
defect = pytest.mark.xfail(strict=True, reason="reproduced in robust_workflow p2 step 1; not fixed yet")

from test_monitor import (  # noqa: F401 - the fixture is used by name
    ACK, AUTOLAB, CHANNEL, DEV, FRONT, incident_posts, post, requests, settle, world,
)


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


@defect
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


@defect
def test_r2_a_different_blockage_is_not_a_rescue(world):
    watcher = open_incident(world)
    # Somebody posts into task 2; autolab's listener never picks it up.
    post(world.realm, "work-m1", task2(world), "[selfnote][rootchat] front/front-a", FRONT)
    started = post(world.realm, "work-m1", task2(world), "Start task 2.", FRONT)
    settle(world, lambda: world.mirror.message(started) is not None)
    world.clock.now += 120
    touched = watcher.tick()
    assert all(r["state"] != monitoring.RESCUED for r in touched), \
        "the task is still not being worked on: queued and unacknowledged is not recovered"


# --- R3: a request that ages out of discovery is abandoned ---------------------------


@defect
def test_r3_an_open_incident_survives_the_discovery_window(world):
    watcher = open_incident(world)
    world.clock.now += 13 * 3600
    touched = watcher.tick()
    assert touched, "the request fell out of the 12-hour window and its open incident is never looked at again"


# --- R4: an origin resolved while its work remains ------------------------------------


@defect
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


@defect
def test_r5_a_renamed_origin_keeps_its_incident(world):
    watcher = open_incident(world)
    rename(world, "front", "front-a", "front-a-renamed")
    post(world.realm, "work-m1", task2(world), "[selfnote][rootchat] front/front-a-renamed", FRONT)
    post(world.realm, "work-m1", task2(world), "Start task 2.", FRONT)
    acked = post(world.realm, "work-m1", task2(world), ACK, AUTOLAB)
    settle(world, lambda: world.mirror.message(acked) is not None)
    world.clock.now += 120
    watcher.tick()
    (record,) = incident_records(watcher)
    assert record["state"] == monitoring.RESCUED, \
        "the record's origin key is the old name, so the recovery is never verified"


# --- R6: the old origin name reused by another request ----------------------------------


@defect
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


@defect
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
    post(world.realm, "work-m1", topic, "[selfnote][rootchat] pj-x/workplan-a", AUTOLAB)
    post(world.realm, "work-m1", topic, "[selfnote][rootchat] front/front-a", FRONT)
    post(world.realm, "work-m1", topic, "Start task 3.", FRONT)
    post(world.realm, "work-m1", topic, ACK, AUTOLAB)
    answer = post(world.realm, "work-m1", topic, "@**Front** task 3 done", AUTOLAB)
    settle(world, lambda: world.mirror.message(answer) is not None)
    world.clock.now = world.realm.messages[answer]["timestamp"] + 400
    del task1
    return answer


@defect
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


@defect
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
