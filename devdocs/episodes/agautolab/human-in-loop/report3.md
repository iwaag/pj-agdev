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

**Not run: a paid mediator session.** A real mission means a real
`claude -p` session (the two on disk cost $0.36 and $1.38 and ran 57 s and
451 s). That is real money and a certain multi-minute wait, so it is the
user's call, not mine. Everything below was verified without it, and the only
thing a paid run would additionally prove is that a real session's JSON has
the fields the page reads — which the two historical sessions on disk already
demonstrate, since the page renders them.

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
