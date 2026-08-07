# agentify — Step 2 report: the autolab agent — 2026-08-08

## What was built

Tracked in `agautolab/agent/` (runtime state deliberately split out to the
gitignored `.local/agent/` per devpolicy — a deviation from the plan's sketch,
which put MISSION/NOTES inside `agent/`):

- **`CHARTER.md`** — the agent's whole system prompt (~55 lines, kept short
  on purpose: a long rulebook is Hook Handing by prompt). Session ritual
  (read MISSION → own NOTES → AGENT_GUIDE.md → work → rewrite NOTES with a
  first-line `STATUS: working|complete|blocked`), the three hard rules
  (rule 3: never write implementation code in any job `target/` — seeding
  contracts/tests is allowed, fixes go through goal/gates/notes; no
  `--dangerously-skip-permissions` anywhere; secrets stay in `.local/`),
  resource pointers (claude binary via `.local/agent/claude_bin`, gitea
  `agstudio.local:3000` org `autodev` + token path, optional `../director`),
  and the verification discipline (name the endpoint before probing; passing
  self-authored gates is a claim about the gates, not the product).
- **`session.sh`** — one headless session, never resumed: `claude -p
  --output-format json` fed CHARTER.md on stdin, cwd = repo root,
  `--allowedTools` with an explicit allowlist (file tools + ~26 scoped Bash
  commands), model `claude-sonnet-5` (env-overridable). Full output JSON
  saved as `.local/agent/sessions/session-NNNN.json`; prints an
  exit/turns/cost summary line. Binary resolution: env > `.local` pointer
  file > PATH (no absolute paths in tracked files).
- **`drive.sh`** — deliberately unintelligent driver: re-invoke `session.sh`
  until NOTES' first line is `STATUS: complete` (exit 0) / `blocked` (exit
  20) or the session budget (default 12) runs out (exit 10). Session
  crashes are logged and the loop continues — state is on disk, mirroring
  the run-once philosophy one level up.
- `agent/README.md` — layout + run instructions.

## Smoke test (plumbing, not intelligence)

Throwaway mission in `.local/agent/MISSION.md`: build a job at
`.local/jobs/smoke-fizz` on the **fake adapter** with gate
`test $(wc -l < progress.log) -ge 2` (forces 2 iterations), run to terminal,
verify via `status --json`, declare complete. Ran `agent/drive.sh 3`:

- **1 session, 9 turns, $0.40, 38 s, exit 0** — the agent seeded
  `job.yaml` + `target/`, ran `autolab loop --sleep 1`, watched it converge
  at iteration 2, cross-checked `status --json`, `gates.json`,
  `diff.patch`, and `progress.log` line count, then wrote NOTES with
  `STATUS: complete` and the evidence paths. Driver saw the status and
  exited 0.
- Rules held: no gitea repo created (mission said not to), `push: false`
  chosen by the agent, no writes into `target/` (fake adapter did the only
  target mutation; confirmed via diff evidence), zero permission denials.
- Independently re-verified from outside the agent: `autolab status` shows
  converged/2 iterations, evidence dirs present.

Cost note: the agent layer's smoke overhead ($0.40) already rivals a whole
Othello coding iteration ($0.31) — supports the plan's warning that the
agent layer multiplies spend; will be tracked per-session in Step 3.

## Deviations

- MISSION/NOTES/sessions live in `.local/agent/` (local-only runtime state),
  not tracked `agent/` — devpolicy `.local` convention wins over the plan's
  sketch; the plan explicitly allows deviation here.
- Driver polls nothing and parses nothing but the STATUS line — continuity
  intelligence stays entirely in the agent per Tool Arming.
