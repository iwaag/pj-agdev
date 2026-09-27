"""failsafe p5 step 2: a queued post is read against the owner's queue.

Two requests reach autolab at once (progress_panel p1 trial B): request 1's
task is being served, request 2's plan post waits for autolab's one
executor. Observer reads the wait the way the progress panel does
(`agag.waits`): from autolab's own listener (`probe_queue`, scripted here)
or, for an owner without the interface, from the open servings the traced
requests show. On an injected clock; nothing sleeps for a threshold.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from agag.mirror import Mirror
from agag.mirror.testing import FakeRealm

from agobserver import monitor as monitoring

from test_failsafe_reproductions import ACK, AUTOLAB, CHANNEL, DEV, FRONT, NAMES, OBS, Client, spec
from test_health_path import T0, Probes, asked, build, incident_posts


class QueueProbes(Probes):
    """Probes of servings as `Probes` scripts them; queue probes answer
    `queue` (a verdict or a document, the last one repeating)."""

    def __init__(self, clock, queue, *verdicts):
        super().__init__(*verdicts)
        self.clock = clock
        self.queue = list(queue)
        self.queue_calls = []

    def probe(self, owner, *, ack, channel, topic, window, queued_since=None):
        if queued_since is None:
            return super().probe(owner, ack=ack, channel=channel, topic=topic, window=window)
        self.runs += 1
        self.queue_calls.append((topic, queued_since))
        answer = self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]
        if isinstance(answer, dict):
            return {"observed_at": self.clock.now, **answer}
        ahead = {"channel": "work-m1", "topic": self.task, "ack": self.ack, "verdict": "running",
                 "why": "alive; its last work was 5 s ago"}
        docs = {
            "queued": {"verdict": "queued", "why": f"queued behind work-m1/{self.task}, whose serving is running",
                       "queue": {"ahead": [ahead]}},
            "idle": {"verdict": "stopped", "why": "queued 400 s while the listener's executor runs nothing: it has "
                                                  "not picked the conversation up for 130 s", "queue": {"ahead": []}},
            "blocked": {"verdict": "unknown", "why": f"queued behind work-m1/{self.task}, whose serving is stopped",
                        "queue": {"ahead": [{**ahead, "verdict": "stopped"}]}},
            "unknown": {"verdict": "unknown", "why": "the listener's queue could not be read", "queue": {}},
        }
        return {"schema": "agag.health.v1", "observed_at": self.clock.now, **docs[answer]}

    def probe_queue(self, owner, *, channel, topic, since, window):
        return self.probe(owner, ack=0, channel=channel, topic=topic, window=window, queued_since=since)


def second_request(realm, case):
    """Request 2: Front asks autolab for a plan at T0+120 while autolab is
    serving request 1's task. Nobody acknowledges it."""
    realm.add_channel(20, "pj-y")

    def post(channel, topic, text, sender, at):
        return realm.post(channel, topic, text, sender_id=sender, sender_name=NAMES[sender], timestamp=T0 + at)

    desk, plan = "front-desk-p5-two", "workplan-y"
    ask = post("front", desk, "Plan something small in y.", DEV, 110)
    post("front", desk, ACK, FRONT, 111)
    post("front", desk, "@**Developer** Asked autolab; I report here.\n\n`ag-post intent=report`", FRONT, 115)
    post("pj-y", plan, f"[selfnote][rootchat] front/{desk} #{ask}", FRONT, 120)
    queued = post("pj-y", plan, "@**autolab-agstudio1** Please plan one task for y.", FRONT, 120)
    case.ask2, case.desk2, case.plan2, case.queued = ask, desk, plan, queued


@pytest.fixture
def two(tmp_path):
    opened = []

    def make(queue, *verdicts, owners=True):
        realm = FakeRealm()
        case = build(realm)
        second_request(realm, case)
        mirror = Mirror.open(tmp_path / "zulip.env", tmp_path / f"mirror{len(opened)}", client_factory=realm.facet,
                             log=lambda line: None, start=True, resync_backoff=0.05)
        deadline = time.time() + 5
        while time.time() < deadline and not mirror.topics("pj-y"):
            time.sleep(0.05)
        time.sleep(0.3)
        clock = SimpleNamespace(now=T0 + 130)
        probes = QueueProbes(clock, queue, *(verdicts or ("running",)))
        probes.task, probes.ack = case.task, case.ack
        if not owners:
            probes.covers = lambda owner: False
        where = tmp_path / f"w{len(opened)}"
        case.realm, case.mirror, case.clock, case.probes, case.where = realm, mirror, clock, probes, where
        case.judged = []

        def judge(*args, **kwargs):
            case.judged.append(args[1].kind)
            return {"verdict": "legit", "evidence": "looks fine"}

        case.watcher = monitoring.Monitor(spec(where), Client(realm, clock), mirror, judge=judge,
                                          clock=lambda: clock.now, interval=60, window_hours=12, probes=probes)
        opened.append(mirror)
        return case

    yield make
    for mirror in opened:
        mirror.stop()


def run(case, until, step=60):
    while case.clock.now <= until:
        case.watcher.tick()
        case.clock.now += step


def asked_in(case, topic):
    return [m for m in asked(case) if m["subject"].endswith(topic)]


def queue_state(case):
    return case.watcher.load_health().get(f"q{_plan_anchor(case)}") or {}


def _plan_anchor(case):
    from agag.trace import MirrorReader, trace

    result = trace(MirrorReader(case.mirror), case.ask2, now=int(case.clock.now))
    return next(n.anchor for n in result.nodes() if n.topic.endswith(case.plan2))


def test_a_post_queued_behind_healthy_work_is_never_asked_about(two):
    case = two(["queued"])
    run(case, T0 + 1800)
    assert not asked_in(case, case.desk2), "Front was asked about a healthy queue"
    assert not [p for p in incident_posts(case) if "unacknowledged" in p or "unserved" in p]
    assert case.probes.queue_calls, "the queue was never read"
    state = queue_state(case)
    assert state["state"] == "behind" and state["evidence"] == "confirmed" and state["post"] == case.queued
    assert state["queued_at"] == T0 + 120 and state["ahead"] == [f"work-m1/{case.task}#{case.ack}"]
    assert case.watcher.health()["queues"] == {"behind": 1}


def test_a_post_the_listener_is_not_serving_is_reported_not_asked(two):
    case = two(["idle"])
    run(case, T0 + 600)
    assert not asked_in(case, case.desk2), "Front was asked to fix a listener"
    posts = incident_posts(case)
    assert any("**Incident: unserved**" in p for p in posts), posts
    assert any("Reported" in p or "reported" in p for p in posts)


def test_a_queue_nothing_confirms_is_the_plain_rule(two):
    case = two(["unknown"])
    run(case, T0 + 600)
    (request,) = asked_in(case, case.desk2)
    assert "acknowledged" in request["content"] and "could not be read" in request["content"]


def test_a_post_blocked_behind_another_requests_stopped_task_is_left_to_that_request(two):
    # Request 1's task stops (its own probe says so); request 2 waits behind it.
    case = two(["blocked"], "stopped")
    run(case, T0 + 600)
    assert asked_in(case, case.desk), "the stopped task's own request was not asked"
    assert not asked_in(case, case.desk2), "the queued request was asked about somebody else's work"
    # …for a bounded time: past `escalate_after` it is reported, never excused for ever.
    run(case, T0 + 130 + 300 + case.watcher.timing["escalate_after"] + 120)
    assert any("**Incident: unserved**" in p for p in incident_posts(case))
    assert not asked_in(case, case.desk2)


def test_an_incident_on_a_wait_later_confirmed_legitimate_is_excused_not_rescued(two):
    case = two(["unknown", "queued"])
    run(case, T0 + 430)
    assert asked_in(case, case.desk2)
    run(case, T0 + 500)
    record = next(r for r in case.watcher.records() if r.get("kind") == "unacknowledged")
    assert record["state"] == "excused"
    assert not any("Rescued" in p for p in incident_posts(case))


def test_an_owner_without_the_interface_is_read_from_the_conversations_for_a_bounded_time(two):
    # Request 1's task shows work at T0+100: autolab is busy (conversation only).
    case = two(["queued"], owners=False)
    case.realm.post("work-m1", case.task, "🔧 Bash: pytest -q\n\n`ag-post intent=progress`", sender_id=AUTOLAB,
                    sender_name=NAMES[AUTOLAB], timestamp=T0 + 400)
    time.sleep(0.3)
    run(case, T0 + 900)
    assert not asked_in(case, case.desk2)
    assert queue_state(case)["evidence"] == "conversation"
    # The task's last work ages past WORK_QUIET: the excuse lapses.
    case.clock.now = T0 + 400 + 1801
    run(case, case.clock.now + 60)
    assert asked_in(case, case.desk2)


def test_an_answer_waiting_for_its_requesters_busy_listener_is_not_undelivered(two):
    """Trial D: autolab's close-out named Front while Front's one executor
    served the other study's run; Observer asked about three answers that
    were only waiting their turn."""
    case = two(["queued"], "running")
    realm = case.realm
    # Request 2's plan is answered by autolab, naming Front…
    answer = realm.post("pj-y", case.plan2, "@**Front** Planned; nothing to start yet.\n\n`ag-post intent=report`",
                        sender_id=AUTOLAB, sender_name=NAMES[AUTOLAB], timestamp=T0 + 140)
    # …while Front is busy serving request 1's desk (acked, working).
    realm.post("front", case.desk, "Please also check the README.", sender_id=DEV, sender_name=NAMES[DEV],
               timestamp=T0 + 130)
    realm.post("front", case.desk, ACK, sender_id=FRONT, sender_name=NAMES[FRONT], timestamp=T0 + 135)
    for at in range(200, 900, 120):
        realm.post("front", case.desk, "🔧 agentchat read pj-x workplan-x\n\n`ag-post intent=progress`",
                   sender_id=FRONT, sender_name=NAMES[FRONT], timestamp=T0 + at)
    time.sleep(0.3)
    run(case, T0 + 900)
    assert not asked_in(case, case.desk2), "Front was asked about an answer waiting in its own queue"
    assert not [p for p in incident_posts(case) if "undelivered" in p]
    state = queue_state(case)
    assert state["evidence"] == "conversation" and state["post"] == answer
