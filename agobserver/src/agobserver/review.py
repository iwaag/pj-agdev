"""A recovered incident is handed to the developer, once, with its evidence.

failsafe p2 step 4. Recovery gets the work moving; it does not remove why it
stopped. Until now the incident topic said so ("the cause stays open") and
nobody was told. Each incident that closes **rescued** (verified recovery)
or **reported** (recovery did not happen, the owners were told) now becomes
an occurrence in a **developer review**: one topic in Observer's own
channel, which the Developer is subscribed to — the developer-facing
conversation that already exists; no issue tracker.

- **One review per signature**: the owner of the stalled work and the kind
  of stall that opened the incident (`autolab-agstudio1 · stopped`). That
  groups by what was *observed*, never by a guessed cause, and the review
  says so: a common cause is a hypothesis until somebody confirms it.
- **Each occurrence keeps its own evidence**: the incident (its topic and
  anchor), the request it belonged to, the timeline (onset, first
  suspicion, detection, requests to Front, recovery or report), durations,
  the health checks, the recovery action and outcome, what is confirmed
  and what is only a hypothesis, and improvement candidates.
- **Operational recovery and the review are two states.** The incident is
  rescued or reported (Observer's record); the review is open until the
  developer ✔'s its topic — their record that it was looked at, which is
  not an acceptance of the original task and changes nothing about it. An
  occurrence of a ✔'d review opens the next episode (`…-2`), linked to the
  earlier one.

**Recurrence policy** (small, on purpose):

| occurrence | notified |
|---|---|
| the first of a review | the realm's owners, by name |
| a recovered recurrence | appended quietly, except every third (3rd, 6th, …), which names the owners with the count |
| not recovered (reported) | always names the owners, marked as such |
| after the review was ✔'d | a new episode, naming the owners and the earlier review |

**Later outcomes join the occurrence** (failsafe p3). An incident keeps
moving after its handoff: a reported one gets its work moving again, and
the work eventually records how it ended. Each such fact is appended once
to the review, under its occurrence ("Occurrence 1 — later: …"), and the
original post — what was seen and told at the time — stays as it was. It is
owed on the incident record before it is posted and carries
`[selfnote][occurrence-update] <occurrence> <kind>`, so repeated looks and a
restart between the post and the record never post it twice.

**An assessment, not a per-kind script** (failsafe p3). Each occurrence says
what failed, the plausible cause **from this occurrence's own evidence**
(the health checks' words, the exit, the report's reason), how confident
that is, what evidence is missing, and one improvement or investigation
candidate. "Unknown" is a valid answer. A trial fault a person injected is
recognised from the evidence (the probe's `run.injected`, a probe's own
fault) and said so: it is not an operational recurrence.

**Review states are posts in the review** (`agobserver.review_status`):
`reviewed`, `fix planned`, `fixed`, `accepted limitation`, on one occurrence
or all, with a note and a reference. The topic's ✔ is still only "looked
at": it accepts no mission and fixes no defect.

**Recoverable, never duplicated.** A pending handoff is marked on the
incident record before anything is posted; each occurrence post carries
`[selfnote][occurrence] <incident key> e<episode>` and each review
`[selfnote][review] <signature> e<n>`, and before posting either the mirror
is read for it. An interruption between the post and the local record is
finished by the next pass without a second post; a lost store adopts the
review from its note.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from agag.selfnote import note, parse_note
from agag.zulip import RESOLVED_TOPIC_PREFIX

REVIEW_PREFIX = "review-"
REVIEW_TAG = "review"
OCCURRENCE_TAG = "occurrence"
UPDATE_TAG = "occurrence-update"
STATUS_TAG = "occurrence-status"
#: What a developer can record on an occurrence (`agobserver.review_status`).
STATUSES = ("reviewed", "fix planned", "fixed", "accepted limitation")
REVIEWS_FILE = "reviews.json"
#: Every this-many-th recovered recurrence names the owners again.
NOTIFY_EVERY = 3
#: Trial fault (one-shot, created only by a person): the process exits right
#: after an occurrence is posted and before it is recorded.
EXIT_FAULT = "review-exit"
#: Incident states that hand over a review.
HANDED = ("rescued", "reported")

__all__ = ["Reviews", "REVIEWS_FILE", "signature"]

def signature(record: dict[str, Any]) -> tuple[str, str]:
    """`(key, slug)`: the owner and the kind that opened the incident."""
    kinds = record.get("kinds") or [record.get("kind", "?")]
    owner = str(record.get("owner") or record.get("responsible_owner") or "unknown owner")
    kind = str(kinds[0])
    key = f"{owner} · {kind}"
    slug = re.sub(r"[^a-z0-9]+", "-", f"{owner.split('-')[0]}-{kind}".lower()).strip("-")
    return key, slug


def _clock(at: float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(float(at))) if at else "?"


def _span(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    seconds = int(max(0, seconds))
    return f"{seconds // 60} min {seconds % 60:02d} s" if seconds >= 60 else f"{seconds} s"


class Reviews:
    """Developer reviews over the monitor's incident store."""

    def __init__(self, monitor, *, clock: Callable[[], float] | None = None):
        self.monitor = monitor
        self.clock = clock or monitor.clock
        self.path: Path = monitor.store_dir / REVIEWS_FILE

    # --- state -----------------------------------------------------------------------

    def load(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save(self, reviews: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(reviews, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    # --- the handoff -------------------------------------------------------------------

    def mark(self, record: dict[str, Any]) -> None:
        """Called as an incident closes rescued or reported: the handoff is
        owed from here on, whatever happens to the process next."""
        if record.get("state") in HANDED and not (record.get("review") or {}).get("delivered"):
            record["review"] = {**(record.get("review") or {}), "owed": True, "outcome": record["state"]}

    def deliver(self, records: list[dict[str, Any]]) -> list[str]:
        """Hand over every owed occurrence. Returns the incident keys handed."""
        handed = []
        reviews = self.load()
        for record in records:
            review = record.get("review") or {}
            if not review.get("owed") or review.get("delivered"):
                continue
            try:
                self._deliver(record, reviews)
            except Exception as error:  # noqa: BLE001 - owed stays owed; the next pass tries again
                self.monitor_log(f"monitor: the review of {record.get('topic')} could not be handed over: {error!r}")
                continue
            handed.append(record["key"])
        self.deliver_updates(records)
        return handed

    def later(self, record: dict[str, Any], kind: str, text: str) -> None:
        """A later fact about a handed incident (`moving`, `final`), owed to
        its occurrence until posted. Idempotent: a kind is owed once."""
        review = record.get("review") or {}
        if not review.get("delivered"):
            return  # not handed yet: the occurrence, when posted, reads the record as it is
        updates = review.setdefault("updates", {})
        if kind in updates:
            return
        updates[kind] = {"owed": True, "text": text, "at": self.clock()}
        record["review"] = review

    def deliver_updates(self, records: list[dict[str, Any]]) -> list[str]:
        """Post every owed later outcome under its occurrence."""
        posted = []
        for record in records:
            review = record.get("review") or {}
            for kind, update in (review.get("updates") or {}).items():
                if not update.get("owed"):
                    continue
                try:
                    self._deliver_update(record, kind, update)
                except Exception as error:  # noqa: BLE001 - owed stays owed; the next pass tries again
                    self.monitor_log(f"monitor: the later outcome of {record.get('topic')} could not be posted: "
                                     f"{error!r}")
                    continue
                posted.append(f"{record['key']}:{kind}")
        return posted

    def _deliver_update(self, record: dict[str, Any], kind: str, update: dict[str, Any]) -> None:
        monitor = self.monitor
        review = record["review"]
        occurrence_id = f"{record['key']} e{record.get('episode', 1)}"
        marker = f"{occurrence_id} {kind}"
        topic = self._live_topic(review)
        if not any(parse_note(m.content, UPDATE_TAG) == marker for m in self._messages(review["topic"])):
            original = ("reported unrecovered" if review.get("outcome") == "reported" or record.get("state") == "reported"
                        else "recovered")
            monitor.post(monitor.spec.instance_name(), topic,
                         f"**Occurrence {review.get('number', '?')} — later:** {update['text']}. "
                         f"(The occurrence above stands as seen then: {original}.)")
            monitor.post(monitor.spec.instance_name(), topic, note(UPDATE_TAG, marker))
            if monitor.fault(EXIT_FAULT):
                self.monitor_log(f"monitor: fault injected: exiting after posting {marker}, before recording it")
                os._exit(70)
        update.update(owed=False, posted=True)
        monitor.save(record)

    def _live_topic(self, review: dict[str, Any]) -> str:
        """The review topic under its name now (a ✔ included), found by the
        review's anchor: posting under the bare name of a ✔'d topic would
        open a twin."""
        entry = self.load().get(review.get("signature") or "") or {}
        anchor = int(entry.get("anchor") or 0)
        where = self.monitor.where(anchor) if anchor else None
        return where[1] if where is not None else review["topic"]

    def monitor_log(self, line: str) -> None:
        from agag.zulip import log

        log(line)

    def _deliver(self, record: dict[str, Any], reviews: dict[str, dict[str, Any]]) -> None:
        monitor = self.monitor
        key, slug = signature(record)
        entry = reviews.get(key)
        if entry is not None and self.reviewed(entry):
            # The developer ✔'d it: this is a recurrence after the review.
            entry.update(state="reviewed", reviewed_seen=self.clock())
            previous = entry
            entry = None
        else:
            previous = None
        if entry is None:
            # The newest episode Zulip holds, when the store does not: an
            # open one is continued, a ✔'d one is followed by the next.
            held = self._episodes(key)
            adopted = self._adopt(key, held) if held else None
            if adopted is not None and not self.reviewed(adopted):
                entry = adopted
            else:
                previous = previous or adopted
                episode = max(held, int((previous or {}).get("episode", 0))) + 1
                entry = {
                    "signature": key, "slug": slug, "episode": episode, "state": "open", "occurrences": [],
                    "topic": f"{REVIEW_PREFIX}{slug}" + (f"-{episode}" if episode > 1 else ""),
                    "opened_at": self.clock(),
                }
                if previous:
                    entry["after"] = {"topic": previous.get("topic"), "anchor": previous.get("anchor")}
            reviews[key] = entry
        occurrence_id = f"{record['key']} e{record.get('episode', 1)}"
        number = len(entry["occurrences"]) + (0 if occurrence_id in entry["occurrences"] else 1)
        if not self._posted(entry, occurrence_id):
            if not entry.get("anchor"):
                entry["anchor"] = monitor.post(monitor.spec.instance_name(), entry["topic"], self._opening(entry))
                monitor.post(monitor.spec.instance_name(), entry["topic"], note(REVIEW_TAG, f"{key} e{entry['episode']}"))
            names = self._notify(entry, record, number)
            monitor.post(monitor.spec.instance_name(), entry["topic"], self._occurrence(entry, record, number, names))
            monitor.post(monitor.spec.instance_name(), entry["topic"], note(OCCURRENCE_TAG, occurrence_id))
            if monitor.fault(EXIT_FAULT):
                # A trial: the process ends between the post and its record.
                self.monitor_log(f"monitor: fault injected: exiting after posting {occurrence_id}, before recording it")
                os._exit(70)
        if occurrence_id not in entry["occurrences"]:
            entry["occurrences"].append(occurrence_id)
        entry["last_at"] = self.clock()
        self.save(reviews)
        record["review"] = {**(record.get("review") or {}), "owed": False, "delivered": True,
                            "topic": entry["topic"], "signature": key, "number": number}
        monitor.save(record)
        monitor.post_incident(record, f"Handed to the developer for review: `{entry['topic']}` "
                                      f"(occurrence {number} of `{key}`).")

    # --- reading back ------------------------------------------------------------------

    def _messages(self, topic: str) -> list:
        channel = self.monitor.spec.instance_name()
        try:
            return list(self.monitor.mirror.messages(channel, topic, across_resolve=True))
        except Exception:  # noqa: BLE001 - a read that fails concludes nothing
            return []

    def _posted(self, entry: dict[str, Any], occurrence_id: str) -> bool:
        if occurrence_id in entry.get("occurrences", []):
            return True
        return any(parse_note(m.content, OCCURRENCE_TAG) == occurrence_id for m in self._messages(entry["topic"]))

    def reviewed(self, entry: dict[str, Any]) -> bool:
        """Whether the developer ✔'d the review topic."""
        if entry.get("state") == "reviewed":
            return True
        anchor = int(entry.get("anchor") or 0)
        where = self.monitor.where(anchor) if anchor else None
        return where is not None and where[1].startswith(RESOLVED_TOPIC_PREFIX)

    def _episodes(self, key: str) -> int:
        """How many review episodes of this signature Zulip holds (a lost store)."""
        found = 0
        for row in self.monitor.mirror.notes(tag=REVIEW_TAG, sender_id=self.monitor.self_id,
                                             channel=self.monitor.spec.instance_name()):
            words = row.value.rsplit(" e", 1)
            if words[0] == key:
                found = max(found, int(words[1]) if len(words) > 1 and words[1].isdigit() else 1)
        return found

    def _adopt(self, key: str, episode: int) -> dict[str, Any] | None:
        """The review episode's record from its note, when the store lost it."""
        for row in self.monitor.mirror.notes(tag=REVIEW_TAG, sender_id=self.monitor.self_id,
                                             channel=self.monitor.spec.instance_name()):
            if row.value != f"{key} e{episode}":
                continue
            message = self.monitor.mirror.message(row.message_id)
            if message is None:
                continue
            history = self._messages(message.topic)
            occurrences = [parse_note(m.content, OCCURRENCE_TAG) for m in history]
            anchor = next((int(m.id) for m in history if int(m.sender_id) == self.monitor.self_id), row.message_id)
            return {"signature": key, "slug": signature({"kind": key.split(" · ")[-1]})[1], "episode": episode,
                    "state": "open", "topic": message.topic.removeprefix(RESOLVED_TOPIC_PREFIX),
                    "anchor": anchor, "occurrences": [o for o in occurrences if o], "adopted": True}
        return None

    # --- the words ---------------------------------------------------------------------

    def _notify(self, entry: dict[str, Any], record: dict[str, Any], number: int) -> str:
        owners = " ".join(f"@**{name}**" for name in self.monitor.report_to())
        if number == 1 or record.get("state") == "reported" or number % NOTIFY_EVERY == 0:
            return owners
        return ""

    def _opening(self, entry: dict[str, Any]) -> str:
        lines = [
            f"**Developer review: `{entry['signature']}`** — recovered (or unrecovered) stalls of this owner and "
            "kind, one post per occurrence below, each with its own evidence.",
            "",
            "- Grouped by what was observed (the owner, the kind of stall that opened the incident), **not by a "
            "cause**: a common cause is a hypothesis until somebody confirms it.",
            "- Operational recovery is each incident's own record; this review is the follow-up on why it "
            "happened. ✔ this topic when it has been looked at — that is your record of the review, and it "
            "accepts nothing about the original work.",
            f"- Policy: the first occurrence and every unrecovered one name the owners; a recovered recurrence is "
            f"appended, and every {NOTIFY_EVERY}rd names them again with the count. An occurrence after this "
            "topic is ✔ opens a new episode.",
        ]
        if entry.get("after"):
            lines.append(f"- It happened again after `{entry['after']['topic']}` was reviewed (✔).")
        return "\n".join(lines)

    def _occurrence(self, entry: dict[str, Any], record: dict[str, Any], number: int, names: str) -> str:
        monitor = self.monitor
        line = record.get("timeline") or {}
        onset = line.get("onset") or record.get("since")
        suspicion = line.get("first_suspicion")
        detected = record.get("detected_at")
        requests = record.get("requests") or []
        ended_at = record.get("rescued_at") or record.get("reported_at")
        rescued = record.get("state") == "rescued"
        where = f"#**{monitor.spec.instance_name()}>{record.get('topic')}**"
        node, origin = record.get("node", {}), record.get("origin", {})
        recurring = number > 1 and number % NOTIFY_EVERY == 0
        head = (f"{names} " if names else "") + (
            f"**Occurrence {number}**" + (" — **not recovered**" if not rescued else "")
            + (f" — **recurring: {number} occurrences**" if recurring else ""))
        lines = [
            head + f": incident {where} (#{record.get('incident_anchor', '?')}), "
                   f"for the request `#{origin.get('channel')} › {origin.get('topic')}` (#{origin.get('message_id')}).",
            "",
            f"- Work: `#{node.get('channel')} › {node.get('topic')}`"
            + (f" ({node.get('identity')})" if node.get("identity") else "") + ".",
            f"- What was seen: {record.get('fact', '')}",
            f"- Timeline: onset ≈ {_clock(onset)}; first suspicion {_clock(suspicion)}; detected {_clock(detected)}; "
            + (f"Front asked {', '.join(_clock(r.get('at')) + (' (#' + str(r['message_id']) + ')' if r.get('message_id') else '') for r in requests)}; "
               if requests else "Front not asked; ")
            + (f"work moving again {_clock(ended_at)}." if rescued else f"reported to the owners {_clock(ended_at)}."),
            f"- Durations: detection {_span((detected or 0) - onset if onset and detected else None)} from onset; "
            + (f"recovery {_span(ended_at - onset if onset and ended_at else None)} from onset." if rescued
               else f"unrecovered for {_span(ended_at - onset if onset and ended_at else None)} when reported."),
        ]
        checks = line.get("checks") or []
        if checks:
            lines.append("- Health checks: " + "; ".join(f"{_clock(c.get('at'))[11:]} {c.get('verdict')} — "
                                                          f"{str(c.get('why', ''))[:160]}" for c in checks[-4:]) + ".")
        action = (f"Front was asked {len(requests)} time(s); a later serving showed fresh work "
                  f"({record.get('outcome', 'moved')})." if rescued else f"Not recovered: {record.get('why', '')}.")
        lines.append(f"- Recovery action and outcome: {action}")
        lines.append(f"- Confirmed: {self._confirmed(record)}")
        found = assess(record)
        if found["injected"]:
            lines.append(f"- **Trial:** the evidence shows an injected fault (`{found['injected']}`). This occurrence "
                         "tests the recovery path; it is not an operational recurrence.")
        lines += [
            f"- Observed failure: {found['observed']}",
            f"- Plausible cause: {found['cause']} (confidence: **{found['confidence']}**).",
            f"- Missing evidence: {found['missing']}",
            f"- Candidate: {found['candidate']}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _confirmed(record: dict[str, Any]) -> str:
        checks = (record.get("timeline") or {}).get("checks") or []
        stopped = [c for c in checks if c.get("verdict") == "stopped"]
        if stopped:
            return f"the health check saw the work stopped ({str(stopped[0].get('why', ''))[:200]})."
        return f"only what the records show ({str(record.get('fact', ''))[:200]})."



def _injected(record: dict[str, Any]) -> str | None:
    for check in (record.get("timeline") or {}).get("checks") or []:
        if check.get("injected"):
            return str(check["injected"])
    for text in (record.get("fact"), record.get("why")):
        if text and "fault injected: " in str(text):
            return str(text).split("fault injected: ")[-1].split(")")[0]
    return None


def assess(record: dict[str, Any]) -> dict[str, Any]:
    """What this occurrence's own evidence supports (failsafe p3): the
    observed failure, a plausible cause with its confidence, what evidence
    is missing, and one improvement or investigation candidate. Deterministic
    and bounded — the handoff never waits on it — and "unknown" is an
    answer. Grouping by symptom (the review's signature) says nothing about
    causes; this is per occurrence."""
    kinds = [str(k) for k in (record.get("kinds") or [record.get("kind")])]
    checks = (record.get("timeline") or {}).get("checks") or []
    whys = " ".join(str(c.get("why") or "") for c in checks) + " " + str(record.get("fact") or "")
    observed = str(record.get("fact") or "?")[:300]
    injected = _injected(record)
    result = {"observed": observed, "injected": injected, "cause": "unknown", "confidence": "none",
              "missing": "evidence of what the run was doing when it stopped",
              "candidate": "investigate from the run record and the owner's log around the onset"}
    if injected:
        result.update(cause=f"the injected trial fault `{injected}`", confidence="high",
                      missing="nothing for the cause; the recovery path's timings are the result",
                      candidate="none for the product; count it with the trial, not as a recurrence")
    elif "stopped" in kinds and "exit -9" in whys:
        result.update(cause="the harness was killed by SIGKILL and posted nothing: memory pressure, a person, or a "
                            "supervisor", confidence="medium",
                      missing="who sent the signal (the host's log at the onset)",
                      candidate="read the host log around the onset; if it was memory, bound the run's memory")
    elif "stopped" in kinds and "never recorded an end" in whys:
        result.update(cause="the harness process vanished without its runner noticing, so the runner itself was "
                            "probably gone (a listener restart or crash)", confidence="low",
                      missing="the listener's log and exit status at the onset",
                      candidate="check whether the listener restarted at the onset")
    elif "stopped" in kinds:
        result.update(cause="the run ended and its serving delivered no reply", confidence="medium",
                      missing="the run's output and its reply outcome (the run record's `reply`)",
                      candidate="the listener could post the failure itself when a run ends with no reply")
    elif "uncertain" in kinds and "past its own bound" in whys:
        result.update(cause="a tool call outlived its own timeout: the harness did not end it", confidence="medium",
                      missing="the process state of the call's tree (`ps -o stat`) at the time",
                      candidate="report the harness version and the stuck call; a probe of the process state")
    elif "uncertain" in kinds and "has advanced" in whys:
        result.update(cause="a named wait stopped advancing (a hung subprocess or subagent)", confidence="low",
                      missing="what the waiting process was blocked on",
                      candidate="sample the stuck process (stack or open files) when this recurs")
    elif "uncertain" in kinds and ("probe" in whys and ("did not answer" in whys or "failed" in whys)):
        result.update(cause="the health probe itself failed or timed out, which says nothing of the work",
                      confidence="medium", missing="the probe's own error output",
                      candidate="run the owner's probe by hand; a failing probe is the owner's defect")
    elif "uncertain" in kinds:
        result.update(cause="the run was alive but idle with nothing explaining it: a stalled model call or a "
                            "frozen process", confidence="low",
                      missing="the process state (running, sleeping, stopped) and what it was waiting on",
                      candidate="add the process state to the probe when this recurs")
    elif "unanswered" in kinds:
        result.update(cause="the agent's runs produced no usable reply twice", confidence="medium",
                      missing="the runs' own outputs (their run records' `reply.failure`)",
                      candidate="read the failed outputs: a reply-contract slip is fixed in the guide or the splitter")
    elif "unheld" in kinds or "quiet" in kinds:
        result.update(cause="the serving ended saying work goes on, and nothing held it", confidence="medium",
                      missing="whether anything was started in the background",
                      candidate="the worker guide: wait for everything started before replying")
    return result
