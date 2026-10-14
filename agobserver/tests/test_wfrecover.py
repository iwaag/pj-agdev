"""observer p3 step 4: the recovery path, from Observer's side.

The documents are what `wfe observe` reports as the story unfolds: the
interrupted run, the recovery run WFE's intake made from Observer's post,
the target's `run.recover`, the continued attempt's report. Zulip is a fake
with the client's interface.
"""

from __future__ import annotations

import copy

from agobserver import wfclassify as wc
from agobserver.wfmonitor import Settings, WorkflowMonitor
from agobserver.wfpost import Poster
from agobserver.wfrecover import Recoverer
from agobserver.wfstore import Store

from test_wfmonitor import Clock, FakeZulip, fixture, time_iso, ts

CHANNEL = "wf-agops.recover"


def recovery_run(message: int, uid_tail="aaaa", situation="executing", execution="in-progress", hold=None) -> dict:
    run = copy.deepcopy(fixture("intentional-hold.json")["observation"]["runs"][1])
    run["identity"].update(project="agops", workspace="agops", workflow="recover", run="run-001", uid=f"agops/recover/run-001#{uid_tail}")
    run["input"] = {"kind": "request", "requester": "Observer", "source": {"kind": "zulip", "message": message, "topic": "request-x"}}
    run["situation"] = situation
    run["execution"]["state"] = execution
    run["hold"] = hold
    if execution == "completed":
        run["attempts"]["open"] = None
        run["process"]["state"], run["process"]["alive"] = "ended", False
    return run


def make(tmp_path, clock, cfg=None, store=None, zulip=None):
    store = store or Store(tmp_path / "observer.sqlite")
    zulip = zulip or FakeZulip()
    state = {"doc": None}

    def observe(runs=None, workspace=None):
        doc = copy.deepcopy(state["doc"])
        if runs:
            doc["runs"] = [r for r in doc["runs"] if f"{r['identity']['workspace']}:{r['identity']['workflow']}/{r['identity']['run']}" in runs]
        return doc, None

    settings = Settings(wfe=["wfe"], recovery={"enabled": True, "workflow": "agops/recover", "channel": CHANNEL, **(cfg or {})})
    m = WorkflowMonitor(settings, store, Poster(store, lambda: zulip, log=lambda _m: None), observe=observe,
                        recoverer=Recoverer(settings.recovery, log=lambda _m: None), clock=clock, log=lambda _m: None)
    return m, store, zulip, state


def requests(zulip):
    return [s for s in zulip.sent if s.get("channel") == CHANNEL]


def target_doc():
    return copy.deepcopy(fixture("interrupted-lost-retry.json")["observation"])


def recovered(doc, iid, seq=12, attempt="amv6sl63n-accd7c", job=True):
    d = copy.deepcopy(doc)
    r = d["runs"][0]
    r["hold"] = None
    r["situation"] = "idle"
    r["seq"] = seq
    r["recoveries"] = [{"seq": seq, "at": d["observedAt"], "by": "recovery-agent", "incident": iid, "attempt": attempt,
                        "agent": {"workspace": "agops", "workflow": "recover", "run": "run-001", "attempt": "arec-1"}}]
    r["waiting"] = {"reason": "resume queued", "responsible": "executor", "since": d["observedAt"]}
    if job:
        r["queue"] = {"job": {"id": 90, "kind": "resume", "state": "queued", "created": d["observedAt"], "reason": f"recover: incident {iid}", "receipt": "x"}, "position": 1, "ahead": []}
    return d


def test_interrupted_run_is_requested_acknowledged_performed_and_verified_restored(tmp_path):
    doc = target_doc()
    clock = Clock(ts(doc["observedAt"]))
    m, store, zulip, state = make(tmp_path, clock)
    state["doc"] = doc
    m.look()
    (inc,) = store.open_incidents()
    iid = inc["id"]
    (req,) = requests(zulip)
    assert req["topic"] == f"request-{iid}"
    assert f"wfe run recover study/run-001 --workspace jevlab --incident {iid} --attempt amv6sl63n-accd7c" in req["content"]
    assert "background tasks stopped with it: 1" in req["content"]
    assert f"obs {iid} recover 1" in req["content"], "the marker that makes a repeat findable"
    assert [s for s in zulip.sent if s["kind"] == "dm"] == [], "the recovery path, not the owners"
    # Observer restarts before anything happens: still one assignment, one post.
    clock.t += 60
    m2, _, _, state2 = make(tmp_path, clock, store=store, zulip=zulip)
    state2["doc"] = doc
    m2.look()
    assert len(requests(zulip)) == 1 and len(store.assignments(iid)) == 1
    # WFE's intake made the recovery run from that post: acknowledged.
    with_run = copy.deepcopy(doc)
    with_run["runs"].append(recovery_run(req["id"]))
    state2["doc"] = with_run
    clock.t += 60
    m2.look()
    assert store.assignments(iid)[0]["acknowledged_by"] == "agops/recover/run-001#aaaa"
    assert store.incident(iid)["state"] == "recovering"
    # The recovery agent continued it: the hold is lifted and the resumption queued. Not yet restored.
    state2["doc"] = recovered(with_run, iid)
    clock.t += 60
    m2.look()
    inc = store.incident(iid)
    assert inc["state"] == "verifying" and inc["outcome"] is None
    a = store.assignments(iid)[0]
    assert a["performed_seq"] == 12 and '"by": "recovery-agent"' in a["actor"]
    # A new attempt starts — a new PID is not restoration.
    working = recovered(with_run, iid, job=False)
    r = working["runs"][0]
    r["situation"] = "executing"
    r["attempts"]["open"] = {"id": "amv7new-000001", "began": time_iso(clock.t), "reason": "resume", "backend": "x", "agent": "jevlab-agent"}
    r["process"].update(attempt="amv7new-000001", state="running", alive=True, ended=None, began=time_iso(clock.t))
    r["process"]["log"].update(last=time_iso(clock.t), ended=None, backgroundStopped=0)
    state2["doc"] = working
    clock.t += 60
    m2.look()
    assert store.incident(iid)["outcome"] is None
    # Its agent reports work after the recovery: restored.
    r["progress"] = {"seq": 15, "at": time_iso(clock.t), "op": "node.progress", "by": "jevlab-agent", "attempt": "amv7new-000001"}
    r["seq"] = 15
    clock.t += 60
    m2.look()
    inc = store.incident(iid)
    assert inc["outcome"] == "restored" and "node.progress" in inc["outcome_evidence"]
    assert store.assignments(iid)[0]["outcome"] == "restored"
    assert len(requests(zulip)) == 1, "one incident, one recovery request"


def test_a_lost_post_answer_is_found_and_a_zulip_outage_never_doubles_the_request(tmp_path):
    doc = target_doc()
    clock = Clock(ts(doc["observedAt"]))
    zulip = FakeZulip()
    zulip.down = True
    m, store, _, state = make(tmp_path, clock, zulip=zulip)
    state["doc"] = doc
    m.look()
    (inc,) = store.open_incidents()
    assert requests(zulip) == []
    # Hours pass while Zulip refuses to answer: the post stays owed; no second assignment.
    for _ in range(40):
        clock.t += 120
        m.look()
    assert len(store.assignments(inc["id"])) == 1
    health = m.health(clock.t)
    assert health["outbox"]["counts"].get("uncertain", 0) >= 1, "the failing delivery is visible"
    # Back: the post goes once; its answer is lost; it is found by its marker, not sent again.
    zulip.down = False
    zulip.lose_answer = True
    clock.t += 1000
    m.look()
    clock.t += 1000
    m.look()
    assert len(requests(zulip)) == 1
    assert store.outbox_row(store.assignments(inc["id"])[0]["outbox"])["state"] == "sent"


def test_unacknowledged_requests_are_bounded_then_told_to_the_owners(tmp_path):
    doc = target_doc()
    clock = Clock(ts(doc["observedAt"]))
    m, store, zulip, state = make(tmp_path, clock, cfg={"ack_timeout": 600})
    state["doc"] = doc
    for _ in range(30):
        m.look()
        clock.t += 120
    (inc,) = store.open_incidents()
    assert [a["n"] for a in store.assignments(inc["id"])] == [1, 2]
    assert len(requests(zulip)) == 2
    dms = [s for s in zulip.sent if s["kind"] == "dm"]
    assert len(dms) == 1 and "2 recovery assignment(s): not taken up" in dms[0]["content"]
    assert store.incident(inc["id"])["state"] == "escalated"


def test_a_recovery_run_that_ends_without_continuing_hands_the_run_to_a_person(tmp_path):
    doc = target_doc()
    clock = Clock(ts(doc["observedAt"]))
    m, store, zulip, state = make(tmp_path, clock)
    state["doc"] = doc
    m.look()
    (inc,) = store.open_incidents()
    (req,) = requests(zulip)
    d = copy.deepcopy(doc)
    d["runs"].append(recovery_run(req["id"]))
    state["doc"] = d
    clock.t += 60
    m.look()
    d2 = copy.deepcopy(doc)
    d2["runs"].append(recovery_run(req["id"], situation="completed", execution="completed"))
    state["doc"] = d2
    clock.t += 60
    m.look()
    inc = store.incident(inc["id"])
    assert inc["outcome"] == "handed-off"
    assert any("its report says what a person must decide" in s["content"] for s in zulip.sent if s["kind"] == "dm")
    assert len(requests(zulip)) == 1, "a decision not to continue is not retried"


def test_a_recovery_run_that_is_itself_interrupted_goes_to_the_owners_not_to_recovery(tmp_path):
    doc = target_doc()
    clock = Clock(ts(doc["observedAt"]))
    m, store, zulip, state = make(tmp_path, clock)
    rr = recovery_run(4242, situation="interrupted")
    rr["hold"] = {"kind": "interrupted", "since": doc["observedAt"], "by": "autolab", "human": False, "reason": "exited with investigate running", "because": None}
    rr["attempts"] = {"count": 1, "beganSeq": 2, "open": None, "last": {"id": "arec-9", "outcome": "interrupted", "ended": doc["observedAt"], "detail": ""}}
    rr["process"].update(attempt="arec-9", state="ended", alive=False)
    d = copy.deepcopy(doc)
    d["runs"] = [rr]
    state["doc"] = d
    m.look()
    (inc,) = store.open_incidents()
    assert inc["recover"] == 0 and inc["state"] == "escalated"
    assert requests(zulip) == []
    assert any("a recovery run is not itself recovered" in s["content"] for s in zulip.sent if s["kind"] == "dm")


def test_the_continuation_interrupted_again_is_a_new_incident_and_a_person_hold_during_investigation_is_respected(tmp_path):
    doc = target_doc()
    clock = Clock(ts(doc["observedAt"]))
    m, store, zulip, state = make(tmp_path, clock)
    state["doc"] = doc
    m.look()
    (first,) = store.open_incidents()
    again = recovered(doc, first["id"], job=False)
    r = again["runs"][0]
    r["hold"] = {"kind": "interrupted", "since": time_iso(clock.t + 60), "by": "autolab", "human": False, "reason": "exited again", "because": None}
    r["attempts"]["last"] = {"id": "amv7second-02", "outcome": "interrupted", "ended": time_iso(clock.t + 60), "detail": "exited again"}
    r["situation"] = "interrupted"
    state["doc"] = again
    clock.t += 60
    m.look()
    assert store.incident(first["id"])["outcome"] == "interrupted-again"
    (second,) = store.open_incidents()
    assert second["episode"] == "amv7second-02" and second["id"] != first["id"]
    assert len(requests(zulip)) == 2
    # While the second is investigated, the person stops the run: their hold stands; nothing more is asked.
    held = copy.deepcopy(again)
    held["runs"][0]["hold"] = {"kind": "stopped", "since": time_iso(clock.t), "by": "iwaag", "human": True, "reason": "leave it", "because": None}
    held["runs"][0]["situation"] = "stopped"
    state["doc"] = held
    clock.t += 60
    m.look()
    assert store.incident(second["id"])["outcome"] == "held"
    assert len(requests(zulip)) == 2


def test_nothing_is_assigned_while_the_executor_is_down(tmp_path):
    doc = target_doc()
    doc["executor"].update(state="unavailable", ageSeconds=900.0)
    clock = Clock(ts(doc["observedAt"]))
    m, store, zulip, state = make(tmp_path, clock)
    state["doc"] = doc
    m.look()
    fams = sorted(i["family"] for i in store.open_incidents())
    assert fams == ["attempt", "executor"]
    assert requests(zulip) == [], "a recovery run would need the executor"
    healthy = copy.deepcopy(doc)
    healthy["executor"].update(state="available", ageSeconds=1.0)
    state["doc"] = healthy
    clock.t += 60
    m.look()
    assert len(requests(zulip)) == 1
