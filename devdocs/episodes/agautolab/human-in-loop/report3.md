# Report 3 — live verification and wrap-up

Status: done, with one deliberate substitution declared below.

## What was run

**Job layer — real, end to end.** A `fake`-adapter job (`zz-live`) with a gate
that needs five appended lines, driven by `uv run autolab loop --sleep 6`.
This is the real `autolab` loop, real `run_once`, real gate execution and real
evidence writing — only the coding agent is the token-free `fake` adapter,
which the plan allows.

**Mediator layer — real drive, stubbed session.** `POST /mission` →
`drive.sh` → `session.sh` was exercised twice for real, with
`AUTOLAB_CLAUDE_BIN` pointed at a stub that prints progress to stderr for
~18 s and then emits one session JSON of the real shape. Everything under
test — gateway, `gateway/current`, run log, session file lifecycle, the page —
is the real code path; only `claude` itself is the double.

**A real paid mission — run after the user approved the cost.** See the
section at the end: one full `POST /mission` → mediator session → job →
convergence, watched on the page throughout. It found two more bugs that
neither the stub nor the fake-adapter job could have surfaced.

## Results against the plan's four checks

| Check | Result |
|---|---|
| log tail moves during the run | yes — `session 4 starting (21:10:44)` then a new `stub session: step N/6` line every 3 s, without reloading |
| sessions/cost appear at session end | yes — `session-0004.json ok 7 $0.0000 18s` appeared at session end; the driver pill went from blue `driver running · run 2` to green `driver finished (exit 0)` |
| job rows update at iteration end | yes — `zz-live` went `running 1/8 gates 0/1` → … → `converged 5/8 gates 1/1`, and the evidence timeline grew one row per iteration |
| evidence links resolve | yes — `/jobs/zz-live/evidence/iter-0005/gates.json` returned `200` with the passing gate |

Also confirmed live: the failing gate command (`test $(wc -l < progress.log)
-ge 5`) was spelled out under the job row for the four failing iterations and
disappeared on convergence; the header showed the mission headline of the
newly submitted mission immediately; and `STATUS: (stale notes, predates
mission)` appeared correctly for the window between mission submission and the
session writing new NOTES.

## Two things the live run found

Both were only visible while something was actually running.

1. **The in-flight session read as a broken one.** `claude` creates
   `sessions/session-NNNN.json` when it starts and only fills it at the end,
   so mid-session the file is empty — and the page rendered a red `unparsed`
   next to it, which reads as "your session failed". Now `/status` reports
   `is_error: "in progress"` when a driver is alive, rendered in the live
   colour. With no driver alive the same file is still reported as
   `unparsed`, because then it really is a broken session.
2. **A stale devstyle report was shown under a new mission.** `NOTES.md`
   survives between missions, so right after a mission is submitted the
   3-line `Style chosen / Why / hindsight` block on screen belonged to the
   *previous* mission, while the STATUS line beside it correctly said the
   notes were stale. `devstyle_report()` now returns `None` whenever NOTES.md
   predates MISSION.md — the same staleness rule `notes_status()` already
   used, factored into a shared `notes_are_stale()`.

Two tests cover these (`test_live_session_reads_as_in_progress_not_broken`,
`test_stale_notes_suppress_the_devstyle_report`). `uv run pytest -q` →
**49 passed**.

## Documentation

- `agent/README.md` — the full route table (which routes authenticate, the
  `autolab.monitor.v1` envelope, the no-write/no-lock guarantee) and a
  section describing the monitoring page.
- `README.md` — a Monitoring section pointing at `/monitor/`.
- `AGENT_GUIDE.md` — a note in the evidence section that a human may be
  watching a job while an agent drives it, and that what they see is the
  agent's own evidence dirs.

## Cleanup

The verification left no residue. `zz-live` removed; the two stub sessions
(`session-0003.json`, `session-0004.json`) and the two `gateway/run-000N.*`
files removed; `MISSION.md` and `NOTES.md` restored byte-identical with their
original mtimes, so the `STATUS: complete` of the snake mission is intact.
Verified afterwards: jobs list is the original four, sessions are the original
two, cumulative cost is back to `$1.741459`.

Nothing under `.local/` was ever committed.

## The real mission (run after cost approval)

Mission: *"a tiny command-line tool that converts an integer into a Roman
numeral … anything outside 1–3999 should be a clear error, not a crash"*,
`max_sessions: 1`, with the mission text itself bounding the job to
`max_iterations <= 3` and no remote.

| | |
|---|---|
| mediator session | `session-0003.json` — 17 turns, **$0.6263**, 112 s, `is_error: false` |
| job | `roman-numeral` — `converged` at iteration **1 / 3**, gates **6/6** |
| job iteration | `iter-0001` — 8 turns, **$0.2027**, 24 s, exit 0 |
| total | **$0.83** |
| driver | exit 0 after one session; `STATUS: complete` |

Watched on the page from submission to completion. The full lifecycle
rendered correctly: mission headline appeared immediately; the driver pill sat
blue at `driver running · run 1` and turned green `driver finished (exit 0)`;
`session-0003.json` showed **`in progress`** (the fix from the stub run,
confirmed on a real session) and then `ok 17 $0.6263 112s`; the
`roman-numeral` row appeared, then converged with `6/6` gates and its cost;
its evidence row linked all six artefacts; the log tail carried the mediator's
own `session summary:` line and `drive: after session 1: STATUS: complete`.
Cumulative cost moved from $1.7415 to **$2.3678**, with `$0.6263 this run`
shown separately.

### Two more bugs, both only reachable on a real mission

5. **A just-created job read as a broken one.** The mediator writes `job.yaml`
   first; `state.json` only appears on the first `run-once`. In that window
   the row showed status `unknown` and a red *"state.json missing or
   unparsable"* — an alarming error message for the most normal moment in a
   job's life. The row now reports `not_started`, rendered as a plain
   `not started`, and `error` is reserved for a `state.json` that exists and
   will not parse. While fixing it, error text moved to its own full-width
   row too — in the status cell it squeezed the columns exactly the way
   failing gate commands did in step 2.
6. **The devstyle report was truncated mid-sentence.** Real `NOTES.md` is
   hard-wrapped prose, so reading one line per answer cut *Why* off at
   `"(max_iterations <= 3, no remote,"`. The parser now absorbs continuation
   lines up to the next blank line, bullet, heading or `Key:` line. This one
   is only visible against a real mediator session — the stub's NOTES.md was
   written by me, and I wrote it unwrapped.

Both are covered by tests (`test_job_without_state_yet_is_not_started_rather_
than_broken`, `test_devstyle_answers_are_joined_across_wrapped_lines`).
`uv run pytest -q` → **51 passed**.

### State left behind

The real mission's artefacts are genuine work product and were kept:
`.local/jobs/roman-numeral/`, `session-0003.json`, `gateway/run-0001.*`, and
`MISSION.md` / `NOTES.md` now describing the Roman-numeral mission. The
previous snake-mission `MISSION.md` / `NOTES.md` were backed up before the run
and can be restored on request; they are also still described in
`.local/jobs/snake-web-b/`.
