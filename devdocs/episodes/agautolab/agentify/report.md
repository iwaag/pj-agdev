# agentify episode — final report — 2026-08-08

Goal (from [plan.md](plan.md)): invert agautolab's control structure — an
**autolab agent** receives only a mission, and drives coding agents through
the existing autolab machinery demoted to a toolbelt. Prove it end to end
with a playable browser Snake from a one-message mission, under Tool Arming
(tools + autonomy, no deterministic pre/post hooks).

Per-step evidence: [report1.md](report1.md) (toolbelt), [report2.md](report2.md)
(agent + smoke), [report3.md](report3.md) (snake, both missions).

## Success criteria — verdicts

**1. Single mission in, playable verified Snake out, no human help mid-run —
MET.** Mission 1 (Snake from scratch): one agent session, complete in
5 m 23 s. Mission 2 (speed ramp + pause, issued to force iteration 2+): one
failed session, one clean recovery session; the only human-shaped action
between mission start and completion was relaunching `drive.sh` after it
exited on a stale STATUS line — a driver-script defect, not a judgment
intervention (no state was inspected or fixed by hand; details below).
Playability was verified externally with Playwright interaction tests
(steering, restart, pause-freeze/resume) against the exact served checkout.

**2. Self-authored acceptance gates, non-trivial and non-self-serving —
MET.** The genuinely new capability under test, and it worked. The agent
wrote 10 tests for mission 1 and tightened to 17 for mission 2 with no
pre-validation by anyone. Human review of gate quality: the tests encode
adversarial intent against its own delegate — direction-reversal guard,
food respawn constrained off-snake via an injected `rng` (making an
untestable-randomness cop-out impossible), self-collision that correctly
exempts the vacating tail, and in mission 2 a structure test that greps
`main.js` to require `getTickInterval()` be re-read every tick — written
explicitly to defeat the fixed-`setInterval` lazy implementation, which the
agent then also audited for in the delegate's diff. The feared failure mode
(gates its delegate trivially passes) did not materialize; nothing
self-serving found. Gates stayed dependency-free (`node --test`), per the
guide's lesson rather than by instruction.

**3. Rule 3 (agent never writes implementation in `target/`) — HELD.**
Audited via git history + evidence diffs: seed commit `eb379e7` contains
contract/tests only; all implementation lines arrived in iteration commits
`bd7cadc`/`ce887d5` produced by the coding agent under `run_once`. One
audit-trail wrinkle: session 2 left its test-tightening uncommitted, so
`ce887d5` bundles agent-authored test changes with coding-agent
implementation (separable only via session logs + README diff). Follow-up
lesson, not a violation.

## Per-layer costs

| layer | spend | detail |
|---|---|---|
| agent (3 snake sessions) | $3.40 | $1.50 + $0.97 (partly wasted) + $0.93 |
| coding (2 iterations) | $0.92 | $0.27 + $0.65 |
| smoke test (fake adapter) | $0.40 | plumbing proof, zero coding tokens |

Management cost ≈ 3.7× implementation on this mission — the agent layer
spends most of its turns on seeding, verification, and honest bookkeeping.
That ratio should fall on bigger missions (more iterations per session of
management), but it is the number to watch.

## NOTES handoff and stuck detection

- **NOTES/crash handoff: finally exercised by a real model, and it worked.**
  Session 3 reconstructed a half-finished mission purely from disk (stale
  NOTES contradicted by `autolab status` + uncommitted test edits), chose
  correctly, and finished. The run-once-one-level-up philosophy (no resumed
  sessions, state on disk) survived its first real crash.
- **Stuck detection: still unexercised by a real model.** Both coding jobs
  converged in one iteration; sonnet-5 + well-seeded contracts are simply
  stronger than a Snake-sized task. Only fake-adapter tests cover
  stuck/no-progress. A genuinely harder mission is the way to reach it.

## Where the agent needed freedom it didn't have — and where freedom cost

- **Missing freedom:** none observed that mattered. The `--allowedTools`
  allowlist produced zero permission denials across all sessions; the agent
  even noted it avoided installing Playwright "in this sandboxed
  environment" and shipped a weaker-but-honest verification instead —
  reasonable behavior, and the external audit covered the gap. If browser
  verification should be in the agent's own lane next time, pre-install
  playwright or allow `Bash(npm:*)`/`npx` fetches explicitly.
- **Freedom that produced waste:** session 2 ($0.97) backgrounded
  `autolab loop` and ended its turn "to wait for the notification" — a
  category error about headless `claude -p` (no later turns exist). The
  session died, the loop died with it, and `drive.sh` then trusted the
  stale mission-1 `STATUS: complete` and exited 0 — a false completion that
  needed a human relaunch. Two defects, both recorded per the feedback
  policy (observe first; harden on recurrence):
  1. Agent-side: headless-background misunderstanding. Candidate one-line
     charter/guide lesson if it recurs ("run loops in the foreground; a
     session's background tasks die with it").
  2. Driver-side: `drive.sh` accepts a STATUS older than the mission.
     Candidate mechanical fix if it recurs: ignore/flag NOTES whose mtime
     predates MISSION.md's.

## What graduates to a tool, what stays judgment

- Graduated this episode (recurred in the Othello runs): `autolab status`
  and push-on-commit/terminal. Both were used heavily and correctly by the
  agent with no instruction beyond the guide.
- Stays judgment (worked without hooks): gate authorship, job configuration,
  verification depth, when to declare complete/blocked, recovery from a
  crashed predecessor.
- Watch list (fix on recurrence): the two session-2 defects above; "commit
  your seed/gate changes before running iterations" as a guide lesson to
  keep authorship auditable.

## VM/systemd next?

Recommendation: yes, as a follow-up episode — host `drive.sh` under the
existing `autolab@.service` pattern on agautolab1 (the VM already runs
claude headless), with the two driver defects fixed first (staleness check
at minimum, since unattended operation amplifies false completions). The
begin episode's deployment stays untouched per plan scope.

## Easier Next Time

No permission-classifier blocks, no >1-minute foreground waits (long runs
went through background tasks), no secrets exposure (`.local/` discipline
held; the gitea token lives only in `.local/` and `target/.git/config`).
The one pain worth an ENT note if it repeats is the headless-background
category error — it silently converts an active mission into a false
success, which is the expensive kind of failure to discover late.
