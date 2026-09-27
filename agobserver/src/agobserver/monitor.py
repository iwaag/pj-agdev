"""Observer's second clock: every active request, looked at without being asked.

`robust_workflow` p1 step 4. Until now Observer looked only at what somebody
had registered as a watch, so a stall was caught only if the agent that was
about to stall had remembered, beforehand, to ask for it to be caught — and
adventure_game p3's 24-minute stall was found by the Omni Agent reading
topics by hand. This loop needs nobody to register anything:

1. **Discover.** Every open `front-…` conversation in `#front` with activity
   in the last few hours is an active request. Read off the listener's
   mirror: no Zulip call.
2. **Look.** `agag.trace` over the mirror (`MirrorReader`) follows each
   request through every conversation opened for it, and
   `stall_candidates` lists what is owed and overdue — mechanical facts only,
   decided in code. Elapsed time makes a candidate, never a verdict.
3. **Judge** only what the facts cannot decide — a ✔ on live work (a
   correction or a mistake?), a long silence while executing (a long job or a
   dead worker?) — with the `triage` role on this host's model.
4. **Ask the responsible side to recover**, in a conversation Front holds —
   the request's own, or (failsafe p1, for `unheld`/`quiet`/`silent`) the one
   Front holds closest above the stalled work, where its answer reaches the
   run that waits for it. Front holds every tool the recovery needs
   (`agentchat send`, `unresolve`, `trace`). At most `MAX_REQUESTS`,
   `RETRY_SECONDS` apart, each preceded by a fresh look.
   A judgment only postpones the next look (failsafe p1): unfinished work
   stays due for review until a record ends it.
5. **Verify.** A request is not recovery. The incident is *rescued* only when
   a later look no longer finds the candidate; otherwise, when the requests
   are spent — or when there is nobody to ask (the request's own conversation
   is ✔, or its owner is the one not answering) — it is **reported** to the
   realm's owners by name and Observer stops.
6. **Record.** One `incident-<kind>-<id>` topic in Observer's own channel per
   incident: what was found and on what evidence, each request, each look,
   and the outcome. Being rescued is not the cause being removed: the
   outcome line says which it was, and the cause stays open.

**The health path (failsafe p2).** For an owner that exposes the execution
health interface (`agobserver.health`, `.local/health.toml`), a silence is
checked instead of judged: an open serving with no confirmed progress for
`PROBE_AFTER`, or one that ended asking nobody anything, is probed every look.
A confirmed stop (`stopped`) is asked about at once; what the probe cannot
confirm (`uncertain`) after `ASK_AFTER` from the first suspicion; either is
told to the developer `ESCALATE_AFTER` from it. `silent`/`quiet` are not used
for such an owner. Rescued and reported incidents are handed to a developer
review (`agobserver.review`).

**Queues (failsafe p5).** A post an agent has not acknowledged is often
just waiting its turn: listeners serve one conversation at a time. Before
`unacknowledged` becomes an incident, the wait is read the way the progress
panel reads it (`agag.waits`): from the owner's own listener for a probed
owner (`probe_queue`), else from the open servings the traced requests show.
A wait `behind` healthy work is deferred and looked at again every look; a
post the listener is not serving (idle, passed over, given up) is
`unserved` and reported to the owners at once, since nobody in the request
can make a listener serve it; a post `blocked` behind a serving that is not
healthy is left to that serving's own request, whose health path asks about
the stopped work itself, for at most `escalate_after`, and is `unserved`
after that or when no traced request holds the blocker. A wait nothing
establishes (no check, a stale or failed one, a conversation-only excuse
past its bound) is the plain `unacknowledged` rule. An incident opened on a
wait later confirmed legitimate is closed `excused`, never `rescued`.

Repeated detection of the same thing is one incident (`Candidate.key`), in the
local store and — when that store is lost — by the incident topic's name, so a
restart neither re-opens nor re-asks. Posts go through `agag.delivery`, whose
read-back settles an ambiguous send instead of repeating it.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from agag.agent import AgentSpec
from agag.delivery import deliver
from agag.selfnote import note
from agag import waits
from agag.trace import FAILSAFE_KINDS, THRESHOLDS, Candidate, MirrorReader, stall_candidates, trace, trace_lines
from agag.zulip import RESOLVED_TOPIC_PREFIX, ZulipClient, log

from . import triage
from .health import HealthProbes, unknown
from .review import REVIEWS_FILE, Reviews

INTERVAL_ENV = "AGOBSERVER_MONITOR_SECONDS"
#: One look interval (failsafe p2: 120 → 60 s). A cycle costs well under a
#: second off the mirror; the interval is most of every detection time.
DEFAULT_INTERVAL_SECONDS = 60.0
WINDOW_ENV = "AGOBSERVER_MONITOR_WINDOW_HOURS"
DEFAULT_WINDOW_HOURS = 12.0
#: Setting this to 0 turns the loop off without a code change.
ENABLED_ENV = "AGOBSERVER_MONITOR"

#: Where requests arrive: Front's entrance. A request is one of its
#: conversations; everything else is reached through the trace.
ORIGIN_CHANNEL = "front"
ORIGIN_PREFIX = "front-"
INCIDENT_PREFIX = "incident-"
INCIDENT_TAG = "incident"
MAX_REQUESTS = 2
RETRY_SECONDS = 600
#: A wait judged legitimate is looked at again after this long, and each
#: further `legit` on the same unmoving evidence doubles it, up to
#: `MAX_REJUDGE_SECONDS` (failsafe p1: a judgment postpones a review; it
#: never ends it).
REJUDGE_SECONDS = 3600
MAX_REJUDGE_SECONDS = 4 * 3600
#: A wait judged legitimate again and again while nothing moves is told to
#: the realm's owners once it has lasted this long: a person confirms it.
#: Not for a ✔ judged deliberate — that is a decision, not a wait.
MAX_POSTPONED_SECONDS = 6 * 3600
POSTPONABLE = ("silent", "quiet")
#: Two unclear judgments and the human decides.
MAX_UNCLEAR = 2
#: A judgment asked for this long ago and still without a verdict counts as
#: `unclear`: the review does not wait on a judge that never answers
#: (failsafe p2: 900 → 240 s, one judgment's own timeout and a margin).
JUDGMENT_DEADLINE_SECONDS = 240

# --- the health path (failsafe p2) -------------------------------------------------
#
# For a unit of work whose owner exposes the execution health interface
# (`agobserver.health`), silence is not judged by a model: it is checked.
#: No confirmed progress (a post, a harness event) in an open serving for
#: this long: probe it, and again every look while it lasts.
PROBE_AFTER = 120
#: A serving that ended without asking anybody anything, on unfinished work,
#: with nothing moving anywhere in the request for this long: check it — the
#: misclassification p1's T3 needed 1800 s and a judgment to find.
QUIET_CHECK = 300
#: Uncertainty that persists this long after the first suspicion is put to
#: Front (investigate; not a recovery), so it reaches Front within five
#: minutes of the suspicion with one look interval of slack.
ASK_AFTER = 180
#: Still unresolved this long after the first suspicion: the developer is
#: told, with the facts and what is not known.
ESCALATE_AFTER = 600
#: `stopped` is a confirmed stop (the probe saw the process gone and nothing
#: posted or queued); `uncertain` is everything the probe could not confirm.
HEALTH_KINDS = ("stopped", "uncertain")
HEALTH_STATE_FILE = "health.json"
#: Ended episodes per incident key, kept when their archives are pruned.
EPISODES_FILE = "episodes.json"
#: A closed incident record nothing refers to is forgotten this long after
#: its last change (`Monitor.prune`); its Zulip topic stays.
INCIDENT_TTL = 14 * 86400
PRUNE_EVERY = 60
#: A unit's health state is forgotten this long after it was last looked at.
HEALTH_STATE_TTL = 24 * 3600
#: The conversation-only kinds the health path replaces for a probed owner.
REPLACED_KINDS = ("silent", "quiet")
#: Accelerated trials (failsafe p2 step 5): `.local/timing.json` may set
#: `interval`, `probe_after`, `quiet_check`, `ask_after` and
#: `escalate_after` (seconds). It is read at every look, so a trial needs no
#: restart, and deleting the file restores the operational values. The
#: health record says which values are in force.
TIMING_FILE = "timing.json"
#: failsafe p3: a wait with no declared bound of its own — a subagent, a
#: fetch, processes the run started — whose process tree has not advanced
#: (no CPU time added) for this long is no longer explained by being named:
#: it becomes uncertainty, and the ordinary bounds from the first suspicion
#: take it to Front and then the developer. A wait that advances again
#: clears it. p1's T2 had 6-minute silences and p2's B a 5-minute quiet
#: command, both bounded Bash calls; 15 minutes is well past either.
WAIT_IDLE = 900
#: The CPU time a wait's process tree must add between two looks to count
#: as advancing (the harness's own bookkeeping adds a little).
WAIT_CPU_STEP = 0.5
TIMING_DEFAULTS = {"probe_after": PROBE_AFTER, "quiet_check": QUIET_CHECK, "ask_after": ASK_AFTER,
                   "escalate_after": ESCALATE_AFTER, "wait_idle": WAIT_IDLE}
#: failsafe p3: the probes due in one look all run at once (up to
#: `PROBE_WORKERS`), and the look waits for them at most this long — longer
#: than a probe's own timeout, so a probe that answers in time is never
#: queued behind slow ones. A probe still running then counts as one that
#: did not answer; its thread ends at its own timeout. Without it the looks
#: were serial in the probes, so k probes timing out (10 s each) delayed
#: every request's next look by 10k s (step 3's reproduction).
PROBE_WORKERS = 16
PROBE_BUDGET = 20.0
#: Trial aid (failsafe p3), created only by a person: while
#: `faults/probe-slow` holds a number k, every look adds k probes of no unit
#: that each take the probe's whole timeout — "several probes time out" on
#: the same budget as the real ones.
PROBE_SLOW_FAULT = "probe-slow"
#: Every this many ticks (and on the first) the bot's subscriptions are
#: checked: a move — a rename, a ✔ — reaches only subscribers, so a mirror
#: on a bot that has not joined a channel keeps its conversations under their
#: old names for ever (seen on this very monitor's first live look, below).
SUBSCRIBE_EVERY = 5

#: An incident whose stalled work the monitor cannot see is reported after
#: this long without a readable look; before that nothing is concluded.
UNOBSERVABLE_REPORT_SECONDS = 1800
TRACKED_FILE = "tracked.json"
#: Requests a person has taken over (`agobserver.hold`): traced, never acted on.
HELD_FILE = "held.json"
#: Requests a person checked and found owing nothing (`agobserver.hold
#: --retire`, failsafe p3): out of tracking until anything new is posted.
RETIRED_FILE = "retired.json"
#: Facts about this monitor's own history (`receipts_from`).
STATE_FILE = "monitor-state.json"
#: The monitor's own progress, read by processes that are not the monitor
#: (robust_workflow p2 step 4): the relay's watchdog, and a human.
HEALTH_FILE = "monitor-health.json"
HEALTH_SCHEMA = "agobserver.monitor-health.v1"
#: Operator fault injection for trials, one file each under `.local/faults/`:
#: `monitor-stop` ends the monitor thread at its next cycle (the process and
#: the listener stay up); `triage-stall` holds the next judgment until the
#: file is removed; `mirror-stale` makes the monitor treat its source as stale
#: while the file exists. Nothing creates them but a person.
FAULTS_DIR = "faults"

DETECTED, RECOVERING, RESCUED, REPORTED, DISMISSED = "detected", "recovering", "rescued", "reported", "dismissed"
#: The owner or the requester recorded a terminal decision: not a recovery.
CANCELLED = "cancelled"
#: A wait judged legitimate ended with the work's own finished record — the
#: acceptance or the owner's `done` — with nobody asked (robust_workflow p3
#: step 2). Not a rescue: nothing had stopped.
FINISHED = "finished"
#: An operator closed an incident the monitor should not have opened.
WITHDRAWN = "withdrawn"
#: The wait was confirmed legitimate after the incident opened — a post
#: queued behind healthy work (failsafe p5): nothing had stalled.
EXCUSED = "excused"
CLOSED = (RESCUED, REPORTED, CANCELLED, FINISHED, WITHDRAWN, EXCUSED)
#: failsafe p5: a post its owner's listener is not serving (`agag.waits`).
QUEUE_KIND = "unserved"
#: Node states that end tracking: the owner's or the requester's record says
#: the work is over. Nothing else does — not a ✔, not a `legit` verdict, not
#: the request going quiet (robust_workflow p3 step 2).
TERMINAL = ("done", "cancelled")
#: A judgment whose evidence changed this many times in a row before a
#: verdict could be used is said in the health record: the relay's watchdog
#: reads it as degraded rather than letting re-evaluation churn unseen.
CHURN_LIMIT = 3
#: Selfnotes that change what a judged conversation means. Every other note
#: (a continuation, an exec snapshot, a root note) is bookkeeping, and
#: bookkeeping moving on does not make a verdict stale.
RELEVANT_NOTES = ("state", "served", "start", "owed", "task", "mission", "asset", "assetrun", "change")

#: What the stalled conversation has to show before an incident of each kind
#: is recovered — the transition it was waiting for, read on a fresh look
#: (robust_workflow p2 step 3). The candidate no longer being produced is
#: not on this list: it is absence, and absence is also what an unreadable
#: target, a rename or a blockage still inside its grace look like.
MOVED_ON = ("executing", "awaiting_requester", "awaiting_delivery", "awaiting_human", "answered", "done")
#: failsafe p1's kinds recover on evidence of work, not on a state
#: (`Monitor.recovered`).
WORK_KINDS = ("unheld", "quiet", "stopped", "uncertain")
RECOVERED_STATES = {
    "unstarted": MOVED_ON,
    "unacknowledged": MOVED_ON,
    QUEUE_KIND: MOVED_ON,
    "failed": MOVED_ON,
    "unanswered": MOVED_ON,
    "undelivered": ("executing", "awaiting_requester", "awaiting_human", "answered", "done"),
    "silent": ("awaiting_requester", "awaiting_delivery", "awaiting_human", "answered", "done"),
    "resolved_live": ("queued", *MOVED_ON),
    "origin_closed": ("queued", *MOVED_ON),
}

#: Seconds from the evidence going stale to Front being asked, at worst:
#: one look interval, the kind's grace, and — for a judged kind — the
#: judgment's own ceiling. The trials measure against these.
def detection_target(kind: str, interval: float = DEFAULT_INTERVAL_SECONDS) -> int:
    judged = kind in ("silent", "quiet", "resolved_live")
    if kind == "stopped":
        return int(interval + PROBE_AFTER + interval)
    if kind == "uncertain":
        return int(interval + PROBE_AFTER + ASK_AFTER + interval)
    return int(interval + THRESHOLDS[kind] + (triage.TIMEOUT_SECONDS if judged else 0))


DETECTION_TARGET = {kind: detection_target(kind) for kind in (*THRESHOLDS, *HEALTH_KINDS)}

__all__ = ["DETECTION_TARGET", "Monitor", "is_incident_topic", "start"]


def is_incident_topic(topic: str) -> bool:
    bare = topic[len(RESOLVED_TOPIC_PREFIX):] if topic.startswith(RESOLVED_TOPIC_PREFIX) else topic
    return bare.startswith(INCIDENT_PREFIX)


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, "") or default)
    except ValueError:
        return default
    return value if value > 0 else default


def _when(timestamp: float) -> str:
    return time.strftime("%H:%M UTC", time.gmtime(timestamp)) if timestamp else "?"


def _asker(node) -> str:
    return node.requested_by[0].split(" #")[0] if node.requested_by else "whoever asked for it"


def _clock(timestamp: float | None) -> str:
    return time.strftime("%H:%M:%S UTC", time.gmtime(float(timestamp))) if timestamp else "?"


def health_lines(report: dict[str, Any] | None) -> list[str]:
    """A probe's facts as request/incident lines, each with where it is from."""
    if not report:
        return []
    process = report.get("process") or {}
    progress = report.get("progress") or {}
    wait = report.get("wait") or {}
    serving = report.get("serving") or {}
    run = report.get("run") or {}
    lines = [f"- Health check ({_clock(report.get('observed_at'))}, {report.get('source', {}).get('host', 'probe')}): "
             f"**{report.get('verdict', 'unknown')}** — {report.get('why', '')}."]
    facts = []
    if process.get("state"):
        how = f" ({process['how']})" if process.get("how") else ""
        facts.append(f"process {process['state']}{how}" + (f", pid {run.get('pid')}" if run.get("pid") else ""))
    if progress.get("last_event_at"):
        facts.append(f"last harness event {progress.get('last_event') or '?'} at {_clock(progress['last_event_at'])}")
    if wait.get("kind") and wait["kind"] != "unknown":
        named = f" {wait.get('name')}" + (f" ({wait['detail']})" if wait.get("detail") else "") if wait.get("name") else ""
        facts.append(f"wait: {wait['kind']}{named}")
    if serving:
        facts.append(f"listener journal: {serving.get('state') or 'no row'}"
                     + (f", queued {','.join(serving['queued'])}" if serving.get("queued") else ""))
    if facts:
        lines.append(f"- Facts: {'; '.join(facts)}.")
    if report.get("unknowns"):
        lines.append(f"- Not established: {'; '.join(map(str, report['unknowns']))}.")
    return lines


def _age(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60} min" if seconds < 5400 else f"{seconds // 3600} h {(seconds % 3600) // 60:02d} min"


def _bare(topic: str) -> str:
    return topic[len(RESOLVED_TOPIC_PREFIX):] if topic.startswith(RESOLVED_TOPIC_PREFIX) else topic


def _path_to(root, anchor: int) -> list:
    """The nodes from `root` down to the one anchored at `anchor`."""
    if root.anchor == anchor:
        return [root]
    for child in root.children:
        below = _path_to(child, anchor)
        if below:
            return [root, *below]
    return []


def _execution_words(node, health: dict[str, Any] | None = None) -> str:
    """The unit's execution as its conversation shows it — overridden by a
    health check that saw its process: a conversation cannot say that a
    serving died (failsafe p3 trial A: "a serving is open" beside "stopped"
    read as two different facts)."""
    process = (health or {}).get("process") or {}
    if node.execution == "open" and (health or {}).get("verdict") == "stopped":
        serving = (f"the serving acknowledged at #{node.ack} is over — the health check found its run's process "
                   f"gone ({process.get('how') or 'exited'}); it will not post again, although its conversation "
                   "shows no end")
    elif node.execution == "open" and process.get("state") == "alive":
        serving = f"a serving is open since its acknowledgement #{node.ack}, and its run's process is alive"
    else:
        serving = {"open": f"a serving is open since its acknowledgement #{node.ack}, and nothing has said it ended",
                   "ended": f"its last serving ended with #{node.ended_by}",
                   "unknown": "no serving of it is on record"}[node.execution]
    holder = {"none": "nothing holds the work now", "delegate": "a conversation opened from it holds the work",
              "owner": "its owner holds the work", "requester": "the move is with whoever asked for it",
              "human": "a person was asked", "unknown": "who holds the work cannot be read"}.get(node.holder, "")
    return f"{serving}; {holder}" if holder else serving


def _owed_words(node) -> str:
    if node.identity:
        return (f"{node.identity} is unfinished until its owner's record says it ended (done, accepted, "
                "cancelled or replaced) — a reply, a ✔ or this request ends nothing")
    return "an answer in that conversation, handed back to whoever asked"


def _unknown_words(candidate: Candidate, node) -> str:
    if node is not None and node.execution == "ended":
        return ("whether anything the last serving started (a background job, a subagent) is still running is not "
                "in Zulip — check before starting the work again, and continue from what it left rather than "
                "redoing it.")
    if node is not None and node.execution == "open":
        return ("whether the open serving is still alive is not in Zulip: it may be a long job. Ask its owner or "
                "wait; do not start a second run of the same work beside it.")
    return "why it stopped; the records show only that it did."


def satisfied(node) -> bool:
    """A plain conversation — no unit of work in it — whose exchange is
    complete for now (failsafe p3): its agent answered, the answer was taken
    up by whoever asked, its serving ended, and the next move is the
    requester's — or one somebody closed with a ✔ once its serving ended. It
    owes nothing, so it does not keep a request tracked.
    A unit of work never is: only its record ends it. Age plays no part."""
    if node.identity or node.execution != "ended":
        return False
    if node.topic.startswith(RESOLVED_TOPIC_PREFIX) and node.state not in ("queued", "executing"):
        # A plain conversation has no record but its ✔: somebody closed the
        # exchange, and nothing in it is running or waiting to be served.
        return True
    return node.state in ("awaiting_requester", "answered") and node.taken_up and node.holder in ("requester", "none")


def origin_key(anchor: int) -> str:
    """A tracked request: its origin conversation's first post."""
    return f"o{int(anchor)}"


def incident_key(origin_anchor: int, candidate: Candidate) -> str:
    """One incident per request and stalled conversation, both by anchor.

    Not the kind: the same work blocked a different way is the same
    incident with the same allowance of requests (p2 step 1, R2). Not a
    name: a rename is display, and a reused name is another conversation
    (R5–R7)."""
    node = candidate.anchor or (candidate.evidence[0] if candidate.evidence else 0)
    return f"{origin_key(origin_anchor)}:n{int(node)}"


#: When one conversation fails several checks at once, the incident is
#: named after the one a reader should worry about first.
PRIORITY = ("failed", "unserved", "unacknowledged", "undelivered", "unstarted", "resolved_live", "silent", "origin_closed")
#: A request's own conversation ✔'d while work opened for it is unfinished,
#: seen for this long: reported, because a ✔ stops nothing and Front does
#: not reopen a finished conversation to deliver into it.
ORIGIN_CLOSED_GRACE = 300


def node_owner(result, candidate: Candidate) -> str:
    node = next((n for n in result.nodes() if n.anchor and n.anchor == candidate.anchor), None)
    return (node.owner if node is not None else "") or "its owner"


def primary(candidates) -> list[Candidate]:
    """One candidate per stalled conversation (by anchor), the most urgent."""
    best: dict[int, Candidate] = {}
    for candidate in candidates:
        node = candidate.anchor or (candidate.evidence[0] if candidate.evidence else 0)
        current = best.get(node)
        rank = PRIORITY.index(candidate.kind) if candidate.kind in PRIORITY else len(PRIORITY)
        if current is None or rank < (PRIORITY.index(current.kind) if current.kind in PRIORITY else len(PRIORITY)):
            best[node] = candidate
    return list(best.values())


class Monitor:
    """The request monitor. One instance, one thread."""

    def __init__(self, spec: AgentSpec, client: ZulipClient, mirror, *,
                 judge: Callable[..., dict] = triage.judge, clock: Callable[[], float] = time.time,
                 interval: float | None = None, window_hours: float | None = None,
                 report_to: list[str] | None = None, async_judge: bool = False,
                 receipts_from: int = 0, obligations_from: int = 0, probes: HealthProbes | None = None) -> None:
        self.spec = spec
        self.client = client
        self.mirror = mirror
        self.judge = judge
        self.clock = clock
        self.interval = interval if interval is not None else _env_float(INTERVAL_ENV, DEFAULT_INTERVAL_SECONDS)
        self.window = 3600 * (window_hours if window_hours is not None
                              else _env_float(WINDOW_ENV, DEFAULT_WINDOW_HOURS))
        self.store_dir: Path = spec.local / "incidents"
        self.self_id = int(client.whoami()["user_id"])
        self._report_to = report_to
        self.ticks = 0
        #: What each tick spent: posts made and model judgments run. The
        #: reads cost nothing — they are the mirror's.
        self.posts = 0
        self.judgments = 0
        #: Judgments run on their own worker when `async_judge` (the running
        #: service): a local-model judgment takes 30–130 s, and a look at
        #: every other request must not wait for it (p2 step 4). Tests judge
        #: inline.
        self.async_judge = async_judge
        #: Answers older than this id are read as p1 read them (the trace's
        #: `receipts_from`). Since p2 an answer counts as taken up only by a
        #: served mark covering it; the listeners before p1's last fix
        #: (`87ac87e`) skipped a callback in a ✔'d topic and left the mark on
        #: the post before it, so on their records a delivered answer reads
        #: unmarked (p2 step 5: nine finished p1 tasks flagged on the first
        #: look, then again as ✔-while-awaiting-delivery). The service sets it
        #: once, at its first start, to the newest post it could see then.
        self.receipts_from = int(receipts_from or 0)
        #: Requests whose origin is older than this id keep the rules they
        #: were tracked under: no `unheld`/`quiet`, no escalation of a long
        #: postponement (failsafe p1). Their posts carry no `end=` evidence,
        #: and several are trial fixtures abandoned days ago; they are a
        #: person's decision, not a reason to nudge Front. 0 applies the
        #: failsafe contract to every request.
        self.obligations_from = int(obligations_from or 0)
        self._judge_lock = threading.Lock()
        self._judge_wake = threading.Event()
        self._pending_judgments: dict[str, tuple] = {}
        #: When each pending judgment was first asked for (a replacement with
        #: newer evidence keeps the original time: the backlog is the wait).
        self._queued_at: dict[str, float] = {}
        self._verdicts: dict[str, dict] = {}
        #: Verdicts thrown away because the evidence they judged had changed
        #: (robust_workflow p3 step 2), in total and per incident in a row.
        self.invalidated = 0
        self._invalidations: dict[str, int] = {}
        self.judging: dict[str, Any] | None = None
        self.last_judgment: dict[str, Any] | None = None
        self.cycle: dict[str, Any] = {"count": 0, "started_at": None, "completed_at": None,
                                      "duration_seconds": None, "in_progress": False}
        self.latest_failure: dict[str, Any] | None = None
        self.looked_last = 0
        #: The owners whose servings can be probed (`agobserver.health`);
        #: nobody when `.local/health.toml` lists none.
        self.probes = probes if probes is not None else HealthProbes.load(spec.local)
        #: This look's probe results, by the stalled unit's anchor: what a
        #: request and an incident say about it.
        self._health_reports: dict[int, dict[str, Any]] = {}
        #: This look's probes, run ahead of the per-request pass (`prefetch`).
        self._prefetched: dict[tuple[str, int, int], dict[str, Any]] = {}
        #: Requests a person retired (`agobserver.hold --retire`), this look.
        self._retired: dict[str, dict[str, Any]] = {}
        self.probe_budget = PROBE_BUDGET
        self.probe_workers = PROBE_WORKERS
        self.timing: dict[str, float] = dict(TIMING_DEFAULTS)
        self._base_interval = self.interval
        #: Recovered and reported incidents handed to the developer (step 4).
        self.reviews = Reviews(self)
        #: This look's queued posts by `agag.waits` state (failsafe p5).
        self.queue_stats: dict[str, int] = {}

    # --- the store -------------------------------------------------------------------

    def _path(self, key: str) -> Path:
        return self.store_dir / f"{hashlib.sha1(key.encode()).hexdigest()[:16]}.json"

    def load(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save(self, record: dict[str, Any]) -> None:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(record["key"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def records(self) -> list[dict[str, Any]]:
        if not self.store_dir.is_dir():
            return []
        found = []
        for path in sorted(self.store_dir.glob("*.json")):
            if "~" in path.stem or path.name in (TRACKED_FILE, STATE_FILE, HELD_FILE, HEALTH_STATE_FILE, REVIEWS_FILE,
                                                  EPISODES_FILE, RETIRED_FILE):
                continue  # an ended episode, or the index of tracked requests
            try:
                found.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return found

    # --- discovery -------------------------------------------------------------------

    def origins(self, now: float) -> list[tuple[str, str, int]]:
        """`(channel, live topic, anchor)` of every active request.

        A request **is** its conversation's first post (robust_workflow p2
        step 2): the name it is shown under changes with a rename or a ✔ and
        can be taken by another request; the id cannot."""
        found = []
        for index in self.mirror.topics(ORIGIN_CHANNEL, include_resolved=False):
            if not index.name.startswith(ORIGIN_PREFIX):
                continue
            messages = self.mirror.messages(ORIGIN_CHANNEL, index.live_name, across_resolve=False)
            if not messages:
                continue
            newest = messages[-1]
            if now - int(newest.timestamp or 0) > self.window:
                continue
            found.append((ORIGIN_CHANNEL, index.live_name, int(messages[0].id)))
        return found

    def where(self, message_id: int) -> tuple[str, str] | None:
        """Where a post is now, off the mirror: `(channel, live topic)`."""
        from agag.identity import whereabouts

        return whereabouts(self.mirror, int(message_id or 0))

    # --- the loop ---------------------------------------------------------------------

    def tick(self) -> list[dict[str, Any]]:
        """One look at every tracked request. Returns the incidents touched.
        The health record says when it began and, afterwards, how it went."""
        started = self.clock()
        self.cycle.update(started_at=started, in_progress=True)
        self.write_health()
        try:
            return self._tick()
        except Exception as error:  # noqa: BLE001 - recorded, then the loop's to handle
            self.latest_failure = {"at": self.clock(), "error": repr(error)[:500]}
            raise
        finally:
            done = self.clock()
            self.cycle.update(count=self.cycle["count"] + 1, completed_at=done,
                              duration_seconds=round(done - started, 3), in_progress=False)
            self.write_health()

    def read_timing(self) -> None:
        """The values in force this look: the operational ones, or a trial's
        overrides (`TIMING_FILE`)."""
        try:
            overrides = json.loads((self.spec.local / TIMING_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            overrides = {}
        timing = dict(TIMING_DEFAULTS)
        for key, value in (overrides if isinstance(overrides, dict) else {}).items():
            if key in timing and isinstance(value, (int, float)) and value > 0:
                timing[key] = float(value)
        interval = overrides.get("interval") if isinstance(overrides, dict) else None
        self.interval = float(interval) if isinstance(interval, (int, float)) and interval > 0 else self._base_interval
        if timing != self.timing:
            log(f"monitor: timing now {timing} (interval {self.interval:g}s)")
        self.timing = timing

    def _tick(self) -> list[dict[str, Any]]:
        self.read_timing()
        if self.ticks % SUBSCRIBE_EVERY == 0:
            try:
                self.ensure_subscribed()
            except Exception as error:  # noqa: BLE001 - a failed check is tried again later
                log(f"monitor: could not check subscriptions: {error!r}")
        self.ticks += 1
        now = self.clock()
        fresh = self.fresh()
        touched: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        looked: dict[str, Any] = {}
        gone: set[str] = set()
        reader = MirrorReader(self.mirror)
        tracked = self.load_tracked()
        held = self.load_held()
        self._retired = self.load_retired()
        health = self.load_health()
        self._health = health
        self._health_reports = {}
        self.queue_stats = {}
        traced = []
        for channel, topic, anchor in self.requests(now, tracked):
            result = trace(reader, anchor, now=int(now), receipts_from=self.receipts_from)
            if result.root is None:
                gone.add(origin_key(anchor))
                continue
            looked[origin_key(anchor)] = result
            traced.append((channel, topic, anchor, result))
        if fresh:
            self.prefetch([result for _, _, anchor, result in traced
                           if self.failsafe(anchor) and origin_key(anchor) not in held], now, health)
        for channel, topic, anchor, result in traced:
            self._nodes = {int(n.anchor): n for n in result.nodes() if n.anchor}
            found = [c for c in stall_candidates(result, now=int(now))
                     if not self.is_own(c) and (c.kind not in FAILSAFE_KINDS or self.failsafe(anchor))
                     and not (c.kind in REPLACED_KINDS and self.failsafe(anchor) and self.probed(c))]
            if fresh:
                found = self.review_queues(found, result, [r for *_, r in traced], anchor, now, health)
            if self.failsafe(anchor) and fresh and origin_key(anchor) not in held:
                found += self.health_candidates(result, now, health)
            closed = self.origin_closed(result, tracked.get(origin_key(anchor)), now)
            if closed is not None and not found:
                # Anything else found here is reported through the ✔ origin
                # already; this is for the work nothing else would flag.
                found.append(closed)
            if origin_key(anchor) in held or self.retired_now(origin_key(anchor), result):
                continue  # a person has taken it over, or found nothing owed (`agobserver.hold`)
            for candidate in primary(found):
                # Our own recovery request, not yet taken up, is the incident
                # it belongs to — watched by its retry and report — never an
                # incident of its own (`is_own`).
                key = incident_key(anchor, candidate)
                seen_keys.add(key)
                try:
                    touched.append(self.handle(candidate, result, (channel, topic, anchor), now, fresh=fresh))
                except Exception as error:  # noqa: BLE001 - one incident must not stop the look
                    log(f"monitor: incident {key} failed this tick: {error!r}")
        for record in self.records():
            okey = record.get("origin", {}).get("key")
            try:
                if record.get("state") == REPORTED and okey in looked and not record.get("cleared_at"):
                    self.cleared(record, looked[okey], now, fresh)
                if record.get("state") == REPORTED and record.get("cleared_at") \
                        and "moving" not in ((record.get("review") or {}).get("updates") or {}):
                    # Moving again before reviews kept later outcomes (p2's C
                    # and D): said once, with the time it was seen.
                    self.reviews.later(record, "moving", f"the work moved again at {_when(record['cleared_at'])} "
                                                         "(seen in its incident topic then)")
                    self.save(record)
                if record.get("state") in (RESCUED, REPORTED) and okey in looked and fresh:
                    self.final_outcome(record, looked[okey], now)
                if record.get("state") == DISMISSED and record["key"] not in seen_keys and okey in looked and fresh:
                    touched.append(self.settle(record, looked[okey], now))
                    continue
                if record.get("state") in CLOSED or record.get("state") == DISMISSED or record["key"] in seen_keys:
                    continue
                if okey in gone and fresh:
                    touched.append(self.report(record, now, "the conversation the request came from no longer "
                                                            "exists, so there is nobody there to ask"))
                elif okey in looked:
                    touched.append(self.verify(record, looked[okey], now, fresh))
            except Exception as error:  # noqa: BLE001
                log(f"monitor: checking {record['key']} failed: {error!r}")
        self.retain(tracked, looked, gone if fresh else set(), now, held)
        if self.ticks % PRUNE_EVERY == 1:
            self.prune(now, tracked, held)
        self.save_health(health, now)
        if fresh:
            self.reviews.deliver(self.records())
        self.looked_last = len(looked)
        return touched

    def origin_closed(self, result, entry: dict[str, Any] | None, now: float) -> Candidate | None:
        """The request's own conversation is ✔ and work opened for it is not
        finished — nothing below would ever say so (robust_workflow p2 step
        5): answers are not delivered into a finished conversation, and a ✔
        cancels nothing. Seen for `ORIGIN_CLOSED_GRACE`, it is a candidate;
        its incident is reported, since there is nobody there to ask."""
        root = result.root
        if entry is None or not root.topic.startswith(RESOLVED_TOPIC_PREFIX):
            if entry is not None:
                entry.pop("closed_seen", None)
            return None
        unfinished = [n for n in result.nodes() if n is not root and n.state not in ("done", "cancelled")
                      and not satisfied(n)]
        if not unfinished:
            return None
        seen = float(entry.setdefault("closed_seen", now))
        if now - seen < ORIGIN_CLOSED_GRACE:
            return None
        listed = ", ".join(f"`{n.topic}` {n.state.replace('_', ' ')}" for n in unfinished[:4])
        return Candidate(
            "origin_closed", root.channel, root.topic, root.identity,
            f"the request's conversation is ✔ while {len(unfinished)} conversation(s) opened for it are unfinished: "
            f"{listed}", "whoever resolved it",
            "un-✔ it if the work should go on (`agentchat unresolve`), or record a decision on the unfinished work",
            int(seen), (root.anchor,), anchor=root.anchor,
        )

    def failsafe(self, origin_anchor: int) -> bool:
        """Whether a request is held to the failsafe contract."""
        return int(origin_anchor) >= self.obligations_from

    # --- the health path (failsafe p2) --------------------------------------------------

    def probed(self, candidate: Candidate) -> bool:
        """Whether the unit a candidate is about belongs to an owner whose
        servings are probed: its silence is checked, not judged."""
        node = self.node_of(candidate)
        return node is not None and self.probes.covers(node.owner)

    def load_health(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads((self.store_dir / HEALTH_STATE_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save_health(self, health: dict[str, dict[str, Any]], now: float) -> None:
        for key in [k for k, v in health.items() if now - float(v.get("looked_at") or 0) > HEALTH_STATE_TTL]:
            del health[key]
        self.store_dir.mkdir(parents=True, exist_ok=True)
        path = self.store_dir / HEALTH_STATE_FILE
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(health, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(path)

    def _units(self, result, now: float, health: dict[str, dict[str, Any]]):
        """`(node, entry, progress_at, due)` for every unfinished unit of a
        probed owner: `due` when a probe has to look at it now."""
        nodes = list(result.nodes())
        root = result.root
        human_wait = any(n.state == "awaiting_human" for n in nodes)
        # Somebody holds the move while any serving in the request is open or
        # a post in it waits for its ack — the request's own conversation
        # included: a person who just answered there is being served (trial
        # A/D: a mission waiting on its acceptance was suspected in the
        # seconds between the answer and the record).
        open_anywhere = any(n.execution == "open" or n.state == "queued" for n in nodes)
        newest = max((n.last_activity for n in nodes if n is not root), default=0)
        for node in nodes:
            if node is root or not node.identity or node.state in TERMINAL or not self.probes.covers(node.owner):
                continue
            if node.topic.startswith(RESOLVED_TOPIC_PREFIX) and node.execution != "open":
                continue  # a ✔ on it is `resolved_live`'s question
            entry = health.get(str(node.anchor))
            if entry is not None and int(entry.get("ack") or 0) != int(node.ack or 0):
                entry = None  # another serving: its own evidence, from scratch
            progress_at = max(int(node.last_activity or 0), int(node.ack_at or 0), int(node.work_at or 0))
            if node.execution == "open":
                due = now - progress_at >= self.timing["probe_after"]
            elif node.execution == "ended" and node.holder in ("requester", "unknown") \
                    and node.ending_intent != "response_request" and not node.waiting_on:
                due = not human_wait and not open_anywhere and now - newest >= self.timing["quiet_check"]
            else:
                due = False
            yield node, entry, progress_at, due

    def prefetch(self, results, now: float, health: dict[str, dict[str, Any]]) -> None:
        """Run this look's due probes side by side, within `probe_budget`.

        A probe still running at the budget is recorded as not answering;
        its thread ends at the probe's own timeout. The per-request pass
        then reads these results instead of probing one unit after another."""
        jobs = {}
        for result in results:
            for node, _, _, due in self._units(result, now, health):
                if due:
                    jobs[(node.owner, int(node.ack or 0), int(node.anchor))] = node
            for node in self._queued(result, now):
                jobs[(node.owner, 0, int(node.anchor))] = node
        self._prefetched = {}
        slow = self._slow_probes()
        if not jobs:
            return
        pool = ThreadPoolExecutor(max_workers=max(1, min(self.probe_workers, len(jobs) + slow)),
                                  thread_name_prefix="probe")
        for n in range(slow):
            pool.submit(self._slow_probe, n)
        futures = {pool.submit(self.probes.probe, node.owner, ack=node.ack, channel=node.channel, topic=node.topic,
                               window=self.timing["probe_after"],
                               **({"queued_since": float(node.last_activity or 0)} if not key[1] else {})): key
                   for key, node in jobs.items()}
        done, late = wait(futures, timeout=self.probe_budget)
        pool.shutdown(wait=False, cancel_futures=True)
        for future in done:
            try:
                self._prefetched[futures[future]] = future.result()
            except Exception as error:  # noqa: BLE001 - a probe answers, it does not raise
                self._prefetched[futures[future]] = unknown(f"the health probe failed: {error!r}")
        for future in late:
            owner = futures[future][0]
            self._prefetched[futures[future]] = unknown(
                f"the health probe of {owner} did not answer within this look's probe budget "
                f"({self.probe_budget:g} s for {len(jobs)} probe(s))")
        if late:
            log(f"monitor: {len(late)} of {len(jobs)} probe(s) did not answer within {self.probe_budget:g} s")

    def _queued(self, result, now: float):
        """Posts a probed owner has not acknowledged for as long as
        `unacknowledged` waits: where each is in that owner's queue is read
        in this look's probes (failsafe p5)."""
        root = result.root
        for node in result.nodes():
            if node is not root and node.state == "queued" and self.probes.covers(node.owner) \
                    and now - int(node.last_activity or 0) >= THRESHOLDS["unacknowledged"]:
                yield node

    def queue_wait(self, node, results, now: float) -> waits.QueueWait:
        """Why this post waits, read as the panel reads it (`agag.waits`)."""
        if self.probes.covers(node.owner):
            key = (node.owner, 0, int(node.anchor))
            report = self._prefetched.pop(key, None) if key in self._prefetched else self.probes.probe_queue(
                node.owner, channel=node.channel, topic=node.topic, since=float(node.last_activity or 0),
                window=self.timing["probe_after"])
            return waits.from_probe(node, report, now)
        return waits.from_conversation(node, waits.open_servings(results, int(now)), int(now))

    def review_queues(self, found: list[Candidate], result, results, origin_anchor: int, now: float,
                      health: dict[str, dict[str, Any]]) -> list[Candidate]:
        """`unacknowledged` candidates, read against the queue (module doc):
        dropped while the post waits behind healthy work or behind a
        blocker another tracked request holds, turned into `unserved` when
        the listener is not serving it, kept as they are otherwise."""
        kept: list[Candidate] = []
        root = result.root
        for candidate in found:
            node = self._nodes.get(int(candidate.anchor or 0)) if candidate.kind == "unacknowledged" else None
            if node is None or node is root:
                kept.append(candidate)
                continue
            wait = self.queue_wait(node, results, now)
            state = self._remember_wait(health, node, wait, now)
            self.queue_stats[wait.state] = self.queue_stats.get(wait.state, 0) + 1
            if wait.excused:
                self._excuse(origin_anchor, candidate, wait, now)
                continue
            post = f"#{wait.post}" if wait.post else "the post"
            if wait.state == waits.BLOCKED:
                blocker = self._blocker(wait, results)
                since = float(state.get("blocked_since") or now)
                if blocker is not None and now - since < self.timing["escalate_after"]:
                    continue  # the serving ahead is its own request's incident
                where = f"{wait.ahead[0].get('channel')}/{wait.ahead[0].get('topic')}" if wait.ahead else "?"
                kept.append(replace(
                    candidate, kind=QUEUE_KIND,
                    fact=f"{post} waits behind {where}, which is not confirmed healthy: {wait.why}"
                         + ("" if blocker is None else f" (for {_age(now - since)})"),
                    responsible=f"{node.owner}'s operator",
                    next_action=f"the serving ahead ({where}) is recovered or ended, so {node.owner} reaches {post}; "
                                "nothing is to be posted where the post waits"))
                continue
            if wait.state == waits.UNSERVED:
                kept.append(replace(
                    candidate, kind=QUEUE_KIND, fact=f"{post} is not being served: {wait.why}",
                    responsible=f"{node.owner}'s operator",
                    next_action=f"a person looks at why {node.owner}'s listener is not serving it (a stuck executor "
                                "is restarted); another post there only joins the same queue"))
                continue
            kept.append(replace(candidate, fact=f"{candidate.fact}; {wait.why}" if wait.why else candidate.fact))
        return kept

    def _remember_wait(self, health: dict[str, dict[str, Any]], node, wait: waits.QueueWait,
                       now: float) -> dict[str, Any]:
        """The wait's history for this post: first seen, the original queued
        time, and each change of what is ahead (kept in the health state)."""
        key = f"q{int(node.anchor)}"
        state = health.get(key)
        if state is None or int(state.get("post") or 0) != int(wait.post):
            state = {"post": wait.post, "queued_at": wait.queued_at, "first_seen": now, "changes": []}
        ahead = [f"{row.get('channel')}/{row.get('topic')}" + (f"#{row['ack']}" if row.get("ack") else "")
                 for row in wait.ahead]
        if [state.get("state"), state.get("ahead")] != [wait.state, ahead]:
            state["changes"] = [*state.get("changes", [])[-9:], {"at": now, "state": wait.state, "ahead": ahead,
                                                                 "why": wait.why[:300]}]
        if wait.state == waits.BLOCKED:
            state.setdefault("blocked_since", now)
        else:
            state.pop("blocked_since", None)
        state.update(state=wait.state, ahead=ahead, evidence=wait.evidence, why=wait.why[:300],
                     observed_at=wait.observed_at, looked_at=now, owner=node.owner, topic=node.topic)
        health[key] = state
        return state

    def _blocker(self, wait: waits.QueueWait, results):
        """The serving ahead, when a traced request holds it."""
        for row in wait.ahead:
            name = (row.get("channel"), _bare(str(row.get("topic") or "")))
            for result in results:
                for node in result.nodes():
                    if (node.channel, _bare(node.topic)) == name and node.state not in TERMINAL:
                        return node
        return None

    def _excuse(self, origin_anchor: int, candidate: Candidate, wait: waits.QueueWait, now: float) -> None:
        """An incident opened on a wait now confirmed legitimate ends
        `excused`: nothing had stalled, and nothing is claimed rescued."""
        record = self.load(incident_key(origin_anchor, candidate))
        if record is None or record.get("state") in CLOSED:
            return
        self.close(record, now, EXCUSED, f"the post is queued behind healthy work, a legitimate wait "
                                         f"({wait.evidence}): {wait.why}")

    def _slow_probes(self) -> int:
        try:
            return max(0, int((self.spec.local / FAULTS_DIR / PROBE_SLOW_FAULT).read_text(encoding="utf-8").strip()
                              or "0"))
        except (OSError, ValueError):
            return 0

    def _slow_probe(self, n: int) -> None:
        """One injected probe of no unit that uses its whole timeout."""
        timeout = max([float(e.get("timeout") or 10) for e in getattr(self.probes, "owners", {}).values()] or [10.0])
        time.sleep(timeout)

    def _probe(self, node) -> dict[str, Any]:
        key = (node.owner, int(node.ack or 0), int(node.anchor))
        if key in self._prefetched:
            return self._prefetched.pop(key)
        return self.probes.probe(node.owner, ack=node.ack, channel=node.channel, topic=node.topic,
                                 window=self.timing["probe_after"])

    def _idle_wait(self, entry: dict[str, Any], report: dict[str, Any], now: float) -> dict[str, Any]:
        """A `waiting` verdict, reassessed against this unit's history
        (failsafe p3). The same wait whose process tree added no CPU time for
        `wait_idle`, and that declares no bound of its own, is uncertainty;
        a wait that advances, or a new wait, starts its clock again."""
        wait = report.get("wait") or {}
        key = f"{wait.get('kind')}:{wait.get('id') or wait.get('name') or ''}:{wait.get('since') or ''}"
        cpu = float(wait.get("cpu_seconds") or 0.0)
        kept = entry.get("wait") or {}
        if kept.get("key") != key:
            kept = {"key": key, "since": now, "cpu": cpu, "advanced_at": now,
                    "bounded": wait.get("bound_seconds") is not None}
        elif cpu >= float(kept.get("cpu") or 0.0) + WAIT_CPU_STEP:
            kept.update(cpu=cpu, advanced_at=now)
        entry["wait"] = kept
        idle = now - float(kept["advanced_at"])
        if kept["bounded"] or idle < self.timing["wait_idle"]:
            return report
        what = wait.get("name") or f"{wait.get('count') or 'its'} process(es)"
        return {**report, "verdict": "unknown",
                "why": f"{report.get('why')}; nothing under it has advanced for {int(idle)} s "
                       f"({cpu:g} s CPU, unchanged), and {what} declares no bound of its own",
                "unknowns": [*report.get("unknowns", []), "whether the wait is still advancing"]}

    def health_candidates(self, result, now: float, health: dict[str, dict[str, Any]]) -> list[Candidate]:
        """Units of work a probe could not confirm are being done.

        For each unfinished unit of a probed owner (`probed`):

        - an **open serving** with no confirmed progress (a post, or the
          harness's own work events) for `PROBE_AFTER`, probed every look
          while that lasts;
        - a serving that **ended asking nobody anything** — no response
          request, no delegate, no person asked anywhere in the request —
          with nothing moving in the request for `QUIET_CHECK`.

        `running`, or `waiting` on a live wait that is explained — inside
        the tool's own bound, or still advancing (`_idle_wait`) — is healthy
        and clears the suspicion. `stopped` is a confirmed stop: a candidate
        at once. Anything else is uncertainty, dated from the **first** look
        that could not confirm health: a repeated claim, another unknown or
        the same evidence again does not move that date (`first_suspicion`),
        so it reaches Front after `ASK_AFTER` whatever is said meanwhile.
        """
        found: list[Candidate] = []
        for node, entry, progress_at, due in self._units(result, now, health):
            key = str(node.anchor)
            if not due:
                if entry is not None and entry.get("first_suspicion") and progress_at > float(entry.get("progress_at") or 0):
                    entry.update(first_suspicion=None, cleared_at=now, cleared_by="progress")
                if entry is not None:
                    entry["looked_at"] = now
                continue
            if entry is None:
                entry = {"ack": int(node.ack or 0), "topic": node.topic, "checks": []}
            health[key] = entry
            report = self._probe(node)
            if report.get("verdict") == "waiting":
                report = self._idle_wait(entry, report, now)
            else:
                entry.pop("wait", None)
            self._health_reports[int(node.anchor)] = report
            verdict = str(report.get("verdict") or "unknown")
            progress = report.get("progress") or {}
            event_at = float(progress.get("last_work_at") or progress.get("last_event_at") or 0)
            entry["progress_at"] = max(float(progress_at), event_at if verdict in ("running", "waiting") else 0.0)
            evidence = f"{verdict}|{report.get('why', '')}"
            if evidence != entry.get("evidence"):
                check = {"at": now, "verdict": verdict, "why": str(report.get("why", ""))[:300]}
                injected = (report.get("run") or {}).get("injected")
                if injected or "fault injected" in check["why"]:
                    # A trial, on the record of the check that saw it (p3):
                    # the review must not read it as an operational failure.
                    check["injected"] = (injected or {}).get("fault") or check["why"].split("fault injected: ")[-1] \
                        .split(")")[0]
                entry["checks"] = [*entry.get("checks", [])[-9:], check]
            entry.update(evidence=evidence, looked_at=now, verdict=verdict, checked_at=now,
                         checks_run=int(entry.get("checks_run", 0)) + 1)
            if verdict in ("running", "waiting"):
                if entry.get("first_suspicion"):
                    entry.update(first_suspicion=None, cleared_at=now, cleared_by=verdict)
                entry.setdefault("healthy_since", now)
                continue
            entry.pop("healthy_since", None)
            entry["first_suspicion"] = entry.get("first_suspicion") or now
            onset = self._onset(node, report)
            entry.setdefault("onset", onset)
            if verdict == "stopped":
                found.append(self._health_candidate("stopped", node, report, onset))
            elif now - float(entry["first_suspicion"]) >= self.timing["ask_after"]:
                found.append(self._health_candidate("uncertain", node, report, onset))
        return found

    @staticmethod
    def _onset(node, report: dict[str, Any]) -> float:
        """When the work stopped, as well as the evidence says: the recorded
        end of the run, else its last harness event, else the serving's
        own end or last activity."""
        run = report.get("run") or {}
        process = report.get("process") or {}
        for value in (process.get("ended_at"), run.get("ended_at"), (report.get("progress") or {}).get("last_event_at"),
                      node.ended_at, node.last_activity):
            if value:
                return float(value)
        return 0.0

    def _health_candidate(self, kind: str, node, report: dict[str, Any], onset: float) -> Candidate:
        why = str(report.get("why") or "the health probe established nothing")
        if kind == "stopped":
            fact = f"a health check found the work stopped: {why}"
            action = (f"whoever asked for it resumes it (a post in {node.channel}/{_bare(node.topic)} starts a new "
                      "serving, which continues from what the work left), or decides otherwise")
        else:
            fact = f"a health check could not confirm the work is being done: {why}"
            action = ("whoever asked for it investigates — asks its owner, checks what it is waiting for — and "
                      "resumes it only once nothing is running; a second run beside a live one is not recovery")
        return Candidate(kind, node.channel, node.topic, node.identity, fact, _asker(node), action, int(onset or 0),
                         (int(node.ack or node.anchor),), anchor=node.anchor)

    def timeline(self, record: dict[str, Any]) -> dict[str, Any]:
        """The incident's timeline from the unit's health state (step 1)."""
        state = getattr(self, "_health", None)
        state = state if state is not None else self.load_health()
        entry = state.get(str(record.get("node", {}).get("anchor") or 0)) or {}
        line = dict(record.get("timeline") or {})
        for field in ("onset", "first_suspicion", "progress_at"):
            if entry.get(field) and not line.get(field):
                line[field] = entry[field]
        line["checks"] = entry.get("checks", line.get("checks", []))
        return line

    # --- which requests are looked at -----------------------------------------------

    def fresh(self) -> bool:
        """Whether the mirror is live — a look that can conclude anything."""
        if self.fault("mirror-stale", consume=False):
            return False
        try:
            return self.mirror.health().get("state") == "live"
        except Exception:  # noqa: BLE001 - a mirror that cannot say is not fresh
            return False

    def load_tracked(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads((self.store_dir / TRACKED_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def load_retired(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads((self.store_dir / RETIRED_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def retired_now(self, okey: str, result) -> bool:
        """Retired, and nothing posted in the request since: a retirement
        lapses by itself when the request moves again."""
        entry = self._retired.get(okey)
        if entry is None:
            return False
        newest = max((int(n.last_activity or 0) for n in result.nodes()), default=0)
        return newest <= float(entry.get("at") or 0)

    def load_held(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads((self.store_dir / HELD_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save_tracked(self, tracked: dict[str, dict[str, Any]]) -> None:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        path = self.store_dir / TRACKED_FILE
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(tracked, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(path)

    def requests(self, now: float, tracked: dict[str, dict[str, Any]]) -> list[tuple[str, str, int]]:
        """Recent requests (discovery) and every request already being
        tracked (retention), each once, where its origin is now.

        Discovery is the window over `#front`; retention is the index this
        monitor keeps of requests it has seen with work outstanding, plus the
        origin of every open incident — so a request that goes quiet for a
        day, is ✔'d, renamed or outlives a restart is still looked at until
        its outcome is established (robust_workflow p2 step 3). A lost index
        is rebuilt from the incident records, whose origins are ids."""
        found: dict[int, tuple[str, str, int]] = {}
        for channel, topic, anchor in self.origins(now):
            found[anchor] = (channel, topic, anchor)
        anchors = {int(k[1:]) for k in (*tracked, *self.load_held()) if k.startswith("o") and k[1:].isdigit()}
        anchors |= {int(r["origin"]["message_id"]) for r in self.records()
                    if r.get("state") not in CLOSED and r.get("origin", {}).get("message_id")}
        for anchor in sorted(anchors - set(found)):
            where = self.where(anchor)
            found[anchor] = (where[0], where[1], anchor) if where else (ORIGIN_CHANNEL, "", anchor)
        return list(found.values())

    def retain(self, tracked: dict[str, dict[str, Any]], looked: dict[str, Any], gone: set[str], now: float,
               held: dict[str, Any] | None = None) -> None:
        """Keep a request while anything below it is unfinished or an incident
        of it is open; let it go once neither is true. The index holds only
        what this monitor has looked at — never the realm's history.

        Unfinished means not `TERMINAL`, and only a record makes a
        conversation terminal (robust_workflow p3 step 2). Until then a ✔
        judged a legitimate wait was counted as finished here, and a request
        whose one task waited on the human left the index in the same look
        (step 1, W1): "nobody needs to be asked" was read as "this is over".
        A dismissal stops the nudges; it ends nothing.

        A plain conversation whose exchange is complete (`satisfied`) is not
        outstanding (failsafe p3): until then every Front → agent exchange
        without a unit of work kept its request tracked for ever. A held
        request stays, whatever its conversations say. A request that left
        is found again by the window when its conversation moves."""
        records = self.records()
        open_origins = {r.get("origin", {}).get("key") for r in records
                        if r.get("state") not in CLOSED and r.get("state") != DISMISSED}
        changed = False
        due = self.next_reviews(records, now)
        held = held or {}
        for okey, result in looked.items():
            root = result.root
            outstanding = [n for n in result.nodes()
                           if n is not root and n.state not in TERMINAL and not satisfied(n)]
            if root.state in ("queued", "executing", "failed") or root.execution == "open":
                # The requester's own conversation owes an answer (a new post,
                # a serving in progress, a failure notice): that is an
                # obligation as much as unfinished work below it.
                outstanding.append(root)
            if self.retired_now(okey, result) and okey not in open_origins:
                outstanding = []  # a person found nothing owed here (`hold --retire`)
            if outstanding or okey in open_origins or okey in held:
                entry = tracked.get(okey)
                if entry is None:
                    entry = tracked[okey] = {"since": now, "topic": result.root.topic}
                # What is owed and who holds it, as of this look (failsafe
                # p1): the facts a reader — or this monitor after a restart —
                # needs without re-deriving the history.
                entry.update(
                    topic=result.root.topic, last_looked=now,
                    evidence_at=max((n.last_activity for n in outstanding), default=0),
                    obligations={str(n.anchor): {"topic": n.topic, "identity": n.identity, "state": n.state,
                                                 "execution": n.execution, "holder": n.holder}
                                 for n in outstanding},
                    next_review=min(due.get(okey, now + self.interval), now + self.interval),
                    contract="failsafe" if self.failsafe(result.root.anchor) else "before-failsafe",
                )
                changed = True  # `last_looked` (and `closed_seen`) move every look
            elif okey in tracked:
                del tracked[okey]
                changed = True
        for okey in gone:
            if okey in tracked and okey not in open_origins and okey not in held:
                del tracked[okey]
                changed = True
        if changed:
            self.save_tracked(tracked)

    def next_reviews(self, records: list[dict[str, Any]], now: float) -> dict[str, float]:
        """When each request's open incident next needs a look beyond the
        ordinary one: a postponed judgment's due time, a retry's."""
        due: dict[str, float] = {}
        for record in records:
            okey = record.get("origin", {}).get("key")
            if not okey or record.get("state") in CLOSED:
                continue
            at = now + self.interval
            if record.get("state") == DISMISSED:
                at = float(record.get("dismissed_at", now)) + float(record.get("postpone_seconds") or REJUDGE_SECONDS)
            elif record.get("requests"):
                at = float(record["requests"][-1]["at"]) + RETRY_SECONDS
            due[okey] = min(due.get(okey, at), at)
        return due

    def ensure_subscribed(self) -> list[str]:
        """Join every public channel the mirror knows and the bot has not,
        and re-read the realm when any was added — the moves missed there are
        gone from the queue. The relay's reader does the same
        (`agentroom.subscriptions`). robust_workflow p1 step 4 found it the
        hard way: p3's `✔ workplan-locations-2` read as still running, because
        this bot had never joined `#pj-protoprey` and its mirror kept the
        pre-✔ name on every message before the resolve."""
        joined = {str(row.get("name")) for row in self.client.subscriptions()}
        missing = sorted(channel.name for channel in self.mirror.channels() if channel.name not in joined)
        if not missing:
            return []
        self.client.subscribe_channels(missing)
        log(f"monitor: joined {len(missing)} channel(s) so their renames and ✔ reach the mirror; re-reading the realm")
        self.mirror.resync()
        return missing

    def escalation_due(self, record: dict[str, Any], now: float) -> str:
        """Why the developer is told now, or "": the unit has been in doubt
        for `ESCALATE_AFTER` since its first suspicion and no fresh evidence
        of work has ended the incident."""
        line = record.get("timeline") or {}
        since = float(line.get("first_suspicion") or record.get("detected_at") or now)
        if now - since < self.timing["escalate_after"]:
            return ""
        asked = len(record.get("requests", []))
        return (f"{_age(now - since)} after the first suspicion ({_clock(since)}) there is still no fresh evidence "
                f"that the work is being done, after {asked} request(s) to Front")

    def timeline_lines(self, record: dict[str, Any]) -> list[str]:
        line = record.get("timeline") or {}
        if not line:
            return []
        parts = [f"onset ≈ {_clock(line.get('onset'))}" if line.get("onset") else "",
                 f"last confirmed progress {_clock(line.get('progress_at'))}" if line.get("progress_at") else "",
                 f"first suspicion {_clock(line.get('first_suspicion'))}" if line.get("first_suspicion") else "",
                 f"{len(line.get('checks') or [])} distinct health check result(s)" if line.get("checks") else ""]
        parts = [p for p in parts if p]
        return [f"- Timeline: {'; '.join(parts)}."] if parts else []

    def is_own(self, candidate: Candidate) -> bool:
        if candidate.kind != "unacknowledged" or not candidate.evidence:
            return False
        message = self.mirror.message(int(candidate.evidence[0]))
        return message is not None and int(message.sender_id) == self.self_id

    def handle(self, candidate: Candidate, result, origin: tuple[str, str, int], now: float, *,
               fresh: bool = True) -> dict[str, Any]:
        key = incident_key(origin[2], candidate)
        record = self.load(key)
        if record is not None and (record.get("state") in (RESCUED, CANCELLED, FINISHED, WITHDRAWN)
                                   or record.get("cleared_at")):
            # That incident ended — the work moved, or a decision closed it —
            # and this is the same work stalling again: a new incident.
            self.archive(record)
            record = None
        if record is None:
            if not fresh:
                return {"key": key, "state": "unconfirmed", "kind": candidate.kind}
            record = self.open(candidate, origin, now, episode=self.episodes(key) + 1)
        if record.get("state") in CLOSED:
            return record
        if not fresh:
            # A look off a stale copy of the realm asks nobody anything.
            return record
        # Where things are *now*: a rename since the last look is display.
        record["origin"].update(channel=origin[0], topic=origin[1])
        record["node"].update(channel=candidate.channel, topic=candidate.topic)
        if candidate.kind != record.get("kind"):
            # The same stalled work, blocked differently: the same incident,
            # the same allowance of requests (robust_workflow p2 step 1, R2).
            self.post_incident(record, f"Now **{candidate.kind}**: {candidate.fact}")
            record.setdefault("kinds", [record.get("kind")]).append(candidate.kind)
            record["kind"] = candidate.kind
            record.pop("judgment", None)
            record["next_action"], record["responsible"] = candidate.next_action, candidate.responsible
            self.save(record)  # said once: every path below may return early
        if record.get("state") == DISMISSED and not candidate.judgment:
            # The dismissal answered a judged question (was that ✔ a
            # mistake? is that silence a long job?). A mechanical fact on the
            # same work — an answer nobody served — is not covered by it
            # (p2 step 5, trial A2: a ✔ judged a deliberate close hid the
            # undelivered report behind it).
            record["state"] = DETECTED
            record.pop("dismissed_at", None)
        if record.get("state") == DISMISSED:
            if int(record.get("postponed_evidence") or -1) != int(candidate.since):
                # The evidence moved since the wait was judged: a new wait.
                record.pop("postponed_since", None)
            if candidate.kind in POSTPONABLE and self.failsafe(origin[2]) and record.get("postponed_since") \
                    and now - float(record["postponed_since"]) >= MAX_POSTPONED_SECONDS:
                return self.report(record, now, f"it has been judged a legitimate wait for "
                                                f"{_age(now - float(record['postponed_since']))} while nothing moved; "
                                                "a person should confirm that it is still wanted and still running")
            if now - float(record.get("dismissed_at", 0)) < float(record.get("postpone_seconds") or REJUDGE_SECONDS):
                return record
            if candidate.kind == "resolved_live" and int(record.get("judged_activity") or -1) == int(candidate.since):
                # A ✔ judged a deliberate close, and nothing has been said in
                # that conversation since: the same question gets the same
                # answer, and each asking is a local-model run (30–130 s).
                return record
            record["state"] = DETECTED
            record["rejudging"] = True
            record.pop("judgment", None)
        record["last_seen"] = now
        record["fact"] = candidate.fact

        if candidate.judgment and record.get("judgment") \
                and record["judgment"].get("snapshot") != self.snapshot(candidate, result):
            # A `stall` on record drives the next request and the report.
            # Judged on a state that has since moved (somebody answered,
            # a record landed), it is asked again before it is acted on —
            # the requests already made still count.
            log(f"monitor: {record['topic']}: the evidence behind its `{record['judgment'].get('verdict')}` "
                "verdict changed; judging it again")
            record.pop("judgment", None)
        if candidate.judgment and not record.get("judgment"):
            verdict = self.judged(candidate, result, record)
            if verdict is None and now - float(record.get("judging_since") or now) >= JUDGMENT_DEADLINE_SECONDS:
                # The review does not wait on a judge that never answers.
                self.drop_judgment(record["key"])
                verdict = {"verdict": "unclear", "evidence": f"no verdict {JUDGMENT_DEADLINE_SECONDS // 60} min "
                                                             "after the judgment was asked for"}
            if verdict is None:
                record.setdefault("judging_since", now)
                self.save(record)
                return record
            record.pop("judging_since", None)
            record["judged_activity"] = int(candidate.since)
            if verdict["verdict"] == "legit":
                again = record.pop("rejudging", False)
                same = again and int(record.get("postponed_evidence") or -1) == int(candidate.since)
                wait = min(MAX_REJUDGE_SECONDS, 2 * float(record.get("postpone_seconds") or REJUDGE_SECONDS)) \
                    if same else REJUDGE_SECONDS
                record.update(state=DISMISSED, dismissed_at=now, judgment=verdict, postpone_seconds=wait,
                              postponed_evidence=int(candidate.since))
                record.setdefault("postponed_since", now)
                record["postponements"] = int(record.get("postponements", 0)) + 1
                if not again:
                    # A second look that agrees with the first is not news.
                    self.post_incident(record, f"Not a stall, on a look at the conversation: {verdict['evidence']}. "
                                               f"I look again in {int(wait) // 60} min if it is still like this.")
                self.save(record)
                return record
            record.pop("rejudging", None)
            if verdict["verdict"] == "unclear":
                record["unclear"] = int(record.get("unclear", 0)) + 1
                if record["unclear"] < MAX_UNCLEAR:
                    self.save(record)
                    return record
                return self.report(record, now, f"I cannot tell whether this is a stall: {verdict['evidence']}")
            record["judgment"] = verdict

        root = result.root
        if root.topic.startswith(RESOLVED_TOPIC_PREFIX):
            return self.report(record, now, "the conversation the request came from is ✔ closed, so there is nobody "
                                             "there to ask")
        if candidate.kind == "unanswered":
            # failsafe p3: its own listener already served the input twice
            # and both runs produced no usable reply — asking it a third time
            # buys a third run of the same failure.
            return self.report(record, now, f"{root.owner or 'the agent that owns it'} could not answer its requester "
                                             "there: its listener served the input twice and neither run produced a "
                                             "usable reply (the failure notice is the last word)")
        if candidate.kind == QUEUE_KIND:
            # failsafe p5: the owner's listener is not serving the post, or
            # the serving ahead of it is not healthy and nothing else holds
            # it. Nobody in the request can make a listener serve a post, and
            # asking Front would buy a post that joins the same queue.
            return self.report(record, now, f"{candidate.fact}; nobody in the request can make {node_owner(result, candidate)} "
                                             "serve it")
        if candidate.kind == "unacknowledged" and (candidate.channel, candidate.topic) == (root.channel, root.topic):
            return self.report(record, now, f"{root.owner or 'the agent that owns it'} itself is not answering "
                                             "there, so asking it would reach nobody")
        if record.get("kind") in HEALTH_KINDS:
            record["timeline"] = self.timeline(record)
            escalation = self.escalation_due(record, now)
            if escalation:
                return self.report(record, now, escalation)
        attempts = record.setdefault("requests", [])
        if attempts and now - float(attempts[-1]["at"]) < RETRY_SECONDS:
            self.save(record)
            return record
        if len(attempts) >= MAX_REQUESTS:
            return self.report(record, now, f"{len(attempts)} requests did not get it moving")
        where = self.asked_where(result, candidate, origin)
        message_id = self.request(record, candidate, origin, len(attempts) + 1, now, where=where, result=result)
        attempts.append({"at": now, "message_id": message_id, "where": f"{where[0]}/{where[1]}"})
        record["state"] = RECOVERING
        self.post_incident(record, f"Asked for recovery ({len(attempts)}/{MAX_REQUESTS}) in "
                                   f"`#{where[0]} › {where[1]}` (#{message_id}).")
        self.save(record)
        return record

    # --- the steps ---------------------------------------------------------------------

    def open(self, candidate: Candidate, origin: tuple[str, str, int], now: float, *,
             episode: int = 1) -> dict[str, Any]:
        key = incident_key(origin[2], candidate)
        topic = f"{INCIDENT_PREFIX}{candidate.kind}-{candidate.anchor or origin[2]}"
        if episode > 1:
            topic = f"{topic}-{episode}"
        if candidate.responsible.startswith("the agent that owns") and candidate.channel == ORIGIN_CHANNEL:
            # A conversation nobody has acknowledged names no owner of its
            # own; the entrance's owner is whoever acknowledges there (seen
            # in trial S1: a stop report that could only say "the agent").
            owner = self.entrance_owner()
            if owner:
                candidate = replace(candidate, responsible=f"{owner} (its listener owns every `{ORIGIN_PREFIX}…` "
                                                          f"conversation in #{ORIGIN_CHANNEL})")
        record = {
            "key": key, "kind": candidate.kind, "state": DETECTED, "detected_at": now,
            "topic": topic, "since": candidate.since,
            "origin": {"channel": origin[0], "topic": origin[1], "message_id": origin[2],
                       "key": origin_key(origin[2])},
            "node": {"channel": candidate.channel, "topic": candidate.topic, "identity": candidate.identity,
                     "anchor": candidate.anchor},
            "fact": candidate.fact, "responsible": candidate.responsible, "next_action": candidate.next_action,
            "evidence": list(candidate.evidence), "episode": episode,
        }
        if candidate.kind in HEALTH_KINDS:
            record["timeline"] = self.timeline(record)
        owner_node = self.node_of(candidate)
        if owner_node is not None and owner_node.owner:
            record["owner"] = owner_node.owner
        node = self.node_of(candidate)
        if node is not None:
            # The serving the stall was seen after: a recovery is a later one
            # that did work (`recovered`).
            record["ack_at_detection"] = node.ack
        adopted = self.adopt(record, now)
        if adopted is not None:
            return adopted
        where = f"`#{candidate.channel} › {candidate.topic}`" + (f" ({candidate.identity})" if candidate.identity else "")
        record["incident_anchor"] = self.post(self.spec.instance_name(), topic, "\n".join([
            f"**Incident: {candidate.kind}** in {where}, for the request in "
            f"`#{origin[0]} › {origin[1]}` (#{origin[2]}).",
            "",
            f"- What the records show: {candidate.fact}",
            f"- Since: {_when(candidate.since)} ({_age(now - candidate.since)})",
            f"- Expected next: {candidate.next_action}",
            f"- Responsible: {candidate.responsible}",
            f"- Evidence: message ids {', '.join(f'#{i}' for i in candidate.evidence if i) or '—'}; "
            f"`agentchat trace {origin[2]}`",
            *health_lines(self._health_reports.get(int(candidate.anchor or 0))),
            *self.timeline_lines(record),
        ]))
        self.post_incident(record, note(INCIDENT_TAG, f"{key} e{episode} origin #{origin[2]}"))
        self.save(record)
        log(f"monitor: incident {topic} opened for {key}")
        return record

    def adopt(self, record: dict[str, Any], now: float) -> dict[str, Any] | None:
        """The store was lost; the record in Zulip was not. Find the incident
        by its `[selfnote][incident] <key>` note — wherever its topic is now
        and whatever it is called — and carry on from what it says: the
        requests already made count, and a closed incident stays closed.
        Never a second topic, never a request asked again blindly."""
        channel = self.spec.instance_name()
        episode = f"e{record.get('episode', 1)}"
        for found in self.mirror.notes(tag=INCIDENT_TAG, sender_id=self.self_id, channel=channel):
            words = found.value.split()
            if words[0:1] != [record["key"]] or (words[1:2] != [episode] and episode != "e1"):
                continue
            if episode == "e1" and len(words) > 1 and words[1].startswith("e") and words[1] != "e1":
                continue
            message = self.mirror.message(found.message_id)
            if message is None:
                continue
            history = self.mirror.messages(channel, message.topic, across_resolve=True)
            own = [m for m in history if m.sender_id == self.self_id]
            asked = [m for m in own if m.content.startswith("Asked for recovery (")]
            states = [m.content.split("[selfnote][state]", 1)[1].strip() for m in own
                      if m.content.startswith("[selfnote][state]")]
            record.update(adopted=True, topic=message.topic, incident_anchor=int(found.message_id),
                          requests=[{"at": float(m.timestamp), "message_id": 0} for m in asked])
            record["state"] = states[-1] if states and states[-1] in CLOSED else (RECOVERING if asked else DETECTED)
            self.save(record)
            log(f"monitor: adopted {message.topic} for {record['key']} ({len(asked)} request(s) on record)")
            return record
        return None

    def node_of(self, candidate: Candidate):
        return getattr(self, "_nodes", {}).get(int(candidate.anchor or 0))

    def entrance_owner(self) -> str:
        """Who acknowledged posts in the origin channel most recently."""
        from agag.agent import is_ack

        for index in sorted(self.mirror.topics(ORIGIN_CHANNEL), key=lambda t: -t.max_id)[:20]:
            for message in reversed(self.mirror.messages(ORIGIN_CHANNEL, index.live_name, limit=40)):
                if is_ack(message.content.strip()):
                    return message.sender_name
        return ""

    def snapshot(self, candidate: Candidate, result) -> str:
        """What a judgment of `candidate` rests on, as one comparable string.

        robust_workflow p3 step 2. A local-model judgment takes 30–130 s on
        its own worker, and the conversation it reads can move meanwhile —
        the human answers, the owner records a cancellation, an acceptance
        lands. A verdict is an answer about *that* state, so it travels with
        the identity of that state and is used only while the state is the
        same (step 1, J1: a `stall` about the conversation before the human's
        answer went out as a recovery request after it).

        The smallest thing that notices a meaningful change: the kind and
        the stalled conversation's traced state and ✔, the newest relevant
        post there (speech by anybody but Observer, or a note that changes
        what the work is — a state, a receipt, a start), and the same for the
        request's own conversation, where the human answers. Observer's own
        posts and other agents' bookkeeping notes do not make a verdict
        stale."""
        node = next((n for n in result.nodes() if candidate.anchor and n.anchor == candidate.anchor), None)
        state = node.state if node is not None else "?"
        resolved = int(candidate.topic.startswith(RESOLVED_TOPIC_PREFIX))
        here = self._newest_relevant(candidate.channel, candidate.topic)
        root = result.root
        home = self._newest_relevant(root.channel, root.topic) if root is not None else 0
        return f"{candidate.kind}|{state}|{resolved}|n{here}|o{home}"

    def _newest_relevant(self, channel: str, topic: str) -> int:
        from agag.selfnote import is_selfnote, is_speech, parse_note

        for message in reversed(self.mirror.messages(channel, topic)):
            if int(message.sender_id) == self.self_id:
                continue
            content = message.content
            if is_speech(message.as_zulip()) or (
                    is_selfnote(content) and any(parse_note(content, tag) is not None for tag in RELEVANT_NOTES)):
                return int(message.id)
        return 0

    def judged(self, candidate: Candidate, result, record: dict[str, Any]) -> dict[str, str] | None:
        """The verdict on this candidate, or None while it is being judged.

        Inline in tests; on the service a judgment is queued for the judge
        worker with a snapshot of what it is to read, and the look moves on
        to the other requests — the verdict is picked up by a later look.

        A verdict is used only for the evidence it judged (`snapshot`). One
        that comes back about a state that has since changed is discarded
        and the current state is queued instead — the incident keeps its
        allowance of requests, since nothing was asked on it. A pending job
        is replaced by the newer one rather than queued beside it, so one
        incident never has more than one judgment waiting; every discard is
        counted, and an incident whose evidence keeps moving under its
        judgment is named in the health record (`CHURN_LIMIT`)."""
        tail = [m.as_zulip() for m in self.mirror.messages(candidate.channel, candidate.topic)[-10:]]
        root = result.root
        home = [] if root is None or (root.channel, root.topic) == (candidate.channel, candidate.topic) else \
            [m.as_zulip() for m in self.mirror.messages(root.channel, root.topic)[-5 * triage.HOME_MESSAGES:]]
        snapshot = self.snapshot(candidate, result)
        job = (candidate, "\n".join(trace_lines(result)), tail, record["topic"], snapshot,
               home, f"#{root.channel} › {root.topic}" if root is not None else "")
        key = record["key"]
        if not self.async_judge:
            return self._run_judgment(key, job)
        with self._judge_lock:
            verdict = self._verdicts.pop(key, None)
            if verdict is not None and verdict.get("snapshot") != snapshot:
                self.invalidated += 1
                self._invalidations[key] = self._invalidations.get(key, 0) + 1
                log(f"monitor: the verdict on {record['topic']} ({verdict.get('verdict')}) judged evidence that has "
                    f"changed ({verdict.get('snapshot')} → {snapshot}); judging the current state instead")
                verdict = None
            if verdict is not None:
                self._invalidations.pop(key, None)
                return verdict
            running = self.judging or {}
            if running.get("key") == key and running.get("snapshot") == snapshot:
                return None  # the current evidence is being judged right now
            pending = self._pending_judgments.get(key)
            if pending is None or pending[4] != snapshot:
                self._pending_judgments[key] = job
                self._queued_at.setdefault(key, self.clock())
                self._judge_wake.set()
        return None

    def drop_judgment(self, key: str) -> None:
        with self._judge_lock:
            self._pending_judgments.pop(key, None)
            self._queued_at.pop(key, None)
            self._verdicts.pop(key, None)

    def _run_judgment(self, key: str, job: tuple) -> dict[str, str]:
        candidate, trace_text, tail, topic, snapshot, home, home_name = job
        self.judgments += 1
        started = self.clock()
        with self._judge_lock:
            self.judging = {"key": key, "topic": topic, "since": started, "snapshot": snapshot}
        # The record follows the judgment as well as the cycle: written only
        # per cycle, a judgment that ended after the last write read as still
        # running to the watchdog (p2 step 5: a false `judgment_stalled`).
        self.write_health()
        try:
            if self.fault("triage-stall", consume=False):
                log(f"monitor: fault injected: the judgment of {topic} is held until the fault file is removed")
                while self.fault("triage-stall", consume=False):
                    time.sleep(1.0)
            verdict = dict(self.judge(self.spec, candidate, trace_text, tail, topic, home=home, home_name=home_name,
                                      snapshot=snapshot))
        finally:
            with self._judge_lock:
                self.judging = None
        verdict["snapshot"] = snapshot
        self.last_judgment = {"key": key, "topic": topic, "at": self.clock(),
                              "seconds": round(self.clock() - started, 1), "verdict": verdict.get("verdict")}
        self.write_health()
        log(f"monitor: {topic} judged {verdict.get('verdict')} in {self.last_judgment['seconds']}s: "
            f"{verdict.get('evidence', '')[:200]}")
        return verdict

    def judge_forever(self, stop: threading.Event) -> None:
        """The judge worker: one judgment at a time, off the look loop."""
        while not stop.is_set():
            self._judge_wake.wait(5.0)
            with self._judge_lock:
                if not self._pending_judgments:
                    self._judge_wake.clear()
                    continue
                key = next(iter(self._pending_judgments))
                job = self._pending_judgments.pop(key)
                self._queued_at.pop(key, None)
            try:
                verdict = self._run_judgment(key, job)
            except Exception as error:  # noqa: BLE001 - a failed judgment is an answer
                verdict = {"verdict": "unclear", "evidence": f"the judgment failed: {error!r}", "snapshot": job[4]}
            with self._judge_lock:
                self._verdicts[key] = verdict

    def asked_where(self, result, candidate: Candidate, origin: tuple[str, str, int]) -> tuple[str, str]:
        """Where a recovery request goes: the conversation closest above the
        stalled work that the request's owner (Front) itself holds — a
        routine's run rather than the Front Desk above it (failsafe p1).
        Whatever Front sends while serving a conversation is anchored to it,
        so an answer to a resumption asked for from the Front Desk would
        come back there and never reach the run that is waiting for it.
        Only the failsafe kinds and a silence are routed this way; the
        older kinds keep the request's own conversation."""
        where = self.where(origin[2]) or (origin[0], origin[1])
        root = result.root if result is not None else None
        if root is None or candidate.kind not in (*WORK_KINDS, "silent") or not root.owner:
            return where
        path = _path_to(root, int(candidate.anchor or 0))
        for node in reversed(path[:-1]):
            if node is root:
                break
            if node.owner == root.owner and not node.topic.startswith(RESOLVED_TOPIC_PREFIX) \
                    and node.state not in TERMINAL:
                return (node.channel, node.topic)
        return where

    def request(self, record: dict[str, Any], candidate: Candidate, origin: tuple[str, str, int],
                number: int, now: float, *, where: tuple[str, str] | None = None, result=None) -> int:
        stalled = f"#**{candidate.channel}>{_bare(candidate.topic)}**" + (
            f" ({candidate.identity})" if candidate.identity else "")
        node = self.find({"node": {"anchor": candidate.anchor}}, result) if result is not None else None
        headline = {"uncertain": "I cannot confirm that work this request depends on is being done",
                    "stopped": "Work this request depends on has stopped"}.get(
            candidate.kind, "Something this request depends on has stopped")
        lines = [
            f"**[Observer] {headline}** — {stalled}.",
            "",
            f"- The request: #**{origin[0]}>{_bare(origin[1])}** (#{origin[2]}).",
            f"- What the records show: {candidate.fact} (since {_when(candidate.since)}, {_age(now - candidate.since)}).",
        ]
        health = self._health_reports.get(int(candidate.anchor or 0)) if candidate.kind in HEALTH_KINDS else None
        if node is not None:
            lines.append(f"- Execution: {_execution_words(node, health)}.")
            lines.append(f"- What is still owed: {_owed_words(node)}.")
        lines += health_lines(health)
        lines += self.timeline_lines(record) if candidate.kind in HEALTH_KINDS else []
        lines += [
            f"- Expected next: {candidate.next_action}.",
            f"- Responsible: {candidate.responsible}.",
            f"- Evidence: `agentchat trace {origin[2]}`, observed {_when(now)}.",
        ]
        stopped_ack = int(record.get("ack_at_detection") or (node.ack if node is not None else 0) or 0)
        if candidate.kind in WORK_KINDS and candidate.anchor and stopped_ack:
            # failsafe p4: this post is evidence as of now. The work may move
            # before it is read — a requester resuming it, the owner's own
            # recovery — and a second start beside it is the one wrong move,
            # so the exact re-check is named: that conversation, that serving.
            lines.append(f"- Re-check right before acting: `agentchat recheck {int(candidate.anchor)} "
                         f"--after {stopped_ack}` — it says whether this work has resumed since.")
        if candidate.kind not in HEALTH_KINDS or not health:
            # For a checked unit the check's own unknowns are listed above; the
            # conversation-only doubt ("it may be a long job; do not start a
            # second run") contradicted a confirmed stop and kept Front from
            # resuming it (failsafe p3 trial A).
            lines.append(f"- Not known: {_unknown_words(candidate, node)}")
        if candidate.kind in HEALTH_KINDS:
            since = float((record.get("timeline") or {}).get("first_suspicion") or now)
            lines += ["", f"Please get it moving, or find out and say here why it waits. If nothing shows the work "
                          f"moving by {_clock(since + self.timing['escalate_after'])} I tell the developer (`{record['topic']}` in "
                          "my channel)."]
        else:
            lines += ["", f"Please get it moving, or say here why it should wait. Request {number} of {MAX_REQUESTS} "
                          f"for `{record['topic']}` in my channel; after that I report it and stop asking."]
        # Information that answers nothing (`agag.post`): whoever serves this
        # conversation replies to the person who asked for the work, never to
        # Observer — trial T1/T3 saw Front address its confirmations here.
        from agag.post import NONE, REPORT, PostMeta, compose

        text = compose("\n".join(lines), PostMeta(intent=REPORT, answer=NONE))
        where = where or self.where(origin[2]) or (origin[0], origin[1])
        if candidate.kind == "undelivered" and candidate.evidence:
            # The answer, named for the requester's listener: the serving
            # this request starts is its receipt once it replies (`owed`),
            # which is what lets the next look see the recovery at all.
            from agag.selfnote import Conversation, owed_note

            self.post(where[0], where[1], owed_note(Conversation(candidate.channel, candidate.topic),
                                                    int(candidate.evidence[0])))
        return self.post(where[0], where[1], text)

    def find(self, record: dict[str, Any], result):
        """The incident's conversation in this look, by its anchor."""
        anchor = int(record.get("node", {}).get("anchor") or 0)
        if not anchor:
            return None
        return next((node for node in result.nodes() if node.anchor == anchor), None)

    def verify(self, record: dict[str, Any], result, now: float, fresh: bool) -> dict[str, Any]:
        """The candidate is not produced on this look. That is absence, and
        absence alone concludes nothing (robust_workflow p2 step 3): the
        work may have moved, or it may be unreadable, blocked differently
        inside that blockage's grace, or closed by somebody's decision. Only
        a fresh look that reads the conversation and finds the transition
        this incident was waiting for is a recovery."""
        if not fresh:
            record["stale_looks"] = int(record.get("stale_looks", 0)) + 1
            self.save(record)
            return record
        node = self.find(record, result)
        if node is None or node.state == "unobservable":
            return self.unobservable(record, now, "it is not in the request's trace any more" if node is None
                                     else node.detail)
        if record.pop("unobservable_since", None) is not None:
            self.post_incident(record, f"Readable again at {_when(now)}.")
        if node.state == "cancelled":
            return self.close(record, now, CANCELLED, f"`{node.note_state or 'cancelled'}` is recorded in "
                                                      f"`{node.topic}`: a decision, not a recovery")
        if node.state == "done" and record.get("kind") in ("resolved_live", "origin_closed") \
                and node.topic.startswith(RESOLVED_TOPIC_PREFIX):
            # A ✔ on work that is now recorded finished is the ordinary
            # close, not a stall that somebody broke.
            return self.close(record, now, FINISHED, f"`{node.note_state or 'done'}` is recorded in `{node.topic}`")
        if self.recovered(record, node):
            return self.rescued(record, now, node)
        if record.get("kind") in HEALTH_KINDS:
            escalation = self.escalation_due(record, now)
            if escalation:
                return self.report(record, now, escalation)
        # Still blocked, perhaps differently and not yet overdue: open, no
        # request until a candidate says it is owed again.
        if record.get("waiting") != node.state:
            record["waiting"] = node.state
            self.save(record)
        return record

    @staticmethod
    def recovered(record: dict[str, Any], node) -> bool:
        """Whether `node` shows the transition this incident waited for."""
        kind = record.get("kind", "")
        if kind in ("resolved_live", "origin_closed") and node.topic.startswith(RESOLVED_TOPIC_PREFIX):
            return False
        if kind in WORK_KINDS:
            # Evidence of work, not an acknowledgement and not another
            # promise (failsafe p1): a serving that began after the stall was
            # seen, and either did something while open or ended handing the
            # move to somebody. A resumed serving that ends saying "work goes
            # on" again is the same stall.
            if node.state in TERMINAL:
                return True
            if kind == "uncertain" and int(node.work_at or 0) > float(record.get("detected_at") or 0) \
                    and (node.execution == "open" or node.holder not in ("none", "unknown")):
                # The doubted serving was alive after all and did work after
                # the doubt: fresh evidence, from the same serving (failsafe
                # p2 trial D). A `stopped` one needs a new serving.
                return True
            resumed = node.ack > int(record.get("ack_at_detection") or 0)
            if not resumed:
                return False
            if node.execution == "open":
                return node.work > node.ack
            return node.execution == "ended" and node.holder not in ("none", "unknown")
        if kind == "silent" and node.state == "executing":
            return node.last_activity > int(record.get("since") or 0)
        return node.state in RECOVERED_STATES.get(kind, MOVED_ON)

    def unobservable(self, record: dict[str, Any], now: float, why: str) -> dict[str, Any]:
        """The stalled work cannot be read. Nothing is concluded; said once,
        and reported once it has lasted `UNOBSERVABLE_REPORT_SECONDS`."""
        since = record.get("unobservable_since")
        if since is None:
            record["unobservable_since"] = now
            self.post_incident(record, f"I cannot see `{record['node']['topic']}` on the look at {_when(now)} "
                                       f"({why}); nothing is concluded until I can.")
            self.save(record)
            return record
        if now - float(since) >= UNOBSERVABLE_REPORT_SECONDS:
            return self.report(record, now, f"I have not been able to see `{record['node']['topic']}` since "
                                            f"{_when(float(since))} ({why})")
        return record

    def rescued(self, record: dict[str, Any], now: float, node) -> dict[str, Any]:
        """The transition this incident waited for is on record."""
        asked = len(record.get("requests", []))
        record.update(state=RESCUED, rescued_at=now, cause="open", outcome=node.state)
        if self.failsafe(int(record.get("origin", {}).get("message_id") or 0)):
            self.reviews.mark(record)
        how = f"after {asked} request(s)" if asked else "with nothing asked (it recovered by itself)"
        self.post_incident(record, f"**Rescued** {how}: on the look at {_when(now)} `{node.topic}` is "
                                   f"{node.state.replace('_', ' ')} ({node.detail}). The cause is not removed by this "
                                   "— it stays open as a defect to fix.")
        self.post_incident(record, note("state", "rescued"))
        self.save(record)
        log(f"monitor: {record['topic']} rescued {how} ({node.state})")
        return record

    def settle(self, record: dict[str, Any], result, now: float) -> dict[str, Any]:
        """A dismissed incident — a wait judged legitimate — whose candidate
        is not produced on this look. It ends only when the work records an
        outcome: `done` closes it as finished, a cancellation as cancelled.
        Anything else (the ✔ undone, the grace of a new post, the work still
        waiting) leaves it dismissed, and a later stall of the same work
        re-opens it by the ordinary path (robust_workflow p3 step 2)."""
        node = self.find(record, result)
        if node is None or node.state not in TERMINAL:
            return record
        if node.state == "cancelled":
            return self.close(record, now, CANCELLED, f"`{node.note_state or 'cancelled'}` is recorded in "
                                                      f"`{node.topic}`: a decision, after a wait nobody had to break")
        return self.close(record, now, FINISHED, f"`{node.note_state or 'done'}` is recorded in `{node.topic}`: "
                                                 "the wait ended with the work's own record, and nobody was asked")

    def close(self, record: dict[str, Any], now: float, state: str, why: str) -> dict[str, Any]:
        record.update(state=state, closed_at=now, why=why)
        self.post_incident(record, f"**Closed, {state}**: {why}.")
        self.post_incident(record, note("state", state))
        self.save(record)
        log(f"monitor: {record['topic']} {state}: {why}")
        return record

    def cleared(self, record: dict[str, Any], result, now: float, fresh: bool) -> None:
        """A reported incident whose work moved again afterwards: said, and
        a later stall of the same work may open a new incident."""
        node = self.find(record, result) if fresh else None
        if node is None or not self.recovered(record, node):
            return
        record["cleared_at"] = now
        self.post_incident(record, f"Moving again at {_when(now)}: `{node.topic}` is "
                                   f"{node.state.replace('_', ' ')}.")
        self.reviews.later(record, "moving", f"the work moved again at {_when(now)}: `{node.topic}` is "
                                             f"{node.state.replace('_', ' ')}")
        self.save(record)

    def final_outcome(self, record: dict[str, Any], result, now: float) -> None:
        """The stalled work's own record, once it has one (`done`/`cancelled`),
        for an incident handed to a review (failsafe p3): the review shows
        how it ended, beside what was seen at the time."""
        if record.get("final_outcome") or not (record.get("review") or {}).get("delivered"):
            return
        node = self.find(record, result)
        if node is None or node.state not in TERMINAL:
            return
        record["final_outcome"] = {"state": node.state, "at": now, "detail": str(node.detail)[:200]}
        self.reviews.later(record, "final", f"the work's own record says `{node.state}` "
                                            f"(seen {_when(now)}; {str(node.detail)[:160]})")
        self.save(record)

    def episodes(self, key: str) -> int:
        """How many ended episodes this incident key has had: the archives
        still kept, or the count kept when they were pruned (`prune`)."""
        kept = len(list(self.store_dir.glob(f"{self._path(key).stem}~*.json")))
        return max(kept, int(self._episode_counts().get(key, 0)))

    def _episode_counts(self) -> dict[str, int]:
        try:
            return json.loads((self.store_dir / EPISODES_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def archive(self, record: dict[str, Any]) -> None:
        """Move an ended incident aside so the same work can have a new one."""
        path = self._path(record["key"])
        n = self.episodes(record["key"]) + 1
        try:
            path.replace(path.with_name(f"{path.stem}~{n}.json"))
        except OSError:
            return
        counts = self._episode_counts()
        counts[record["key"]] = n
        tmp = self.store_dir / f"{EPISODES_FILE}.tmp"
        tmp.write_text(json.dumps(counts, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(self.store_dir / EPISODES_FILE)

    def prune(self, now: float, tracked: dict[str, Any], held: dict[str, Any]) -> int:
        """Forget closed incidents nothing refers to any more (failsafe p3).

        A record is kept while it is open, while its request is tracked or
        held, while its review handoff or a later outcome is owed, and for
        `INCIDENT_TTL` after its last change. Its topic and notes in Zulip
        stay: they are the record; this is only the monitor's cache. Ended
        episodes keep their count, so a later episode never reuses a name."""
        removed = 0
        for path in self.store_dir.glob("*.json") if self.store_dir.is_dir() else []:
            if path.name in (TRACKED_FILE, STATE_FILE, HELD_FILE, HEALTH_STATE_FILE, REVIEWS_FILE, EPISODES_FILE,
                             RETIRED_FILE):
                continue
            try:
                if now - path.stat().st_mtime < INCIDENT_TTL:
                    continue
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            review = record.get("review") or {}
            owed = review.get("owed") or any(u.get("owed") for u in (review.get("updates") or {}).values())
            okey = (record.get("origin") or {}).get("key")
            if "~" not in path.stem and record.get("state") not in CLOSED:
                continue
            if owed or okey in tracked or okey in held:
                continue
            if "~" not in path.stem:
                self.archive(record)  # counted, then removed with the archives
                path = path.with_name(f"{path.stem}~{self.episodes(record['key'])}.json")
            path.unlink(missing_ok=True)
            removed += 1
        if removed:
            log(f"monitor: pruned {removed} closed incident record(s) older than {INCIDENT_TTL // 86400} days")
        return removed

    def report(self, record: dict[str, Any], now: float, why: str) -> dict[str, Any]:
        """Nobody left to ask: tell the realm's owners, by name, and stop."""
        record.update(state=REPORTED, reported_at=now, cause="open", why=why)
        if self.failsafe(int(record.get("origin", {}).get("message_id") or 0)):
            self.reviews.mark(record)
        names = " ".join(f"@**{name}**" for name in self.report_to())
        self.post_incident(record, "\n".join([
            f"{names} **Stopped: I could not get this moving.** {why}.",
            "",
            f"- What the records show: {record.get('fact', '')}",
            f"- Expected next: {record.get('next_action', '')}",
            f"- Responsible: {record.get('responsible', '')}",
            f"- The request: `#{record['origin']['channel']} › {record['origin']['topic']}` "
            f"(`agentchat trace {record['origin']['message_id']}`)",
            *(health_lines(self._health_reports.get(int(record.get("node", {}).get("anchor") or 0)))
              if record.get("kind") in HEALTH_KINDS else []),
            *(self.timeline_lines(record) if record.get("kind") in HEALTH_KINDS else []),
        ]))
        self.post_incident(record, note("state", "reported"))
        self.save(record)
        log(f"monitor: {record['topic']} reported: {why}")
        return record

    def report_to(self) -> list[str]:
        if self._report_to is None:
            try:
                owners = set(self.client.realm_owners())
                self._report_to = [str(u.get("full_name")) for u in self.client.users()
                                   if int(u.get("user_id", 0)) in owners and u.get("full_name")]
            except Exception as error:  # noqa: BLE001 - a report without a name is still a report
                log(f"monitor: could not read the realm's owners: {error!r}")
                self._report_to = []
        return self._report_to

    # --- posting -----------------------------------------------------------------------

    def post(self, channel: str, topic: str, text: str) -> int:
        self.posts += 1
        return int(deliver(self.client, channel, topic, text, self_id=self.self_id, after_id=0, log=log) or 0)

    def post_incident(self, record: dict[str, Any], text: str) -> int:
        where = self.where(int(record.get("incident_anchor") or 0))
        topic = where[1] if where is not None and where[0] == self.spec.instance_name() else record["topic"]
        message_id = self.post(self.spec.instance_name(), topic, text)
        record.setdefault("incident_anchor", message_id)
        return message_id

    def run(self, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        log(f"request monitor starting (every {self.interval:g}s, requests active in the last "
            f"{self.window / 3600:g} h)")
        while not stop.is_set():
            if self.fault("monitor-stop"):
                log("monitor: fault injected: the monitor thread stops here; the process stays up")
                return
            started = self.clock()
            try:
                self.tick()
            except Exception as error:  # noqa: BLE001 - the loop outlives its ticks
                log(f"monitor tick failed: {error!r}")
            stop.wait(max(1.0, self.interval - max(0.0, self.clock() - started)))

    # --- health ----------------------------------------------------------------------------

    def fault(self, name: str, *, consume: bool = True) -> bool:
        path = self.spec.local / FAULTS_DIR / name
        if not path.exists():
            return False
        if consume:
            path.unlink(missing_ok=True)
        return True

    def health(self) -> dict[str, Any]:
        """What this monitor has been doing, for somebody who is not it."""
        now = self.clock()
        tracked = self.load_tracked()
        looked = [float(entry.get("last_looked") or entry.get("since") or now) for entry in tracked.values()]
        try:
            source = self.mirror.health()
        except Exception as error:  # noqa: BLE001
            source = {"state": "unknown", "reason": repr(error)}
        if self.fault("mirror-stale", consume=False):
            source = {**source, "state": "stale", "reason": "fault injected (mirror-stale)"}
        with self._judge_lock:
            judging, pending = dict(self.judging or {}), len(self._pending_judgments)
            waiting = min(self._queued_at.values(), default=None)
            churning = sorted(key for key, count in self._invalidations.items() if count >= CHURN_LIMIT)
        records = self.records()
        return {
            "schema": HEALTH_SCHEMA,
            "written_at": now,
            "pid": os.getpid(),
            "enabled": True,
            "interval_seconds": self.interval,
            "timing": dict(self.timing),
            "window_hours": self.window / 3600,
            "cycle": dict(self.cycle),
            "source": {"state": source.get("state"), "reason": source.get("reason"),
                       "stale_since": source.get("stale_since"), "last_event_at": source.get("last_event_at")},
            "requests": {
                "tracked": len(tracked),
                "held": len(self.load_held()),
                "looked_last_cycle": self.looked_last,
                "oldest_unchecked_seconds": round(max((now - t for t in looked), default=0.0), 1),
                "open_incidents": sum(1 for r in records if r.get("state") not in CLOSED and r.get("state") != DISMISSED),
            },
            "judgment": {
                "running": judging or None,
                "pending": pending,
                "oldest_pending_seconds": round(now - waiting, 1) if waiting is not None else None,
                "invalidated": self.invalidated,
                "churning": churning,
                "last": self.last_judgment,
                "timeout_seconds": triage.TIMEOUT_SECONDS,
            },
            "latest_failure": self.latest_failure,
            "probes": self.probes.stats(),
            "queues": dict(self.queue_stats),
            "spent": {"posts": self.posts, "judgments": self.judgments, "probes": self.probes.runs},
        }

    def write_health(self) -> None:
        try:
            write_health(self.spec, self.health())
        except Exception as error:  # noqa: BLE001 - a health file must never stop the monitor
            log(f"monitor: could not write its health record: {error!r}")


def write_health(spec: AgentSpec, record: dict[str, Any]) -> None:
    path = spec.local / HEALTH_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def obligations_from(spec: AgentSpec, mirror) -> int:
    """The newest post this monitor could see when it first ran with the
    failsafe contract, kept in `STATE_FILE` beside `receipts_from`."""
    path = spec.local / "incidents" / STATE_FILE
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    if state.get("obligations_from"):
        return int(state["obligations_from"])
    newest = 0
    deadline = time.time() + 120
    while not newest and time.time() < deadline:
        newest = int(mirror.store.newest_id() or 0) if getattr(mirror, "live", False) else 0
        if not newest:
            time.sleep(1.0)
    if newest:
        state.update(obligations_from=newest, obligations_since=time.time())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
    return newest


def receipts_from(spec: AgentSpec, mirror) -> int:
    """The newest post this monitor could see when it first started, kept in
    `STATE_FILE` so a restart does not move it."""
    path = spec.local / "incidents" / STATE_FILE
    try:
        return int(json.loads(path.read_text(encoding="utf-8"))["receipts_from"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    newest = 0
    deadline = time.time() + 120
    while not newest and time.time() < deadline:
        # The mirror fills on its own thread; its first answer is the one.
        newest = int(mirror.store.newest_id() or 0) if getattr(mirror, "live", False) else 0
        if not newest:
            time.sleep(1.0)
    if newest:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"receipts_from": newest, "since": time.time()}), encoding="utf-8")
    return newest


def start(spec: AgentSpec, mirror, **kwargs) -> Monitor | None:
    """Run the monitor beside the watch worker, on its own client, with its
    judgments on a worker of their own."""
    if os.environ.get(ENABLED_ENV, "1").strip() in ("0", "false", "off"):
        log("request monitor is off")
        # Said in the record too: off is a state a watchdog must tell apart
        # from stopped.
        write_health(spec, {"schema": HEALTH_SCHEMA, "written_at": time.time(), "pid": os.getpid(),
                            "enabled": False})
        return None
    monitor = Monitor(spec, ZulipClient.from_env(spec.zulip_env), mirror, async_judge=True, **kwargs)
    stop = threading.Event()

    def begin() -> None:
        # On the monitor's own thread: the first start waits for the mirror.
        monitor.receipts_from = receipts_from(spec, mirror)
        log(f"request monitor judges answers after #{monitor.receipts_from} by their served marks")
        monitor.obligations_from = obligations_from(spec, mirror)
        log(f"request monitor holds requests from #{monitor.obligations_from} to the failsafe contract")
        monitor.run(stop)

    threading.Thread(target=monitor.judge_forever, args=(stop,), name="observer-judge", daemon=True).start()
    threading.Thread(target=begin, name="observer-monitor", daemon=True).start()
    return monitor
