# Observer over workflows (observer p3)

Observer watches workflow runs, not conversations. It reads WFE's observation
(`wfe observe --json`, `agdevworld/workflow_editor/docs/observation.md`),
decides mechanically what is moving, waiting or stopped, opens one incident
per interruption episode, asks a recovery recipient to investigate through
Zulip, and records a recovery only when later observations show useful
work. Front, `#front` conversations, traces and serving probes are not part
of it.

## Who does what

| Party | Responsibility | Never |
| --- | --- | --- |
| WFE | run state, validated transitions (`run.recover`), the observation | infers liveness from silence |
| Executor (autolab `wfexec`) | processes, the queue and slot, heartbeat, reconcile | decides a recovery |
| Observer | discovery, classification, incidents, assignment and delivery, verification, its own health | changes a run, resumes, accepts, kills |
| Recovery agent (`agops/recover` runs) | investigates the evidence and decides: continue (`wfe run recover`), repair the environment, or hand the question to a person | writes while the old attempt lives, replays side effects, accepts results |
| Person | holds, answers, cancellation, acceptance, anything outside the recovery authority | — |
| Watchdog (`agobserver.watchdog`, separate process) | Observer's loop and source freshness, the executor heartbeat, recovery backlog | depends on Observer's process |

## Classification

Each look classifies every observed run from its own facts. Elapsed time
makes a suspicion, never a verdict.

| Observation | Condition | Response |
| --- | --- | --- |
| `hold.human` (stopped), or an unanswered question to a person | `respected-hold`, `awaiting-person` | none; stays observed |
| `node.wait` on an external reference | `awaiting-external` | none; observed, with its age |
| `interrupted` / `unknown` hold, no recovery recorded for that attempt | `interrupted` | incident (family `attempt`) → recovery request |
| an attempt open in the record, process gone or the attempt row ended | `lost-attempt` | grace for the executor's reconcile (180 s), then incident (family `attempt`) |
| an attempt alive with an open tool call inside its declared timeout (+60 s), or log/CPU advancing | `working` | none |
| an attempt alive with an open tool call past its declared timeout (+60 s) | `uncertain` (`tool-overrun`) | as below, suspected from the moment the bound passed |
| an attempt alive, log silent ≥ 900 s, no open tool call with a timeout, CPU not advancing | `uncertain` (`silent`) | suspected from the moment the silence crossed 900 s; judged by the local model 300 s later; `waiting` postpones (30 min, doubling to 2 h, only while the evidence digest still matches, at most 6 h in all); `stalled`/`unclear` are told to the owners at 900 s, never before a pending judgment; never a second writer |
| a node failed and nothing else runs (execution `stopped`) | `awaiting-person` (`failed`) | none: the failure is a record, the person decides |
| an external wait past its declared `deadline` | `uncertain` (family `wait`) | told to the owners |
| ready work or an answer recorded and not taken up, no hold, no attempt, no queued job | `unowned` | grace 180 s (the executor's reconcile re-queues answers), then incident (family `continuation`) → recovery request |
| a queued job behind a healthy executing attempt | `queued` | none (legitimate wait, `ahead` recorded) |
| a queued job, slot free, executor healthy, not claimed for 300 s | `queue-stalled` | incident (family `queue`) → owners |
| executor heartbeat older than 180 s | `executor-down` | one infrastructure incident naming every affected run → owners (independent route); no per-run requests |
| failed/attention checkpoint, failed/refused/attention integration | `publication` / `integration` | separate incident; recovery may retry publication, never re-run work or accept |
| `source.state` not ok, `ambiguous`, or the observation command failing | `unobservable` | observation problem recorded once; nothing concluded, nobody asked |
| completed or cancelled with nothing outstanding | `terminal` | an open incident closes with that outcome |

## Incident identity

An incident is `(run uid, family, episode)`:

| Family | Episode |
| --- | --- |
| `attempt` (interrupted, unknown, lost-attempt, uncertain) | the attempt id whose end (or silence) is the problem; a silence that ended (`false-alarm`, `resumed`) and returns reopens it with a new first suspicion |
| `wait` | the waiting node and its deadline |
| `observation` | the source state |
| `continuation` | the record sequence at which the run became unowned |
| `queue` | the job id |
| `publication` | the checkpoint id |
| `integration` | the integration row id |
| `executor` | the last heartbeat time seen before the outage |

The kind and its description are attributes: `lost-attempt` becoming
`unknown` after the executor's reconcile is the same incident, and so is a
different wording of the same evidence. Retry budgets belong to the
incident and are never replenished by a re-description. A later attempt
interrupted again is a new episode — and WFE's own `recover-budget` (2 per
person-originated control) bounds the chain.

## Records (`agobserver/.local/workflow/observer.sqlite`)

| Record | Fields |
| --- | --- |
| incident | id, run uid, workspace, ref, family, episode, kind, state (`open`, `assigned`, `recovering`, `verifying`, `escalated`, `closed`), first suspicion, detected, next review, outcome (`restored`, `handed-off`, `completed`, `cancelled`, `held`, `false-alarm`, `withdrawn`, `escalated`), outcome evidence |
| evidence | incident, observed at, observation digest, the run facts the decision used |
| judgment | incident, evidence digest, verdict, model, prompt/input/transcript paths, invalidated |
| assignment | incident, n (≤ 2), recipient, request text digest, journaled, delivery state (`owed` → `sending` → `sent` \| `failed` \| `uncertain`), message id, acknowledged by (recovery run uid), performed (`run.recover` seq), actor, outcome |
| event | append-only log of every transition above |

Workflow records and Git stay authoritative; these records say what
Observer saw, asked and verified.

## Recovery path

1. **Journal, then send.** The assignment is written (`owed`), set to
   `sending` before the post, `sent` with the message id after. A post that
   may have gone out is looked for (the incident marker in the request topic)
   before anything is posted again; a failed search keeps it `uncertain`.
2. **Zulip request.** One `request-<incident>` topic in the channel of the
   `agops/recover` workflow (`wf-agops.recover`), posted by Observer's bot.
   WFE's intake accepts posts from configured agent requesters for named
   workflows only (`zulip.json` `intake.agents`), and the post becomes a
   recovery run (input kind `request`, requester Observer). The same post
   never creates a second run (its receipt). The run's progress and result
   are posted back into that topic by WFE's notifier.
3. **Acknowledgement** is the recovery run existing with that post as its
   source; **performance** is `run.recover` naming the incident in the target
   run's history; **restoration** is a later observation showing the
   continued attempt's agent reporting work (a progress, completion, a
   question to a person, or the run completed) after the recovery. A new PID,
   an ack or a promise is none of these.
4. **Bounds.** At most 2 assignments per incident, the second after 30 min
   without acknowledgement or with the recovery run ended without action.
   A recovery run is never itself the target of a recovery request: an
   incident on an `agops` run is told to the owners. Zulip failure is
   recorded and retried with backoff; it never stops observation or erases
   an assignment.
5. **Outcomes.** `restored` (verified progress), `handed-off` (the recovery
   agent recorded a question to a person, or left the run held with its
   reasons), `completed` / `cancelled` / `held` (the run reached that state
   by someone else's record), `false-alarm` (the next observation shows it
   was never stopped), `escalated` (owners told; the incident stays open
   until one of the others).

## Sessions

Run = the work; session = a retained harness conversation; attempt = one
execution interval. The observation carries the attempt's session id when
the log names one (`process.log.session`, from the harness's `init` event).
Monitoring obligations attach to the run and incidents to attempts:

- two intervals sharing a session id are two attempts, two episodes, each
  with its own first suspicion (`test_a_fresh_session_and_two_intervals_…`);
- a process restart within an attempt is the same episode and keeps its age
  (`test_a_process_restart_within_an_attempt_…`);
- an idle retained session can wait legitimately (a question, an external
  result with a deadline); its existence does not prove a process, and its
  waits are judged from the run's record, not from the session;
- a background job does not become durable because a session is kept: the
  `wfrun` guide's foreground-wait rule stands until the job-lifetime
  contract changes.

**The attempt time budget is not a session lifetime.** Today `wfexec`
stops an attempt after `timeout_seconds` (4 h, `.local/wfexec.toml`), one
process per attempt, one fresh session per process. When agent_session p1
reuses a session across attempts, the budget must stay per execution
interval (an attempt), a wait must keep its own deadline (`node.wait
--deadline`), and the attempt should carry the session it resumed in its
record (`attempt.begin` settings) so the observation reads it from the
record rather than from the log. Delegation will add parent/child run and
result-wait references; until then no conversation ancestry is inferred.

## Retired (observer p3 step 5)

The conversation monitor (`monitor`, its `triage`, `health` probes,
`review`/`review_status`, `hold`, `disposition`, `withdraw`, `trial`) is
removed with its tests: it discovered `#front` conversations, traced them,
probed listener servings and asked Front to recover. The watch entrance
(`listener`, `intake`, `worker`, `observe`, `notify`, `anchor`,
`destination`, `store`) stays as a library and is not started.
`python -m agobserver.retire_legacy [--dry-run]` archives the old local
state (incidents, watches, health files) with an inventory, once, at the
cutover; nothing is replayed and nothing is claimed complete. The process is
`com.agdev.agobserver` (`service/workflow.sh`,
`devenv/launchd/com.agdev.agobserver.plist.in`); it writes `agag.status.v1`
to `AGAG_STATUS_PATH` after each look whose observation came back, which is
how nodeutils and nctl see Observer alive.

## Running it

`python -m agobserver.wfmonitor [--once] [--settings .local/workflow.toml]`
(`agobserver-workflow`). Settings (ignored, per host):

```toml
wfe = ["<area>/bin/wfe"]          # the launcher of the operating area
channel = "agobserver-agstudio1"  # incident topics: incident-<id>
interval_seconds = 60
judge = true                      # local-model judgments (role wftriage)
[timing]                          # optional overrides for trials (seconds; wfclassify.TIMING)
[recovery]                        # the recovery path (wfrecover)
enabled = true
workflow = "agops/recover"        # <project>/<workflow> of the recovery recipient
channel = "wf-agops.recover"      # its Zulip channel (request-<incident> topics)
workspace = "agops"               # observed whole (--terminal) while assignments are open
# ack_timeout = 1800, max_assignments = 2, verify_timeout = 3600
```

Store: `.local/workflow/observer.sqlite`; health: `.local/workflow-health.json`
(`agobserver.workflow-health.v1`: cycle, observation source, run conditions,
open incidents by state, judgments, unacknowledged recovery assignments,
outbox). While the executor is down, lost attempts and unowned work are
listed as affected runs of the one executor incident, not incidents of
their own.
