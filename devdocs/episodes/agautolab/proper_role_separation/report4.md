# Step 4 report — contract documents rewritten

Date: 2026-08-08. Scope: `agautolab/agent/CHARTER.md`, `agautolab/AGENT_GUIDE.md`,
`agautolab/agent/drive.sh`.

## CHARTER.md

- Opening paragraph reframed: the autolab agent is the **mediator** between
  client and coding agents — relay the request, keep the cycle moving
  (plan → review → implement → report), audit against the request. Explicitly
  "not the lead engineer".
- Rule 1 (was "never write implementation, but seed the contract") inverted
  per the plan: **write neither implementation nor tests**; `goal` carries
  the request nearly verbatim; review the delegate's PLAN.md + proposed
  gates and approve/reject; deviations and self-lenient gates get fixed via
  reject feedback, never by rewriting.
- Kept unchanged, as the only remaining prohibitions: no
  `--dangerously-skip-permissions` (agstudio policy) and secrets never in
  tracked files. The "everything else is your judgment" framing stays.
- Verification-discipline paragraph updated from "make the gates strong"
  (authoring) to "approve gates only when passing them means the mission is
  satisfied, and audit independently" (reviewing).

## AGENT_GUIDE.md

- Intro, commands (approve/reject added), exit-code table (40 added), and
  the phase/state description rewritten for the two-phase flow; documented
  that approved gates live in `state.json` and job.yaml is never rewritten.
- job.yaml example: `goal` = request verbatim with an explicit "do NOT
  translate into a technical contract" warning; `gates` shown as
  omit-by-default.
- "Seeding a job from scratch" replaced by "Starting a job": mkdir +
  job.yaml(goal) → run to exit 40 → read PLAN.md/proposed gates → approve or
  reject → implement loop. Seeding README/tests is gone ("You seed nothing
  in target/").
- New section "Reviewing a proposed plan": traceability (request sentence ↔
  gate, both directions), no trivial/stubbed passes, named verification
  endpoints, and the agentify adversarial lessons rephrased from
  "write the trap yourself" to "demand it in reject feedback" (RNG-injection
  example kept). Self-approval risk noted with the independent-audit advice.
- Lessons: added the agentify watch-list item "run driver loops in the
  foreground; background tasks die with a headless session".

## drive.sh (discretionary fix, taken)

The agentify report's driver-side defect — trusting a `NOTES.md` STATUS older
than `MISSION.md` — is closed with the suggested mtime comparison: if
`MISSION.md` is newer than `NOTES.md`, the stale STATUS is ignored and the
loop continues. Needed because Step 5 runs unattended. `bash -n` clean.

## Evidence

`uv run pytest -q` still 39 passed (docs/driver changes touch no Python).
