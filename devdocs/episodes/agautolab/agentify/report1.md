# agentify — Step 1 report: toolbelt + operator guide — 2026-08-08

## What was built

All in the `agautolab` submodule:

- **`autolab status <job-dir>` (`--json`)** — new `src/agautolab/status.py` +
  CLI wiring. Read-only and lock-free (safe while a loop is live): prints
  status/terminal flag, iteration vs `max_iterations`, no-progress counter,
  last gate summary with failing commands, error, latest evidence dir, and
  (in JSON) a digest of job.yaml. Missing dir / unreadable state exit 2.
- **`push: true` in job.yaml** — after each iteration commit and on reaching
  a terminal status, `run_once` pushes `target/` to its `origin` remote.
  Deliberately non-fatal: a transient push failure must not turn a healthy
  iteration into an error verdict; the outcome (including "no origin
  remote") is recorded as `evidence/iter-NNNN/push.json` and echoed to
  stderr. This closes the begin episode's "pushed manually" gap.
- **`AGENT_GUIDE.md`** — the primary interface of the toolbelt, written for
  an LLM reading it cold: commands, exit codes 0/10/20/30, the job-dir
  contract, job.yaml reference (incl. the agstudio no-skip-permissions
  policy), how to seed a job from scratch, how to retry a stuck job by
  resetting state.json, the evidence layout as an audit trail, and the
  Othello/asset-reconcile lessons (bare `node --test`, name the verification
  endpoint before verifying, per-iteration cost datapoint) framed as advice,
  not rules — judgment stays in the agent per Tool Arming.
- README updated (status command, push flag, pointer to the guide).

## Verification

- `uv run pytest -q` → **30 passed** (23 baseline + 7 new in
  `tests/test_status_push.py`): status before first run / after runs
  (text + JSON) / missing dir / corrupt state / read-only guarantee on a
  terminal job; push-on-commit and push-on-terminal actually landing in a
  bare remote; push without remote non-fatal; no push.json when disabled.
- Live smoke: `uv run autolab status .local/jobs/fizzbuzz` (real job from
  the begin episode) renders correctly in both text and JSON.

## Notes / deviations

- Push failure is evidence, not an error state — implementer's-discretion
  call, reasoned above.
- Default `.gitignore` for auto-initialized targets (begin-episode backlog)
  was not pulled into this step; it is not needed for the snake path and
  stays backlog.
