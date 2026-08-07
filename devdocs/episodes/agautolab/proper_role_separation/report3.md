# Step 3 report — tests for the two-phase flow

Date: 2026-08-08. Scope: `agautolab/adapters/fake.py`, `tests/`.

## What was built

- `adapters/fake.py` — the fake adapter now behaves like a planning coding
  agent when it receives a plan-phase prompt (detected by the "plan, do not
  implement yet" marker; literal substrings, since adapters must not import
  run_once): it writes `PLAN.md` and `proposed_gates.yaml`. When the prompt
  carries a "plan REJECTED" reviewer-feedback section, it appends a
  `## Revision N` section instead of rewriting the plan, so reject→replan is
  observable in the artifact. New config key `plan_gates` controls the
  proposed gates (default `test -s <file>`, which the implement-phase append
  behavior satisfies after one iteration — a self-consistent tiny agent).
  Implement-phase behavior (append one line per run) is unchanged.
- `tests/test_run_once.py` — `make_job` now emits job.yaml via `yaml.safe_dump`
  and takes `gates=None` to mean "no gates → plan phase". The obsolete
  `test_awaiting_approval_auto_passes` (old full-auto behavior, deleted per
  the no-backward-compat license) is replaced by
  `test_awaiting_approval_stops_without_running` asserting exit 40 with the
  iteration counter untouched. All other implement-phase tests pass
  unmodified — jobs with job.yaml gates behave exactly as before.
- `tests/test_plan_flow.py` (new) — token-zero coverage of:
  - plan → awaiting_approval (exit 40, deliverables in target/, goal verbatim
    in the plan prompt) → `approve` → implement (prompt contains "Approved
    plan" + the approved gate) → converged.
  - `reject --feedback` → feedback lands in NOTES.md → next plan prompt
    contains it → PLAN.md gains Revision 1 → awaiting again.
  - `--feedback <file>` reads content, not the path.
  - Invalid proposed gates → plan phase continues (exit 10) and hits the
    `max_iterations` ceiling as plan-phase stuck.
  - approve/reject outside awaiting_approval → exit 2; approve with invalid
    proposed_gates.yaml → exit 2, state untouched.
  - Implement phase with no effective gates → error (no vacuous convergence).
  - `status --json` review surface: `awaiting_approval`, `phase`,
    `proposed_gates`, `plan_file`, then `approved_gates` after approval.
  - `loop` stops at awaiting_approval with 40 and, after approval, drives the
    implement phase to convergence.

## Evidence

`uv run pytest -q` → **39 passed** (was 24 tests before this episode; old
suite deleted/adapted where the full-auto flow died).

## Next

Step 4: CHARTER.md Rule 3 inversion + AGENT_GUIDE.md seeding-section
replacement and review-lessons.
