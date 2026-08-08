# Plan: human-in-loop scope 1 — minimal browser monitoring

Goal: a human can open one browser page and understand what the autolab is
doing — without SSH. Read-only monitoring only; intervention controls are out
of scope. This is an experimental, non-production environment: no backward
compatibility required, security kept deliberately thin (auth will be designed
system-wide in a later phase).

## Context and findings (read this before implementing)

All progress information already exists on disk in three layers. Nothing new
needs to be produced by the agents — scope 1 is exposure + presentation.

| Layer | Where | Notes |
|---|---|---|
| Mediator | `agautolab/.local/agent/` | `MISSION.md`, `NOTES.md` (line 1 = `STATUS: ...`, overwritten per session), `sessions/session-NNNN.json` (finalized at session end; has `total_cost_usd`, `num_turns`, `is_error`, `duration_ms`), `gateway/run-NNNN.log` (append-only, the only realtime stream) |
| Job | `agautolab/.local/jobs/<job>/` | `state.json` (status/iteration/phase/last_gate_summary, rewritten per iteration), `job.yaml`, `NOTES.md` (overwritten), `evidence/iter-NNNN/` (**the only append-only history**: `prompt.txt`, `adapter_output.txt`, `claude_output.json`, `adapter_result.json`, `diff.patch`, `gates.json`, `push.json`, `error.txt`) |
| HTTP | `agautolab/agent/gateway.py` (:8791) | stdlib-only, already serves `/status`, `/log?tail=N`, static `/game/`. **Gap: the job layer is not exposed at all.** |

Useful existing code:
- `src/agautolab/status.py` — `collect_status(job_dir)` already builds exactly
  the per-job JSON we want (status, iteration, gates, last_evidence,
  approval info). It is read-only and lock-free by design.
- `gateway.py:serve_game` — has a working path-traversal guard; reuse the
  pattern for serving evidence files.

Display selection (decided during planning, adjust freely if reality
disagrees):
- Show in the overview: mission first line, driver running/exit, NOTES status
  line, per-session cost/turns/errors, **cumulative cost** (top billing —
  agentify measured mediator cost at 3.7x implementation cost; cost is the
  single most decision-relevant number for a human), per-job status /
  iteration / gates passed-failing / last evidence link.
- Do NOT inline in the overview: `prompt.txt` full text, raw
  `claude_output.json`, full `diff.patch`. Link to them instead
  (`adapter_result.json` is a subset of `claude_output.json`; job `NOTES.md`
  largely duplicates `state.json` + `gates.json`).
- Surface the devstyle 3-line report (`Style chosen / Why / hindsight`) when
  present in mediator NOTES.md — it is an ENT asset.

Constraints (kept to the true minimum):
1. Monitoring reads must never write job/agent state or take the job `.lock`.
2. Nothing under `.local/` gets committed.
3. Code lives in the `agautolab` submodule.

Everything else — naming, layout, endpoint shapes, HTML structure — is
implementer's discretion.

## Step 1 — expose the job layer over HTTP

Add read-only, **unauthenticated** GET routes to `gateway.py` (auth stays
bearer-only for `POST /mission`; while touching this, drop the bearer
requirement from the existing GET `/status` and `/log` too — thin-auth is the
deliberate current posture):

- jobs list: enumerate `.local/jobs/*/`, one summary row each
- job detail: the `collect_status` document, plus a cost rollup and the list
  of `evidence/iter-NNNN/` dirs (that listing is the timeline)
- evidence file passthrough: serve individual files from
  `evidence/iter-NNNN/` as text/plain or application/json

Hints:
- Two ways to get the per-job document: (a) import `collect_status`
  (`job.yaml` parsing may pull non-stdlib deps into the gateway process —
  check; gateway currently runs bare python3, not under uv), or
  (b) `subprocess` out to `uv run autolab status <dir> --json`, or (c) read
  `state.json` directly with stdlib and skip `job.yaml`. Any is acceptable;
  (c) is the least coupling, (a) the least duplication.
- Wrap responses in a versioned envelope (e.g. `{"kind":
  "autolab.monitor.v1", ...}`) like nctl's `nctl.drift.v1`. Scope 3 will
  point agdevworld at the same feed; the envelope is what makes "no
  information loss" cheap later.
- Per-iteration cost lives in `evidence/iter-NNNN/adapter_result.json` (and
  `claude_output.json.total_cost_usd`); cumulative session cost is the sum
  over `sessions/session-*.json`. Tolerate missing/unparsable files — a
  half-written `state.json` mid-iteration should degrade to a row with an
  error note, not a 500.

Done when: `curl` shows the jobs list, one job detail with evidence timeline,
and a `gates.json` fetched through the gateway. Write `report1.md`.

## Step 2 — minimal HTML monitor page

One static page (plus optional small JS/CSS) under the submodule, e.g.
`agautolab/agent/monitor/`, served by the gateway at `/monitor/`
(unauthenticated, same as `/game/`). Vanilla JS, no build step, no framework —
it polls the Step 1 + existing endpoints every few seconds and renders:

- header: mission first line, driver state, STATUS line, cumulative cost
- sessions table (per-session cost/turns/errors/duration)
- jobs table (status, iteration/max, gates n/m + failing gate text, cost,
  link to latest evidence)
- evidence browser: iteration list per job, links opening raw files
- drive log tail (`/log?tail=200`), auto-refreshing

Hints:
- Polling `/status` + `/log` every 2–5 s already captures everything that is
  realtime in this system (session JSON and state.json only change at
  session/iteration boundaries), so scope 2 will likely be satisfied for
  free — note in the report whether you agree, so scope 2 can be closed or
  re-scoped based on evidence.
- Dark, dense, monospace is fine. This page's audience is the developer;
  attractive presentation is scope 3's job (agdevworld).

Done when: with the gateway running and at least one historical job on disk,
opening `http://localhost:8791/monitor/` shows all of the above without SSH.
`report2.md`.

## Step 3 — live verification and wrap-up

Run one real (or fake-adapter) mission end-to-end while watching the page:
confirm the log tail moves during the run, sessions/cost appear at session
end, job rows update at iteration end, and evidence links resolve. Fix what
falls out. Update `agautolab/AGENT_GUIDE.md` / `README.md` with the new
routes and page. `report3.md`, plus a final `report.md` for the episode
summarizing what was shown/omitted and the scope‑2 recommendation.
