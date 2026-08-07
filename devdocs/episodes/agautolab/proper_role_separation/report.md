# proper role separation — final report — 2026-08-08

Goal (from [plan.md](plan.md), rooted in [discussion.md](discussion.md)):
return the autolab agent from lead engineer to **mediator**. Authorship of
plans and acceptance gates moved to the coding-agent side; the autolab agent
keeps only request relay, cycle progression, and deviation review.

Per-step evidence: [report1.md](report1.md) (plan phase),
[report2.md](report2.md) (approve/reject CLI), [report3.md](report3.md)
(tests, 39 green), [report4.md](report4.md) (CHARTER/GUIDE rewrite +
drive.sh staleness fix), [report5.md](report5.md) (Snake A/B).

## What changed, in one paragraph

A job.yaml with `goal` = the client's request verbatim and no `gates` now
runs plan → awaiting_approval (exit 40) → implement. The coding agent's
first deliverable is `PLAN.md` + `proposed_gates.yaml`; the autolab agent
reviews them against the request and runs `autolab approve` (gates recorded
in state.json; job.yaml never rewritten) or `autolab reject --feedback`
(feedback rides the existing NOTES channel back into the next plan prompt).
CHARTER Rule 1 is inverted — write neither implementation nor tests — with
only the skip-permissions and secrets prohibitions surviving. The A/B run
delivered a verified Snake with zero interventions and zero reject rounds.

## The unresolved points from discussion.md — evidence and residue

**1. Gate determinism.** Resolved with the lighter option: proposed gates
are ordinary deterministic shell commands that `approve` promotes verbatim
into the existing gate machinery — the "proposal→approval" concept lives in
the job lifecycle (phase + state.json), not inside the gate runner, which is
unchanged. The A/B gates stayed dependency-free `node --test` + grep
structural checks entirely on the worker's own initiative. No further
mechanism needed on current evidence.

**2. Self-approval risk.** It moved to the worker as predicted, and on this
sample it did not bite: the worker self-proposed the adversarial patterns
(injectable rng, goal→gate mapping) that the lead-engineer design had to
impose, and the external Playwright audit passed 7/7 against the exact
delivered checkout. But n=1 and the mission is small. Standing posture (now
in the GUIDE): mediator review by traceability checklist + one independent
audit for anything user-facing. Residue: no automated place for the audit —
it ran from this session's tooling, not the agent's sandbox (which lacks a
browser and honestly said so). Candidate ENT: preinstall Playwright in the
agent's environment or add an audit hook slot.

**3. Existing-repo application.** Improved but not proven. The seed step is
gone (nothing is pre-placed in target/), so "existing repo" reduces to
cloning into `target/` before the first run-once — structurally the flow no
longer assumes greenfield. Untested residue: a plan phase over a non-empty
codebase (does the planner read before proposing? do proposed gates avoid
breaking existing behavior?). Needs its own episode on a real repo.

**4. Prime-agent connection.** Made strictly easier by this episode:
because `goal` is now the request nearly verbatim, a prime-agent request
can flow MISSION.md → goal with no translation layer — the mediator no
longer adds engineering content anywhere on that path. Still undesigned:
the transport (how agdevworld's prime agent writes MISSION.md and receives
the report back) and multi-mission queueing. Unchanged residue for the
agdevworld side.

## Costs and the number to watch

Management ratio (agent layer / coding layer) went **5.6× → 1.29×** on the
same mission; total cost rose $1.77 → $3.09 because plan authorship became
a paid coding iteration. The old ratio measured a lead engineer doing the
engineering in the expensive seat; the new one measures actual mediation
overhead. Expect the total gap to narrow on missions where a human-grade
plan review would have cost reject rounds anyway.

## CHARTER/GUIDE — further amendments?

None required by the run. Two optional lines noted for the future, only on
recurrence per the agent-first policy: "plan-phase test authorship precedes
approval by design" (if it ever confuses a reviewer) and session-1-style
setup-only sessions with no NOTES (harmless so far).

## Verdict

The mediator design is implemented, tested (39 green, token-zero), and has
one clean end-to-end proof at parity with the lead-engineer design on
convergence and gate quality, at a structurally healthier cost split. The
empirical claim from the braindump — that the lead/worker split buys
nothing over client↔designer-worker mediation — now has its first piece of
machine evidence in its favor; the next differentiating test is a mission
hard enough to force reject rounds and stuck detection.
