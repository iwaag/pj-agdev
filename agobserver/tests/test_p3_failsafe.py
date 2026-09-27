"""failsafe p3: the monitor's side of the consolidated recovery path."""

from __future__ import annotations

from agag.post import PROGRESS as PROGRESS_INTENT, REPORT, PostMeta, compose
from agag.reply import failure_line

from test_failsafe_reproductions import ACK, AUTOLAB, CHANNEL, DEV, FRONT, OBS, PROGRESS
from test_health_path import asked, incident_posts, post, world  # noqa: F401 - the fixture


def test_a_request_left_unanswered_by_two_failed_replies_goes_to_the_owners(world):
    """p2's #12509 without its luck: Front's listener served the Developer's
    question twice and neither run produced a usable reply. Asking Front a
    third time buys a third run of the same failure; the owners are told."""
    case = world("running")
    watcher = case.make()
    question = post(case, "front", case.desk, "And which file changed?", DEV, after=100)
    post(case, "front", case.desk, ACK, FRONT)
    post(case, "front", case.desk, compose(f"@**Developer**\n\n{failure_line('no block', final=False)}",
                                            PostMeta(intent=PROGRESS_INTENT)), FRONT)
    again = post(case, "front", case.desk, ACK, FRONT, after=25)
    post(case, "front", case.desk, compose(f"@**Developer**\n\n{failure_line('no block')}",
                                            PostMeta(intent=REPORT, end=again)), FRONT)
    watcher.tick()
    assert not [p for p in incident_posts(case) if "could not answer" in p], "not before its 60 s"
    for _ in range(3):
        case.clock.now += 60
        watcher.tick()
    said = [p for p in incident_posts(case) if "could not answer its requester" in p]
    reports = [p for p in said if "Stopped: I could not get this moving" in p]
    assert len(reports) == 1 and reports[0].startswith("@**Developer**"), "reported once, to the owners by name"
    assert len(said) == 2, "and handed to a developer review once"
    assert not asked(case), "Front is not asked a third time"
    assert question


# --- waits: explained, advancing, or only named (step 3) -----------------------------------

import time as _time

from agobserver import monitor as monitoring
from test_health_path import T0, look


def idle_wait(cpu=2.0, bound=None, since=T0 + 60):
    return {"schema": "agag.health.v1", "observed_at": 0, "verdict": "waiting",
            "why": "alive; waiting 400 s on Task (run the suite) with a process under it",
            "process": {"state": "alive"}, "progress": {"last_work_at": T0 + 60, "last_work": "tool Task"},
            "wait": {"kind": "tool", "id": "t1", "name": "Task", "detail": "run the suite", "since": since,
                     "bound_seconds": bound, "cpu_seconds": cpu},
            "serving": {"state": "acked", "queued": []}, "run": {"pid": 4242}, "unknowns": [],
            "source": {"host": "agstudio"}}


def test_a_named_wait_that_stops_advancing_reaches_front_within_its_bounds(world):
    """A subagent's call open with nothing under it advancing: named, but no
    longer explained. It is uncertainty after `wait_idle`, and Front is asked
    `ask_after` later — not reset by every look that sees the same wait."""
    case = world(idle_wait())
    watcher = case.make()
    first = look(case, watcher, T0 + 100 + 3000)
    started = T0 + 100 + monitoring.PROBE_AFTER
    bound = monitoring.WAIT_IDLE + monitoring.ASK_AFTER + 2 * 60
    assert first is not None and first - started <= bound, first - started
    content = asked(case)[0]["content"]
    assert "nothing under it has advanced" in content and "declares no bound of its own" in content


def test_a_wait_that_keeps_advancing_is_left_alone(world):
    case = world(*[idle_wait(cpu=10.0 * n) for n in range(1, 60)])
    watcher = case.make()
    assert look(case, watcher, T0 + 100 + 2400) is None
    assert not [p for p in incident_posts(case) if "Incident" in p]


def test_a_bounded_wait_is_the_probe_s_business(world):
    """A Bash call inside its own timeout is explained by that bound; past it
    the probe itself says unknown (`agag.health`)."""
    case = world(idle_wait(bound=600.0))
    watcher = case.make()
    assert look(case, watcher, T0 + 100 + 2400) is None


class SlowProbes:
    """Probes that take `delay` seconds each, but one unit's is at once and
    says `stopped`: the several-timeouts trial, scaled down."""

    def __init__(self, delay, fast_ack):
        self.delay, self.fast_ack, self.calls = delay, fast_ack, []

    def covers(self, owner):
        return owner == "autolab-agstudio1"

    def probe(self, owner, *, ack, channel, topic, window):
        self.calls.append(ack)
        if ack != self.fast_ack:
            _time.sleep(self.delay)
            return {"schema": "agag.health.v1", "verdict": "unknown", "why": "did not answer", "unknowns": ["x"]}
        return {"schema": "agag.health.v1", "verdict": "stopped", "why": "the process is gone", "unknowns": [],
                "process": {"state": "exited"}, "progress": {}, "wait": {"kind": "none"}}

    @property
    def runs(self):
        return len(self.calls)

    def stats(self):
        return {"runs": len(self.calls)}


def build_many(realm, n):
    """`n` requests, each Front → a plan → one task whose serving is open
    (acked at T0+60, quiet since T0+100); the last task is the one whose
    probe will say `stopped`."""
    from test_failsafe_reproductions import AUTOLAB, NAMES
    from test_health_path import PROGRESS

    realm.add_channel(3, "front")
    realm.add_channel(4, "pj-x")
    realm.add_channel(5, CHANNEL)
    acks = []
    for i in range(n):
        realm.add_channel(10 + i, f"work-m{i}")

        def post(channel, topic, text, sender, at):
            return realm.post(channel, topic, text, sender_id=sender, sender_name=NAMES[sender], timestamp=T0 + at)

        desk, plan = f"front-desk-p3-{i}", f"workplan-p3-{i}"
        post("front", desk, f"Request {i}.", DEV, 0)
        post("front", desk, ACK, FRONT, 1)
        started = post("front", desk, "@**Developer** Asked autolab.\n\n`ag-post intent=report`", FRONT, 5)
        post("pj-x", plan, f"[selfnote][rootchat] front/{desk} #{started}", FRONT, 6)
        post("pj-x", plan, "@**autolab-agstudio1** Mission request.", FRONT, 6)
        post("pj-x", plan, ACK, AUTOLAB, 7)
        mission = post("pj-x", plan, "[selfnote][mission] x", AUTOLAB, 20)
        post("pj-x", plan, "[selfnote][state] started", AUTOLAB, 20)
        planned = post("pj-x", plan, "@**Front** Planned.\n\n`ag-post intent=report`", AUTOLAB, 21)
        post("front", desk, f"[selfnote][served] pj-x/{plan} {planned}", FRONT, 25)
        task = f"workrun-task1-m{mission}"
        post(f"work-m{i}", task, f"[selfnote][task] {mission}#1", AUTOLAB, 50)
        post(f"work-m{i}", task, f"[selfnote][rootchat] pj-x/{plan} #{mission}", AUTOLAB, 50)
        post(f"work-m{i}", task, "# Task 1\n\nDo it.", AUTOLAB, 50)
        post(f"work-m{i}", task, f"[selfnote][start] #{planned} for {FRONT} Front", AUTOLAB, 51)
        acks.append(post(f"work-m{i}", task, ACK, AUTOLAB, 60))
        post(f"work-m{i}", task, "🔧 Read: x.py\n\n" + PROGRESS, AUTOLAB, 100)
    return acks


import pytest


@pytest.mark.parametrize("serial", [True, False], ids=["as-p2-ran-them", "with-the-budget"])
def test_slow_probes_do_not_hold_the_look_that_finds_a_stopped_task(tmp_path, serial):
    """Six probes that each take their whole timeout, and one unit whose
    probe answers `stopped` at once. Serially the look lasted the sum of the
    timeouts, and every request's next look waited for it. Within the budget
    the look ends on time and Front is asked about the stopped task in it."""
    from types import SimpleNamespace

    from agag.mirror import Mirror
    from agag.mirror.testing import FakeRealm

    from test_failsafe_reproductions import Client, spec

    realm = FakeRealm()
    acks = build_many(realm, 7)
    mirror = Mirror.open(tmp_path / "zulip.env", tmp_path / "mirror", client_factory=realm.facet,
                         log=lambda line: None, start=True, resync_backoff=0.05)
    try:
        deadline = _time.time() + 10
        while _time.time() < deadline and len(mirror.topics("work-m6")) < 1:
            _time.sleep(0.05)
        _time.sleep(0.3)
        clock = SimpleNamespace(now=T0 + 100 + monitoring.PROBE_AFTER + 1)
        probes = SlowProbes(0.6, fast_ack=acks[-1])
        watcher = monitoring.Monitor(spec(tmp_path / "w"), Client(realm, clock), mirror,
                                     judge=lambda *a, **k: {"verdict": "legit", "evidence": ""},
                                     clock=lambda: clock.now, interval=60, window_hours=12, probes=probes)
        if serial:
            # p2's scheduling: one probe after another, no budget.
            watcher.probe_workers, watcher.probe_budget = 1, 1000.0
        else:
            watcher.probe_budget = 1.0
        began = _time.monotonic()
        watcher.tick()
        took = _time.monotonic() - began
        print(f"look took {took:.2f} s ({'serial' if serial else 'budget 1 s, 4 workers'})")
        assert len(probes.calls) == 7
        if serial:
            assert took >= 0.6 * 6, "the reproduction: the look is the sum of the slow probes"
            return
        assert took < watcher.probe_budget + 1.5, f"the look took {took:.2f} s"
        asked_front = [m for m in realm.messages.values() if m["sender_id"] == 23 and m["display_recipient"] != CHANNEL
                       and "[selfnote]" not in m["content"]]
        assert len(asked_front) == 1 and "stopped" in asked_front[0]["content"].lower()
        health = watcher.health()
        assert health is not None
    finally:
        mirror.stop()


# --- reviews that stay current (step 4) -------------------------------------------------

from agobserver import review as reviewing
from test_review import review_posts, spoken, stall_and_recover


def report_unrecovered(case, watcher):
    """The task's serving is doubted (unknown every look) until the
    developer is told: a reported incident with its review occurrence."""
    case.probes.verdicts = ["unknown"]
    for _ in range(20):
        case.clock.now += 60
        watcher.tick()
        if [m for m in spoken(review_posts(case)) if "not recovered" in m["content"]]:
            break
    (record,) = [r for r in watcher.records() if r.get("state") == monitoring.REPORTED]
    return record


def test_a_reported_incident_that_recovers_later_says_so_in_its_review_once(world, monkeypatch):
    case = world("unknown")
    watcher = case.make()
    record = report_unrecovered(case, watcher)
    before = [m["content"] for m in spoken(review_posts(case))]
    assert any("not recovered" in text for text in before)
    # The work moves again: a new serving of the task shows work.
    post(case, "work-m1", case.task, "@**autolab-agstudio1** Continue.", FRONT)
    post(case, "work-m1", case.task, ACK, AUTOLAB, after=1)
    post(case, "work-m1", case.task, "🔧 Edit: wordcount.py\n\n" + PROGRESS, AUTOLAB, after=20)
    case.probes.verdicts = ["running"]
    # The process exits right after posting the update, before recording it.
    (case.where / "local" / "faults").mkdir(parents=True, exist_ok=True)
    (case.where / "local" / "faults" / reviewing.EXIT_FAULT).touch()
    exits = []
    monkeypatch.setattr(reviewing.os, "_exit", lambda code: (exits.append(code), (_ for _ in ()).throw(SystemExit)))
    case.clock.now += 60
    try:
        watcher.tick()
    except SystemExit:
        pass
    assert exits == [70]
    restarted = case.make()
    for _ in range(3):
        case.clock.now += 60
        restarted.tick()
    later = [m["content"] for m in spoken(review_posts(case)) if "— later:" in m["content"]]
    assert len(later) == 1, later
    assert "the work moved again" in later[0] and "stands as seen then: reported unrecovered" in later[0]
    assert [m["content"] for m in spoken(review_posts(case))][:len(before)] == before, "the original stays"
    stored = restarted.load(record["key"])
    assert stored["review"]["updates"]["moving"]["posted"] is True


def test_the_final_record_joins_the_occurrence_once(world):
    case = world("stopped")
    watcher = case.make()
    record = stall_and_recover(case, watcher)
    post(case, "work-m1", case.task, "[selfnote][state] completed", AUTOLAB)
    for _ in range(3):
        case.clock.now += 60
        watcher.tick()
    later = [m["content"] for m in spoken(review_posts(case)) if "— later:" in m["content"]]
    assert len(later) == 1 and "the work's own record says `done`" in later[0], later
    assert "stands as seen then: recovered" in later[0]


def test_an_injected_fault_is_said_to_be_a_trial_not_a_recurrence():
    record = {"kind": "stopped", "fact": "a health check found the work stopped: …",
              "timeline": {"checks": [{"verdict": "stopped", "why": "the run ended (failed, exit -9)",
                                       "injected": "silent-exit"}]}}
    found = reviewing.assess(record)
    assert found["injected"] == "silent-exit" and found["confidence"] == "high"
    assert "not as a recurrence" in found["candidate"]
    probe_fault = {"kind": "uncertain", "fact": "a health check could not confirm the work is being done: the health "
                                               "probe of autolab-agstudio1 failed (fault injected: probe-fail)"}
    assert reviewing.assess(probe_fault)["injected"] == "probe-fail"


def test_the_assessment_reads_this_occurrence_s_evidence_and_may_say_unknown():
    killed = {"kind": "stopped", "fact": "x", "timeline": {"checks": [
        {"verdict": "stopped", "why": "the run ended (failed, exit -9), its serving delivered no reply"}]}}
    assert "SIGKILL" in reviewing.assess(killed)["cause"] and reviewing.assess(killed)["confidence"] == "medium"
    over = {"kind": "uncertain", "fact": "x", "timeline": {"checks": [
        {"verdict": "unknown", "why": "alive; its Bash call has been open 700 s, past its own bound of 600 s"}]}}
    assert "outlived its own timeout" in reviewing.assess(over)["cause"]
    nothing = {"kind": "origin_closed", "fact": "the request's conversation is ✔"}
    assert reviewing.assess(nothing)["cause"] == "unknown" and reviewing.assess(nothing)["confidence"] == "none"


class StatusClient:
    def __init__(self, history):
        self.history, self.sent = history, []

    def message(self, message_id, **kwargs):
        return {"id": message_id, "display_recipient": CHANNEL, "subject": "✔ review-autolab-stopped",
                "content": "opening"}

    def topic_history(self, channel, topic, num_before=1000):
        return list(self.history)

    def send_to_channel(self, channel, topic, content):
        self.sent.append((topic, content))
        self.history.append({"id": 900 + len(self.sent), "content": content})
        return 900 + len(self.sent)


def test_a_follow_up_decision_is_a_post_in_the_review_and_is_recorded_once(monkeypatch):
    from agobserver import review_status

    from types import SimpleNamespace

    monkeypatch.setattr(review_status, "SPEC", SimpleNamespace(instance_name=lambda: CHANNEL))
    reviews = {"autolab-agstudio1 · stopped": {"topic": "review-autolab-stopped", "anchor": 500,
                                                "occurrences": ["o1:n2 e1", "o3:n4 e1"]}}
    client = StatusClient([])
    assert review_status.main(["review-autolab-stopped", "all", "fixed", "--note", "the splitter reads tags",
                               "--ref", "pyagag a686f22", "--by", "Omni Agent"], client=client, reviews=reviews) == 0
    (said, *notes) = [content for _, content in client.sent]
    assert said.startswith("**Occurrences 1, 2: fixed** — the splitter reads tags (pyagag a686f22). Recorded by "
                           "Omni Agent.") and "not the review's ✔" in said
    assert notes == ["[selfnote][occurrence-status] o1:n2 e1 fixed", "[selfnote][occurrence-status] o3:n4 e1 fixed"]
    assert {topic for topic, _ in client.sent} == {"✔ review-autolab-stopped"}, "posted where the topic is now"
    assert review_status.main(["review-autolab-stopped", "1", "fixed", "--note", "again"], client=client,
                              reviews=reviews) == 0
    assert len(client.sent) == 3, "already recorded: nothing posted twice"


def test_a_recovery_seen_before_reviews_kept_later_outcomes_is_added_once(world):
    """p2's C and D moved again after their report, before this existed."""
    case = world("unknown")
    watcher = case.make()
    record = report_unrecovered(case, watcher)
    stored = watcher.load(record["key"])
    stored["cleared_at"] = case.clock.now - 30
    watcher.save(stored)
    case.probes.verdicts = ["running"]
    for _ in range(3):
        case.clock.now += 60
        watcher.tick()
    later = [m["content"] for m in spoken(review_posts(case)) if "— later:" in m["content"]]
    assert len(later) == 1 and "the work moved again at" in later[0] and "seen in its incident topic" in later[0]
