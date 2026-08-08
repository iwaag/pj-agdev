# asset_reconcile ex1 — duration and session-count analysis

Date: 2026-08-08.

## Question

Why did a tiny three-image browser gallery take approximately 39 minutes,
six mediator sessions, and USD 9.81 of known LLM spend?

The evidence is sufficient to identify the dominant causes. The product code
was small and all three agforge requests succeeded on their first attempt. The
run became expensive primarily because the mediator repeatedly launched or
waited for background autolab work across headless session boundaries, lost
durable progress narration, misdiagnosed one permission path as a hard
blocker, and required a disproportionately large plan/gate framework for the
small product.

This document distinguishes directly observed facts from inferences. The
gateway session JSON stores each session's final answer and aggregate
cost/timing, but not a complete raw tool-call transcript. Therefore the
dominant causes are identifiable, while every second and token cannot be
attributed to a specific command.

## Overall measurements

Gateway run 3 started at approximately 03:27:02 UTC and reached terminal
`STATUS: complete` at approximately 04:05:58 UTC: about 2,336 seconds, or
38 minutes 56 seconds, including the five-second driver gaps between fresh
sessions.

| Layer | Work | Turns | Recorded duration | Cost |
|---|---:|---:|---:|---:|
| Gateway mediator | 6 fresh sessions | 303 | 2,269 s | $7.3324366 |
| Coding agent | 3 completed iterations | 94 | 453.581 s | $2.0515236 |
| Director | 3 compose + 3 review calls | 9 | 26.790 s | $0.4239135 |
| agforge agent | 3 successful requests | 22 | 252.834 s | $0.00 |
| **Known LLM spend** |  |  | durations overlap | **$9.8078737** |

The durations must not be summed as wall time: coding-agent, director, and
agforge work happened inside the mediator sessions. The useful comparison is
that the three coding iterations, six director calls, and three agforge runs
account for about 733 seconds of serial backend work, while the top-level run
took about 2,336 seconds. Some difference is legitimate orchestration and
verification, but a large portion was session/process overhead and repeated
state reconstruction.

## Session-by-session reconstruction

| Session | Duration | Turns | Cost | Final message / observed role |
|---|---:|---:|---:|---|
| 0003 | 569 s | 72 | $2.0451565 | Ended saying it would resume after a background iteration finished. |
| 0004 | 56 s | 19 | $0.3219610 | Ended waiting for the same background `run-once` before plan review. |
| 0005 | 112 s | 26 | $0.6493258 | Again ended waiting for the background plan iteration. |
| 0006 | 686 s | 68 | $1.6839028 | Completed two real plan iterations, then declared direct Claude invocation permission a genuine blocker. |
| 0007 | 512 s | 68 | $1.4569622 | Reconciled all three images, approved the plan, then left the implement loop running in the background. |
| 0008 | 334 s | 50 | $1.1751283 | Reconstructed stale state, ran the actual implement iteration, independently re-audited, installed, and completed. |

Sessions 0003–0005 alone consumed 737 seconds, 117 turns, and $3.0164433.
Their final messages contain no completed plan review or durable job result;
all three describe waiting for background work.

## Primary cause: background work did not match the headless session lifetime

The deployed operator guide contains two incompatible instructions:

1. Near the command overview it says that a long-running `loop` is best
   launched in the background and polled with `status`.
2. In the lessons section it says driver loops must run in the foreground of a
   live session because background tasks started inside a headless session die
   with that session.

The mediator followed the first instruction in sessions 0003–0005 and again
at the end of session 0007. The observed durable job state strongly supports
the second instruction as the true runtime behavior.

The final job state says `iteration: 7`, but evidence exists only for:

```text
evidence/iter-0004/
evidence/iter-0005/
evidence/iter-0007/
```

There are no evidence directories for iterations 0001, 0002, 0003, or 0006.
This is not normal successful or handled-error behavior: a handled autolab
iteration writes an evidence directory, and even an `IterationError` attempts
to write `error.txt`.

The implementation explains the exact failure signature:

1. `run_once` calculates the next iteration number.
2. It immediately sets `state.status = running`, stores the new iteration
   number, and saves `state.json`.
3. Only afterward does it invoke the coding adapter and gates.
4. It writes the normal evidence directory near the end of the iteration.

If the containing process is killed after step 2 but before step 4, the state
retains the consumed iteration number and no evidence directory is created.
That is exactly the observed pattern for 0001–0003 and 0006.

It is therefore a strong evidence-based inference—not merely speculation—that
the background `run-once`/`loop` processes were terminated with their
headless mediator sessions. Iterations 0001–0003 correspond to the repeated
background plan attempts in sessions 0003–0005. Iteration 0006 corresponds to
the background implement loop session 0007 said it had launched; session 0008
then ran the completed implementation as iteration 0007.

Consequences:

- four iteration numbers were consumed without evidence;
- three early mediator sessions spent substantial time starting, polling, or
  reasoning about work that did not complete durably;
- the final implement work had to be started again in session 0008;
- state and narration became harder to trust, increasing later verification.

## Secondary cause: the plan phase was much larger than the product

The first completed plan iteration, 0004, took 273.755 seconds, 28 turns, and
$0.918962. Although the plan-phase contract principally requires `PLAN.md`
and `proposed_gates.yaml`, that iteration also authored the actual gate and
test implementation:

- four test files plus a hand-written DOM stub;
- a PNG parser;
- a manifest schema validator;
- a delivered-asset validator;
- an external-reference scanner.

The first plan commit added 744 textual lines across 12 files. By comparison,
the final product implementation commit added only 148 textual lines, plus the
three image binaries.

This was not useless work: the episode explicitly required deterministic
asset checks, switching behavior, exact dimensions, local references, and
non-trivial gates. However, the chosen verification architecture was large for
a three-button static gallery. The hand-written DOM environment and multiple
single-purpose scanners made the acceptance framework substantially more
complex than the application being accepted.

The first plan also used an incompatible manifest contract:

```json
{
  "assets": [
    {"width": 800, "height": 600, "status": "pending"}
  ]
}
```

The tested reconcile tool requires a top-level `requests` array and
`status: requested`; the proven generation dimensions were 1024×1024. The
mediator correctly rejected the plan, and iteration 0005 changed it to:

```json
{
  "requests": [
    {"width": 1024, "height": 1024, "status": "requested"}
  ]
}
```

That correction cost another 72.469 seconds, 25 turns, and $0.4230525. The
review round trip was an intentional part of the episode, but the initial
mismatch also shows that the coding-agent goal did not make the existing
reconcile schema sufficiently unavoidable. The mediator had the schema
knowledge, while the isolated coding agent was asked to invent a technical
manifest and naturally chose different field names and dimensions.

## Secondary cause: permission-path failure was misdiagnosed as an environment blocker

After the two plan iterations, session 0006 tried to invoke the Claude binary
directly through Bash for the director. The permission system rejected the
direct binary call and wrapper variations. The session's final answer called
this a genuine blocker and asked for an allowlist change or user guidance.

That diagnosis was incorrect. Session 0007 successfully invoked the allowed
`python3 tools/reconcile.py` path, which in turn launched the configured
director subprocess. All three compose/review flows completed without any
permission change or user action.

The difference is important:

- denied path: the mediator asks its shell tool to execute the Claude binary
  directly;
- working path: the mediator executes the already-allowed reconcile Python
  program, and that program owns its director subprocess boundary.

Session 0006 did perform legitimate plan work, so its full 686 seconds and
$1.6839028 cannot be classified as waste. The available aggregate session JSON
does not permit an exact split. Nevertheless, the repeated direct-invocation
attempts, false blocker conclusion, and need for the next session to recover
clearly added avoidable turns and delay.

The coding-agent iterations separately recorded 13 permission denials, mainly
for compound shell probes, `file`, broad environment/tool discovery, and
chained gate commands. The coding agent recovered with allowed alternatives,
so these denials did not block completion, but they increased reasoning and
command-reformulation overhead.

## Secondary cause: NOTES did not track real progress

The mediator charter requires every session to update
`.local/agent/NOTES.md` before ending. Sessions 0003–0007 made material
progress but did not leave NOTES synchronized with the durable job state.
Session 0008 found narration left at an earlier planning snapshot even though:

- the plan had been corrected and approved;
- all three assets had been reconciled and delivered;
- direction evidence had been committed and pushed;
- the job had entered implement phase.

Session 0008 correctly refused to trust the stale narrative. It re-read
`state.json`, git history, iteration evidence, the manifest, every director
envelope, and candidate/delivered hashes before continuing. This avoided
duplicate agforge requests and an incorrect approval, but duplicated
verification already performed by prior sessions.

The final session took 334 seconds, 50 turns, and $1.1751283. It also performed
necessary work—the real implement iteration took 107.357 seconds, followed by
install and endpoint checks—so the exact cost of NOTES reconstruction cannot
be separated. Still, the final NOTES and session result explicitly identify
stale handoff reconstruction as a substantial part of the session.

The underlying design problem is that the only cross-session narrative
checkpoint is agent-authored prose written near the end of a session. A
session that spends its budget on a long child process or troubleshooting can
terminate after changing durable state but before updating the narration.

## What was not the cause: agforge retries or image failures

All three images succeeded on their first request:

| Image | agforge duration | Agent turns | Result |
|---|---:|---:|---|
| `gallery-image-1` | 68.431 s | 6 | valid 1024×1024 PNG, accepted |
| `gallery-image-2` | 103.938 s | 6 | valid 1024×1024 PNG, accepted |
| `gallery-image-3` | 80.465 s | 10 | valid 1024×1024 PNG, accepted |

Total agforge runtime was 252.834 seconds, about 4 minutes 13 seconds. Director
compose/review added 26.790 seconds. There were no second attempts, format
failures, dimension failures, subjective rejections, URL failures, or image
conversion workarounds.

Asset work was necessarily sequential in the current `reconcile.py` usage and
therefore contributed roughly five minutes including director calls and
polling, but it does not explain the remaining duration or the six mediator
sessions.

## Root-cause ranking

The causes, from highest confidence and likely impact downward, are:

1. **Background child work was incompatible with fresh headless mediator
   sessions.** Four iteration numbers have no evidence, and session final
   messages explicitly describe background waiting.
2. **The operator guide contradicted itself about background versus foreground
   execution.** The mediator selected the unsafe instruction more than once.
3. **The acceptance framework was much larger than the product.** The first
   plan commit added 744 lines of tests/tools before the 148-line app existed.
4. **The first invented manifest did not match the existing reconcile tool,**
   requiring a second coding-agent plan iteration.
5. **A direct director-binary permission denial was misdiagnosed as a genuine
   blocker,** even though the sanctioned Python boundary worked unchanged in
   the next session.
6. **Agent-authored NOTES lagged durable state,** forcing the final session to
   reconstruct and re-verify prior work.
7. **Three image generations were serial.** This was real necessary work, but
   all succeeded and accounted for only about four minutes.

## Corrective direction

The evidence suggests the following changes, in priority order:

1. Remove the guide contradiction. For the current gateway/session model,
   require `autolab loop`/`run-once` to remain in the foreground of the live
   mediator session. Alternatively, move long child ownership into a durable
   gateway/service process before recommending background execution again.
2. Make interrupted iterations explicit. Create an evidence directory with a
   `started` record before invoking the adapter and mark abandoned/incomplete
   work on recovery, or delay committing the new iteration number until a
   durable start record exists.
3. Add a machine-generated mediator checkpoint after every major transition
   (job created, awaiting approval, rejected, approved, each asset delivered,
   implement started, converged). Do not depend only on end-of-session NOTES.
4. Expose director reconciliation as one sanctioned command/service boundary.
   The mediator should never need to experiment with direct Claude binary
   invocation.
5. Scale gates to the risk. Preserve PNG/dimension/reference and real switching
   checks, but combine mechanical scanners and avoid a custom DOM framework
   unless browser behavior genuinely cannot be tested more cheaply.
6. Publish the reconcile manifest schema to the isolated coding side as a
   technical protocol, without exposing creative direction. Isolation should
   not require rediscovering field names already fixed by the consumer.
7. If generation latency matters, allow independent manifest entries to run in
   parallel while retaining a two-attempt limit and per-entry durable evidence.

The most important conclusion is that the one-mission architecture itself was
not disproven. The run completed correctly and preserved role separation. The
expensive behavior came from how long-lived child work and progress state were
mapped onto short-lived fresh mediator sessions. Fixing that lifecycle boundary
should remove several sessions and much of the $7.33 mediator overhead without
weakening the end-to-end verification.
