# ex1 — final report

Executed 2026-08-10 against `plan.md` in this directory. Outcome: **success
(braindump 3-2)** on the third attempt, after two informative failures that
were both harness gaps, not judgment failures by the window.

## What was built

- `/director` removed from `agent/gateway.py` (route, prompt, runner,
  records, lock), from `tests/test_gateway_window.py`, and from
  `agent/README.md`; `AUTOLAB_DIRECTOR_WORKSPACE` dropped from `.local/.env`.
  Old run records under `.local/agent/director/` kept as evidence.
- `.local/direction/projects.md` — the hand-written one-line-per-project
  index; `.local/direction/<name>/` is the projects root.
- `agent/GUIDE.md` gained the four-line "Project directors" section (paths +
  the launch command, nothing about project selection or passthrough).
- Window Tool Giving in `gateway.py`:
  `WINDOW_ALLOWED_TOOLS = "Read,Glob,Grep,Bash(cd:*),Bash(claude:*)"`,
  `WINDOW_TIMEOUT_SECONDS = 300`, and the resolved claude binary's directory
  prepended to the one-shot's `PATH`. `.local/.env` sets
  `AUTOLAB_WINDOW_BACKEND=claude` permanently.
- All 81 tests pass; the gateway was restarted and `/director` verified 404.

## The experiment

`POST /window` with 「SFゲームのプロジェクトのディレクターに依頼。この
ゲームのバックストーリーを提案して」, three attempts, records
`window/run-0050..0052`:

1. **run-0050 — failure (3-1), $0.51, 91 s, 19 turns.** Allowed tools were
   `Bash(claude:*)` only; reaching the workspace takes `cd <dir> && claude`,
   and the permission check rejects the `cd` part. The window reported the
   denial honestly, then composed a backstory itself — the defined failure.
   Fix: allow `Bash(cd:*)`.
2. **run-0051 — failure (tooling), $0.25, 31 s, 9 turns.** Permission passed
   but `claude` was `command not found`: the gateway launches its own backend
   via the `claude_bin()` glob, and the one-shot's `PATH` never contained
   that directory. Notably the window did NOT self-answer this time — it
   reported the breakage and asked how to proceed. Fix: prepend the resolved
   binary's directory to `PATH`.
3. **run-0052 — success (3-2), $0.185 outer, 107 s, 4 turns.** The window
   identified `scifi-direction` from the index, launched a real director
   session in that workspace (verified in the session transcript, cwd
   `agautolab/.local/direction/scifi-direction`, started 09:11:04Z during the
   run), passed the request through, and returned the director's proposal
   (『AZURE VEIL』: title, timeline, central mystery, themes, visual-guideline
   consistency) with a thin frame — 「ディレクターからバックストーリー案が
   届きました」.

No project-selection or passthrough instruction was ever added: the two
Failure Farming corrections were both capability plumbing. The vague-request
routing itself worked with zero guidance.

## Deviations and caveats

- **Relay is a digest, not verbatim.** The braindump asks for the proposal
  「そのまま」; run-0052 relays a faithful but condensed version (the
  director's full text, with a complete chapter-level backstory, exists only
  in the inner session transcript). Judged within 3-2's thin-framing
  allowance, but a stricter verbatim bar would call it partial.
- **The inner director run's cost is recorded nowhere.** The outer record's
  `cost_usd` covers only the window session; the nested one-shot's spend is
  invisible to `/status` and the run records.
- **The window rephrased the request** into 「このゲームのバックストーリーを
  提案してください。既存の資料があればそれを踏まえてください」 rather than
  forwarding the user's words untouched. Reasonable, but it is
  interpretation, not pure passthrough.
- A stray `/director` run (run-0007, "hi", $0.13) happened mid-deploy: the
  first `pkill` pattern missed the live process (its argv starts with the
  Python.app binary, not `python3`), so an old server briefly kept serving.
  Deploy checks caught it; kill with `pkill -f "agent/gateway.py"`.

## Elements the runs suggest adding next (only on observed need)

1. Verbatim-passthrough evidence: have the window (or the harness) keep the
   inner director's raw reply somewhere inspectable, so 3-2 judgments don't
   require digging session transcripts.
2. Nested-run cost visibility, folding the inner one-shot's `total_cost_usd`
   into the window record.
3. The director tried to save `backstory.md` and was refused (read-only
   tools); if persisting direction documents becomes a real task, that is a
   Tool Giving decision for the workspace, not a prompt change.
4. Gateway supervision (launchd) — the stale-process incident is the second
   restart-related surprise across episodes.

## Deus Ex Machina record

Omni Agent did the gateway surgery, index/GUIDE edits, restarts, and drove
the three experiment runs for the autolab window agent — handoff candidate.

## Costs

Experiment total ~$0.95 (0.51 + 0.25 + 0.185) plus the $0.13 stray director
run and an unrecorded inner director run in attempt 3.
