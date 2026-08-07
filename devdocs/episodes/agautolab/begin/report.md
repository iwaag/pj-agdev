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

## Step 2 — Claude Code headless adapter + real toy job — 2026-08-07

Added the `claude_code` adapter: one-shot `claude -p --output-format json`
with `cwd=target/`, prompt on stdin, full stdout JSON kept as
`claude_output.json` evidence and token/cost fields copied into
`adapter_result.json`. `AdapterResult` gained optional `meta`/`artifacts` to
carry those; the orchestrator's wall-clock guard now gives the adapter's own
subprocess timeout a 30 s grace. `skip_permissions` exists as config but per
policy the local proof used `--allowedTools` restriction instead.

Verified: 8 new stub-CLI tests (18 total passing), then a real-model proof:
fizzbuzz toy job in `.local/jobs/fizzbuzz` converged on iteration 1
($0.13, 5 turns, 13 s, no permission denials), gate re-verified by hand.
Details in the autodev episode's `report2.md`.
