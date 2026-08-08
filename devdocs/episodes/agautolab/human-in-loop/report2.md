# Report 2 — minimal HTML monitor page

Status: done. `http://<host>:8791/monitor/` shows the mission, the driver, cost,
sessions, jobs, gates, the evidence timeline and the drive log without SSH.

## What was added

`agautolab/agent/monitor/` — three files, no build step, no framework, no
dependency: `index.html` (structure), `monitor.css` (dark/dense/monospace),
`monitor.js` (poll + render). Served by the gateway at `/monitor/`,
unauthenticated, the same as `/game/`. `serve_game` was generalised into
`serve_static(base, rel)` so both paths share one containment guard rather
than growing a second copy of it.

The page polls `/status`, `/jobs`, `/log?tail=200` and (when a job is
selected) `/jobs/<job>` every 3 s and re-renders:

- **header** — mission headline, driver pill (running / finished exit N /
  idle), the `STATUS:` line from mediator NOTES.md, cumulative cost in the
  top-right, and the devstyle 3-line report when NOTES.md carries it.
- **jobs table** — status, `iteration / max`, gates `n/m`, cost, latest
  evidence dir and how many are on disk. Clicking a row expands its evidence.
- **evidence browser** — newest iteration first: wall-clock time, cost, turns,
  duration, exit code, gates `n/m`, and a link per evidence file that opens
  the raw `prompt.txt` / `diff.patch` / `gates.json` / `claude_output.json`
  through the gateway.
- **sessions table** — per session: result, turns, cost, duration, with a note
  when the view is scoped to the current run rather than everything on disk.
- **drive log** — `tail=200`, refreshed on every poll.

Two details worth keeping:

- The selected job lives in the URL hash (`/monitor/#job=snake-web-b`), so a
  reload returns to the same job and the link can be pasted to someone else.
- The log pane only follows the tail while the reader is already scrolled to
  the bottom. Reading scrollback is not yanked away by the next poll.

## Two bugs found by looking at the rendered page

Both were invisible from `curl` and only showed up in a real browser render:

1. **Columns drifted apart.** `width: 100%` on a 6-column table spreads the
   slack across every column, so the cost sat halfway across a 1280px screen
   from the job name. Fixed by `white-space: nowrap` on cells plus an empty
   trailing `.grow` column that absorbs all the slack.
2. **A failing gate destroyed the layout.** Gate commands are long
   (`grep -q '<canvas id="board"' index.html`); rendered inside the gates
   cell, the wrap squeezed that column to about four characters wide and
   broke the command one character per line. Fixed by giving each failing
   gate its own full-width row beneath the job. Verified against a seeded job
   with 2 of 4 gates failing (screenshot taken; the seeded job was removed
   afterwards).

## Verification

Gateway on `127.0.0.1:8791`, four real historical jobs on disk, rendered
headless at 1280x860.

- Header: mission headline (full first paragraph — the literal first line
  stopped mid-sentence, so `/status` now reports `mission_headline`),
  `driver idle`, `STATUS: complete`, `cost $1.7415 (all sessions)`.
- Jobs: 4 rows, e.g. `snake-web-b converged 2 / 10 gates 4/4 $1.3485
  iter-0002 (2 on disk)`. `smoke-fizz` (fake adapter) shows `—` for cost
  rather than a fabricated `$0.0000`.
- Evidence for `snake-web`: `iter-0003 3:45:44 AM $0.6527 29 turns 82s exit 0
  gates 1/1` with seven working file links; `iter-0001` below it.
- Sessions: both sessions with turns, cost and duration.
- Log: `no drive run yet (POST /mission starts one)` — correct, no run has
  been started on this machine. The live behaviour is step 3's job.
- `/monitor/../gateway.py` and `/monitor/../../.local/agent/gateway_token`
  return **403** over a raw socket (curl normalises the path away before it
  is sent, so this had to be checked without it).
- `uv run pytest -q` → **47 passed**.

## Scope 2 recommendation: close it

The plan asked whether polling already satisfies scope 2 (realtime progress).
It does, and the evidence is in the data model rather than in the page:

- `sessions/session-NNNN.json` is written **once, at session end**.
- `state.json` and `evidence/iter-NNNN/` are written **once per iteration**,
  at the iteration boundary.
- `gateway/run-NNNN.log` is the **only** append-only realtime stream, and it
  is already tailed every 3 s.

So there is nothing in this system that changes faster than the poll except
the drive log, which the page follows. An SSE or WebSocket transport would
carry the same three files at the same three moments — it would move the
latency of a session-end row from ≤3 s to ~0 s and nothing else. That is not
worth a persistent-connection code path in a stdlib-only gateway.

One thing genuinely is missing at the realtime end, and it is **not** a
transport problem: while an iteration is running (60–160 s in the observed
runs) the job layer emits nothing at all — the coding agent's tool calls are
only visible after `claude_output.json` lands. If more within-iteration
visibility is wanted, the work is to make the adapter stream turns to disk,
and only then does a push transport start to earn itself. Recommendation:
**close scope 2 as satisfied**, and if the within-iteration blind spot
matters, open it as its own item rather than as "realtime display".

## Note

The page is deliberately developer-facing: dark, dense, monospace, desktop
widths. Attractive presentation is scope 3's job (agdevworld), and the
`autolab.monitor.v1` envelope is what lets scope 3 consume the same feed
without information loss.
