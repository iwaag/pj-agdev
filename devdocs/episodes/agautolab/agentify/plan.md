# agentify plan — autolab as an agent (Tool Arming)

Goal: invert agautolab's control structure. Today a deterministic Python loop
calls an LLM as a tool; after this episode an **autolab agent** receives only a
mission (braindump), plans it, and drives coding agents and the director using
the existing autolab machinery as its toolbelt. Prove it end to end by having
the agent build a playable browser Snake game from a one-message mission.

Decisions already made (see [braindump.md](braindump.md) and conversation):

- Policy is **Tool Arming**, not Hook Handing (devpolicy/policy.md): give the
  agent tools and autonomy; do not wrap it in deterministic pre/post hooks.
  When the agent misbehaves, record it and review — harden into scripts only
  on recurrence (established feedback policy).
- Everything runs **locally on agstudio** this episode. The VM/systemd
  deployment from the begin episode stays as-is and is not migrated.
- The existing deterministic core (`run_once.py`, `gates.py`, `loop.py`,
  `state.py`, adapters) is **demoted to tools, not rewritten**. It is proven
  and keeps flock/evidence/state for free.
- Coding-agent backend stays behind the existing adapter interface
  (`run(prompt, workdir, timeout)`); claude_code now, opencode/ollama later
  needs no design work in this episode.
- Breaking-change phase: no backward compatibility required anywhere in
  agautolab.

Constraints (deliberately minimal — everything else is implementer's discretion):

1. Secrets stay in `.local/` per devpolicy; never in tracked files.
2. **No `--dangerously-skip-permissions` on agstudio** (this Mac holds real
   credentials — standing rule). Use `--allowedTools` for all local agent
   invocations, both the autolab agent and the coding agents it spawns.
3. **The autolab agent must not write code in `target/` itself.** It plans,
   seeds contracts/tests, launches iterations, monitors, verifies, pushes —
   but implementation code comes only from the coding agents it drives. This
   is the one rule that keeps the experiment measurable: without it the agent
   collapses into a plain coding agent (the exact failure mode observed in the
   previous episodes, where all management intelligence stayed in the top
   layer).

Success criteria for the episode (evaluate in the final report):

- A single mission message in, a playable verified Snake out, no human help
  mid-run.
- The acceptance gates were **authored by the autolab agent itself** and a
  post-hoc human review judges them non-trivial and non-self-serving. (In the
  Othello runs the humans/VSCode agent pre-validated the gates; self-authored
  gates are the genuinely new capability under test. Risk: the agent writes
  tests its own delegate trivially passes — do not block this with hooks,
  observe and report it.)
- Rule 3 held (verify via git authorship + evidence diffs).

## Step 1 — toolbelt + operator guide

Make the existing machinery convenient for an LLM operator:

- Add `autolab status <job-dir>` (compact human/agent-readable state +
  last-gate summary + iteration; backlog item from the begin episode).
- Add optional push-on-commit (or at least push-on-terminal) to `run_once`,
  config-flagged in `job.yaml` — the Othello runs needed manual pushes.
- Write `agautolab/AGENT_GUIDE.md`: the job-dir contract, CLI commands, exit
  codes (0/10/20/30), evidence layout, adapter config, how to seed a job from
  scratch. Written for an LLM reading it cold — this document *is* the primary
  interface of the toolbelt; keep the tools dumb and put judgment nowhere but
  the agent.

Hints:
- CLI entry is `src/agautolab/cli.py`; state shape in `state.py` already has
  everything `status` needs.
- Verify with the fake adapter: existing tests keep passing (`uv run
  pytest -q`, 23 as of begin episode) plus tests for `status`/push.

## Step 2 — the autolab agent

Define the agent itself. Suggested shape (implementer may deviate):

- `agautolab/agent/` holding: a system-prompt/charter file (mission intake
  rules, rule 3, pointer to AGENT_GUIDE.md), `MISSION.md` (the only external
  input), agent-level `NOTES.md` for continuity, and a thin launcher script
  that runs one agent session headless (`claude -p` with `--allowedTools`,
  session-per-invocation, state on disk — same philosophy as run-once).
- Continuity: the agent is re-invoked (manually or by a trivial while-loop)
  and reconstructs context from `MISSION.md` + its own `NOTES.md` + `autolab
  status` of its jobs. Sessions are never resumed, mirroring the proven
  run-once pattern one level up.
- Give it real freedom inside its lane: bash, git, the autolab CLI, gitea API
  (agstudio gitea `agstudio.local:3000`, org `autodev`, token in `.local/`),
  and `pj-agdev/director` (`director.py` / `reconcile.py`) if it chooses to
  request assets.

Smoke test before spending real coding tokens: give it a throwaway mission
("make a job that creates fizzbuzz via the fake adapter" or similar) and
check it can seed a job dir, run `run-once`/`loop`, read status, and update
its NOTES — the plumbing, not the intelligence.

Hints:
- Record the agent layer's own cost/turns per session next to the job
  evidence (the claude JSON output gives `total_cost_usd`/`num_turns` for
  free). Othello data point: one coding iteration ran $0.31–0.48, 12–17
  turns; the agent layer on top multiplies spend — numbers make the overhead
  visible in the report.
- Keep the charter short. A long rulebook is Hook Handing by prompt.

## Step 3 — snake mission, full-auto

The VSCode agent (or the user) writes one mission message into `MISSION.md` —
roughly: "playable browser Snake on agstudio, you own the plan, the gates,
and the verification" — and starts the launcher. No intervention mid-run
except stopping a runaway.

Expected agent behavior (observe, don't enforce): plan in NOTES, create
`autodev/snake-web` on gitea, seed README contract + acceptance tests it
writes itself, configure `job.yaml` (claude_code adapter, `--allowedTools`,
sane `max_iterations`/timeouts), run the loop, monitor via `status`, verify,
push, and declare done with evidence.

Hints worth passing into the guide (lessons, not rules):
- Cheap deterministic gates won in Othello: plain ES module + bare
  `node --test`, no npm deps. Note `node --test test/` (directory arg)
  misbehaved on newer Node — use bare `node --test`.
- Name the verification endpoint **before** verifying: the asset_reconcile
  episode had a false screenshot taken from the wrong server; proof must
  state which port/process it probed (e.g. `python3 -m http.server <port>` in
  the checked-out target, then screenshot/HTTP-probe that exact port).
- Snake needs multi-iteration pressure to finally exercise NOTES handoff and
  stuck detection with a real model (Othello converged in 1 iteration and
  left both paths untested). If it converges instantly, a follow-up mission
  tightening the gates (e.g. add speed-increase or wall-mode requirements) is
  a cheap way to force iteration 2+.

## Step 4 — report + feedback

`report.md` in this episode (per-step evidence in `report1.md`…): did the
mission-only contract hold, gate quality review, rule-3 audit, per-layer
costs (agent layer vs coding layer), whether NOTES handoff / stuck detection
finally ran, where the agent needed freedom it didn't have, and where freedom
produced waste. Concrete follow-ups: what graduates to a tool (recurred),
what stays agent judgment, and whether the VM/systemd deployment should host
this agent next. Painful items go through the Easier Next Time flow.

## Reporting requirement (applies to every step)

Work on agautolab is additionally appended per step to
`pj-agdev/devdocs/episodes/agautolab/begin/report.md`'s sibling — use this
episode's own `reportN.md` files; only cross-report to other projects if
their code is touched (clusterintent work → its vision report, per standing
practice).

Out of scope: migrating the agent onto agautolab1/systemd, persistent
director service, agdevworld wiring, multi-mission scheduling, adapter
implementations beyond claude_code.
