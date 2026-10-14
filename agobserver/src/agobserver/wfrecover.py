"""The recovery path: an incident becomes a request to a recovery agent.

observer p3 step 4 (`docs/workflow.md`, *Recovery path*). For an open
incident of a recoverable family (`attempt`, `continuation`, `publication`,
`integration`) on a run that is not itself a recovery run:

1. **Journal, then send.** An assignment row (`n` ≤ `max_assignments`) and
   its outbox post are written together; the post goes out through
   `wfpost` (owed → sending → sent, looked for by its marker before any
   repeat). The post opens a `request-<incident>` topic in the recovery
   workflow's channel; WFE's intake turns it into a recovery run (input
   kind `request`, requester Observer) — the durable intake and wakeup path.
2. **Acknowledged** = a recovery run exists whose input is that post.
   **Performed** = the target run's history has `run.recover` naming the
   incident. **Restored** = a later observation shows the run's agent
   reporting work after the recovery (or the run completed). A sent post,
   a new PID or a promise is none of these.
3. **Bounds.** A second assignment only when the first was never taken up
   within `ack_timeout`, or its run ended without acting; after the last,
   the owners are told. A recovery run that ends without `run.recover` is a
   hand-off to a person (its report says why). While the executor is down
   nothing is assigned — a recovery run would need it.

Nothing here changes a run: the recovery agent decides and WFE validates.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from . import wfclassify as wc

DEFAULTS = {"workflow": "agops/recover", "channel": "wf-agops.recover", "ack_timeout": 1800.0, "max_assignments": 2, "verify_timeout": 3600.0}


def request_text(inc, f: wc.Finding, n: int) -> str:
    ev = f.evidence or {}
    attempts = ev.get("attempts") or {}
    last = attempts.get("last") or {}
    log = ev.get("log") or {}
    proc = ev.get("process") or {}
    ws, ref = inc["workspace"], inc["ref"]
    lines = [
        f"Recovery request for incident `{inc['id']}`{f' (assignment {n})' if n > 1 else ''}.",
        "",
        f"**Run:** `{ref}` in workspace `{ws}` (uid `{inc['uid']}`).",
        f"**Observed:** {f.condition} — {f.fact}",
        f"**First suspected:** {time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(float(inc['first_suspected'])))}.",
        "",
        "Evidence (from `wfe observe`):",
        f"- hold: {json.dumps(ev.get('hold'), ensure_ascii=False)}",
        f"- the attempt that ended: `{last.get('id')}` — {last.get('outcome')}: {last.get('detail')}",
        f"- its process: alive={proc.get('alive')}, exit={proc.get('exit')}, signal={proc.get('signal')}",
        f"- its session log: last write {log.get('last')}, turns {log.get('turns')}, the harness ended the session: {json.dumps(log.get('ended'))}, background tasks stopped with it: {log.get('backgroundStopped')}",
        f"- the agent's last report: {json.dumps(ev.get('progress'), ensure_ascii=False)}",
        f"- running nodes: {ev.get('active')}; ready: {ev.get('ready')}; earlier recoveries: {len(ev.get('recoveries') or [])}",
        f"- unpublished checkpoints / integration: {json.dumps(ev.get('publication'))} / {json.dumps(ev.get('integration'))}",
        "",
        "**To resolve:** can this run's work continue safely from where its record stands? Look before deciding:",
        f"the run's record and history (`wfe run show {ref} --workspace {ws} --history`), its attempts, process and log "
        f"(`wfe exec status {ref} --workspace {ws}`), its own working copy and what is uncommitted there (`wfe runs index --workspace {ws}`), "
        "and any effect outside Git the attempt may have caused. Git history cannot prove that an external operation did not happen.",
        "",
        "Then do one of:",
        f"- continue it: `wfe run recover {ref} --workspace {ws} --incident {inc['id']} --attempt {(f.episode if inc['family'] == 'attempt' else last.get('id')) or 'none'} --reason \"<what you checked>\"` (see `wfe run help recover`);",
        "- repair what stops it (a failed publication: `wfe exec publish <checkpoint>`; an executor problem: say so) and say what you did;",
        "- or leave it to a person: say in your report what they must decide (a scope change, an external effect that may have happened).",
        "",
        "You never resume a person's hold, accept a result, answer a question for the person, or change the run's plan.",
    ]
    return "\n".join(lines)


class Recoverer:
    def __init__(self, cfg: dict[str, Any], log: Callable[[str], None] = print):
        self.cfg = {**DEFAULTS, **(cfg or {})}
        self.log = log

    @property
    def workflow(self) -> str:
        return str(self.cfg["workflow"])

    def _recovery_run(self, doc: dict, message: int | None) -> dict | None:
        """The recovery run created from our post (its input's source)."""
        if not message:
            return None
        for r in doc.get("runs") or []:
            src = ((r.get("input") or {}).get("source") or {})
            ident = r.get("identity") or {}
            if f"{ident.get('project')}/{ident.get('workflow')}" == self.workflow and src.get("message") == message:
                return r
        return None

    def assign(self, m, inc, f: wc.Finding, n: int, now: float) -> None:
        iid = inc["id"]
        marker = f"obs {iid} recover {n}"
        with m.store.tx():
            if m.store.db.execute("SELECT 1 FROM assignments WHERE incident = ? AND n = ?", (iid, n)).fetchone():
                return
            oid = m.store.enqueue(kind="channel", channel=self.cfg["channel"], topic=f"request-{iid}"[:60], text=request_text(inc, f, n), marker=marker, incident=iid, now=now)
            m.store.db.execute("INSERT INTO assignments (incident, n, recipient, journaled, outbox, state) VALUES (?, ?, ?, ?, ?, 'requested')",
                               (iid, n, self.workflow, now, oid))
            m.store.event(iid, "assigned", {"n": n, "recipient": self.workflow, "outbox": oid})
        m.store.update(iid, state="assigned")
        m.note(iid, f"Asked a recovery agent ({self.workflow}, assignment {n}): request topic `request-{iid}` in `#{self.cfg['channel']}`.", f"assigned-{n}")
        self.log(f"incident {iid}: recovery assignment {n} journaled")

    def step(self, m, doc: dict, by_uid: dict[str, wc.Finding], executor: wc.Finding | None, now: float) -> None:
        for inc in m.store.open_incidents():
            if not inc["recover"] or inc["state"] == "escalated":
                continue
            f = by_uid.get(inc["uid"])
            if f is None or f.key != inc["id"]:
                continue  # verification decides
            if executor is not None:
                continue  # a recovery run would need the executor; its incident is told to the owners
            if f.condition == "lost-attempt":
                continue  # the record still has the attempt open: the executor ends it first (then interrupted/unknown)
            rows = m.store.assignments(inc["id"])
            if not rows:
                self.assign(m, inc, f, 1, now)
                continue
            a = rows[-1]
            if a["closed"] is not None:
                continue
            # Any of this incident's posts may have become the recovery run (a late intake included).
            rr = None
            for b in reversed(rows):
                post = m.store.outbox_row(b["outbox"]) if b["outbox"] else None
                rr = rr or self._recovery_run(doc, post["message_id"] if post else None)
            post = m.store.outbox_row(a["outbox"]) if a["outbox"] else None
            if a["acknowledged"] is None:
                if rr is not None:
                    m.store.db.execute("UPDATE assignments SET acknowledged = ?, acknowledged_by = ?, state = 'acknowledged' WHERE id = ?", (now, rr["identity"]["uid"], a["id"]))
                    m.store.event(inc["id"], "acknowledged", {"n": a["n"], "run": rr["identity"]["uid"]})
                    m.store.update(inc["id"], state="recovering")
                    m.note(inc["id"], f"The recovery run `{rr['identity']['workflow']}/{rr['identity']['run']}` took it up.", f"ack-{a['n']}")
                elif post is not None and post["sent"] and now - float(post["sent"]) > float(self.cfg["ack_timeout"]):
                    # Counted from the post's delivery: a Zulip outage delays, it never doubles the request.
                    self.next_or_escalate(m, inc, f, a, now, f"not taken up within {self.cfg['ack_timeout']:.0f} s of its post", "unacknowledged")
                continue
            # Taken up: the recovery run ended without continuing the run, or never acts?
            rr = rr or self._recovery_run_by_uid(doc, a["acknowledged_by"])
            if rr is not None and _finished(rr):
                self.next_or_escalate(m, inc, f, a, now, f"the recovery run {rr['identity']['workflow']}/{rr['identity']['run']} ended ({rr.get('situation')}) without continuing the run", "no-action", handoff=rr)
            elif now - float(a["acknowledged"]) > float(self.cfg["verify_timeout"]):
                self.next_or_escalate(m, inc, f, a, now, f"the recovery run took it up {self.cfg['verify_timeout']:.0f} s ago and has not acted", "stuck")

    def _recovery_run_by_uid(self, doc: dict, uid: str | None) -> dict | None:
        return next((r for r in doc.get("runs") or [] if r["identity"].get("uid") == uid), None) if uid else None

    def next_or_escalate(self, m, inc, f: wc.Finding, a, now: float, why: str, outcome: str, handoff: dict | None = None) -> None:
        m.store.db.execute("UPDATE assignments SET closed = ?, outcome = ?, note = ? WHERE id = ?", (now, outcome, why, a["id"]))
        m.store.event(inc["id"], "assignment-closed", {"n": a["n"], "outcome": outcome, "why": why})
        if handoff is not None:
            # The agent looked and decided not to continue: the person decides (its report says why).
            m.close(inc, "handed-off", {"why": f"{why}; see its report", "recovery_run": handoff["identity"]["uid"]}, now)
            m.tell_owners(inc["id"], f"Observer: incident `{inc['id']}` ({inc['workspace']} {inc['ref']}): {why}. The run stays held; its report says what a person must decide.", "handed-off")
            return
        if int(a["n"]) < int(self.cfg["max_assignments"]):
            self.assign(m, inc, f, int(a["n"]) + 1, now)
            return
        m.escalate(inc, f, now, why=f"{a['n']} recovery assignment(s): {why}")

    def verify(self, m, inc, f: wc.Finding, run: dict, now: float):
        """The outcome once the incident's condition is gone; False while still
        verifying a recovery; None when no recovery of ours is involved."""
        rows = m.store.assignments(inc["id"])
        ours = [r for r in run.get("recoveries") or [] if r.get("incident") == inc["id"]]
        if not ours:
            return None
        rc = ours[-1]
        # The recovery run may have come and gone between two looks: its
        # acknowledgement is recorded from the same observation.
        for a in rows:
            if a["acknowledged"] is None and a["outbox"]:
                post = m.store.outbox_row(a["outbox"])
                rr = self._recovery_run(m.last_doc, post["message_id"] if post else None)
                agent = rc.get("agent") or {}
                if rr is None and agent:
                    rr = next((r for r in (m.last_doc.get("runs") or []) if r["identity"]["workspace"] == agent.get("workspace") and r["identity"]["workflow"] == agent.get("workflow") and r["identity"]["run"] == agent.get("run")), None)
                if rr is not None:
                    m.store.db.execute("UPDATE assignments SET acknowledged = ?, acknowledged_by = ? WHERE id = ?", (now, rr["identity"]["uid"], a["id"]))
                    m.store.event(inc["id"], "acknowledged", {"n": a["n"], "run": rr["identity"]["uid"], "late": True})
        for a in rows:
            if a["performed_seq"] is None and a["closed"] is None:
                agent = rc.get("agent") or {}
                m.store.db.execute("UPDATE assignments SET performed_seq = ?, actor = ?, state = 'performed' WHERE id = ?",
                                   (rc["seq"], json.dumps({"by": rc.get("by"), **agent}), a["id"]))
                m.store.event(inc["id"], "performed", {"n": a["n"], "seq": rc["seq"], "by": rc.get("by"), "agent": agent})
        if inc["state"] != "verifying":
            m.store.update(inc["id"], state="verifying")
        progress = run.get("progress") or {}
        evidence = {"recovery_seq": rc["seq"], "recovered_by": rc.get("by"), "progress": progress, "seq": run.get("seq"), "situation": run.get("situation")}
        if run.get("cancelled"):
            return "cancelled", {**evidence, "why": "the run was cancelled after the recovery"}
        if f.condition == "respected-hold":
            return "held", {**evidence, "why": "a person holds the run"}
        if progress.get("seq") and progress["seq"] > rc["seq"] and progress.get("attempt") and progress["attempt"] != inc["episode"]:
            self._close_assignments(m, inc, now, "restored")
            return "restored", {**evidence, "why": f"the run's agent reported {progress.get('op')} (seq {progress['seq']}) in attempt {progress['attempt']} after the recovery (seq {rc['seq']})"}
        if f.condition == "terminal" and f.kind == "completed":
            self._close_assignments(m, inc, now, "restored")
            return "restored", {**evidence, "why": "the run completed after the recovery"}
        if f.condition == "interrupted" and f.episode != inc["episode"]:
            self._close_assignments(m, inc, now, "interrupted-again")
            return "interrupted-again", {**evidence, "why": f"the continuation (attempt {f.episode}) was interrupted too; that is a new incident"}
        if now - float(rc_time(rc) or now) > float(self.cfg["verify_timeout"]) and not inc["escalated"]:
            m.escalate(inc, f, now, why=f"recovered at seq {rc['seq']}, but no work was reported in {self.cfg['verify_timeout']:.0f} s")
        return False

    def _close_assignments(self, m, inc, now: float, outcome: str) -> None:
        m.store.db.execute("UPDATE assignments SET closed = ?, outcome = ? WHERE incident = ? AND closed IS NULL", (now, outcome, inc["id"]))


def rc_time(rc: dict) -> float | None:
    return wc.ts(rc.get("at"))


def _finished(run: dict) -> bool:
    ex = run.get("execution") or {}
    return bool(run.get("cancelled")) or ex.get("state") in ("completed", "stopped") or (run.get("hold") or {}).get("kind") == "stopped"
