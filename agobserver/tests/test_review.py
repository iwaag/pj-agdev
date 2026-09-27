"""failsafe p2 step 4: recovered incidents are handed to the developer."""

from __future__ import annotations

import json

import pytest

from agobserver import monitor as monitoring
from agobserver import review as reviewing

from test_failsafe_reproductions import ACK, AUTOLAB, CHANNEL, FRONT, PROGRESS
from test_health_path import T0, asked, post, settle, world  # noqa: F401 - the fixture


def stall_and_recover(case, watcher):
    """The task's current serving stops (the probe says so), Front is
    asked, Front resumes it and the new serving works; returns the rescued
    incident record."""
    before = len(asked(case))
    case.probes.verdicts = ["stopped"]
    for _ in range(12):
        case.clock.now += 60
        watcher.tick()
        if len(asked(case)) > before:
            break
    assert len(asked(case)) == before + 1, "Front was asked"
    post(case, "work-m1", case.task, "@**autolab-agstudio1** Continue from what the copy holds.", FRONT)
    post(case, "work-m1", case.task, ACK, AUTOLAB, after=1)
    post(case, "work-m1", case.task, "🔧 Edit: wordcount.py\n\n" + PROGRESS, AUTOLAB, after=20)
    case.probes.verdicts = ["running"]
    case.clock.now += 60
    touched = watcher.tick()
    (record,) = [r for r in touched if r.get("state") == monitoring.RESCUED]
    return record


def review_posts(case, topic_prefix="review-"):
    return [m for m in case.realm.messages.values()
            if m["display_recipient"] == CHANNEL and m["subject"].lstrip("✔ ").startswith(topic_prefix)]


def spoken(posts):
    return [m for m in posts if "[selfnote]" not in m["content"]]


def test_a_recovered_incident_is_handed_to_the_developer_once(world):
    case = world("stopped")
    watcher = case.make()
    record = stall_and_recover(case, watcher)
    for _ in range(3):
        case.clock.now += 60
        watcher.tick()

    posts = review_posts(case)
    assert {m["subject"] for m in posts} == {"review-autolab-stopped"}
    opening, occurrence = [m["content"] for m in spoken(posts)]
    assert "Developer review: `autolab-agstudio1 · stopped`" in opening and "not by a cause" in opening
    assert occurrence.startswith("@**Developer** **Occurrence 1**")
    for words in ("onset ≈", "first suspicion", "Front asked", "work moving again", "Durations: detection",
                  "recovery", "Health checks", "Confirmed: the health check saw the work stopped",
                  "Observed failure:", "Plausible cause:", "(confidence: **", "Missing evidence:", "Candidate:"):
        assert words in occurrence, words
    assert f"#**{CHANNEL}>{record['topic']}**" in occurrence
    notes = [m["content"] for m in posts if "[selfnote]" in m["content"]]
    assert notes == ["[selfnote][review] autolab-agstudio1 · stopped e1",
                     f"[selfnote][occurrence] {record['key']} e1"]
    incident = [m["content"] for m in case.realm.messages.values() if m["subject"] == record["topic"]]
    assert sum("Handed to the developer for review" in text for text in incident) == 1
    # The operational record and the review are separate states.
    stored = watcher.load(record["key"])
    assert stored["state"] == monitoring.RESCUED and stored["review"]["delivered"] is True


def test_recurrences_append_with_their_own_evidence_and_the_third_names_the_owners(world):
    case = world("stopped")
    watcher = case.make()
    keys = [stall_and_recover(case, watcher)["episode"] for _ in range(3)]
    case.clock.now += 60
    watcher.tick()
    assert keys == [1, 2, 3]
    occurrences = [m["content"] for m in spoken(review_posts(case))][1:]
    assert [text.split("**")[1] if text.startswith("**") else text.split("**")[3] for text in occurrences] == \
        ["Occurrence 1", "Occurrence 2", "Occurrence 3"]
    assert occurrences[0].startswith("@**Developer**")
    assert not occurrences[1].startswith("@**"), "a recovered recurrence is appended quietly"
    assert occurrences[2].startswith("@**Developer**") and "recurring: 3 occurrences" in occurrences[2]
    reviews = json.loads((case.where / "local" / "incidents" / reviewing.REVIEWS_FILE).read_text())
    assert len(reviews["autolab-agstudio1 · stopped"]["occurrences"]) == 3


def test_an_interrupted_handoff_is_finished_without_a_second_post(world, monkeypatch):
    """Observer stops between posting the occurrence and recording it."""
    case = world("stopped")
    watcher = case.make()
    original = reviewing.Reviews.save
    calls = {"n": 0}

    def crash_once(self, reviews):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("the process died here")
        return original(self, reviews)

    monkeypatch.setattr(reviewing.Reviews, "save", crash_once)
    stall_and_recover(case, watcher)
    # A restarted monitor over the same store and the same realm.
    monkeypatch.setattr(reviewing.Reviews, "save", original)
    (case.where / "local" / "incidents" / reviewing.REVIEWS_FILE).unlink(missing_ok=True)
    watcher = case.make()
    for _ in range(2):
        case.clock.now += 60
        watcher.tick()
    occurrences = [m for m in spoken(review_posts(case)) if "Occurrence" in m["content"]]
    assert len(occurrences) == 1
    assert len({m["subject"] for m in review_posts(case)}) == 1


def test_a_review_the_developer_closed_opens_a_new_episode_on_recurrence(world):
    case = world("stopped")
    watcher = case.make()
    stall_and_recover(case, watcher)
    case.clock.now += 60
    watcher.tick()
    first = spoken(review_posts(case))[0]
    case.realm.resolve(CHANNEL, "review-autolab-stopped")
    settle(case, lambda: watcher.where(first["id"])[1].startswith("✔"))
    stall_and_recover(case, watcher)
    case.clock.now += 60
    watcher.tick()
    topics = {m["subject"] for m in review_posts(case)}
    assert topics == {"✔ review-autolab-stopped", "review-autolab-stopped-2"}
    second = [m["content"] for m in spoken(review_posts(case)) if m["subject"] == "review-autolab-stopped-2"]
    assert "after `review-autolab-stopped` was reviewed" in second[0]
    assert second[1].startswith("@**Developer** **Occurrence 1**")


def test_requests_before_the_failsafe_horizon_are_not_reviewed(world):
    case = world("stopped")
    watcher = case.make()
    watcher.obligations_from = 10 ** 9
    for _ in range(10):
        case.clock.now += 60
        watcher.tick()
    assert review_posts(case) == []
