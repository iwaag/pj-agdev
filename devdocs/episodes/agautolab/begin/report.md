# agautolab — begin episode report

Per-step log of work on agautolab driven by the autodev episode
(`../../../../devdocs/episodes/autodev/plan.md` in the projects root).

## Step 1 — skeleton + run-once core (fake adapter) — 2026-08-07

Implemented the `agautolab` Python/uv package in the `agautolab` submodule:
`autolab run-once <job-dir>` executing the full per-iteration contract
(flock → state check → prompt from goal + gate failures + NOTES.md → adapter
under wall-clock timeout → gates → evidence/iter-NNNN + NOTES.md regeneration
+ state.json update + `target/` commit → exit 0/10/20/30). State machine
`pending → running → converged | stuck | error` with `awaiting_approval`
defined but auto-passed (full-auto only). Fake adapter (appends a line to a
file) keeps everything runnable without tokens; adapter interface is
`run(prompt, workdir, timeout) -> {output, exit}` behind a name registry.

Verified: `uv run pytest -q` → 10 passed (convergence, terminal short-circuit,
lock, stuck by no-progress and by max_iterations, approval auto-pass, error
paths), plus a manual CLI smoke run. Details in the autodev episode's
`report1.md`.
