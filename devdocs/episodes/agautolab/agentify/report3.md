# agentify — Step 3 report: snake mission, full-auto — 2026-08-08

Input: one mission message in `.local/agent/MISSION.md` (playable browser
Snake, delivered as `autodev/snake-web` on the agstudio gitea, "you own the
plan, the gates, and the verification"). No intervention mid-run.

## Mission 1 — Snake from scratch

`agent/drive.sh 10` → **1 session, 50 turns, $1.50, 5 m 23 s → STATUS:
complete.** The agent, unprompted on specifics: seeded the contract
(README spec + `game.js` API, `package.json` zero-deps, **self-authored
acceptance tests** — 7 logic tests incl. reversal-guard, food respawn
off-snake via injected rng, tail-vacating self-collision, plus 3 structure
tests wiring index.html→main.js→game.js), configured `job.yaml`
(claude_code, sonnet-5, scoped `--allowedTools`, `push: true`, gate
`node --test` — the guide's lessons taken), created the gitea repo, ran the
loop (converged iteration 1, **$0.27**, 9 turns, 0 permission denials),
then verified beyond gate-passing: hand-read the implementation, served the
exact checkout on a named port (8934) and curl-probed it, and byte-diffed
the gitea copy against the tested copy via API. It even cleaned up its
verification server and honestly recorded what it did NOT test (no
browser-interaction test) with a suggested path for stronger evidence.

External audit (VSCode agent):

- **Rule 3 held**: seed commit `eb379e7` = contract/tests only (192 lines);
  all implementation (game.js/index.html/main.js/style.css, 247 lines)
  arrived in iteration commit `bd7cadc`. Evidence diffs agree.
- **Playability confirmed visually** (the gap the agent disclosed):
  Playwright screenshots — game loop runs (snake auto-moves, wall collision
  → Game Over UI), and a keypress test (R restart, arrow steering) shows
  live input response. Screenshots in scratchpad; probe target
  `http://localhost:8934/` = the exact `target/` checkout.

## Mission 2 (follow-up, forcing iteration 2+) — speed ramp + pause

Since mission 1 converged in one iteration (as Othello did), a follow-up
mission was issued: speed-up on score growth + `P` pause, "tighten the gates
so passing proves both". This produced the episode's most valuable data:

- **Session 2 failure (observed, not blocked)**: 26 turns, $0.97 — the agent
  correctly extended the README contract and tests (+7 tests), reset
  `state.json` to running, launched the loop — *in a background Bash task,
  then ended its turn with "I'll wait for the loop to notify me"*. Headless
  `claude -p` sessions die at end of turn: the loop was killed pre-adapter,
  NOTES was never updated, and `drive.sh` read the **stale**
  `STATUS: complete` from mission 1 and exited 0 — a false completion.
  Two distinct defects: (a) agent misunderstanding of headless background
  semantics, (b) driver trusting a STATUS line that predates the mission.
- **Recovery proved the architecture**: relaunched `drive.sh` with no other
  help. Session 3 (32 turns, $0.93) reconstructed everything from disk —
  found the tightened-but-uncommitted tests, confirmed old code failed the
  new gates by running `node --test` itself, ran `run-once` (iteration
  numbering jumped to 0003, harmless), got 17/17 gates passing, audited the
  diff for the lazy-implementation trap it had anticipated (fixed
  `setInterval` vs re-read `getTickInterval()` per tick — the coding agent
  did it right with self-rescheduling `setTimeout`), verified push
  (`ce887d5`), re-diffed gitea vs local byte-for-byte, re-served and probed,
  and wrote honest NOTES. This is the NOTES-handoff / crash-recovery path
  finally exercised by a real model — the begin episode never reached it.
- Coding iteration 0003: **$0.65**, 29 turns, converged in 1 iteration.
- External audit: pause verified live via Playwright (paused message shown,
  canvas frozen across 800 ms while paused, motion resumes on second `P`).
  Gitea `main` = `ce887d5`, history clean (seed → iter1 → iter3).

## Costs (agent layer vs coding layer)

| layer | spend | detail |
|---|---|---|
| agent sessions | $3.40 | S1 $1.50/50t, S2 $0.97/26t (partly wasted), S3 $0.93/32t |
| coding iterations | $0.92 | iter1 $0.27/9t, iter3 $0.65/29t |

The management layer cost ~3.7× the implementation layer on this mission.

## Observations for Step 4

- Self-authored gates were non-trivial and anti-self-serving (reversal
  guard, rng injection, the structure test that greps for per-tick interval
  re-reading — written specifically to defeat a lazy delegate). No gate
  weakening by either layer (diff-audited).
- Audit-trail wrinkle: session 2 left its test-tightening uncommitted, so
  `run_once`'s `git add -A` bundled agent-authored test changes and
  coding-agent implementation into one commit (`ce887d5`). Rule 3 still
  auditable via evidence diffs + session logs, but "agent commits its
  seeds/gate changes before running iterations" would keep authorship clean
  — candidate guide lesson, not a hook.
- Recurrence watch (per feedback policy): the "background task + end turn"
  headless misunderstanding is one occurrence; if it recurs, a charter line
  or a `drive.sh` staleness check (compare NOTES mtime vs MISSION mtime)
  graduates to a fix.
