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
4. **Ask the responsible side to recover**, in the conversation the request
   came from: Front owns it, holds every tool the recovery needs (`agentchat
   send`, `unresolve`, `trace`), and the human reads it there. At most
   `MAX_REQUESTS`, `RETRY_SECONDS` apart, each preceded by a fresh look.
5. **Verify.** A request is not recovery. The incident is *rescued* only when
   a later look no longer finds the candidate; otherwise, when the requests
   are spent — or when there is nobody to ask (the request's own conversation
   is ✔, or its owner is the one not answering) — it is **reported** to the
   realm's owners by name and Observer stops.
6. **Record.** One `incident-<kind>-<id>` topic in Observer's own channel per
   incident: what was found and on what evidence, each request, each look,
   and the outcome. Being rescued is not the cause being removed: the
   outcome line says which it was, and the cause stays open.

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
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from agag.agent import AgentSpec
from agag.delivery import deliver
from agag.selfnote import note
from agag.trace import Candidate, MirrorReader, stall_candidates, trace, trace_lines
from agag.zulip import RESOLVED_TOPIC_PREFIX, ZulipClient, log

from . import triage

INTERVAL_ENV = "AGOBSERVER_MONITOR_SECONDS"
DEFAULT_INTERVAL_SECONDS = 120.0
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
#: A wait judged legitimate is looked at again after this long.
REJUDGE_SECONDS = 3600
#: Two unclear judgments and the human decides.
MAX_UNCLEAR = 2
#: Every this many ticks (and on the first) the bot's subscriptions are
#: checked: a move — a rename, a ✔ — reaches only subscribers, so a mirror
#: on a bot that has not joined a channel keeps its conversations under their
#: old names for ever (seen on this very monitor's first live look, below).
SUBSCRIBE_EVERY = 5

DETECTED, RECOVERING, RESCUED, REPORTED, DISMISSED = "detected", "recovering", "rescued", "reported", "dismissed"
CLOSED = (RESCUED, REPORTED)

__all__ = ["Monitor", "is_incident_topic", "start"]


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


def _age(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60} min" if seconds < 5400 else f"{seconds // 3600} h {(seconds % 3600) // 60:02d} min"


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
PRIORITY = ("failed", "unacknowledged", "undelivered", "unstarted", "resolved_live", "silent")


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
                 report_to: list[str] | None = None) -> None:
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
        """One look at every active request. Returns the incidents touched."""
        if self.ticks % SUBSCRIBE_EVERY == 0:
            try:
                self.ensure_subscribed()
            except Exception as error:  # noqa: BLE001 - a failed check is tried again later
                log(f"monitor: could not check subscriptions: {error!r}")
        self.ticks += 1
        now = self.clock()
        touched: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        looked_origins: set[str] = set()
        reader = MirrorReader(self.mirror)
        for channel, topic, anchor in self.origins(now):
            result = trace(reader, anchor, now=int(now))
            if result.root is None:
                continue
            looked_origins.add(origin_key(anchor))
            for candidate in primary(c for c in stall_candidates(result, now=int(now)) if not self.is_own(c)):
                # Our own recovery request, not yet taken up, is the incident
                # it belongs to — watched by its retry and report — never an
                # incident of its own (`is_own`).
                key = incident_key(anchor, candidate)
                seen_keys.add(key)
                try:
                    touched.append(self.handle(candidate, result, (channel, topic, anchor), now))
                except Exception as error:  # noqa: BLE001 - one incident must not stop the look
                    log(f"monitor: incident {key} failed this tick: {error!r}")
        for record in self.records():
            if record.get("state") in CLOSED or record.get("state") == DISMISSED:
                continue
            if record.get("origin", {}).get("key") in looked_origins and record["key"] not in seen_keys:
                try:
                    touched.append(self.rescued(record, now))
                except Exception as error:  # noqa: BLE001
                    log(f"monitor: closing {record['key']} failed: {error!r}")
        return touched

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

    def is_own(self, candidate: Candidate) -> bool:
        if candidate.kind != "unacknowledged" or not candidate.evidence:
            return False
        message = self.mirror.message(int(candidate.evidence[0]))
        return message is not None and int(message.sender_id) == self.self_id

    def handle(self, candidate: Candidate, result, origin: tuple[str, str, int], now: float) -> dict[str, Any]:
        key = incident_key(origin[2], candidate)
        record = self.load(key)
        if record is None:
            record = self.open(candidate, origin, now)
        if record.get("state") in CLOSED:
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
        if record.get("state") == DISMISSED:
            if now - float(record.get("dismissed_at", 0)) < REJUDGE_SECONDS:
                return record
            record["state"] = DETECTED
            record["rejudging"] = True
            record.pop("judgment", None)
        record["last_seen"] = now
        record["fact"] = candidate.fact

        if candidate.judgment and not record.get("judgment"):
            verdict = self.judged(candidate, result, record)
            if verdict["verdict"] == "legit":
                again = record.pop("rejudging", False)
                record.update(state=DISMISSED, dismissed_at=now, judgment=verdict)
                if not again:
                    # A second look that agrees with the first is not news.
                    self.post_incident(record, f"Not a stall, on a look at the conversation: {verdict['evidence']}. "
                                               f"I look again in {REJUDGE_SECONDS // 60} min if it is still like this.")
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
        if candidate.kind == "unacknowledged" and (candidate.channel, candidate.topic) == (root.channel, root.topic):
            return self.report(record, now, f"{root.owner or 'the agent that owns it'} itself is not answering "
                                             "there, so asking it would reach nobody")
        attempts = record.setdefault("requests", [])
        if attempts and now - float(attempts[-1]["at"]) < RETRY_SECONDS:
            self.save(record)
            return record
        if len(attempts) >= MAX_REQUESTS:
            return self.report(record, now, f"{len(attempts)} requests did not get it moving")
        message_id = self.request(record, candidate, origin, len(attempts) + 1, now)
        attempts.append({"at": now, "message_id": message_id})
        record["state"] = RECOVERING
        self.post_incident(record, f"Asked for recovery ({len(attempts)}/{MAX_REQUESTS}) in "
                                   f"`#{origin[0]} › {origin[1]}` (#{message_id}).")
        self.save(record)
        return record

    # --- the steps ---------------------------------------------------------------------

    def open(self, candidate: Candidate, origin: tuple[str, str, int], now: float) -> dict[str, Any]:
        key = incident_key(origin[2], candidate)
        topic = f"{INCIDENT_PREFIX}{candidate.kind}-{candidate.anchor or origin[2]}"
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
            "evidence": list(candidate.evidence),
        }
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
        ]))
        self.post_incident(record, note(INCIDENT_TAG, f"{key} origin #{origin[2]}"))
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
        for found in self.mirror.notes(tag=INCIDENT_TAG, sender_id=self.self_id, channel=channel):
            if found.value.split()[0:1] != [record["key"]]:
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

    def entrance_owner(self) -> str:
        """Who acknowledged posts in the origin channel most recently."""
        from agag.agent import is_ack

        for index in sorted(self.mirror.topics(ORIGIN_CHANNEL), key=lambda t: -t.max_id)[:20]:
            for message in reversed(self.mirror.messages(ORIGIN_CHANNEL, index.live_name, limit=40)):
                if is_ack(message.content.strip()):
                    return message.sender_name
        return ""

    def judged(self, candidate: Candidate, result, record: dict[str, Any]) -> dict[str, str]:
        self.judgments += 1
        tail = [m.as_zulip() for m in self.mirror.messages(candidate.channel, candidate.topic)[-10:]]
        verdict = self.judge(self.spec, candidate, "\n".join(trace_lines(result)), tail, record["topic"])
        log(f"monitor: {record['topic']} judged {verdict.get('verdict')}: {verdict.get('evidence', '')[:200]}")
        return verdict

    def request(self, record: dict[str, Any], candidate: Candidate, origin: tuple[str, str, int],
                number: int, now: float) -> int:
        where = f"`#{candidate.channel} › {candidate.topic}`" + (f" ({candidate.identity})" if candidate.identity else "")
        text = "\n".join([
            f"**[Observer] Something this request depends on has stopped** — {where}.",
            "",
            f"- What the records show: {candidate.fact} (since {_when(candidate.since)}, {_age(now - candidate.since)}).",
            f"- Expected next: {candidate.next_action}.",
            f"- Responsible: {candidate.responsible}.",
            f"- Evidence: `agentchat trace {origin[2]}`, observed {_when(now)}.",
            "",
            f"Please get it moving, or say here why it should wait. Request {number} of {MAX_REQUESTS} for "
            f"`{record['topic']}` in my channel; after that I report it and stop asking.",
        ])
        where = self.where(origin[2]) or (origin[0], origin[1])
        return self.post(where[0], where[1], text)

    def rescued(self, record: dict[str, Any], now: float) -> dict[str, Any]:
        """The candidate is gone on a later look: the work moved again."""
        asked = len(record.get("requests", []))
        record.update(state=RESCUED, rescued_at=now, cause="open")
        how = f"after {asked} request(s)" if asked else "with nothing asked (it recovered by itself)"
        self.post_incident(record, f"**Rescued** {how}: on the look at {_when(now)} "
                                   f"`{record['node']['topic']}` is no longer {record['kind']}. The cause is not "
                                   "removed by this — it stays open as a defect to fix.")
        self.post_incident(record, note("state", "rescued"))
        self.save(record)
        log(f"monitor: {record['topic']} rescued {how}")
        return record

    def report(self, record: dict[str, Any], now: float, why: str) -> dict[str, Any]:
        """Nobody left to ask: tell the realm's owners, by name, and stop."""
        record.update(state=REPORTED, reported_at=now, cause="open", why=why)
        names = " ".join(f"@**{name}**" for name in self.report_to())
        self.post_incident(record, "\n".join([
            f"{names} **Stopped: I could not get this moving.** {why}.",
            "",
            f"- What the records show: {record.get('fact', '')}",
            f"- Expected next: {record.get('next_action', '')}",
            f"- Responsible: {record.get('responsible', '')}",
            f"- The request: `#{record['origin']['channel']} › {record['origin']['topic']}` "
            f"(`agentchat trace {record['origin']['message_id']}`)",
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
            started = self.clock()
            try:
                self.tick()
            except Exception as error:  # noqa: BLE001 - the loop outlives its ticks
                log(f"monitor tick failed: {error!r}")
            stop.wait(max(1.0, self.interval - max(0.0, self.clock() - started)))


def start(spec: AgentSpec, mirror, **kwargs) -> Monitor | None:
    """Run the monitor beside the watch worker, on its own client."""
    if os.environ.get(ENABLED_ENV, "1").strip() in ("0", "false", "off"):
        log("request monitor is off")
        return None
    monitor = Monitor(spec, ZulipClient.from_env(spec.zulip_env), mirror, **kwargs)
    threading.Thread(target=monitor.run, name="observer-monitor", daemon=True).start()
    return monitor
