"""observer p3 step 7: the relocated watchdog — Observer's workflow health and
the executor's heartbeat, judged from outside both, told once per change."""

from __future__ import annotations

import json

from agobserver.watchdog import Watchdog, evaluate_executor, evaluate_observer

NOW = 1_800_000_000.0


def health(**over):
    h = {"schema": "agobserver.workflow-health.v1", "enabled": True, "interval_seconds": 60, "pid": 999999,
         "written_at": NOW - 10, "cycle": {"count": 5, "in_progress": False, "started_at": NOW - 12, "completed_at": NOW - 10},
         "source": {"state": "live", "failed_since": None}, "judgment": {"timeout_seconds": 150, "running": None, "pending": 0, "oldest_pending_seconds": None},
         "recovery": {"unacknowledged": 0, "oldest_unacknowledged_seconds": None}, "outbox": {"counts": {"sent": 3}, "oldest_unsent": None},
         "runs": {"observed": 2}, "incidents": {"open": 0}}
    for k, v in over.items():
        h[k] = {**h[k], **v} if isinstance(v, dict) and isinstance(h.get(k), dict) else v
    return h


def test_states():
    assert evaluate_observer(None, NOW)["state"] == "missing"
    assert evaluate_observer(health(), NOW)["state"] == "ok"
    assert evaluate_observer(health(runs={"observed": 0}), NOW)["state"] == "idle"
    assert evaluate_observer(health(enabled=False), NOW)["state"] == "disabled"
    stopped = evaluate_observer(health(cycle={"completed_at": NOW - 400}), NOW)
    assert stopped["state"] == "stopped" and stopped["process_alive"] is False
    assert evaluate_observer(health(cycle={"in_progress": True, "started_at": NOW - 400}), NOW)["state"] == "stalled"
    assert evaluate_observer(health(source={"state": "failed", "failed_since": NOW - 400, "reason": "x"}), NOW)["state"] == "unable_to_observe"
    assert evaluate_observer(health(source={"state": "failed", "failed_since": NOW - 100, "reason": "x"}), NOW)["state"] == "ok"
    assert evaluate_observer(health(judgment={"running": {"since": NOW - 400, "incident": "i1"}}), NOW)["state"] == "judgment_stalled"
    assert evaluate_observer(health(recovery={"unacknowledged": 1, "oldest_unacknowledged_seconds": 8000}), NOW)["state"] == "degraded"
    assert evaluate_observer(health(outbox={"oldest_unsent": NOW - 1000}), NOW)["state"] == "degraded"
    assert evaluate_executor({"executor": {"state": "available", "detail": "idle"}})["state"] == "available"
    assert evaluate_executor({"executor": {"state": "unavailable", "detail": "last reported 600 s ago"}})["state"] == "down"
    assert evaluate_executor(None)["state"] == "unknown"


def test_a_change_into_and_out_of_failure_is_told_once_each(tmp_path):
    path = tmp_path / "workflow-health.json"
    path.write_text(json.dumps(health()))
    executor = {"executor": {"state": "available", "detail": "idle"}}
    sent: list[str] = []
    clock = [NOW]
    dog = Watchdog(path, lambda: executor, alert=sent.append, out_path=tmp_path / "watchdog.json", clock=lambda: clock[0], log=lambda m: None)
    dog.check(); dog.check()
    assert sent == []
    clock[0] += 400  # the loop stopped writing
    dog.check(); dog.check()
    assert len(sent) == 1 and "workflow monitor is stopped" in sent[0]
    executor = {"executor": {"state": "unavailable", "detail": "autolab last reported 300 s ago"}}
    dog.read_executor = lambda: executor
    dog.check()
    assert len(sent) == 2 and "executor is down" in sent[1], "the executor's outage is seen without Observer"
    path.write_text(json.dumps(health(written_at=clock[0], cycle={"completed_at": clock[0] - 5})))
    dog.read_executor = lambda: {"executor": {"state": "available", "detail": "idle"}}
    dog.check()
    assert len(sent) == 4 and all("again" in s for s in sent[2:])
    assert json.loads((tmp_path / "watchdog.json").read_text())["observer"]["state"] == "ok"
