# Plan — stub out agautolab

Reconciles `braindump.txt`: agautolab's implementation is garbage. Keep the
input/output surface and the sub-agent configuration; delete the rest and
replace every route body with a dummy answer or a `pass`.

## What survives, and why

Three things are worth keeping, and nothing else is:

1. **The I/O surface** — the gateway's route table and the Zulip listener's
   accept/handle shape. This is the design that was worth having: what a
   caller can ask an autolab node, and what shape comes back. It stays as an
   empty frame.
2. **The sub-agent configuration** — `agents.toml` (roles → profiles →
   models), the ignored `.local/agents.local.toml` overlay, the per-role
   OpenCode permission files, and the per-role allowed-tool grants.
3. **The config-resolution layer that reads them** — `agent_settings.py` and
   `project_settings.py`. Kept *alive*, not just kept: `GET /projects` and the
   `POST /window` run record continue to resolve roles for real, so the
   surviving TOML is still exercised and a broken profile still shows up.
   Nothing below that line ever launches a harness, so the stubbed node cannot
   spend money or spawn a subprocess.

Everything else — the job loop, the adapters, the mission driver, the CLI, the
monitor page, the implementation docs, and every unit test — is deleted.

## File-by-file

### Delete outright

| Path | Note |
|---|---|
| `src/agautolab/adapters/` | the whole package (`__init__`, `fake`, `opencode`, `claude_code`) |
| `src/agautolab/run_once.py` | the iteration |
| `src/agautolab/loop.py`, `detach.py` | iteration driving |
| `src/agautolab/job.py`, `state.py`, `gates.py`, `review.py`, `status.py` | the job model |
| `src/agautolab/mission_witness.py` | mission-consumption witness |
| `src/agautolab/cli.py` | the `autolab` CLI; not a surviving entrance |
| `agent/drive.sh`, `agent/session.sh` | the mission driver |
| `agent/monitor/` | `index.html`, `monitor.css`, `monitor.js` |
| `devenv/systemd/autolab@.service` | runs `autolab loop`, which no longer exists |
| `tests/` | all 18 files |
| `AGENT_GUIDE.md`, `agent/README.md`, `agent/CHARTER.md`, `styles/` | implementation docs |

`devenv/gitea/` stays: it is local infrastructure, unrelated to the loop.

### Keep unchanged

`agents.toml`, `agent/opencode-front.json`, `agent/opencode-coding.json`,
`agent/opencode-mediator.json`, `agent/opencode-readonly.json`,
`opencode.json`, `src/agautolab/agent_settings.py`,
`src/agautolab/project_settings.py`, `.gitignore`, `LICENSE`.

The `coding` and `mediator` roles keep their profiles and permission files even
though nothing runs them any more — they are the configuration the braindump
asks to preserve, and a future implementation is meant to pick them back up.

### Stub

| Path | Stub shape |
|---|---|
| `agent/gateway.py` | route table preserved, ~150 lines, bodies dummy |
| `src/agautolab/role_run.py` | `run_role()` resolves the role, returns canned output |
| `src/agautolab/zulip_listener.py` | `accept()` real, `handle_message()` a no-op |
| `agent/GUIDE.md` | trimmed to what is still true |
| `README.md` | a few lines: this is a stub, here is the surface |
| `pyproject.toml` | drop the `autolab` script and the `pyyaml` dependency |

## Step 1 — `role_run.py`

Keep `ROLE_ALLOWED_TOOLS` and `_opencode_config()` verbatim: they are
sub-agent configuration, and a caller reading the stub should still see which
tools each role was granted and which permission file it maps to.

`run_role(role, prompt, *, cwd, timeout, profile, transcript, record, project)`
keeps its signature and its first half — project roles are loaded,
`resolve_project_role()` runs, `ProjectSettingsError` / `AgentConfigError`
still propagate. Then, instead of `run_harness()`:

- return a fixed dummy string as the output,
- build the `ag.agent-run.v1` record from the resolved agent (role, profile,
  harness, provider, model, `project`) with `outcome: "stub"`, zero cost, zero
  turns, and no transcript file,
- return exit code `0`.

Drop the `agag.harness` import; keep `agag.agent_config`. Delete the
`__main__` CLI at the bottom of the module — the only remaining caller is the
gateway, in-process.

A resolution failure must stay a failure. That is the one behaviour that makes
the surviving TOML checkable.

## Step 2 — `agent/gateway.py`

Keep the module docstring's route list (it is the design being preserved), the
`Handler` dispatch in `do_GET` / `do_POST`, the envelope kinds
(`autolab.monitor.v1`, `autolab.projects.v1`), the `SAFE_NAME` / `ITER_NAME`
validation, and the HTTP status vocabulary (400 bad input, 404 unknown, 409
busy, 202 accepted). Delete every helper that walks `.local/`: `current_run`,
`drive_running`, `pid_alive`, `session_summaries`, `sessions_cost`,
`game_info`, `job_summary`, `job_detail`, `job_yaml_fields`, `evidence_iters`,
`iter_cost`, `summary_*`, `start_summarizer`, and the static file servers.

Route by route:

| Route | Stub |
|---|---|
| `GET /healthz` | unchanged, `{"ok": true}` |
| `GET /guide` | unchanged: reads `agent/GUIDE.md` per request |
| `GET /projects` | **real**: `projects_document()` kept as-is |
| `GET /status` | fixed `autolab.monitor.v1` document, driver not running, empty sessions, zero cost |
| `GET /log` | fixed dummy log text |
| `GET /jobs` | `{"kind": …, "type": "jobs", "jobs": []}` |
| `GET /jobs/<job>` | name validated, then always `404 no such job` |
| `GET /jobs/<job>/evidence/<iter>/<file>` | name validated, then always `404` |
| `POST /jobs/<job>/summarize/<iter>` | validated, then `202 {"status": "pending"}`, nothing spawned |
| `GET /jobs/<job>/summarize/<iter>` | validated, then `{"status": "absent"}` |
| `POST /window` | body validated, one-at-a-time lock kept, answered by the stubbed `run_role` |
| `GET /monitor/…`, `GET /game/…` | `404` with a "removed in the stub" message |

`POST /window` keeps the most: `next_window_id()`, `record_window_run()`, the
`window_lock`, `read_guide()`, the `WINDOW_PROMPT` template, the
`MISSION_BLOCK` regex and `apply_mission_block()`. It still writes
`.local/agent/window/run-NNNN.json`, and that record still carries the real
resolved front-role identity — that is the surviving proof that `agents.toml`
is being read. `window_state()` shrinks to the node time plus an empty mission
and empty job list.

`start_mission()` keeps its validation and its `400` / `409` / `202` codes but
spawns nothing and writes no `MISSION.md`: it returns
`202 {"accepted": true, "run": 0, "stub": true}`. With `drive.sh` gone there is
no drive to be concurrent with, so the `409` branch becomes unreachable; keep
the branch, since the concurrency contract is part of the preserved design.

`main()` keeps the `AUTOLAB_GATEWAY_HOST` / `AUTOLAB_GATEWAY_PORT` env vars and
the `:8791` default, and drops the `SIGCHLD` reaper (nothing is spawned).

**Response shapes must not change.** `agdevworld/assistant/server.mjs` proxies
these routes at `/api/autolab/<node>/…` and the assistant's GUIDE documents
them; a stub that answers with a different shape breaks a live consumer
instead of merely emptying it. Empty lists and zeroed numbers, not absent keys.

## Step 3 — `zulip_listener.py`

Keep the module as the second surviving entrance, and keep exactly the part
that defines the surface: `MISSION_TOPIC_PREFIX`, `accept()`,
`bridge_briefing()`, `node_url()`, `max_sessions()`, `observe_message()`, and
`main()`'s `AUTOLAB_ZULIP_LOG_ONLY` switch and `serve()` wiring.

Delete `post_window()`, `get_status()`, `wait_for_terminal_status()`, and
`terminal_message()` — the HTTP client half. `handle_message()` becomes a stub
that logs the message and replies once in-topic that this node is a stub and
started nothing. It must not block: the old version polled `/status` until the
driver stopped, and a stub that inherits that loop hangs the listener.

`agent/zulip_listen.sh` stays as-is (it only invokes the module).

## Step 4 — docs

- `AGENT_GUIDE.md`, `agent/README.md`, `agent/CHARTER.md`, `styles/README.md`:
  deleted. Each documents machinery that no longer exists.
- `agent/GUIDE.md`: kept — it is read per request and served at `GET /guide`,
  so it is live surface, not prose. Trim to: this node is a stub, the route
  list, the roles and profiles, and one sentence that no mission runs and
  nothing costs money. Delete the cost table, the Plane reporting section, and
  the project-director section.
- `README.md`: reduced to a short statement that agautolab is currently a stub
  of its own I/O surface and sub-agent configuration, plus the route list and
  a pointer to this episode.

Removing `CHARTER.md` and `styles/` while `GUIDE.md` still references them
would leave a dangling pointer — that trim belongs in this step, not later.

## Step 5 — `pyproject.toml` and packaging

- Remove `[project.scripts] autolab` (`cli.py` is gone).
- Remove the `pyyaml` dependency (only `run_once`/`job`/`gateway`'s job.yaml
  scan used it).
- Keep `pyagag` — `agent_config` is still the resolution contract.
- Keep the `dev` group with `pytest`, so the next implementation has a place to
  put tests back. `uv.lock` gets refreshed by `uv lock`.

## Step 6 — `.local/` cleanup

All untracked; the braindump asks for the auto-development projects, and the
job directories are the same generation of garbage:

- `.local/projects/` — `scifi`, `yokai`, `project-agent-setting-smoke`, and
  `projects.md`. The auto-developed projects, deleted as asked. Their Gitea
  repositories under the `autodev` org are **not** touched by this plan.
- `.local/jobs/` — 25 job directories. Nothing reads them once `/jobs` is a
  stub. *(Beyond the braindump's literal words; say so if they should be kept
  as evidence instead — they are the only surviving record of what the loop
  actually did.)*
- `.local/agent/` — `MISSION.md`, `NOTES.md`, `done`, `sessions/`, `window/`,
  `director/`, `gateway/`, `serve/`, `archive-*/`.

Keep `.local/agents.local.toml` (the node's real profile overlay, still read),
`.local/.env`, `.local/gitea/`, `.local/zulip.env`.

## Step 7 — verify

There is no test suite left, so verification is by hand and deliberately
shallow — the point is that the frame answers, not that anything works:

```sh
cd pj-agdev/agautolab
python3 -c "import ast,sys; [ast.parse(open(f).read()) for f in sys.argv[1:]]" \
  agent/gateway.py src/agautolab/*.py
uv run python agent/gateway.py &          # or plain python3
curl -s localhost:8791/healthz
curl -s localhost:8791/projects           # real: profiles from agents.toml
curl -s localhost:8791/status
curl -s localhost:8791/jobs
curl -s localhost:8791/guide
curl -s -X POST localhost:8791/window -H 'Content-Type: application/json' \
  -d '{"text":"what are you"}'            # dummy reply, real front-role identity
ls .local/agent/window/                   # a new run record exists
grep -rn "run_once\|adapters\|drive.sh\|autolab loop" --include='*.py' --include='*.md' .
```

The last grep is the removal check the deleted `test_legacy_removed.py` used to
do: no surviving file should still name the deleted machinery.

Then confirm the live consumer: with the stub gateway on `:8791`, the
agdevworld assistant container's `/api/autolab/agstudio/jobs`, `/status` and
`/projects` passthroughs must still return valid documents rather than error.

## Step 8 — deployment consequences

Out of scope for the code change, but this stub is not confined to this Mac
until someone acts:

- `agautolab1` deploys from the agstudio Gitea mirror
  (`autodev/agautolab.git`) via `ansible_agdev/playbooks/agent/setup_autolab_node.yml`.
  Until that push and playbook run, the node keeps serving the old
  implementation, so the two nodes disagree about what agautolab is.
- The `autolab_node` role's `autolab-gateway.service.j2` still starts
  `agent/gateway.py`, which the stub preserves; `agents.local.toml.j2` and
  `plane.env.j2` still generate files the stub reads or ignores harmlessly. No
  role change is required to deploy the stub.
- `agdevworld/assistant` and `pj-clusterintent` are not modified by this plan.
  The assistant's GUIDE still promises autolab behaviour that will no longer
  happen; that is a separate episode.

Recommendation: push and redeploy in the same session as the commit, so both
nodes are stubs together.

## Order

1. Delete the files in "Delete outright" (`git rm`).
2. Stub `role_run.py`.
3. Stub `agent/gateway.py`.
4. Stub `zulip_listener.py`.
5. Trim the docs.
6. `pyproject.toml` + `uv lock`.
7. Clean `.local/`.
8. Verify (step 7), commit in the `agautolab` repo, then decide on step 8.

Steps 2–4 depend on nothing but step 1; step 5 must not precede step 4, since
`GUIDE.md`'s trim is decided by what the routes still do.

## Out of scope

- Any replacement implementation. This episode ends at a stub that answers.
- The `autodev` Gitea repositories, the Plane workspace, the `#pj-*` Zulip
  channels, and their contents.
- `agdevworld`, `pj-clusterintent`, and the `autolab_node` Ansible role.
