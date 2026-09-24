"""robust_workflow p3 step 1: waiting and judgment gaps in the request
monitor, reproduced.

Each test states the outcome p3 requires and is `xfail(strict=True)` while
the defect stands; the fix removes the mark. Same fake realm and real mirror
as `test_monitor.py`, with a request of its own: one delegated conversation
whose owner answered and now waits for the human.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from agag.mirror import Mirror
from agag.mirror.testing import FakeRealm

from agobserver import monitor as monitoring

from test_monitor import ACK, AUTOLAB, CHANNEL, DEV, FRONT, Client, post, requests, settle, spec

defect = pytest.mark.xfail(strict=True, reason="reproduced in robust_workflow p3 step 1; not fixed yet")

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

    def judge(spec_, candidate, trace_text, tail, incident):
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


@defect
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


@defect
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
