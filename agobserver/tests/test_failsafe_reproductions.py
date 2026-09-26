"""failsafe p1: a worker that stops after a progress post, with nobody told.

The reproduction is m11741 (2026-09-26) in miniature, as its posts stood:
Front's Front Desk conversation, the routine run Front opened, autolab's
mission and its one task. autolab started the task itself, its supercoder
posted live progress, and the serving ended on a reply that said the local
kit run was "still running" and that a report would follow — then nothing.
Two of the progress posts were long enough that Zulip cut their tails, and
the `ag-post intent=progress` line went with them.

Two readings of the same stall are reproduced:

- **as posted** — the historical shapes: a truncated progress post that
  reads as the task's answer, and no evidence that the serving ended;
- **as a fixed listener posts** — every marker intact and the final reply
  saying it ends its serving.

Each must reach Front with a recovery request; neither may be dismissed for
good by one judgment that believed the "still running" post.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from agag.mirror import Mirror
from agag.mirror.testing import FakeRealm
from agag.trace import MirrorReader, stall_candidates, trace

from agobserver import monitor as monitoring

#: Step 1 records the gap; step 2 closes it and removes this mark.
pytestmark = pytest.mark.xfail(strict=True, reason="failsafe p1 step 1: the reproduced gap")

DEV, FRONT, AUTOLAB, OBS = 8, 15, 11, 23
NAMES = {DEV: "Developer", FRONT: "Front", AUTOLAB: "autolab-agstudio1", OBS: "agobserver-agstudio1"}
ACK = "Message received. Please wait for the reply."
CHANNEL = "agobserver-agstudio1"
PROGRESS = "`ag-post intent=progress`"
#: 2026-09-26 13:16:32 UTC, the Developer's question.
T0 = 1790428592


class Client:
    def __init__(self, realm, clock):
        self.realm, self.clock, self.sent = realm, clock, []

    def whoami(self):
        return {"user_id": OBS, "full_name": NAMES[OBS]}

    def send_to_channel(self, channel, topic, content):
        self.sent.append((channel, topic, content))
        return self.realm.post(channel, topic, content, sender_id=OBS, sender_name=NAMES[OBS],
                               timestamp=int(self.clock.now))

    def subscriptions(self):
        return [{"name": c["name"]} for c in self.realm.channels_by_id.values()]

    def subscribe_channels(self, names):
        self.sent.append(("subscribe", tuple(names)))

    def realm_owners(self):
        return [DEV]

    def users(self):
        return [{"user_id": DEV, "full_name": "Developer"}]


def spec(tmp_path):
    return SimpleNamespace(local=tmp_path / "local", topics_root=tmp_path / "topics",
                           records_root=tmp_path / "records", instance_name=lambda: CHANNEL)


def m11741(fixed: bool, end: bool = True):
    """The request as the realm held it at 13:43:49 UTC. `fixed`: posted as
    a listener with the failsafe contract posts (markers survive, the final
    reply says it ends its serving)."""
    realm = FakeRealm()
    for stream_id, name in enumerate(("front", "routine-study-x", "pj-x", "work-m1", CHANNEL), start=3):
        realm.add_channel(stream_id, name)

    def post(channel, topic, text, sender, at):
        return realm.post(channel, topic, text, sender_id=sender, sender_name=NAMES[sender], timestamp=T0 + at)

    desk, run, plan = "front-desk-20260926-221323", "routinerun-20260926-2225", "workplan-x-round2"
    ask = post("front", desk, "Is the study exhausted? If not, run one more phase.", DEV, 0)
    post("front", desk, ACK, FRONT, 1)
    started = post("front", desk, "@**Developer** Not exhausted, so I started one more phase; I report here "
                                  "when it ends.\n\n`ag-post intent=report`", FRONT, 446)
    post("routine-study-x", run, f"[selfnote][rootchat] front/{desk} #{started}", FRONT, 434)
    opened = post("routine-study-x", run, "Request to run routine study-x, one more bounded phase.", FRONT, 434)
    post("routine-study-x", run, ACK, FRONT, 446)
    post("pj-x", plan, f"[selfnote][rootchat] routine-study-x/{run} #{opened}", FRONT, 483)
    post("pj-x", plan, "@**autolab-agstudio1** Mission request: one bounded phase, one task.", FRONT, 483)
    post("pj-x", plan, ACK, AUTOLAB, 483)
    mission = post("pj-x", plan, "[selfnote][mission] x", AUTOLAB, 510)
    post("pj-x", plan, "# round 2\n\nOne task.", AUTOLAB, 510)
    post("pj-x", plan, "[selfnote][state] started", AUTOLAB, 510)
    planned = post("pj-x", plan, "@**Front** Planned as one task; task 1 starts now.\n\n`ag-post intent=report`",
                   AUTOLAB, 511)
    post("routine-study-x", run, ACK, FRONT, 511)
    post("routine-study-x", run, "Checked autolab's plan: one mission, one task.\n\n" + PROGRESS, FRONT, 533)
    post("routine-study-x", run, f"[selfnote][served] pj-x/{plan} {planned}", FRONT, 533)

    task = f"workrun-task1-m{mission}"
    post("work-m1", task, f"[selfnote][task] {mission}#1", AUTOLAB, 510)
    post("work-m1", task, f"[selfnote][rootchat] pj-x/{plan} #{mission}", AUTOLAB, 510)
    post("work-m1", task, "# Task 1\n\nWhole round in one task.", AUTOLAB, 510)
    post("work-m1", task, "Task 1 of the mission starts now.\n\n" + PROGRESS, AUTOLAB, 511)
    post("work-m1", task, f"[selfnote][start] #{planned} for {FRONT} Front", AUTOLAB, 511)
    ack = post("work-m1", task, ACK, AUTOLAB, 511)
    lines = "\n".join(f"🔧 Bash: step {n} " + "x" * 120 for n in range(80))
    if fixed:
        post("work-m1", task, lines[:9000] + "\n\n[… cut by the poster to fit]\n\n" + PROGRESS, AUTOLAB, 632)
        post("work-m1", task, lines[:9000] + "\n\n[… cut by the poster to fit]\n\n" + PROGRESS, AUTOLAB, 753)
    else:
        # Zulip keeps the first 10000 characters and says so; the line was
        # at the end.
        post("work-m1", task, lines[:9980] + "\n[message truncated]", AUTOLAB, 632)
        post("work-m1", task, lines[:9980] + "\n[message truncated]", AUTOLAB, 753)
    post("work-m1", task, "🔧 Write: reports/strand5a-people.md\n💬 Strand 5A is written.\n\n" + PROGRESS,
         AUTOLAB, 1111)
    post("work-m1", task, "🔧 Bash: refine_svg on the kit\n\n" + PROGRESS, AUTOLAB, 1614)
    post("work-m1", task, "[selfnote][change] checkpoint main=abc:def", AUTOLAB, 1614)
    final = ("@**Front**\n\nStrands 5A, 5B, the reinforcement and the appendix are written. The local kit run "
             "is still running; after it finishes I'll merge, add the INDEX rows, commit and report.\n\n")
    final += f"`ag-post intent=progress end={ack}`" if fixed and end else PROGRESS
    last = post("work-m1", task, final, AUTOLAB, 1615)
    post("routine-study-x", run, ACK, FRONT, 1615)
    post("routine-study-x", run, "autolab's progress post: the kit run is still going; I wait for its report."
                                 "\n\n" + PROGRESS, FRONT, 1637)
    post("routine-study-x", run, f"[selfnote][served] work-m1/{task} {last}", FRONT, 1637)
    return SimpleNamespace(realm=realm, ask=ask, task=task, last_at=T0 + 1637)


def open_world(tmp_path, fixed, verdict, end=True):
    case = m11741(fixed, end)
    mirror = Mirror.open(tmp_path / "zulip.env", tmp_path / "mirror", client_factory=case.realm.facet,
                         log=lambda line: None, start=True, resync_backoff=0.05)
    deadline = time.time() + 5
    while time.time() < deadline and not mirror.topics("work-m1"):
        time.sleep(0.05)
    time.sleep(0.3)
    clock = SimpleNamespace(now=case.last_at)
    judged = []

    def judge(spec_, candidate, trace_text, tail, incident, **_):
        judged.append(candidate.kind)
        return {"verdict": verdict, "evidence": "the last post says the kit run is still running"}

    case.mirror, case.clock, case.judged = mirror, clock, judged
    case.make = lambda: monitoring.Monitor(spec(tmp_path), Client(case.realm, clock), mirror, judge=judge,
                                           clock=lambda: clock.now, interval=120, window_hours=12)
    return case


def asked_front(case):
    return [m for m in case.realm.messages.values()
            if m["display_recipient"] == "front" and m["sender_id"] == OBS and "[selfnote]" not in m["content"]]


def run_for(case, watcher, seconds, step=120):
    """Look every `step` seconds for `seconds`; the time of the first request
    to Front, or None."""
    end = case.clock.now + seconds
    while case.clock.now <= end:
        watcher.tick()
        time.sleep(0.05)
        if asked_front(case):
            return case.clock.now - case.last_at
        case.clock.now += step
    return None


@pytest.fixture
def world(tmp_path):
    cases = []

    def make(kind, verdict):
        case = open_world(tmp_path / f"{kind}-{verdict}", kind == "fixed", verdict)
        case.kind = kind
        cases.append(case)
        return case

    yield make
    for case in cases:
        case.mirror.stop()


def test_the_truncated_progress_post_is_not_read_as_the_tasks_answer(world):
    """As posted: the cut post lost its line, so nothing says what it is —
    but a post Zulip cut is not an answer, and nothing says the serving
    ended, so the task is unfinished work whose execution is unknown."""
    case = world("as_posted", "legit")
    result = trace(MirrorReader(case.mirror), case.ask, now=case.last_at + 600)
    task = next(n for n in result.nodes() if n.topic == case.task)
    assert task.state != "awaiting_requester"
    assert task.execution == "unknown"
    assert task.holder != "requester"


def test_with_the_fixed_posts_the_task_is_held_by_nobody(world):
    """The final reply ends its serving and says only that work goes on:
    nobody is running it and nobody else was handed it."""
    case = world("fixed", "legit")
    result = trace(MirrorReader(case.mirror), case.ask, now=case.last_at + 600)
    task = next(n for n in result.nodes() if n.topic == case.task)
    assert task.execution == "ended"
    assert task.holder == "none"
    assert [c.kind for c in stall_candidates(result, now=case.last_at + 600)] == ["unheld"]


def test_fixed_posts_reach_front_without_a_judgment(world):
    """Mechanical: a judge that believes "still running" is never asked."""
    case = world("fixed", "legit")
    target = monitoring.DETECTION_TARGET["unheld"]
    detected = run_for(case, case.make(), target + 240)
    assert detected is not None and detected <= target, detected
    assert case.task in asked_front(case)[0]["content"]
    assert case.judged == []


def test_as_posted_a_stall_verdict_reaches_front_within_the_quiet_review(world):
    case = world("as_posted", "stall")
    target = monitoring.DETECTION_TARGET["quiet"]
    detected = run_for(case, case.make(), target + 240)
    assert detected is not None and detected <= target, detected
    assert case.task in asked_front(case)[0]["content"]


def test_as_posted_a_legit_verdict_postpones_the_review_but_never_ends_it(world):
    """The judgment that believed the last post is asked again after the
    postponement, and a wait that never moves is escalated to the owners
    rather than looked at for ever in silence."""
    case = world("as_posted", "legit")
    watcher = case.make()
    run_for(case, watcher, monitoring.DETECTION_TARGET["quiet"] + monitoring.REJUDGE_SECONDS + 600)
    assert len(case.judged) >= 2, case.judged
    run_for(case, watcher, monitoring.MAX_POSTPONED_SECONDS)
    posts = [m["content"] for m in case.realm.messages.values() if m["display_recipient"] == CHANNEL]
    assert any("@**Developer**" in text for text in posts), "a wait that never moves reaches a person"
