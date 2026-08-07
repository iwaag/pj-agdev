# Step 1 report — plan phase in the toolbelt

Date: 2026-08-08. Scope: `agautolab/src/agautolab/` (state.py, job.py,
run_once.py). Tests are rewritten in Step 3; the pre-existing test suite is
expected to be red until then.

## What was built

Jobs now run in two phases: **plan → awaiting_approval → implement**.

- `job.py` — `gates` is optional. A job.yaml with no gates (the new normal:
  goal = the client's request verbatim) starts in the plan phase. Non-empty
  gates skip planning and behave exactly as before.
- `state.py` — two new fields, per the plan's recommendation to keep job.yaml
  as human/agent input and state.json as machine state:
  - `phase`: `"plan" | "implement" | null` (null = derived from job.yaml on
    first iteration, then sticky).
  - `approved_gates`: gates confirmed by the reviewer; once set they override
    job.yaml gates.
  - New exit code `EXIT_AWAITING_APPROVAL = 40` (existing: 0/10/20/30), and
    `awaiting_approval` now maps to it in `STATUS_EXIT_CODES`.
- `run_once.py`:
  - `build_prompt()` split into `build_plan_prompt()` and
    `build_implement_prompt()`.
    - Plan prompt: goal verbatim + "plan, do not implement yet". Deliverables:
      `PLAN.md` and `proposed_gates.yaml` (machine-readable, `gates:` list;
      a bare YAML list is also accepted). The prompt demands: deterministic
      gates, goal-requirement→gate mapping stated in PLAN.md, no trivially
      passing gates, named verification endpoints. Test files may be created;
      product code may not.
    - Implement prompt: the old prompt (including the "make the failing gates
      pass without weakening..." sentence, now implement-only) plus the
      approved `PLAN.md` inlined as "Approved plan".
  - Plan iterations run the adapter, then check `target/PLAN.md` +
    `target/proposed_gates.yaml`. Both present and parseable → status
    `awaiting_approval`, exit 40. Otherwise the plan phase continues
    (exit 10) up to `max_iterations`.
  - `run-once` on a job in `awaiting_approval` no longer auto-passes: it
    prints the approve/reject hint and exits 40 without running anything.
    `loop` needs no change — 40 ≠ EXIT_CONTINUE ends the loop naturally.
  - Guard: implement phase with no effective gates (neither approved nor in
    job.yaml) is an error, so an empty gate list can never "converge" by
    vacuous `all()`.

## Discretionary calls (plan left these open)

- Phase and approved gates live in **state.json**, not written back to
  job.yaml (plan's recommended option; keeps the input/state distinction).
- Proposed gates format: separate `proposed_gates.yaml` at the target root —
  machine-readable, and its diff shows up in the per-iteration evidence like
  everything else.
- Stuck/no-progress detection is **disabled in the plan phase** (a good plan
  can be a small diff); only `max_iterations` bounds it, as the plan's advice
  section suggested.
- Reviewer feedback will ride the existing NOTES.md channel (Step 2): the
  plan prompt already tells the agent that notes may contain reviewer
  feedback.
- `push: true` also pushes when entering `awaiting_approval`, so a remote
  reviewer can read the plan without filesystem access.

## Evidence

Smoke test (fake adapter, zero tokens) in the session scratchpad:

1. job.yaml with goal only → plan iteration 1, no deliverables → exit 10,
   `phase: plan`, `status: running`.
2. PLAN.md + proposed_gates.yaml placed in target/ → plan iteration 2 →
   exit 40, `status: awaiting_approval`.
3. run-once again → exit 40 immediately, iteration counter untouched.
4. Hand-edited state (approve simulation: `approved_gates` set, phase
   `implement`) → implement iterations run the approved gate, converge with
   exit 0 once the gate passes.

## Next

Step 2: `autolab approve` / `autolab reject --feedback` CLI + `status --json`
phase fields, replacing the hand-edit in step 4 of the smoke test.
