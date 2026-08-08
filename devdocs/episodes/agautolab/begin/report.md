# agautolab — begin episode report

Per-step log of work on agautolab driven by the autodev episode
(`../../../../devdocs/episodes/autodev/plan.md` in the projects root).

## Step 1 — skeleton + run-once core (fake adapter) — 2026-08-07

Implemented the `agautolab` Python/uv package in the `agautolab` submodule:
`autolab run-once <job-dir>` executing the full per-iteration contract
(flock → state check → prompt from goal + gate failures + NOTES.md → adapter
under wall-clock timeout → gates → evidence/iter-NNNN + NOTES.md regeneration
+ state.json update + `target/` commit → exit 0/10/20/30). State machine
`pending → running → converged | stuck | error` with `awaiting_approval`
defined but auto-passed (full-auto only). Fake adapter (appends a line to a
file) keeps everything runnable without tokens; adapter interface is
`run(prompt, workdir, timeout) -> {output, exit}` behind a name registry.

Verified: `uv run pytest -q` → 10 passed (convergence, terminal short-circuit,
lock, stuck by no-progress and by max_iterations, approval auto-pass, error
paths), plus a manual CLI smoke run. Details in the autodev episode's
`report1.md`.

## Step 2 — Claude Code headless adapter + real toy job — 2026-08-07

Added the `claude_code` adapter: one-shot `claude -p --output-format json`
with `cwd=target/`, prompt on stdin, full stdout JSON kept as
`claude_output.json` evidence and token/cost fields copied into
`adapter_result.json`. `AdapterResult` gained optional `meta`/`artifacts` to
carry those; the orchestrator's wall-clock guard now gives the adapter's own
subprocess timeout a 30 s grace. `skip_permissions` exists as config but per
policy the local proof used `--allowedTools` restriction instead.

Verified: 8 new stub-CLI tests (18 total passing), then a real-model proof:
fizzbuzz toy job in `.local/jobs/fizzbuzz` converged on iteration 1
($0.13, 5 turns, 13 s, no permission denials), gate re-verified by hand.
Details in the autodev episode's `report2.md`.

## Step 3 — loop mode — 2026-08-07

Added `autolab loop <job-dir>`: repeats `run-once` while it returns 10
(continue) with a configurable `--sleep` (default 5 s) between iterations,
and exits with the terminal code (0/20/30; 130 on Ctrl-C). No recovery code
needed — state is on disk, the next run continues. Template systemd user unit
recorded at `devenv/systemd/autolab@.service` (`Restart=on-failure` with
`RestartPreventExitStatus=20 30` so terminal verdicts don't restart-loop);
installation is Step 5 work.

Verified: 5 new tests in `tests/test_loop.py` (23 total passing) plus a
foreground smoke run of a fake-adapter job converging in 3 iterations.
Details in the autodev episode's `report3.md`.

## Step 4 — fresh agent-only gitea on agstudio — 2026-08-07

Removed agstudio's old experimental gitea (the `localgit` service in
`~/services/service_scripts`'s compose; container + `gitea_data` removed by
the user after the permission classifier blocked agent-side `docker rm`, the
compose entry removed by the agent). Deployed a fresh agent-only Gitea
1.27.1 from `devenv/gitea/compose.yaml`: named volume, sqlite3 +
INSTALL_LOCK, registration disabled, ports 3000/2222. Admin user
`autolab-agent`, org `autodev`; password and all-scopes API token live only
in `.local/gitea/` (mode 600). Verified: API repo create → token push →
clone round-trip → smoke repo deleted; reachable via `agstudio.local:3000`.
Setup notes in `devenv/gitea/SETUP.md`; details in the autodev episode's
`report4.md`.

## Step 5 — dev node setup (agautolab1) — 2026-08-07

Provisioned the job-runner VM `agautolab1.local` (Proxmox VM 109 on aghub,
Ubuntu 24.04, 4 vCPU / 8 GB): uv 0.12.2, agautolab cloned from gitea
(`autodev/agautolab`, 23 tests passing on the VM), gitea token + credential
store in `~/.agautolab/.local/gitea/`, `autolab@.service` installed as a
systemd user unit with linger and an explicit PATH (`~/.local/bin` +
`~/.local/node/bin`). Claude Code CLI 2.1.224 installed via npm under
user-space Node 22; user logged in with the dedicated Claude account;
headless `claude -p` smoke test OK (7 s).

Incident: the VM's default `kvm64` CPU (no AVX2) made the bun-built claude
binary busy-loop at 100 % CPU through every install path; fixed by
`qm set 109 --cpu host` + full stop/start (user-run). Recorded as
WorkflowEpisode `701ad4e6-00c0-4cc0-b367-1e55d2548927`; follow-up candidate:
default `cpu: host` in clusterintent's `create_qemu.yml`. Details in the
autodev episode's `report5.md`.

## Step 6 — first real full-auto job: browser Othello — 2026-08-07

Ran the first end-to-end job with no human help mid-run: `autodev/othello-web`
(private, on the agstudio gitea) seeded with a contract README and a
pre-validated 10-case `node:test` acceptance suite (engine API, rules, CPU
legality, self-play termination, index.html wiring); gate = bare `node --test`
(no npm deps — cheap and deterministic on the VM's Node 22).
`autolab@othello-web.service` on agautolab1 converged in **one iteration**:
64 s adapter wall, 12 turns, $0.311, sonnet-5 pinned via
`adapter_config.args`. Agent wrote `othello.js` (109 lines) + `index.html`
(235 lines), left `test/` untouched; result pushed to gitea `main`.

agautolab change en route: `jobs/` added to `.gitignore`. Observed gaps for
Step 7: no auto-push from `run_once` (pushed manually), no status/monitoring
command (ssh-polled `state.json`), and a one-iteration convergence means
NOTES handoff / stuck detection are still unexercised by a real model.
Details in the autodev episode's `report6.md`.

## Step 7 — episode close — 2026-08-07

The autodev episode is closed with its final `report.md` (projects-root
devdocs). agautolab's follow-up backlog from the episode: push `target/`
(and ideally `evidence/`) off-node on iteration/terminal, an
`autolab status` subcommand, a default `.gitignore` for auto-initialized
targets, and a harder job to exercise NOTES handoff + stuck detection with
a real model. Total real-model spend across the episode: ≈ $0.44.
