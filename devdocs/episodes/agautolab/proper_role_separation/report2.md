# Step 2 report — approval CLI

Date: 2026-08-08. Scope: `agautolab/src/agautolab/` (new review.py, cli.py,
status.py).

## What was built

- `autolab approve <job-dir>` — valid only in `awaiting_approval`. Parses
  `target/proposed_gates.yaml` once more (refusing if missing/invalid),
  stores the gates as `approved_gates` in state.json — job.yaml stays the
  untouched input record — sets `phase: implement`, `status: running`, and
  resets `consecutive_no_progress` / `last_gate_summary` so the implement
  phase starts with a clean progress baseline.
- `autolab reject <job-dir> --feedback <file|text>` — valid only in
  `awaiting_approval`. Feedback (inline text, or a file path if one exists)
  is appended to NOTES.md as a "Reviewer feedback — plan REJECTED" section,
  riding the existing notes channel exactly as the plan suggested: the plan
  prompt already merges NOTES.md, so no new conduit was needed. State returns
  to `phase: plan`, `status: running`.
- Both commands take the job lock non-blocking (awaiting_approval means no
  iteration should be in flight; a held lock is a real conflict) and exit 2
  on any misuse: wrong status, missing dir, held lock, empty feedback.
- `status` / `status --json` now expose `phase`, `awaiting_approval`,
  `approved_gates`, and — while awaiting — `proposed_gates` plus the PLAN.md
  path, so a polling agent can review from the status document alone.

## Evidence

Fake-adapter CLI smoke (zero tokens) via `agautolab.cli.main`:

- `reject`/`approve` outside `awaiting_approval` → exit 2, state untouched.
- plan iteration with deliverables → exit 40; `status` shows the awaiting
  hint and the proposed gate list.
- `reject --feedback "gate \`true\` passes trivially..."` → NOTES.md gains the
  REJECTED section with the text, phase back to `plan`; next run-once returns
  to `awaiting_approval` (fake adapter can't actually revise — Step 3 gives
  the fake adapter plan-phase behavior).
- `approve` → `approved_gates` recorded, phase `implement`; second `approve`
  → exit 2. Implement iterations then converge (exit 0) once the approved
  gate passes.

## Notes for later steps

- The reviewer edits nothing in target/: approve/reject + feedback text is
  the entire interface, which is the "mediator, not lead engineer" posture
  the episode is about.
- `reject` leaves the previous PLAN.md/proposed_gates.yaml in place for the
  coding agent to revise; the REJECTED notes section tells it why.
