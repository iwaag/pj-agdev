# Report 1 — expose the job layer over HTTP

Status: done. The gateway now serves the job layer read-only, and the mediator
layer no longer requires a bearer token to read.

## What was added

All of it in `agautolab/agent/gateway.py`, which stays a stdlib-only single
file.

| Route | Returns |
|---|---|
| `GET /jobs` | one summary row per `.local/jobs/<job>/` |
| `GET /jobs/<job>` | the same row plus the evidence timeline |
| `GET /jobs/<job>/evidence/<iter>/<file>` | the raw evidence file |

Responses carry a versioned envelope, `{"kind": "autolab.monitor.v1", "type":
"jobs"|"job"|"status", ...}`, in the spirit of nctl's `nctl.drift.v1`. Scope 3
points agdevworld at this same feed; the kind is what makes "no information
loss" cheap there.

A summary row is: `status`, `terminal`, `phase`, `awaiting_approval`,
`iteration` / `max_iterations`, `consecutive_no_progress`,
`last_gate_summary` (total / passed / failing), `state_error`, `adapter`,
`push`, `iterations_on_disk`, `last_evidence`, `cost_usd`, `has_notes`.

A timeline entry per `evidence/iter-NNNN/` is: the file list (so the page can
link only to files that exist), `cost_usd`, `exit_code`, `timed_out`,
`num_turns`, `duration_ms`, `is_error`, `mtime`, and a per-gate list of
`command` / `exit_code` / `timed_out` — command and exit code, not the output
tail, which can be tens of kilobytes and is one click away as
`gates.json`.

Two changes to existing routes while in there:

- `GET /status` and `GET /log` dropped the bearer requirement. Only
  `POST /mission` — the sole route that starts anything — still authenticates.
  This is the deliberate thin-auth posture for this experimental node.
- `/status` gained `cost` (cumulative `sessions_usd` over every
  `sessions/session-*.json`, plus `current_run_sessions_usd` scoped to the
  running mission) and `devstyle` (the 3-line `Style chosen / Why / Was it
  right in hindsight` report, parsed out of mediator `NOTES.md` when present).
  Its `mission_first_line` now skips the markdown heading — every mission
  opens with `# Mission`, which told a human nothing.

## Decisions

**Job document: read `state.json` directly (plan option c).** Not
`collect_status`: importing it would pull `yaml` into a gateway process that
runs bare `python3`, not under `uv`. Not `subprocess`-ing `uv run autolab
status`: a subprocess per job per poll, on a page that polls every few
seconds. Reading `state.json` is the whole document minus `job.yaml` fields,
and those come from a helper that uses PyYAML **when the process happens to
have it** and falls back to a scan of top-level scalars otherwise — the
monitor must not hard-depend on a package the server may lack. Both paths go
through the same type coercion, so `iteration / max` stays arithmetic on the
page even when the fallback fired.

**Cost is computed unconditionally, at both layers.** Per job it is the sum of
`total_cost_usd` over `evidence/iter-*/adapter_result.json` (falling back to
`claude_output.json`); per mission it is the sum over
`sessions/session-*.json`. Agentify measured mediator cost at 3.7x
implementation cost, so these are two genuinely different numbers and the page
shows both.

**`iterations_on_disk` is reported separately from `iteration`.** `snake-web`
has `iteration: 3` but only `iter-0001` and `iter-0003` on disk. The gap is
real; the monitor reports what is there rather than inferring a range.

## Constraint compliance

- **No writes, no lock.** Every added code path is `read_text` / `glob` /
  `stat`. Nothing opens `.lock`, and nothing under `.local/jobs/` is created
  or modified by a read.
- **Nothing under `.local/` committed.** The routes read it at runtime only.
- **Code lives in the `agautolab` submodule.**

## Verification

Gateway started on `127.0.0.1:8791` against the four real historical jobs on
disk.

- `GET /jobs` → 4 rows. `snake-web-b` `converged`, `iteration 2/10`, gates
  `4/4`, `cost_usd 1.348516`, `push true`; `smoke-fizz` (fake adapter) reports
  `cost_usd: null` rather than a fabricated zero.
- `GET /jobs/snake-web-b` → the timeline with both iterations, per-iteration
  cost `0.799` / `0.549`, turns `31` / `19`, and all four gate commands with
  exit code 0.
- `GET /jobs/snake-web-b/evidence/iter-0002/gates.json` → `200`,
  `application/json`, 4 gates parsed. `.../iter-0003/diff.patch` → `200`,
  `text/plain`.
- `GET /status` and `GET /log` → `200` with no `Authorization` header.

**Degradation.** A job seeded with a truncated `state.json`, an unparsable
`adapter_result.json` and a broken `job.yaml` returned `200` with
`"error": "state.json missing or unparsable"`, null status, null cost, and the
one `job.yaml` field that was still readable. The jobs list stayed `200` with
that job present — a half-written `state.json` mid-iteration cannot 500 the
page. (The seeded job was removed afterwards.)

**Path traversal**, checked over a raw socket so curl could not normalise the
request away:

| request | result |
|---|---|
| `/jobs/../agent/gateway_token` | 400 bad job name |
| `/jobs/snake-web/evidence/iter-0003/../../job.yaml` | 404 |
| `/jobs/snake-web/evidence/iter-0003/../../../agent/gateway_token` | 404 |
| `/jobs/snake-web/evidence/iter-0003/gates.json` | 200 |

Names are pattern-checked (`^[A-Za-z0-9][A-Za-z0-9._-]*$`, `^iter-\d+$`) and
the resolved path is then required to sit under the job's `evidence/`, the
same containment guard `serve_game` uses — so a symlink cannot widen it
either.

**Tests.** `tests/test_gateway_jobs.py` added (6 tests: rollup, degradation,
timeline shape, session cost, mission first line, devstyle extraction).
`uv run pytest -q` → **47 passed**.

## Notes for step 2

- The file list per iteration is in the detail response on purpose: the page
  can render evidence links without probing for 404s.
- `last_gate_summary.failing` carries the failing gate command strings, so the
  jobs table can show "gates 3/4 — failing: node --test" from the list
  endpoint alone, with no per-job fetch.
- Nothing new needs to be produced by the agents, as the plan predicted. Every
  number above already existed on disk.
