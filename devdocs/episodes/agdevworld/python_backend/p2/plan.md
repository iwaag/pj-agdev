# Phase 2 plan — the Python server and `/api/chat`

Five steps. The JS server keeps serving every route it serves today until step
4 takes three of them away; no step ends with a broken UI. Write `report<N>.md`
per step (or one `report.md` at the end — your call).

## Prohibitions (all of them)

- No credentials, no `.local/` content, no local absolute paths in committed
  files.
- Do not touch `agents.toml`'s schema (`ag.agent-config.v1`).
- No fallback. A resolution, launch or authentication failure is a 502 plus a
  record — never a silent downgrade to another profile or harness.
- Both services write records into the same `/records` volume. Do not delete or
  rewrite records the JS side wrote.

Everything else — module layout, naming, decomposition, test style, how much of
`server.mjs`'s comment prose survives — is yours.

---

## Step 1 — `agag` in the image, and a Python service that answers

The whole phase depends on `import agag` working *inside the container*. Retire
that risk first, with the smallest server that proves it.

**Image.** `assistant/Dockerfile` is `node:26-alpine` with `python3` added in
phase 1. Verified on this Mac 2026-08-13: `apk add --no-cache uv git` in that
image gives uv 0.11.19 (musl) and git 2.54 — `git` is not optional, uv shells
out to it for the `pyagag` git source. Then, from `assistant/`,
`uv sync --frozen --python /usr/bin/python3` (uv's managed CPython is glibc and
will not run on Alpine). `agag` has **zero runtime dependencies** — it is pure
stdlib — so this is a pip-shaped install with nothing to compile.

- Two interpreters now coexist, deliberately: the MCP tool service stays on the
  system `python3` (stdlib-only, and `opencode.json` names it), while the server
  runs from the venv. Do not repoint the tool service at the venv — that would
  break the native, non-container workflow.
- `uv.lock` pins pyagag at a commit of `iwaag/pyagag` **on GitHub**. A local edit
  under `~/projects/pyagag` is invisible to the image until it is pushed and the
  lock is refreshed.

**Service.** New module, e.g. `agdevworld_assistant/server.py`, on
`ThreadingHTTPServer`. Read `agautolab/agent/gateway.py` first and steal its
handler shape (routing, body read, JSON reply, `protocol_version`, logging to
stderr) rather than inventing one.

Routes in this step: `GET /healthz`, `GET /api/guide`, `GET /guide`. `GUIDE.md`
is re-read from disk on **every** request — that per-request read is a feature
(edit the card, the next answer changes, no restart), not an oversight to
optimise away. Unreadable card → the same `'No capability card is installed on
this assistant.'` string, not a 500.

**Compose.** A second service off the same image and build context:

```yaml
  assistant-py:
    build: { context: ., dockerfile: assistant/Dockerfile }
    command: ["/app/assistant/.venv/bin/python", "-m", "agdevworld_assistant.server"]
    environment: …same block as `assistant`, plus PORT: 8093
    volumes: [assistant_records:/records]
    extra_hosts: ["host.docker.internal:host-gateway"]
    ports: ["8093:8093"]
```

8092 is agforge's host port; 8093 is free. `-m` needs the package importable —
set `WORKDIR`/`PYTHONPATH` to `/app/assistant`, or give the venv the project
itself (`uv sync` already installs it).

Done when: `curl localhost:8093/healthz` and `curl localhost:8093/api/guide`
answer, and `docker compose exec assistant-py /app/assistant/.venv/bin/python -c
"import agag; print(agag.__file__)"` prints a path.

## Step 2 — `/api/chat` end to end on the `stub` profile

Everything except a real model: role resolution, prompt shaping, the record, the
reply envelope. `profiles.stub` (harness `fake`) is already in `agents.toml`, so
this whole step costs nothing and needs no ollama.

Port from `server.mjs`:

| Piece | Where it is now |
|---|---|
| `ROLE_PROMPT` | `server.mjs:63-85` — copy verbatim; the paths it lists are the assistant's map |
| system assembly | `${ROLE_PROMPT}${screen}\n\n=== CAPABILITY CARD ===\n${guide}`, screen = `\n\n${context}` only when non-empty |
| `composePrompt` | `harness.mjs:104-109` — `USER:`/`ASSISTANT:` blocks, then the fixed trailing instruction |
| request validation | non-empty array; every item `{role: user|assistant, content: string}`; otherwise 400 `bad_request` |
| reply envelope | `{reply, actions, run:{id, role, profile, harness, provider, model, outcome}}` |
| `/api/note` | `server.mjs:482-504`; `assistant.note.v1`, 201, `<id>.note.json` |

Resolution is `agag.agent_config.load_config(/app/agents.toml,
/app/.local/agents.local.toml)` then `resolve_role(config, overlay, "front")`,
per request (so an overlay edit lands on the next chat, as today).

`AgentConfigError` → 502 `assistant_offline` + a `failed` record, exactly like
the JS.

**Traps.**

- `run_harness` **never raises** for a bad run. It returns `HarnessResult` with
  `meta["outcome"]` in `done | failed | aborted` and `meta["failure"]` set.
  `if result.meta["outcome"] != "done": 502`. Reading `exit_code` alone is not
  enough — `is_error` and empty output are failures with exit code 0.
- The `fake` harness has no default command (`agag.agent_config` only defaults
  `opencode` and `claude_code`), so a `stub` run raises `E_UNAVAILABLE` unless
  the overlay sets `[local.harness.fake] command = …`. `/bin/cat` is a genuinely
  useful fake: the prompt arrives on stdin, comes back on stdout, and
  `extract_event_text` passes non-JSON lines through — so the reply is the
  prompt, which makes the composed prompt directly assertable.
- `extract_event_text` does not strip. `.strip()` the output before it becomes
  `reply`; the JS trimmed.
- Record: agautolab's shape is `{"schema": "ag.agent-run.v1", **result.meta}`
  (`agautolab/src/agautolab/role_run.py`). Converge on that, keeping `id`,
  `started` and `actions`. Note `agag.harness.write_run_record` whitelists keys
  and **drops `actions`** — so either write the file yourself or write it and
  then merge. Keep the stdout line (`kind: assistant.run.v1`) whichever you pick;
  it is what `docker compose logs` shows.

Tests: prompt composition, validation rejections, the `stub` round trip against
a temporary `agents.toml` + overlay, the failure→502→record path.

Done when: `uv run pytest` is green and, against the real container,
`POST :8093/api/chat` with `AGENT_FRONT_PROFILE=stub` returns the composed
prompt as `reply` and leaves a record in `/records`.

## Step 3 — a real run: `local` (opencode) with tools

Now the harness launch conditions. `harness.mjs:125-204` is the spec being
replaced; `agag.harness.run_harness` does the process work, but the wiring
around it is agdevworld's.

**The per-run environment is the one thing `run_harness` gives you no parameter
for.** Its env is `{**os.environ, **agent.environment, NO_COLOR, PWD, provider
base url}` — there is no `env=` argument. `AGDEVWORLD_ACTIONS_FILE` and
`AGDEVWORLD_TOOL_BASE_URL` are per-run, and mutating `os.environ` in a threaded
server is a race. `ResolvedAgent` is a frozen dataclass with a plain-dict
`environment` field, so:

```python
agent = dataclasses.replace(agent, environment={
    **agent.environment,
    "AGDEVWORLD_TOOL_BASE_URL": TOOL_BASE_URL,
    "AGDEVWORLD_ACTIONS_FILE": str(actions_path),
})
```

**cwd and the MCP config, per harness:**

- **opencode** — `opencode.json`'s `mcp.agdevworld.command` is the *relative*
  `["python3", "assistant/agdevworld_assistant/tool_service.py"]`, and opencode
  spawns it with its own cwd. So keep `cwd=/app` (the project root). Passing
  `opencode_config=Path("/app/opencode.json")` would let you move cwd, but only
  if you also make that command absolute — a change worth avoiding unless
  something forces it, since the same file is used in native runs.
- **claude_code** — write `claude-mcp.json` into a per-run
  `tempfile.TemporaryDirectory()` (`{"mcpServers": {"agdevworld": {"command":
  "python3", "args": ["<abs>/tool_service.py"]}}}`, honouring `AGDEVWORLD_PYTHON`
  as phase 1 step 3 did), run with `cwd=` that directory, and pass
  `extra_args=["--mcp-config", str(path), "--strict-mcp-config"]` with
  `allowed_tools="mcp__agdevworld__fetch,…wait,…switch_view,…show_image"`.
  `--model` in `extra_args` raises — the profile owns the model.
- The actions file lives in a per-run temp dir either way. Keeping claude_code's
  own cwd temporary is a judgement call (roadmap): if you change it, say why.

**Also:** timeout stays `AGDEVWORLD_AGENT_TIMEOUT_MS` (300 s default) and
`run_harness` wants **seconds** — divide. 300 < nginx's 310; keep that ordering.
Transcript path `<records>/<id>.agent.jsonl`, as today. Read the actions JSONL
after the run and map it into the reply; a malformed line crashing the request
(the JS behaviour) is worth improving to a skipped line plus a stderr note.

Done when: with ollama up, `POST :8093/api/chat` — *"Read /api/guide with the
fetch tool, then switch to the tasks view"* — answers with a `switch_view`
action and writes `assistant.run.v1` + `.agent.jsonl` into `/records`.

## Step 4 — the nginx split, and the four views

Route the three ported paths to the Python service, everything else to the JS
one. Exact-match locations win over the prefix in nginx, so:

```nginx
location = /api/chat  { proxy_pass http://assistant-py:8093; proxy_read_timeout 310s; }
location = /api/guide { proxy_pass http://assistant-py:8093; }
location = /api/note  { proxy_pass http://assistant-py:8093; }
location /api/        { proxy_pass http://assistant:8091;    proxy_read_timeout 310s; }
```

`/guide` (the alias) can go either way; pick one and say which. The `/api`
contract does not change in this phase, so the frontend needs no edit.

`vite.config.ts` has one `ASSISTANT_URL` target and cannot express the split —
the `dev` HMR profile therefore reaches only the JS side during this phase. That
is acceptable and temporary (phase 3 deletes the split); note it in the report
rather than building a second dev proxy.

Prove in a real browser at `http://localhost:8090`: chat answers and switches a
view, and **nodes / workspaces / autolab / tasks** all still populate — those
read `/api/autolab/*` and `/api/plane/*`, which are still the JS server's, so
this is a check that the split routes what it means to route.

Done when: `docker compose up --build -d web assistant assistant-py` serves all
four views, and chat comes from Python.

## Step 5 — `sonnet`, and the report

`AGENT_FRONT_PROFILE=sonnet` in the ignored `agdevworld/.env`, recreate
`assistant-py` so the entrypoint's overlay regenerates, one short prompt.

Phase 1 step 5 left this blocked: no `ANTHROPIC_API_KEY` on this machine, and
compose only forwards `${ANTHROPIC_API_KEY:-}`. If it is still absent, that is
the result — record it and say precisely what stays unproven (the claude_code
launch conditions of step 3, and nothing else). Do not synthesise a pass, and do
not spend money working around it.

Two notes if a key does appear:

- The overlay names `anthropic_api_key_env = "ANTHROPIC_API_KEY"`;
  `resolve_role` reads that variable **from the server process's environment**
  and fails with `E_UNAVAILABLE` when empty — a clean 502, before any spend.
- Keep the prompt to one sentence and one tool call. Switch `.env` back after.

Done when: `report.md` (or `report5.md`) records both profiles' outcomes, the
record keys actually written, and whatever the port proved wrong about
`GUIDE.md` — phase 4 will want that list.
