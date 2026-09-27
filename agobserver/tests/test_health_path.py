"""failsafe p2 step 3: early diagnosis through the owner's health interface.

A request as autolab serves it — Front's conversation, the mission, one task
whose serving is open (acknowledged, no reply) — looked at by the monitor on
an injected clock, with the owner's probe scripted. Every threshold is
exercised on the clock; nothing here sleeps for it.
"""

from __future__ import annotations

import json
import sys
import time
from types import SimpleNamespace

import pytest

from agag.mirror import Mirror
from agag.mirror.testing import FakeRealm

from agobserver import monitor as monitoring
from agobserver.health import HealthProbes, unknown

from test_failsafe_reproductions import ACK, AUTOLAB, CHANNEL, DEV, FRONT, NAMES, OBS, PROGRESS, Client, spec

T0 = 1790500000


class Probes:
    """The owner's health interface, scripted: `verdicts` is consumed one
    per probe (the last one repeats)."""

    def __init__(self, *verdicts, owner="autolab-agstudio1"):
        self.verdicts = list(verdicts) or ["unknown"]
        self.owner = owner
        self.calls = []
        self.runs = 0

    def covers(self, owner):
        return owner == self.owner

    def probe(self, owner, *, ack, channel, topic, window):
        self.runs += 1
        self.calls.append((ack, topic))
        verdict = self.verdicts.pop(0) if len(self.verdicts) > 1 else self.verdicts[0]
        if isinstance(verdict, dict):
            return verdict
        why = {"stopped": "the harness process is gone and its runner never recorded an end, its serving "
                          "delivered no reply (journal: acked) and nothing is queued to serve it again",
               "waiting": "alive; waiting 400 s on Bash (pytest -q) with a process under it",
               "running": "alive; its last event (text) was 5 s ago",
               "unknown": "alive, but no event for 300 s and no tool call or child process explains the wait",
               "ended": "the run is over and its serving is delivered: a reply is (being) posted"}[verdict]
        return {"schema": "agag.health.v1", "observed_at": 0, "verdict": verdict, "why": why,
                "process": {"state": "exited" if verdict in ("stopped", "ended") else "alive"},
                "progress": {"last_event_at": T0 + 100, "last_event": "tool Bash"},
                "wait": {"kind": "tool", "name": "Bash", "detail": "pytest -q"} if verdict == "waiting" else {"kind": "none"},
                "serving": {"state": "acked", "queued": []}, "run": {"pid": 4242},
                "unknowns": ["what the process is doing"] if verdict == "unknown" else [],
                "source": {"host": "agstudio"}}

    def stats(self):
        return {"runs": self.runs}


def build(realm, *, ended=False):
    """Front's request, autolab's mission and its task 1, whose serving was
    acknowledged at T0+60 and posted progress until T0+100."""
    for stream_id, name in enumerate(("front", "pj-x", "work-m1", CHANNEL), start=3):
        realm.add_channel(stream_id, name)

    def post(channel, topic, text, sender, at):
        return realm.post(channel, topic, text, sender_id=sender, sender_name=NAMES[sender], timestamp=T0 + at)

    desk, plan = "front-desk-p2", "workplan-x"
    ask = post("front", desk, "Add a flag to wordcount.py.", DEV, 0)
    post("front", desk, ACK, FRONT, 1)
    started = post("front", desk, "@**Developer** Asked autolab; I report here.\n\n`ag-post intent=report`",
                   FRONT, 5)
    post("pj-x", plan, f"[selfnote][rootchat] front/{desk} #{started}", FRONT, 6)
    post("pj-x", plan, "@**autolab-agstudio1** Mission request: one task.", FRONT, 6)
    post("pj-x", plan, ACK, AUTOLAB, 7)
    mission = post("pj-x", plan, "[selfnote][mission] x", AUTOLAB, 20)
    post("pj-x", plan, "[selfnote][state] started", AUTOLAB, 20)
    planned = post("pj-x", plan, "@**Front** Planned; task 1 starts now.\n\n`ag-post intent=report`", AUTOLAB, 21)
    post("front", desk, f"[selfnote][served] pj-x/{plan} {planned}", FRONT, 25)
    task = f"workrun-task1-m{mission}"
    post("work-m1", task, f"[selfnote][task] {mission}#1", AUTOLAB, 50)
    post("work-m1", task, f"[selfnote][rootchat] pj-x/{plan} #{mission}", AUTOLAB, 50)
    post("work-m1", task, "# Task 1\n\nAdd the flag.", AUTOLAB, 50)
    post("work-m1", task, "Task 1 starts now.\n\n" + PROGRESS, AUTOLAB, 51)
    post("work-m1", task, f"[selfnote][start] #{planned} for {FRONT} Front", AUTOLAB, 51)
    ack = post("work-m1", task, ACK, AUTOLAB, 60)
    post("work-m1", task, "🔧 Read: wordcount.py\n\n" + PROGRESS, AUTOLAB, 100)
    if ended:
        post("work-m1", task, f"@**Front**\n\nI read the code and changed nothing yet.\n\n`ag-post end={ack}`",
             AUTOLAB, 110)
    return SimpleNamespace(ask=ask, task=task, ack=ack, desk=desk, plan=plan)


@pytest.fixture
def world(tmp_path):
    opened = []

    def make(*verdicts, ended=False, local=None):
        realm = FakeRealm()
        case = build(realm, ended=ended)
        mirror = Mirror.open(tmp_path / "zulip.env", tmp_path / f"mirror{len(opened)}", client_factory=realm.facet,
                             log=lambda line: None, start=True, resync_backoff=0.05)
        deadline = time.time() + 5
        while time.time() < deadline and not mirror.topics("work-m1"):
            time.sleep(0.05)
        time.sleep(0.3)
        clock = SimpleNamespace(now=T0 + 100)
        probes = Probes(*verdicts)
        where = tmp_path / (local or f"w{len(opened)}")
        case.realm, case.mirror, case.clock, case.probes, case.where = realm, mirror, clock, probes, where
        case.judged = []

        def judge(*args, **kwargs):
            case.judged.append(args[1].kind)
            return {"verdict": "legit", "evidence": "looks fine"}

        case.make = lambda probes=probes: monitoring.Monitor(spec(where), Client(realm, clock), mirror, judge=judge,
                                                             clock=lambda: clock.now, interval=60, window_hours=12,
                                                             probes=probes)
        opened.append(mirror)
        return case

    yield make
    for mirror in opened:
        mirror.stop()


def asked(case):
    return [m for m in case.realm.messages.values()
            if m["display_recipient"] != CHANNEL and m["sender_id"] == OBS and "[selfnote]" not in m["content"]]


def incident_posts(case):
    return [m["content"] for m in case.realm.messages.values() if m["display_recipient"] == CHANNEL]


def look(case, watcher, until, step=60):
    """Look every `step` s until `until` (clock time); the clock time of the
    first request to Front, or None."""
    while case.clock.now <= until:
        watcher.tick()
        if asked(case):
            return case.clock.now
        case.clock.now += step
    return None


def settle(case, predicate):
    deadline = time.time() + 5
    while time.time() < deadline and not predicate():
        time.sleep(0.05)


def post(case, channel, topic, text, sender, after=5):
    case.clock.now += after
    ident = case.realm.post(channel, topic, text, sender_id=sender, sender_name=NAMES[sender],
                            timestamp=int(case.clock.now))
    settle(case, lambda: case.mirror.message(ident) is not None)
    return ident


# --- the trials' mechanics ------------------------------------------------------------


def test_a_silent_exit_reaches_front_within_five_minutes_and_is_rescued_by_resumed_work(world):
    """The worker exits at T0+100 right after its last progress post; its
    serving never replies. No model is asked; the probe confirms the stop."""
    case = world("stopped")
    exit_at = T0 + 100
    watcher = case.make()
    at = look(case, watcher, exit_at + 600)
    assert at is not None and at - exit_at <= 300, at - exit_at if at else None
    assert at - exit_at <= monitoring.DETECTION_TARGET["stopped"]
    request = asked(case)[0]
    assert request["subject"] == case.desk, "the conversation Front holds above the task"
    assert "has stopped" in request["content"] and "Health check" in request["content"]
    assert "process exited" in request["content"] and "listener journal: acked" in request["content"]
    assert "first suspicion" in request["content"] and "I tell the developer" in request["content"]
    assert request["content"].endswith("`ag-post intent=report answer=none`")
    assert case.judged == []
    assert case.probes.calls[0] == (case.ack, case.task), "the probe names the serving by its ack"

    # Front resumes: a post in the task starts a new serving that works.
    post(case, "work-m1", case.task, "@**autolab-agstudio1** Continue from what the copy holds.", FRONT)
    post(case, "work-m1", case.task, ACK, AUTOLAB, after=1)
    post(case, "work-m1", case.task, "🔧 Edit: wordcount.py\n\n" + PROGRESS, AUTOLAB, after=20)
    case.probes.verdicts = ["running"]
    case.clock.now += 60
    (record,) = [r for r in watcher.tick() if r.get("kind") == "stopped"]
    assert record["state"] == monitoring.RESCUED
    assert record["timeline"]["first_suspicion"] and record["timeline"]["onset"]
    assert len(asked(case)) == 1


def test_a_healthy_quiet_tool_wait_is_probed_and_never_asked_about(world):
    """A 30-minute test run: silent in Zulip, `waiting` on a named tool
    call every look. No request, no incident, no competing work."""
    case = world("waiting")
    watcher = case.make()
    assert look(case, watcher, T0 + 100 + 1800) is None
    assert case.probes.runs >= 25, "kept under review: probed every look while silent"
    assert not [p for p in incident_posts(case) if "Incident" in p]
    state = json.loads((case.where / "local" / "incidents" / monitoring.HEALTH_STATE_FILE).read_text())
    (entry,) = state.values()
    assert entry["verdict"] == "waiting" and not entry.get("first_suspicion")


def test_alive_without_progress_is_asked_about_then_escalated_within_bounds(world):
    case = world("unknown")
    watcher = case.make()
    at = look(case, watcher, T0 + 100 + 900)
    suspicion = T0 + 100 + monitoring.PROBE_AFTER
    assert at is not None and at - suspicion <= 300, at - suspicion
    assert "cannot confirm" in asked(case)[0]["content"] and "Not established" in asked(case)[0]["content"]
    # Repeated identical unknowns do not move the first suspicion; the
    # developer is told within ten minutes of it.
    while case.clock.now < suspicion + monitoring.ESCALATE_AFTER + 120:
        case.clock.now += 60
        watcher.tick()
    escalations = [m["content"] for m in case.realm.messages.values() if m["display_recipient"] == CHANNEL
                   and m["subject"].startswith("incident-") and "@**Developer**" in m["content"]]
    assert len(escalations) == 1 and "after the first suspicion" in escalations[0]
    # …and an unrecovered occurrence is handed to the developer's review.
    review = [m["content"] for m in case.realm.messages.values() if m["subject"].startswith("review-")]
    assert any("**not recovered**" in text and "@**Developer**" in text for text in review)
    reported = [r for r in watcher.records() if r.get("state") == monitoring.REPORTED]
    assert reported and reported[0]["reported_at"] - suspicion <= monitoring.ESCALATE_AFTER + 60
    assert len(asked(case)) == 1, "no second request after the escalation"


def test_a_claim_of_progress_does_not_reset_the_uncertainty(world):
    """Healthy verdicts clear a suspicion; another `unknown` on the same
    evidence does not — and neither does a model's `legit`, which is never
    asked on this path."""
    case = world("unknown", "unknown", "unknown", "unknown")
    watcher = case.make()
    look(case, watcher, T0 + 100 + monitoring.PROBE_AFTER + 60)
    state = watcher.load_health()
    first = next(iter(state.values()))["first_suspicion"]
    look(case, watcher, case.clock.now + 120)
    assert next(iter(watcher.load_health().values()))["first_suspicion"] == first
    assert case.judged == []


def test_a_failing_probe_is_uncertainty_with_bounds_and_other_work_stays_monitored(world, tmp_path):
    """The adapter itself fails (here: times out). The unit is uncertain —
    asked about and escalated in the same bounds — and the look goes on."""
    case = world()
    slow = HealthProbes({"autolab-agstudio1": {"command": [sys.executable, "-c", "import time; time.sleep(5)"],
                                               "timeout": 0.5}})
    watcher = case.make(probes=slow)
    started = time.time()
    at = look(case, watcher, T0 + 100 + 900)
    assert time.time() - started < 30, "every probe returned promptly"
    assert at is not None and at - (T0 + 100 + monitoring.PROBE_AFTER) <= 300
    assert "did not answer within 0.5 s" in asked(case)[0]["content"]
    assert slow.failures >= 1 and watcher.health()["probes"]["failures"] >= 1


def test_the_probe_fault_file_fails_every_probe_without_running_it(tmp_path):
    ran = []
    probes = HealthProbes({"a": {"command": ["x"]}}, faults=tmp_path, runner=lambda *a, **k: ran.append(a))
    (tmp_path / "probe-fail").write_text("")
    report = probes.probe("a", ack=1, channel="c", topic="t", window=120)
    assert report["verdict"] == "unknown" and "fault injected" in report["why"] and ran == []
    assert probes.probe("b", ack=1, channel="c", topic="t", window=120)["why"].startswith("b exposes no")


def test_a_restart_during_diagnosis_keeps_the_first_suspicion_and_asks_once(world):
    case = world("unknown")
    watcher = case.make()
    look(case, watcher, T0 + 100 + monitoring.PROBE_AFTER + 60)
    first = next(iter(watcher.load_health().values()))["first_suspicion"]
    # Observer restarts: a new monitor over the same store.
    watcher = case.make()
    at = look(case, watcher, T0 + 100 + 900)
    assert next(iter(watcher.load_health().values()))["first_suspicion"] == first
    assert at is not None and at - first <= monitoring.ASK_AFTER + 60
    # …and again after the request: nothing is asked twice.
    watcher = case.make()
    for _ in range(3):
        case.clock.now += 60
        watcher.tick()
    assert len(asked(case)) == 1


def test_a_probed_owner_s_silence_is_not_judged(world):
    """`silent` (2700 s, a model judgment) is replaced for a probed owner:
    a `running` harness that posts nothing for an hour is left alone."""
    case = world("running")
    watcher = case.make()
    assert look(case, watcher, T0 + 100 + 3600, step=300) is None
    assert case.judged == []


def test_an_owner_without_the_interface_keeps_the_conversation_rules(world):
    case = world("stopped")
    watcher = case.make(probes=Probes("stopped", owner="somebody-else"))
    assert look(case, watcher, T0 + 100 + 1200) is None, "not probed, and silent's 2700 s not reached"


def test_a_serving_that_ended_asking_nobody_is_checked_early(world):
    """p1's T3 shape: the serving ended with a reply that asks nobody
    anything, on unfinished work, and nothing moves. Checked after
    QUIET_CHECK (not 1800 s and a judgment); the probe finds the run over
    and nothing waiting, which confirms nothing — so it is put to Front."""
    case = world("ended", ended=True)
    watcher = case.make()
    at = look(case, watcher, T0 + 110 + 1200)
    assert at is not None and at - (T0 + 110) <= monitoring.QUIET_CHECK + monitoring.ASK_AFTER + 120, at - T0 - 110
    assert case.judged == []


def test_the_real_probe_command_is_what_the_monitor_calls(tmp_path):
    """End to end through `python -m agag.health`: a record whose process is
    gone and a journal that posted nothing are `stopped`."""
    executions = tmp_path / "executions"
    executions.mkdir()
    (executions / "s1-supercoder-1.json").write_text(json.dumps({
        "schema": "agag.execution.v1", "serving": {"ack": 41}, "harness": "claude_code", "pid": 999999,
        "started_at": time.time() - 100, "deadline_at": time.time() + 1000, "last_event_at": time.time() - 90,
        "tool_results": True, "open_tools": {}, "ended_at": None}))
    probes = HealthProbes({"autolab-agstudio1": {"command": [sys.executable, "-m", "agag.health", "--dir",
                                                             str(executions)], "timeout": 20}})
    report = probes.probe("autolab-agstudio1", ack=41, channel="work-m1", topic="t", window=120)
    assert report["verdict"] == "stopped", report
    assert probes.stats()["runs"] == 1 and probes.stats()["failures"] == 0


def test_unknown_documents_say_why():
    assert unknown("x")["unknowns"] == ["x"]


def test_a_trial_timing_file_shortens_the_bounds_and_its_removal_restores_them(world):
    case = world("unknown")
    watcher = case.make()
    timing = case.where / "local" / monitoring.TIMING_FILE
    timing.parent.mkdir(parents=True, exist_ok=True)
    timing.write_text(json.dumps({"interval": 10, "probe_after": 30, "ask_after": 20, "escalate_after": 60}))
    at = look(case, watcher, T0 + 100 + 300, step=10)
    assert at is not None and at - (T0 + 100) <= 30 + 20 + 20, at - T0 - 100
    assert watcher.interval == 10 and watcher.health()["timing"]["ask_after"] == 20
    timing.unlink()
    watcher.tick()
    assert watcher.interval == 60 and watcher.timing == monitoring.TIMING_DEFAULTS


def test_an_uncertain_serving_that_then_works_is_recovered_by_its_own_work(world):
    """Trial D: the probe could not confirm a live run (its probe failed);
    the same serving then posts its result. That is fresh work, not a new
    serving, and it recovers the incident."""
    case = world("unknown")
    watcher = case.make()
    assert look(case, watcher, T0 + 100 + 900) is not None
    post(case, "work-m1", case.task, f"@**Front**\n\nDone: the flag works.\n\n`ag-post intent=report end={case.ack}`",
         AUTOLAB)
    case.clock.now += 60
    (record,) = [r for r in watcher.tick() if r.get("kind") == "uncertain"]
    assert record["state"] == monitoring.RESCUED


def test_a_serving_of_the_request_s_own_conversation_holds_the_move(world):
    """The ended-asking-nobody check does not suspect the work while Front
    is serving the request's own conversation (a person just answered)."""
    case = world("ended", ended=True)
    watcher = case.make()
    case.clock.now = T0 + 110 + monitoring.QUIET_CHECK + 10
    post(case, "front", case.desk, "Accepted, thanks.", 8, after=0)
    post(case, "front", case.desk, ACK, FRONT, after=1)
    watcher.tick()
    assert case.probes.runs == 0 and not watcher.load_health()
