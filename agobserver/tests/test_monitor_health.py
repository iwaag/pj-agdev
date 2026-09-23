"""robust_workflow p2 step 4: the monitor says what it has been doing, and a
slow judgment does not stop it looking at everything else."""

from __future__ import annotations

import json
import threading
import time

from agobserver import monitor as monitoring

from test_monitor import CHANNEL, requests, settle, world  # noqa: F401 - the fixture is used by name
from test_p2_reproductions import task2


def health(tmp_path) -> dict:
    return json.loads((tmp_path / "local" / monitoring.HEALTH_FILE).read_text("utf-8"))


def test_every_cycle_leaves_a_health_record(world, tmp_path):
    watcher = world.make()
    watcher.tick()
    record = health(tmp_path)
    assert record["schema"] == monitoring.HEALTH_SCHEMA and record["enabled"] is True
    assert record["cycle"]["count"] == 1 and record["cycle"]["in_progress"] is False
    assert record["cycle"]["completed_at"] >= record["cycle"]["started_at"]
    assert record["source"]["state"] == "live"
    assert record["requests"]["tracked"] == 1 and record["requests"]["open_incidents"] == 1
    assert record["requests"]["oldest_unchecked_seconds"] == 0
    assert record["judgment"]["running"] is None and record["latest_failure"] is None


def test_a_stuck_judgment_holds_only_itself(world, tmp_path):
    """p1 judged inside the look loop: 30–130 s per judgment, and every other
    request waited. Now the look queues it and moves on."""
    from test_monitor import ACK, AUTOLAB, DEV, FRONT, post

    release = threading.Event()
    calls = []

    def slow_judge(spec, candidate, trace_text, tail, incident):
        calls.append(incident)
        release.wait(10)
        return {"verdict": "stall", "evidence": "no word for hours"}

    # Task 2 started and acknowledged, then nothing for hours: `silent`, judged.
    post(world.realm, "work-m1", task2(world), "Start task 2.", FRONT)
    acked = post(world.realm, "work-m1", task2(world), ACK, AUTOLAB)
    # Another request whose entrance post nobody acknowledged: mechanical.
    other = post(world.realm, "front", "front-b", "A second question.", DEV)
    settle(world, lambda: world.mirror.message(other) is not None and world.mirror.message(acked) is not None)
    world.clock.now = world.realm.messages[acked]["timestamp"] + 3 * 3600
    watcher = world.make()
    watcher.judge, watcher.async_judge = slow_judge, True
    stop = threading.Event()
    threading.Thread(target=watcher.judge_forever, args=(stop,), daemon=True).start()
    started = time.time()
    touched = watcher.tick()
    assert time.time() - started < 3, "the look did not wait for the judgment"
    assert {r["kind"] for r in touched} == {"silent", "unacknowledged"}
    deadline = time.time() + 5
    while time.time() < deadline and not calls:
        time.sleep(0.05)
    watcher.write_health()
    running = health(tmp_path)["judgment"]["running"]
    assert calls and running and running["topic"] == calls[0]
    watcher.tick()
    assert health(tmp_path)["cycle"]["count"] == 2, "looks go on while the judgment is held"
    release.set()
    deadline = time.time() + 5
    while time.time() < deadline and health(tmp_path)["judgment"]["running"]:
        watcher.write_health()
        time.sleep(0.05)
    world.clock.now += 5
    silent = [r for r in watcher.tick() if r["kind"] == "silent"]
    assert silent and silent[0]["judgment"]["verdict"] == "stall"
    stop.set()


def test_the_stop_fault_ends_the_thread_and_the_record_stops_moving(world, tmp_path):
    watcher = world.make()
    watcher.tick()
    before = health(tmp_path)["cycle"]["count"]
    (tmp_path / "local" / "faults").mkdir(parents=True, exist_ok=True)
    (tmp_path / "local" / "faults" / "monitor-stop").write_text("")
    thread = threading.Thread(target=watcher.run, daemon=True)
    thread.start()
    thread.join(3)
    assert not thread.is_alive()
    assert health(tmp_path)["cycle"]["count"] == before
    assert not (tmp_path / "local" / "faults" / "monitor-stop").exists(), "one-shot"


def test_a_monitor_switched_off_says_so(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv(monitoring.ENABLED_ENV, "0")
    spec = SimpleNamespace(local=tmp_path / "local")
    assert monitoring.start(spec, mirror=None) is None
    assert health(tmp_path)["enabled"] is False
