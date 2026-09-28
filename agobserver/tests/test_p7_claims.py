"""failsafe p7: a reply that claims an act it never did, as Observer sees it.

The listener serves the agent once with the mismatch; a repeat is an
escalated `[selfnote][claim]`, which the trace makes a `claim` candidate.
Observer reports it to the owners and never asks the agent again — another
ask buys another run of the same failure (the `unanswered` rule)."""

from __future__ import annotations

from agag.claims import claim_note, settled_note
from agag.post import REPORT, PostMeta, compose

from test_failsafe_reproductions import ACK, DEV, FRONT
from test_health_path import asked, incident_posts, post, world  # noqa: F401 - the fixture
from agobserver.monitor import Monitor


def test_an_escalated_claim_goes_to_the_owners_and_front_is_not_asked(world):
    case = world("running")
    watcher = case.make()
    post(case, "front", case.desk, "I release the hold; stop following this request", DEV, after=100)
    ack = post(case, "front", case.desk, ACK, FRONT)
    reply = post(case, "front", case.desk, compose("@**Developer**\n\nReleased hold #15837.",
                                                   PostMeta(intent=REPORT, end=ack)), FRONT)
    first = post(case, "front", case.desk, claim_note({"reply": reply, "attempt": 1, "missing": [
        {"act": "release", "target": 15837, "quote": "Released hold #15837."}]}), FRONT)
    ack2 = post(case, "front", case.desk, ACK, FRONT, after=5)
    again = post(case, "front", case.desk, compose("@**Developer**\n\nReleased hold #15837, as I said.",
                                                   PostMeta(intent=REPORT, end=ack2)), FRONT)
    post(case, "front", case.desk, claim_note({"reply": again, "attempt": 2, "of": first, "missing": [
        {"act": "release", "target": 15837}]}), FRONT)
    watcher.tick()
    for _ in range(3):
        case.clock.now += 60
        watcher.tick()
    said = [p for p in incident_posts(case) if "no record shows" in p]
    reports = [p for p in said if "Stopped: I could not get this moving" in p]
    assert len(reports) == 1 and reports[0].startswith("@**Developer**"), "reported once, to the owners by name"
    assert not asked(case), "Front is not asked again"


def test_a_claim_incident_recovers_only_on_its_settlement():
    class Node:
        claims = [{"id": 30}]

    record = {"kind": "claim", "evidence": [30, 29]}
    assert not Monitor.recovered(record, Node())
    Node.claims = []
    assert Monitor.recovered(record, Node())
    assert settled_note(30, "recorded", 31).endswith("#30 recorded #31")
