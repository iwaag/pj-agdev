"""observer p3 step 3: workflow monitoring from workflow and executor evidence.

The fixtures (`tests/fixtures/workflow/`) are observation documents shaped as
`wfe observe` prints them; nothing here reads Zulip history, `#front`, topic
names or serving ids. Zulip and the local model are fakes with the same
interface the monitor uses.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agobserver import wfclassify as wc
from agobserver.wfmonitor import Settings, WorkflowMonitor, digest
from agobserver.wfpost import Poster
from agobserver.wfstore import Store

FIXTURES = Path(__file__).parent / "fixtures" / "workflow"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def ts(text: str) -> float:
    return wc.ts(text)


# ---- classification ------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.glob("*.json")))
def test_fixture_classification(name):
    fx = fixture(name)
    doc = fx["observation"]
    findings, executor = wc.classify(doc, ts(doc["observedAt"]))
    by_uid = {f.uid: f for f in findings}
    for uid, want in fx["expect"].items():
        f = executor if uid == "executor" else by_uid[uid]
        assert f is not None, uid
        assert f.condition == want["condition"], (uid, f.condition, f.fact)
        if want["incident"]:
            assert (f.family, f.episode) == (want["incident"]["family"], want["incident"]["episode"])
        else:
            assert f.key is None or f.condition == "unobservable", (uid, f.family, f.episode)
        assert f.recover == want["request"], uid
        if "affected" in want:
            assert f.affected == want["affected"]


def test_a_standing_conductor_at_rest_is_idle_input_not_a_person_wait_or_a_stall():
    """workflow_editor p18: one conductor run per conversation rests between turns."""
    doc = copy.deepcopy(fixture("normal-wait.json")["observation"])
    run = doc["runs"][0]
    run.update(situation="awaiting-input", hold=None, stop=None, cancelled=None, queue=None)
    run["execution"] = {"state": "idle", "ready": [], "active": [], "failed": [], "blocked": [], "waiting": []}
    run["attempts"] = {**(run.get("attempts") or {}), "open": None}
    run["waiting"] = {"reason": "at rest: the standing conductor of room-a (open); the conversation's next event continues it",
                      "responsible": "conversation:room-a", "since": run.get("updated")}
    run["delegations"] = []
    findings, _ = wc.classify(doc, ts(doc["observedAt"]))
    (f,) = [x for x in findings if x.uid == run["identity"]["uid"]]
    assert f.condition == "idle-input" and f.kind == "idle"
    assert f.condition in wc.QUIET and f.key is None and not f.recover


def test_motivating_interruption_names_the_lost_background_task():
    doc = fixture("interrupted-lost-retry.json")["observation"]
    (f,), _ = wc.classify(doc, ts(doc["observedAt"]))
    assert f.condition == "interrupted" and f.kind == "interrupted"
    assert "1 background task(s) stopped by the harness" in f.fact
    assert f.evidence["log"]["backgroundStopped"] == 1


def test_an_open_call_past_its_declared_timeout_is_uncertain_not_working():
    doc = copy.deepcopy(fixture("normal-wait.json")["observation"])
    run = doc["runs"][1]
    since = ts(run["process"]["log"]["openTool"]["since"])
    (f,) = [x for x in wc.classify(doc, since + 600 + 61)[0] if x.uid == run["identity"]["uid"]]
    assert f.condition == "uncertain" and f.family == "attempt" and f.kind == "tool-overrun" and "past its 600 s" in f.fact
    (g,) = [x for x in wc.classify(doc, since + 600 + 59)[0] if x.uid == run["identity"]["uid"]]
    assert g.condition == "working"


def test_a_remote_workers_attempt_is_judged_by_its_shipped_log_and_its_contact():
    """project_migration p7: the process of an attempt on a remote worker is
    that worker's; the coordinator has its shipped log and its contact."""
    doc = copy.deepcopy(fixture("normal-wait.json")["observation"])
    run = doc["runs"][1]
    run["executor"] = {**(run.get("executor") or {}), "node": "gpupc"}
    run["process"].update({"alive": None, "local": False, "group": None})
    run["process"]["log"]["openTool"] = None
    last = ts(run["process"]["log"]["last"])
    doc["workers"] = [{"id": "studio", "local": True, "state": "available"},
                      {"id": "gpupc", "local": False, "state": "available", "heartbeatAt": doc["observedAt"]}]
    (f,) = [x for x in wc.classify(doc, last + 30)[0] if x.uid == run["identity"]["uid"]]
    assert f.condition == "working" and f.kind == "log", f.fact
    (g,) = [x for x in wc.classify(doc, last + 7200)[0] if x.uid == run["identity"]["uid"]]
    assert g.condition == "uncertain" and g.kind == "silent", "a quiet log on a reporting worker is still a suspicion"
    doc["workers"][1]["state"] = "unavailable"
    (h,), = [[x for x in wc.classify(doc, last + 7200)[0] if x.uid == run["identity"]["uid"]]]
    assert h.condition == "working" and h.kind == "worker-down" and h.key is None, "lost contact is not a lost process"


def test_cpu_progress_between_looks_is_work():
    doc = copy.deepcopy(fixture("intentional-hold.json")["observation"])
    run = doc["runs"][1]
    later = ts(run["process"]["log"]["last"]) + 2000
    a = run["process"]["attempt"]
    assert [f for f in wc.classify(doc, later, prev_cpu={a: 41.2})[0] if f.uid == run["identity"]["uid"]][0].condition == "uncertain"
    assert [f for f in wc.classify(doc, later, prev_cpu={a: 30.0})[0] if f.uid == run["identity"]["uid"]][0].condition == "working"


def test_a_recovery_run_is_never_sent_to_recovery():
    doc = copy.deepcopy(fixture("interrupted-lost-retry.json")["observation"])
    doc["runs"][0]["identity"].update(project="agops", workflow="recover")
    (f,), _ = wc.classify(doc, ts(doc["observedAt"]), recovery_workflows=("agops/recover",))
    assert f.condition == "interrupted" and f.recover is False


def test_a_recorded_failure_and_an_overdue_external_wait():
    doc = copy.deepcopy(fixture("normal-wait.json")["observation"])
    run = doc["runs"][0]
    run["execution"] = {"state": "stopped", "ready": [], "active": [], "failed": ["survey"], "blocked": [], "waiting": []}
    run["waiting"] = {"reason": "execution stopped", "responsible": "none", "since": None}
    run["inputs"]["questions"] = []
    f = wc.classify(doc, ts(doc["observedAt"]))[0][0]
    assert f.condition == "awaiting-person" and f.kind == "failed" and f.key is None
    run["execution"] = {"state": "in-progress", "ready": [], "active": [], "failed": [], "blocked": [],
                        "waiting": [{"node": "render", "on": {"external": "gpu:job/1"}, "holder": "gpu", "since": "2026-10-14T03:00:00.000Z", "deadline": "2026-10-14T04:00:00.000Z"}]}
    run["waiting"] = {"reason": "external: gpu:job/1", "responsible": "external:gpu:job/1", "since": "2026-10-14T03:00:00.000Z"}
    assert wc.classify(doc, ts("2026-10-14T03:59:00Z"))[0][0].condition == "awaiting-external"
    late = wc.classify(doc, ts("2026-10-14T04:01:00Z"))[0][0]
    assert late.condition == "uncertain" and late.family == "wait" and late.recover is False


# ---- the monitor ------------------------------------------------------------------------------

class FakeZulip:
    def __init__(self):
        self.sent: list[dict] = []
        self.fail_next: Exception | None = None
        self.lose_answer = False
        self.next_id = 1000

    down = False

    def _post(self, **m) -> int:
        if self.down:
            raise TimeoutError("Zulip is down")
        if self.fail_next is not None:
            e, self.fail_next = self.fail_next, None
            raise e
        self.next_id += 1
        self.sent.append({"id": self.next_id, **m})
        if self.lose_answer:
            self.lose_answer = False
            raise TimeoutError("the answer was lost")
        return self.next_id

    def send_to_channel(self, channel, topic, content):
        return self._post(kind="channel", channel=channel, topic=topic, content=content)

    def send_dm(self, user_ids, content):
        return self._post(kind="dm", to=user_ids, content=content)

    def topic_history(self, channel, topic, num_before=50):
        if self.down:
            raise TimeoutError("Zulip is down")
        return [m for m in self.sent if m.get("channel") == channel and m.get("topic") == topic]

    def dm_history(self, user_ids, num_before=50):
        return [m for m in self.sent if m["kind"] == "dm"]

    def realm_owners(self):
        return [8]


class FakeJudge:
    def __init__(self, verdict="waiting"):
        self.verdict = verdict
        self.asked: list[tuple] = []
        self.queue: list = []
        self.running = None

    def submit(self, job_id, incident, fact, evidence, seconds):
        self.asked.append((job_id, incident, digest(evidence)))
        self.queue.append((job_id, {"verdict": self.verdict, "evidence": f"fake {self.verdict}"}))

    def results(self):
        out, self.queue = self.queue, []
        return out


class Clock:
    def __init__(self, t: float):
        self.t = t

    def __call__(self):
        return self.t


def make(tmp_path, docs, clock, judge=None, store=None, zulip=None):
    store = store or Store(tmp_path / "observer.sqlite")
    zulip = zulip or FakeZulip()
    state = {"docs": docs}

    def observe(runs=None, workspace=None):
        doc = state["docs"]() if callable(state["docs"]) else state["docs"]
        if doc is None:
            return None, "wfe observe exited 1: registry unreadable"
        doc = copy.deepcopy(doc)
        if runs:
            doc["runs"] = [r for r in doc["runs"] if f"{r['identity']['workspace']}:{r['identity']['workflow']}/{r['identity']['run']}" in runs]
        return doc, None

    m = WorkflowMonitor(Settings(wfe=["wfe"]), store, Poster(store, lambda: zulip, log=lambda _m: None), observe=observe, judge=judge,
                        health_path=tmp_path / "workflow-health.json", clock=clock, log=lambda _m: None)
    return m, store, zulip, state


def test_the_motivating_interruption_opens_one_incident_across_restarts_and_rewordings(tmp_path):
    doc = fixture("interrupted-lost-retry.json")["observation"]
    clock = Clock(ts(doc["observedAt"]))
    m, store, zulip, state = make(tmp_path, doc, clock)
    m.look()
    (inc,) = store.open_incidents()
    assert (inc["family"], inc["episode"], inc["condition"]) == ("attempt", "amv6sl63n-accd7c", "interrupted")
    # No recovery path in this monitor: the owners are told once, the incident topic records it.
    dms = [s for s in zulip.sent if s["kind"] == "dm"]
    assert len(dms) == 1 and inc["id"] in dms[0]["content"] and "no recovery recipient" in dms[0]["content"]
    assert {s["topic"] for s in zulip.sent if s["kind"] == "channel"} == {f"incident-{inc['id']}"}
    # A restart on the same store, and a different wording of the same episode.
    clock.t += 120
    reworded = copy.deepcopy(doc)
    reworded["runs"][0]["hold"]["reason"] = "the attempt ended with survey still running (reworded)"
    m2, _, _, _ = make(tmp_path, reworded, clock, store=store, zulip=zulip)
    m2.look()
    (again,) = store.open_incidents()
    assert again["id"] == inc["id"] and again["first_suspected"] == inc["first_suspected"]
    assert len([s for s in zulip.sent if s["kind"] == "dm"]) == 1, "no second message for the same episode"
    assert store.db.execute("SELECT count(*) FROM events WHERE kind = 'redescribed'").fetchone()[0] == 1
    health = json.loads((tmp_path / "workflow-health.json").read_text())
    assert health["schema"] == "agobserver.workflow-health.v1" and health["incidents"]["open"] == 1 and health["source"]["state"] == "live"


def test_intentional_hold_and_normal_waits_open_nothing(tmp_path):
    for name in ("intentional-hold.json", "normal-wait.json"):
        doc = fixture(name)["observation"]
        clock = Clock(ts(doc["observedAt"]))
        m, store, zulip, _ = make(tmp_path / name, doc, clock)
        for _ in range(2):  # the long command stays inside its declared timeout (540 s, 600 s of 600 + 60)
            m.look()
            clock.t += 60
        assert store.open_incidents() == [] and zulip.sent == [], name


def test_unowned_work_waits_its_grace_and_keeps_its_first_sight_across_a_restart(tmp_path):
    doc = copy.deepcopy(fixture("normal-wait.json")["observation"])
    doc["runs"] = [doc["runs"][2]]  # the answered question: its queue entry is lost
    doc["executor"]["slot"], doc["executor"]["queued"] = None, 0
    run = doc["runs"][0]
    run["queue"] = {"job": None, "position": None, "ahead": []}
    run["waiting"] = {"reason": "answer to q2 recorded, not yet taken up, no job queued", "responsible": "executor", "since": doc["observedAt"]}
    clock = Clock(ts(doc["observedAt"]))
    m, store, zulip, _ = make(tmp_path, doc, clock)
    m.look()
    assert store.open_incidents() == []
    first = store.db.execute("SELECT first_seen FROM suspects").fetchone()[0]
    clock.t += 100
    m2, _, _, _ = make(tmp_path, doc, clock, store=store, zulip=zulip)  # restart
    m2.look()
    assert store.open_incidents() == []
    clock.t += 90
    m2.look()
    (inc,) = store.open_incidents()
    assert inc["family"] == "continuation" and inc["first_suspected"] == first
    # The executor's reconcile queues it again: the run waits in the queue, the incident closes.
    fixed = fixture("normal-wait.json")["observation"]
    fixed["runs"] = [fixed["runs"][2]]
    clock.t += 60
    m3, _, _, _ = make(tmp_path, fixed, clock, store=store, zulip=zulip)
    m3.look()
    assert store.open_incidents() == []
    closed = store.incident(inc["id"])
    assert closed["outcome"] == "resumed", "it had been told to the owners, so it is resumed, not a false alarm"


def silent_run_doc():
    doc = copy.deepcopy(fixture("intentional-hold.json")["observation"])
    doc["runs"] = [doc["runs"][1]]
    return doc


def test_an_uncertain_attempt_is_judged_and_a_legitimate_wait_postpones_without_suppressing(tmp_path):
    doc = silent_run_doc()
    run = doc["runs"][0]
    t0 = ts(run["process"]["log"]["last"]) + 1000  # the log is 1000 s quiet
    clock = Clock(t0)
    judge = FakeJudge("waiting")
    m, store, zulip, _ = make(tmp_path, doc, clock, judge=judge)
    m.look()
    (inc,) = store.open_incidents()
    first = inc["first_suspected"]
    assert inc["condition"] == "uncertain" and judge.asked == [], "judged only after judge_after"
    for _ in range(5):  # 300 s later: judged
        clock.t += 60
        m.look()
    assert len(judge.asked) == 1
    clock.t += 700  # past escalate_uncertain, but judged a legitimate wait
    m.look()
    inc = store.incident(inc["id"])
    assert inc["first_suspected"] == first, "repeated uncertainty never resets the first suspicion"
    assert inc["escalated"] is None and inc["next_review"] is not None
    assert [s for s in zulip.sent if s["kind"] == "dm"] == []
    # The review comes due: a new judgment on the same evidence, not a permanent suppression.
    clock.t = float(inc["next_review"]) + 1
    m.look()
    assert len(judge.asked) == 2
    # The attempt writes again: the incident closes as a false alarm.
    moving = copy.deepcopy(doc)
    moving["runs"][0]["process"]["log"]["last"] = time_iso(clock.t - 5)
    m.observe = lambda runs=None, workspace=None: (copy.deepcopy(moving), None)
    m.look()
    assert store.incident(inc["id"])["outcome"] == "false-alarm"


def time_iso(t: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def test_a_judged_stall_is_told_to_the_owners_at_its_bound_and_a_verdict_on_moved_evidence_is_discarded(tmp_path):
    doc = silent_run_doc()
    t0 = ts(doc["runs"][0]["process"]["log"]["last"]) + 1000
    clock = Clock(t0)

    class SlowJudge(FakeJudge):
        def submit(self, job_id, incident, fact, evidence, seconds):
            self.asked.append((job_id, incident, digest(evidence)))
            self.held = (job_id, {"verdict": "waiting", "evidence": "slow"})

    judge = SlowJudge()
    m, store, zulip, _ = make(tmp_path, doc, clock, judge=judge)
    m.look()
    clock.t += 300
    m.look()
    assert len(judge.asked) == 1
    # The evidence moves (CPU sample changes the digest) before the verdict arrives.
    moved = copy.deepcopy(doc)
    moved["runs"][0]["process"]["group"]["cpuSeconds"] = 43.0  # +1.8 s: work
    m.observe = lambda runs=None, workspace=None: (copy.deepcopy(moved), None)
    clock.t += 60
    judge.queue.append(judge.held)
    m.look()
    row = store.db.execute("SELECT * FROM judgments").fetchone()
    assert row["invalidated"] == 1, "a verdict on evidence that has since moved is discarded"
    # Silent again with a stall verdict: told to the owners once the bound is reached.
    judge2 = FakeJudge("stalled")
    m.judge = judge2
    m.observe = lambda runs=None, workspace=None: (copy.deepcopy(moved), None)
    for _ in range(20):
        clock.t += 60
        m.look()
    dms = [s for s in zulip.sent if s["kind"] == "dm"]
    assert len(dms) == 1 and "stalled" in dms[0]["content"]


def test_executor_outage_is_one_incident_naming_the_affected_runs(tmp_path):
    doc = copy.deepcopy(fixture("unavailable-source.json")["observation"])
    # Add two more runs the outage affects: a queued request and an attempt whose process is gone.
    queued = copy.deepcopy(fixture("normal-wait.json")["observation"]["runs"][2])
    lost = copy.deepcopy(fixture("intentional-hold.json")["observation"]["runs"][1])
    lost["identity"]["uid"] = "rts-vs-bot/improve-game/run-009#ffff"
    lost["identity"]["run"] = "run-009"
    lost["process"]["alive"] = False
    doc["runs"] += [queued, lost]
    clock = Clock(ts(doc["observedAt"]))
    m, store, zulip, _ = make(tmp_path, doc, clock)
    for _ in range(4):
        m.look()
        clock.t += 60
    incidents = store.open_incidents()
    assert [i["family"] for i in incidents] == ["executor"], "one infrastructure incident, no per-run repairs"
    affected = json.loads(incidents[0]["affected"])
    assert queued["identity"]["uid"] in affected and lost["identity"]["uid"] in affected
    assert len([s for s in zulip.sent if s["kind"] == "dm"]) == 1
    # The executor reports again.
    healthy = copy.deepcopy(doc)
    healthy["executor"].update(state="available", ageSeconds=2.0, heartbeatAt=time_iso(clock.t))
    healthy["runs"] = [queued]
    m.observe = lambda runs=None, workspace=None: (copy.deepcopy(healthy), None)
    m.look()
    assert store.incident(incidents[0]["id"])["outcome"] == "resumed"


def test_a_failed_observation_concludes_nothing_and_an_unobserved_run_stays_open(tmp_path):
    doc = fixture("interrupted-lost-retry.json")["observation"]
    clock = Clock(ts(doc["observedAt"]))
    m, store, zulip, state = make(tmp_path, doc, clock)
    m.look()
    (inc,) = store.open_incidents()
    state["docs"] = None
    clock.t += 60
    m.look()
    health = json.loads((tmp_path / "workflow-health.json").read_text())
    assert health["source"]["state"] == "failed" and "registry unreadable" in health["source"]["reason"]
    assert store.incident(inc["id"])["state"] != "closed"
    empty = copy.deepcopy(doc)
    empty["runs"] = []
    state["docs"] = empty
    clock.t += 60
    m.look()
    assert store.incident(inc["id"])["state"] != "closed", "absence is never a rescue"


def test_a_person_resuming_or_holding_closes_the_incident_with_that_outcome(tmp_path):
    doc = fixture("interrupted-lost-retry.json")["observation"]
    clock = Clock(ts(doc["observedAt"]))
    m, store, _, state = make(tmp_path, doc, clock)
    m.look()
    (inc,) = store.open_incidents()
    held = copy.deepcopy(doc)
    held["runs"][0]["hold"] = {"kind": "stopped", "since": doc["observedAt"], "by": "iwaag", "human": True, "reason": "stop it", "because": None}
    held["runs"][0]["situation"] = "stopped"
    state["docs"] = held
    clock.t += 60
    m.look()
    assert store.incident(inc["id"])["outcome"] == "held"


def test_a_post_whose_answer_was_lost_is_found_not_repeated(tmp_path):
    store = Store(tmp_path / "s.sqlite")
    zulip = FakeZulip()
    poster = Poster(store, lambda: zulip, log=lambda _m: None)
    store.enqueue(kind="channel", channel="c", topic="t", text="hello", marker="obs x 1", now=1.0)
    zulip.lose_answer = True
    assert poster.flush(2.0) == {"uncertain": 1}
    assert len(zulip.sent) == 1
    assert poster.flush(100.0) == {"sent": 1}
    assert len(zulip.sent) == 1, "found by its marker, not posted again"
    # A post that never left: looked for, absent, sent once.
    store.enqueue(kind="dm", text="hi", marker="obs x 2", now=200.0)
    zulip.fail_next = TimeoutError("connection reset")
    poster.flush(200.0)
    assert len(zulip.sent) == 1
    poster.flush(300.0)
    assert len(zulip.sent) == 2 and "obs x 2" in zulip.sent[-1]["content"]


# ---- sessions are not attempts (observer p3 step 5) -------------------------------------------

def interrupted_doc(attempt: str, session: str, at: str) -> dict:
    doc = copy.deepcopy(fixture("interrupted-lost-retry.json")["observation"])
    r = doc["runs"][0]
    r["attempts"]["last"]["id"] = attempt
    r["hold"]["since"] = at
    r["process"].update(attempt=attempt)
    r["process"]["log"]["session"] = session
    doc["observedAt"] = at
    return doc


def test_a_fresh_session_and_two_intervals_sharing_one_session_are_two_episodes(tmp_path):
    clock = Clock(ts("2026-10-14T05:00:00Z"))
    first = interrupted_doc("a-first", "session-A", "2026-10-14T05:00:00.000Z")
    m, store, zulip, state = make(tmp_path, first, clock)
    m.look()
    (i1,) = store.open_incidents()
    assert json.loads(i1["evidence"])["log"]["session"] == "session-A"
    # A later interval of the same retained session is interrupted too: its own
    # episode (attempt), its own first suspicion — a session id does not merge them.
    clock.t += 3600
    second = interrupted_doc("a-second", "session-A", "2026-10-14T06:00:00.000Z")
    state["docs"] = second
    m.look()
    i2 = store.incident(wc.incident_id(i1["uid"], "attempt", "a-second"))
    assert i2 is not None and i2["id"] != i1["id"]
    assert i2["first_suspected"] > i1["first_suspected"]
    assert store.incident(i1["id"])["state"] == "closed", "the first episode ended when the run moved past it"
    # A fresh session in a third interval: again an episode of its attempt.
    clock.t += 3600
    third = interrupted_doc("a-third", "session-B", "2026-10-14T07:00:00.000Z")
    state["docs"] = third
    m.look()
    assert store.incident(wc.incident_id(i1["uid"], "attempt", "a-third")) is not None


def test_a_process_restart_within_an_attempt_neither_opens_an_incident_nor_resets_its_age(tmp_path):
    doc = silent_run_doc()
    t0 = ts(doc["runs"][0]["process"]["log"]["last"]) + 1000
    clock = Clock(t0)
    m, store, _, state = make(tmp_path, doc, clock)
    m.look()
    (inc,) = store.open_incidents()
    restarted = copy.deepcopy(doc)
    restarted["runs"][0]["process"]["pid"] = 99999  # the same attempt, another process (a future session resume)
    state["docs"] = restarted
    clock.t += 60
    m.look()
    (same,) = store.open_incidents()
    assert same["id"] == inc["id"] and same["first_suspected"] == inc["first_suspected"]


def test_legacy_state_is_archived_with_an_inventory_and_nothing_replayed(tmp_path):
    from agobserver.retire_legacy import retire

    local = tmp_path / "local"
    (local / "incidents").mkdir(parents=True)
    (local / "watches").mkdir()
    (local / "incidents" / "abc.json").write_text(json.dumps({"state": "reported", "kind": "silent", "topic": "incident-silent-1"}))
    (local / "incidents" / "tracked.json").write_text("{}")
    (local / "watches" / "w1.json").write_text(json.dumps({"state": "met", "delivered": {"id": 5}}))
    (local / "monitor-health.json").write_text("{}")
    dry = retire(local, dry_run=True, now=1_800_000_000)
    assert (local / "incidents").exists() and dry["replayed"] is False
    rec = retire(local, now=1_800_000_000)
    archive = local / rec["archive"]
    assert not (local / "incidents").exists() and (archive / "incidents" / "abc.json").exists()
    assert json.loads((archive / "retirement.json").read_text())["inventory"]["incidents"][0]["state"] == "reported"
    assert rec["inventory"]["open"] == {"incidents": [], "watches": []}


def test_each_successful_look_writes_the_liveness_status_nodeutils_reads(tmp_path, monkeypatch):
    status = tmp_path / "agag-status.json"
    monkeypatch.setenv("AGAG_STATUS_PATH", str(status))
    doc = fixture("normal-wait.json")["observation"]
    clock = Clock(ts(doc["observedAt"]))
    m, _, _, state = make(tmp_path, doc, clock)
    m.look()
    s1 = json.loads(status.read_text())
    assert s1["schema"] == "agag.status.v1" and s1["last_poll_ok"].startswith("2026-10-14T04:40")
    state["docs"] = None  # the observation fails: liveness is not renewed
    clock.t += 60
    m.look()
    assert json.loads(status.read_text())["last_poll_ok"] == s1["last_poll_ok"]


def test_an_unreadable_copy_that_is_readable_again_closes_its_observation_incident(tmp_path):
    fx = fixture("unavailable-source.json")["observation"]
    doc = copy.deepcopy(fx)
    doc["runs"] = [doc["runs"][0]]
    doc["runs"][0]["identity"].update(uid="", creation="", project="")  # as WFE reports a record it cannot read
    doc["executor"].update(state="available", ageSeconds=1.0)
    clock = Clock(ts(doc["observedAt"]))
    m, store, _, state = make(tmp_path, doc, clock)
    m.look()
    clock.t += 1900
    m.look()
    (inc,) = store.open_incidents()
    assert inc["family"] == "observation" and ":" in inc["uid"]
    back = copy.deepcopy(fixture("intentional-hold.json")["observation"])
    run = back["runs"][0]
    run["identity"].update(workspace="rts-vs-bot", workflow="improve-game", run="run-007", project="rts-vs-bot", uid="rts-vs-bot/improve-game/run-007#77")
    back["runs"] = [run]
    state["docs"] = back
    clock.t += 60
    m.look()
    assert store.incident(inc["id"])["outcome"] == "resumed"


# ---- recorded sessions (agent_session p1) --------------------------------------------------

def test_recorded_session_is_evidence_and_reaches_the_recovery_request(tmp_path):
    from agobserver import wfrecover
    clock = Clock(ts("2026-10-14T05:00:00Z"))
    doc = interrupted_doc("a-second", "session-A", "2026-10-14T05:00:00.000Z")
    r = doc["runs"][0]
    r["session"] = {"policy": "run", "current": {"id": "session-A", "began": "2026-10-14T04:00:00.000Z", "attempts": ["a-first", "a-second"], "attached": "session-A", "mismatch": False}, "count": 1, "ended": []}
    r["process"]["session"] = {"id": "session-A", "resumed": True}
    m, store, zulip, state = make(tmp_path, doc, clock)
    m.look()
    (inc,) = store.open_incidents()
    ev = json.loads(inc["evidence"])
    assert ev["session"]["policy"] == "run" and ev["process"]["session"] == {"id": "session-A", "resumed": True}
    assert inc["id"] == wc.incident_id(inc["uid"], "attempt", "a-second"), "the incident is the attempt's, not the session's"
    text = wfrecover.request_text(inc, wc.Finding(**{**{k: None for k in wc.Finding.__dataclass_fields__}, "uid": inc["uid"], "family": "attempt", "episode": "a-second", "condition": "interrupted", "fact": "x", "evidence": ev}), 1)
    assert "session policy `run`" in text and "(resumed)" in text
    assert "--retire" in text, "the recovery agent learns how to start the next attempt in a new session"
    # A mismatched session (agent_session p1 ex1) is named as unverified, with both ids.
    ev["session"]["current"] = {**ev["session"]["current"], "attached": "session-B", "mismatch": True}
    text = wfrecover.request_text(inc, wc.Finding(**{**{k: None for k in wc.Finding.__dataclass_fields__}, "uid": inc["uid"], "family": "attempt", "episode": "a-second", "condition": "interrupted", "fact": "x", "evidence": ev}), 1)
    assert "UNVERIFIED" in text and "`session-B`" in text and "Continuing is refused until it is retired" in text and "--retire" in text
    # Fresh runs say their policy and no retirement advice.
    ev["session"]["policy"] = "fresh"
    text = wfrecover.request_text(inc, wc.Finding(**{**{k: None for k in wc.Finding.__dataclass_fields__}, "uid": inc["uid"], "family": "attempt", "episode": "a-second", "condition": "interrupted", "fact": "x", "evidence": ev}), 1)
    assert "session policy `fresh`" in text and "--retire" not in text


# ---- project_migration p8 ex1: waits, causes, repeats -----------------------------------------

def _parent_child(doc):
    parent = next(r for r in doc["runs"] if r["identity"]["workflow"] == "use")
    child = next(r for r in doc["runs"] if r["identity"]["workflow"] == "make")
    return parent, child


def test_a_healthy_delegation_wait_stays_quiet_however_long_it_lasts():
    doc = copy.deepcopy(fixture("delegation-healthy-wait.json")["observation"])
    parent, child = _parent_child(doc)
    child["queue"]["job"] = None
    child["attempts"]["open"] = {"id": "achild-1", "began": doc["observedAt"], "reason": "start", "backend": None, "agent": "kid-agent"}
    child["process"] = {"attempt": "achild-1", "state": "running", "alive": True, "local": True, "pid": 1, "log": {"last": doc["observedAt"]}, "group": {"cpuSeconds": 1.0}}
    eight_hours = ts(doc["observedAt"]) + 8 * 3600
    by = {f.uid: f for f in wc.classify(doc, eight_hours)[0]}
    p = by[parent["identity"]["uid"]]
    assert p.condition == "awaiting-delegation" and p.key is None, p.fact
    # The child's own silence is the child's suspicion, never the parent's.
    assert by[child["identity"]["uid"]].condition == "uncertain"


def test_a_lost_child_process_is_the_childs_incident_and_the_parents_wait_stays_quiet():
    doc = copy.deepcopy(fixture("delegation-healthy-wait.json")["observation"])
    parent, child = _parent_child(doc)
    child["queue"]["job"] = None
    child["attempts"]["open"] = {"id": "achild-1", "began": doc["observedAt"], "reason": "start", "backend": None, "agent": "kid-agent"}
    child["process"] = {"attempt": "achild-1", "state": "running", "alive": False, "local": True, "pid": 1, "log": None}
    by = {f.uid: f for f in wc.classify(doc, ts(doc["observedAt"]))[0]}
    c = by[child["identity"]["uid"]]
    assert c.condition == "lost-attempt" and c.family == "attempt" and c.recover
    assert by[parent["identity"]["uid"]].condition == "awaiting-delegation"


def test_an_unreadable_child_is_said_not_concluded():
    doc = copy.deepcopy(fixture("delegation-healthy-wait.json")["observation"])
    parent, _ = _parent_child(doc)
    parent["delegations"][0]["childUid"] = parent["delegations"][0]["child"]["uid"]
    parent["delegations"][0]["child"] = None
    parent["delegations"][0]["problem"] = "the child kid make/run-001 cannot be read here"
    by = {f.uid: f for f in wc.classify(doc, ts(doc["observedAt"]))[0]}
    p = by[parent["identity"]["uid"]]
    assert p.condition == "unobservable" and p.kind == "child-unreadable" and not p.recover
    assert "cannot be read here" in p.fact


def _missed(doc, ends=None):
    parent, child = _parent_child(doc)
    cause = {"code": "missed-event", "events": [{"delegation": "d1", "n": 1, "type": "completed"}]}
    parent["hold"] = {"kind": "interrupted", "since": doc["observedAt"], "by": "autolab", "reason": "the executor exited without taking up delegation event d1 completed #1",
                      "because": None, "human": False, "cause": cause}
    parent["attempts"]["last"] = {"id": "apar-3", "outcome": "interrupted", "ended": doc["observedAt"], "detail": ""}
    parent["attempts"]["ends"] = ends or [{"attempt": "apar-3", "seq": 9, "at": doc["observedAt"], "outcome": "interrupted", "held": "interrupted", "cause": cause, "recovered": False}]
    parent["delegations"][0]["pending"] = [{"n": 1, "type": "completed", "at": doc["observedAt"]}]
    parent["delegations"][0]["state"] = "attention"
    return parent, child, cause


def test_an_interrupted_parent_names_its_cause_and_children_and_the_recovery_request_carries_them():
    from agobserver.wfrecover import request_text
    doc = copy.deepcopy(fixture("delegation-healthy-wait.json")["observation"])
    parent, child, _ = _missed(doc)
    by = {f.uid: f for f in wc.classify(doc, ts(doc["observedAt"]))[0]}
    f = by[parent["identity"]["uid"]]
    assert f.condition == "interrupted" and f.recover and f.episode == "apar-3"
    assert f.fact.startswith("held interrupted after attempt apar-3: d1 completed #1 not taken up")
    assert child["identity"]["uid"] in f.affected
    inc = {"id": f.key, "workspace": f.workspace, "ref": f.ref, "uid": f.uid, "family": f.family, "first_suspected": ts(doc["observedAt"])}
    text = request_text(inc, f, 1)
    assert "why it is held, in short: d1 completed #1 not taken up" in text
    assert f"child `{child['identity']['uid']}`" in text and "not taken up: completed #1" in text
    assert "never dispatch a replacement child" in text


def test_the_same_interruption_after_two_recoveries_goes_to_the_owners_not_a_third_recovery():
    doc = copy.deepcopy(fixture("delegation-healthy-wait.json")["observation"])
    cause = {"code": "left-running", "nodes": ["talk"]}
    ends = [{"attempt": f"apar-{i}", "seq": i * 5, "at": doc["observedAt"], "outcome": "interrupted", "held": "interrupted", "cause": cause, "recovered": i < 3} for i in (1, 2, 3)]
    parent, _, _ = _missed(doc, ends)
    parent["hold"]["cause"] = cause
    parent["hold"]["reason"] = "the executor exited with talk recorded as running"
    f = {x.uid: x for x in wc.classify(doc, ts(doc["observedAt"]))[0]}[parent["identity"]["uid"]]
    assert f.condition == "interrupted" and f.kind == "repeated" and not f.recover
    assert "talk left running at exit" in f.fact and "after 2 recoveries in a row" in f.fact
    # Once, with another cause in between, it is recovered as usual.
    ends[1]["cause"] = {"code": "process", "detail": "process ended with exit code 1"}
    g = {x.uid: x for x in wc.classify(doc, ts(doc["observedAt"]))[0]}[parent["identity"]["uid"]]
    assert g.kind == "interrupted" and g.recover
