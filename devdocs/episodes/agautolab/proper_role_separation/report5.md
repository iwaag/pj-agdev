# Step 5 report — Snake A/B under the mediator flow

Date: 2026-08-08. A = agentify mission 1 (lead-engineer flow, agent-authored
contract+tests), B = this run (mediator flow, coding-agent-authored
plan+gates). Same mission scope, same launcher (`agent/drive.sh 10`), same
models (agent and coder both sonnet-5).

## Setup

- Old agent state archived to `.local/agent/archive-agentify/`.
- `MISSION.md` = request language only (arrow keys, eat-to-grow/score, game
  over on wall/self, restart, deliver to gitea `autodev/snake-web-b`,
  "genuinely playable"). No technical translation, no "you own the gates"
  instruction — the rewritten CHARTER/GUIDE carry the roles now.

## Run trace (unattended, zero interventions)

- Session 1: 15 turns, $0.36, 57 s — set up job dir/remote, ended without
  NOTES. Driver continued correctly ("no notes" is not a STATUS).
- Session 2: 48 turns, $1.38, 451 s — wrote job.yaml with **goal = mission
  text verbatim and no gates**, ran the plan phase, reviewed PLAN.md +
  proposed gates against the GUIDE checklist, **approved without a reject
  round**, ran the implement loop to convergence, then audited
  independently (re-ran tests itself, served the checkout, traced the code,
  verified gitea HEAD == local HEAD) and wrote honest NOTES → complete.
- Coding job `snake-web-b`: plan iteration $0.80/31 turns, implement
  iteration $0.55/19 turns, **converged in one implement iteration** (same
  as A). Clean authorship trail: commit 1 = plan+tests (coding agent),
  commit 2 = implementation (coding agent), agent wrote nothing in target/
  — this also fixes A's audit wrinkle where agent test edits and coder
  implementation shared a commit.

## Comparison

| axis | A (agentify m1) | B (this run) |
|---|---|---|
| agent layer | $1.50, 1 session | $1.74, 2 sessions |
| coding layer | $0.27, 1 iteration | $1.35, 2 iterations (plan+impl) |
| total | $1.77 | $3.09 |
| management ratio | 5.6× | **1.29×** |
| convergence | 1 impl iteration | 1 impl iteration |
| reject rounds | n/a | 0 |

Total cost rose ~75%: plan authorship became a metered coding iteration, and
the mediator still pays for a full review+audit session. But the management
ratio — the number the agentify report said to watch — collapsed from 5.6×
to 1.29×: spend moved from the management layer to the productive layer,
which is the structural change this episode wanted.

**Gate quality (human review).** The coding agent self-proposed, unprompted:
a DOM-free `SnakeGame` engine split exactly so gates stay `node --test` with
zero deps; an **injectable `rng`** with scripted-queue determinism — the
very adversarial pattern A's lead engineer had to author to forbid the
"randomness is untestable" cop-out; a goal-sentence→gate mapping table in
PLAN.md; plus 3 structural grep gates naming the wiring they verify. 8/8
tests, 4/4 gates. Quality is comparable to A's self-authored gates; the
adversarial know-how emerged on the worker side without the mediator writing
a single test.

**Implementation-detail mentions in the agent session.** The agent's writes
were job.yaml, the git remote, approve, and NOTES — zero authorship of plan,
tests, or code (vs A: README spec, game.js API sketch, 10 tests). It did
read the implementation closely, but strictly in its audit role, which the
charter keeps in scope.

**Self-approval check (external Playwright audit, 7/7).** Independent
audit script against the exact served checkout (this session, not the
agent): canvas present; score UI visible; canvas pixels change over ticks;
driving into a wall reaches an announced game over with the restart button;
restart hides the overlay and the game runs again. Artifacts:
`scratchpad/audit/audit.mjs` + screenshot (session-local). The agent itself
had honestly declined a browser click-through (no Playwright in its
sandbox) and said so in NOTES — the self-authored-gates-pass-themselves
risk did not materialize here, but the sample size is 1.

## Watch items produced

- Session 1 burned $0.36 setting up and left no NOTES; harmless but pure
  overhead. Not recurrent yet; no rule proposed (agent-first policy).
- Plan-phase test authorship happens **before** approval (tests are part of
  the proposal) — turned out to be a feature for auditability, worth
  stating in the GUIDE if it ever confuses a reviewer.
