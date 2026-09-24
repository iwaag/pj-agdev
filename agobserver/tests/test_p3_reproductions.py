"""robust_workflow p3 step 1: waiting and judgment gaps in the request
monitor, reproduced.

Each test states the outcome p3 requires. Step 1 committed them as
`xfail(strict=True)`; step 2 removed each mark with the fix, and added the
tests after them for what the fix promises beyond the reproduction. Same fake realm and real mirror
as `test_monitor.py`, with a request of its own: one delegated conversation
whose owner answered and now waits for the human.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from agag.mirror import Mirror
from agag.mirror.testing import FakeRealm

from agobserver import monitor as monitoring

from test_monitor import ACK, AUTOLAB, CHANNEL, DEV, FRONT, Client, post, requests, settle, spec

OWNER_CHANNEL = "pj-x"
PLAN = "assetplan-icon"


def waiting_realm():
    """A request whose one delegated conversation waits on the human: the
    owner answered with a question, Front relayed it (its receipt is
    written) and asked the Developer, who has not answered yet."""
    realm = FakeRealm()
    realm.add_channel(3, "front")
    realm.add_channel(6, OWNER_CHANNEL)
    realm.add_channel(9, CHANNEL)
    ask = post(realm, "front", "front-h", "Make an icon for the README.", DEV)
    post(realm, "front", "front-h", ACK, FRONT)
    post(realm, OWNER_CHANNEL, PLAN, f"[selfnote][rootchat] front/front-h #{ask}", FRONT)
    post(realm, OWNER_CHANNEL, PLAN, "@**autolab-agstudio1** An icon for the README, please.", FRONT)
    post(realm, OWNER_CHANNEL, PLAN, "[selfnote][asset] icon", AUTOLAB)
    post(realm, OWNER_CHANNEL, PLAN, ACK, AUTOLAB)
    answer = post(realm, OWNER_CHANNEL, PLAN, "@**Front** Two drafts are ready: which one do you want?", AUTOLAB)
    post(realm, "front", "front-h", ACK, FRONT)
    post(realm, "front", "front-h", "@**Developer** The drafts are ready; which one do you want?", FRONT)
    post(realm, "front", "front-h", f"[selfnote][served] {OWNER_CHANNEL}/{PLAN} {answer}", FRONT)
    return realm, ask, answer


@pytest.fixture
def waiting(tmp_path):
    realm, ask, answer = waiting_realm()
    mirror = Mirror.open(tmp_path / "zulip.env", tmp_path / "mirror", client_factory=realm.facet,
                         log=lambda line: None, start=True, resync_backoff=0.05)
    deadline = time.time() + 5
    while time.time() < deadline and not mirror.topics(OWNER_CHANNEL):
        time.sleep(0.05)
    clock = SimpleNamespace(now=max(m["timestamp"] for m in realm.messages.values()) + 600)
    verdicts: list[str] = []
    judged: list[tuple[str, int]] = []

    def judge(spec_, candidate, trace_text, tail, incident, **_):
        judged.append((candidate.kind, candidate.since))
        verdict = verdicts.pop(0) if verdicts else "legit"
        return {"verdict": verdict, "evidence": "the owner asked the human a question and nobody answered yet"}

    def make(**kwargs):
        return monitoring.Monitor(spec(tmp_path), Client(realm, clock), mirror, judge=judge,
                                  clock=lambda: clock.now, interval=60, window_hours=12, **kwargs)

    yield SimpleNamespace(realm=realm, mirror=mirror, clock=clock, make=make, ask=ask, answer=answer,
                          verdicts=verdicts, judged=judged)
    mirror.stop()


def resolve_plan(world):
    """The human ✔s the delegated conversation while it waits on them."""
    world.realm.resolve(OWNER_CHANNEL, PLAN)
    settle(world, lambda: any(t.resolved for t in world.mirror.topics(OWNER_CHANNEL)))


# --- W1: a legitimate human wait after a ✔ is dropped from tracking --------------------


def test_w1_a_human_wait_judged_legitimate_stays_tracked(waiting):
    """The review's reproduction: `retain()` counts a ✔ conversation judged a
    deliberate close as finished (`closed_by_decision`), and a dismissed
    incident is not open — so the request leaves the index although the
    only thing opened for it is waiting on the human."""
    resolve_plan(waiting)
    watcher = waiting.make()
    touched = watcher.tick()
    assert [(r["kind"], r["state"]) for r in touched] == [("resolved_live", monitoring.DISMISSED)]
    assert not requests(waiting), "a legitimate wait is not nudged"
    okey = monitoring.origin_key(waiting.ask)
    assert okey in watcher.load_tracked(), "the request was dropped while its work waits on the human"
    # …and still after the discovery window and a restart.
    waiting.clock.now += 13 * 3600
    again = waiting.make()
    again.tick()
    assert okey in again.load_tracked()
    assert not requests(waiting)


# --- J1: a verdict computed on superseded evidence is applied to the new state ---------


def test_j1_a_verdict_on_superseded_evidence_is_not_applied(waiting):
    """`judged()` pops whatever verdict the worker left under the incident's
    key. The Developer answers inside the ✔ conversation while the
    judgment of the earlier state is running; the old verdict (`stall`) is
    then applied to the new state and a recovery request goes out on it."""
    resolve_plan(waiting)
    watcher = waiting.make(async_judge=True)
    watcher.tick()
    (key,) = list(watcher._pending_judgments)
    job = watcher._pending_judgments.pop(key)
    # While the job is being judged, the human answers in the ✔ conversation.
    said = post(waiting.realm, OWNER_CHANNEL, f"✔ {PLAN}", "Cancel it — we do not need the icon any more.", DEV)
    settle(waiting, lambda: waiting.mirror.message(said) is not None)
    waiting.verdicts.append("stall")
    watcher._verdicts[key] = watcher._run_judgment(key, job)
    waiting.clock.now = waiting.realm.messages[said]["timestamp"] + 120
    watcher.tick()
    settle(waiting)
    assert not requests(waiting), "a recovery request went out on a verdict about the state before the answer"
    assert watcher._pending_judgments or len(waiting.judged) > 1, "the new state was never judged"


# --- step 2: what the fix promises beyond the reproductions ---------------------------


def record_state(world, word, sender):
    post(world.realm, OWNER_CHANNEL, f"✔ {PLAN}", f"[selfnote][state] {word}", sender)
    settle(world)


@pytest.mark.parametrize("word, sender, closed", [
    ("cancelled", AUTOLAB, monitoring.CANCELLED),
    ("accepted", FRONT, monitoring.FINISHED),
])
def test_a_recorded_outcome_ends_the_wait_and_the_tracking(waiting, word, sender, closed):
    """Completion and cancellation have their own evidence: the owner's
    `cancelled`, the requester's `accepted`. Either closes the dismissed
    incident — not as a rescue, nothing had stopped — and the request leaves
    the index on the same look."""
    resolve_plan(waiting)
    watcher = waiting.make()
    watcher.tick()
    okey = monitoring.origin_key(waiting.ask)
    assert okey in watcher.load_tracked()
    record_state(waiting, word, sender)
    waiting.clock.now += 120
    touched = watcher.tick()
    assert [r["state"] for r in touched] == [closed]
    assert okey not in watcher.load_tracked()
    assert not requests(waiting)


def test_a_dismissal_does_not_hide_a_later_blockage_of_the_same_work(waiting):
    """The owner answers again after the ✔ and nobody serves it: an
    `undelivered` is a mechanical fact the dismissal did not judge."""
    resolve_plan(waiting)
    watcher = waiting.make()
    watcher.tick()
    again = post(waiting.realm, OWNER_CHANNEL, f"✔ {PLAN}", "@**Front** A third draft is up too.", AUTOLAB)
    settle(waiting, lambda: waiting.mirror.message(again) is not None)
    waiting.clock.now = waiting.realm.messages[again]["timestamp"] + 400
    touched = watcher.tick()
    assert [(r["kind"], r["state"]) for r in touched] == [("undelivered", monitoring.RECOVERING)]
    visible = [m for m in requests(waiting) if not m["content"].startswith("[selfnote]")]
    assert len(visible) == 1 and "[selfnote][owed]" in requests(waiting)[0]["content"]


def test_a_stall_verdict_on_record_is_judged_again_when_its_evidence_moves(waiting):
    """A `stall` kept in the incident drives the second request and the
    report. The human answering in between is new evidence: the verdict is
    asked again before anything more is done on it — and the request already
    made still counts."""
    resolve_plan(waiting)
    waiting.verdicts.extend(["stall", "legit"])
    watcher = waiting.make()
    (record,) = watcher.tick()
    assert record["state"] == monitoring.RECOVERING and len(requests(waiting)) == 1
    post(waiting.realm, "front", "front-h", "I will pick a draft tomorrow; leave it closed until then.", DEV)
    post(waiting.realm, "front", "front-h", ACK, FRONT)
    said = post(waiting.realm, "front", "front-h", "@**Developer** Understood; it stays closed until then.", FRONT)
    settle(waiting, lambda: waiting.mirror.message(said) is not None)
    waiting.clock.now += monitoring.RETRY_SECONDS + 5
    (record,) = watcher.tick()
    assert len(waiting.judged) == 2, "the stored verdict was used on evidence it never saw"
    assert record["state"] == monitoring.DISMISSED and len(requests(waiting)) == 1
    assert len(record["requests"]) == 1, "re-judging spent or reset the allowance"


def test_evidence_that_keeps_moving_under_a_judgment_is_visible_in_health(waiting):
    resolve_plan(waiting)
    watcher = waiting.make(async_judge=True)
    watcher.tick()
    (key,) = list(watcher._pending_judgments)
    for n in range(monitoring.CHURN_LIMIT):
        job = watcher._pending_judgments.pop(key)
        watcher._verdicts[key] = watcher._run_judgment(key, job)
        said = post(waiting.realm, "front", "front-h", f"still thinking ({n})", DEV)
        settle(waiting, lambda: waiting.mirror.message(said) is not None)
        waiting.clock.now += 120
        watcher.tick()
    health = watcher.health()["judgment"]
    assert health["invalidated"] == monitoring.CHURN_LIMIT
    assert health["churning"] == [key]
    assert health["pending"] == 1 and health["oldest_pending_seconds"] is not None
    assert not requests(waiting)


# --- step 6: what a judgment reads, and that it is kept ----------------------------


def test_a_judgment_reads_the_request_s_own_conversation(waiting):
    """p3 step 5, trial C: a ✔ on a task waiting for the human's acceptance
    was judged a stall twice; the judgment saw the task and a one-line trace
    of the origin, not that Front had just put the question to the human."""
    resolve_plan(waiting)
    seen = {}
    watcher = waiting.make()

    def judge(spec_, candidate, trace_text, tail, incident, **extra):
        seen.update(extra)
        return {"verdict": "legit", "evidence": "the human was asked"}

    watcher.judge = judge
    watcher.tick()
    assert seen["home_name"] == "#front › front-h"
    assert any("which one do you want?" in m["content"] for m in seen["home"])
    assert seen["snapshot"].startswith("resolved_live|")


def test_the_prompt_and_its_input_are_kept_beside_the_verdict(tmp_path, monkeypatch):
    from agag.trace import Candidate

    from agobserver import triage

    spec_ = spec(tmp_path)
    monkeypatch.setattr(triage, "run_role", lambda *a, **k: ('{"verdict": "legit", "evidence": "asked"}', None, 0))
    candidate = Candidate("resolved_live", "pj-x", "✔ t", "task 1#1", "✔ while awaiting requester", "x", "y", 5,
                          (7,), judgment=True, anchor=3)
    home = [{"id": 9, "sender_full_name": "Front", "content": "@**Developer** Do you accept task 1?"}]
    verdict = triage.judge(spec_, candidate, "trace text", [], "incident-x", home=home, home_name="#front › f",
                           snapshot="s1")
    assert verdict["verdict"] == "legit"
    (workspace,) = list((tmp_path / "topics").rglob("triage"))
    prompt = (workspace / triage.PROMPT_FILE).read_text(encoding="utf-8")
    assert "request's own conversation (#front › f)" in prompt and "Do you accept task 1?" in prompt
    kept = json.loads((workspace / triage.INPUT_FILE).read_text(encoding="utf-8"))
    assert kept["snapshot"] == "s1" and kept["home"][0]["id"] == 9
