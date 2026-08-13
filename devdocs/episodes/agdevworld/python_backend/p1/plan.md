# Phase 1 plan — the MCP tool service in Python

Five steps. Each step ends green and leaves the UI working; the JS server keeps
running throughout. Write `report<N>.md` per step (or one `report.md` at the
end — your call).

## Prohibitions (all of them)

- No credentials, no `.local/` content, no local absolute paths in committed
  files. `agdevworld/.env` and `.local/` stay ignored.
- Do not touch `agents.toml`'s schema (`ag.agent-config.v1`).
- No fallback: if the Python tool service cannot start, the run fails and is
  recorded. Never fall back to the `.mjs` one.
- The MCP process writes **nothing** to stdout except JSON-RPC lines. Logs go to
  stderr.

Everything else — layout, naming, decomposition, test style — is yours.

---

## Step 1 — Python foundation

Create the uv project. Recommended location: **`agdevworld/assistant/`**, not
the repository root — `agdevworld/src/` is already the Phaser frontend, so a
root `src/` layout would collide, and `assistant/Dockerfile` already does
`COPY assistant/ ./assistant/`.

Suggested shape:

```
assistant/pyproject.toml         # name agdevworld-assistant, requires-python >=3.11
assistant/agdevworld_assistant/  # flat package, no src/ layer
assistant/tests_py/              # or tests/, next to the .mjs tests
```

- Copy the dependency convention from `agautolab/pyproject.toml`: hatchling
  build backend, `[dependency-groups] dev = ["pytest>=8.0"]`, and
  `[tool.uv.sources] pyagag = { git = "https://github.com/iwaag/pyagag.git",
  branch = "main" }`.
- Adding `pyagag` as a dependency **now**, even though this phase does not
  import it, is cheap and proves the git source resolves — inside the image
  too. That resolution is a phase-2 risk worth retiring here.
- `.gitignore`: add `__pycache__/`, `.venv/`, `.pytest_cache/`. Note the
  existing `*.local` and `.local` rules already cover the overlay.
- Entrance: `uv run pytest` from `assistant/`. `npm test` keeps running the
  remaining `.mjs` tests until phase 4.

Done when: `uv sync` and `uv run pytest` succeed with one trivial test.

## Step 2 — Port `tool-service.mjs`

Stdlib only (`json`, `sys`, `os`, `time`, `urllib`). Read
`assistant/tool-service.mjs` (136 lines) as the spec; keep tool names,
descriptions, input schemas and reply wording identical — the model reads them,
and `assistant/GUIDE.md` describes them.

Behaviour that must survive:

| Item | Detail |
|---|---|
| tools | `fetch`, `wait`, `switch_view`, `show_image`, in that order |
| base URL | `AGDEVWORLD_TOOL_BASE_URL`, default `http://127.0.0.1:8090` |
| path guard | must start with one `/`; reject `//…`; reject after-join origin drift |
| method | `GET`/`POST` only; `content-type: application/json` only when a body was supplied |
| timeout | 60 s per fetch |
| clip | 1,000,000 bytes, then `\n\n[body clipped at 1000000 bytes]` |
| reply | `HTTP {status} {content-type}\n\n{body}`; empty string when the header is absent |
| wait | `min(seconds, 60)`, non-finite or ≤0 → 0; the "(N was requested)" suffix when clamped |
| actions | one JSON object per line appended to `AGDEVWORLD_ACTIONS_FILE`; `{"action":"switch_view","view":…}` / `{"action":"show_image","url":…}` |
| views | `nodes`, `workspaces`, `autolab`, `tasks` |
| errors | tool-level failures return `isError: true` with a text block, never a JSON-RPC error |

Traps found while reading the code:

- **`urllib` raises on 4xx/5xx, `fetch()` does not.** Catch `HTTPError` and
  treat it as a normal response — the agent is supposed to see a 404 body. Only
  `URLError`/socket errors become `isError`.
- Decode with `errors="replace"` to match `TextDecoder`'s behaviour on binary.
- `urljoin("http://web", "//example.com/x")` yields `http://example.com/x`, so
  the origin comparison catches it exactly as the JS does — keep both the
  literal `//` check and the origin check.
- The MCP framing is line-delimited JSON, one request per line: `initialize`
  (`protocolVersion "2025-03-26"`, `serverInfo.name "agdevworld-tools"`),
  `tools/list`, `tools/call`, `ping`. Messages without an `id` are
  notifications — skip them silently. Unknown method → error code `-32601`.
  Flush after every write; do not buffer.
- Keep the module runnable both as a file and as `-m` (Step 3 needs the file
  form), so avoid package-relative imports inside it.

Port `assistant/tests/tool-service.test.mjs` too: the catalog, the `//` refusal,
a stubbed fetch (use `http.server` on `127.0.0.1:0` instead of monkeypatching),
and the end-to-end stdio exchange that ends in a written actions line. Adding a
404-passthrough test is worth it — that is the one behaviour the port can
silently get wrong.

Done when: `uv run pytest` passes and a hand-fed JSON-RPC exchange over stdin
returns four tools.

## Step 3 — Repoint the MCP command, delete the JS one

Two call sites, and they differ in cwd:

1. `opencode.json` → `mcp.agdevworld.command`, today
   `["node", "assistant/tool-service.mjs"]`. OpenCode runs with cwd = the
   agdevworld root (`harness.mjs:147`), so a **relative** path keeps working
   both in the container (`/app`) and in a native run. Keep `timeout: 65000` —
   it must stay above the 60 s `wait` cap.
2. `assistant/harness.mjs:9,137` writes `claude-mcp.json` with
   `command: process.execPath, args: [TOOL_SERVICE]`. Claude Code runs with
   cwd = a per-run temp directory, so this path must stay **absolute**: resolve
   it from `dirname(fileURLToPath(import.meta.url))` as today. Interpreter: a
   plain `python3`, or an `AGDEVWORLD_PYTHON` override defaulting to `python3` —
   no hard-coded venv path, which would break the native workflow.

Then delete `assistant/tool-service.mjs` and
`assistant/tests/tool-service.test.mjs`. Leave `package.json`'s `test` script
alone. Update the two `README_DEV.md` lines that name the file (line 27 and the
Files section) — one line each, the full rewrite is phase 4.

Done when: `npm test` still passes with the file gone, and `git grep
tool-service.mjs` is empty.

## Step 4 — Python in the assistant image

`assistant/Dockerfile` is `node:26-alpine`. Smallest move that works:
`RUN apk add --no-cache python3` — the service is stdlib-only, so nothing else
is needed. Choosing the image base is a phase-3 decision; do not pre-empt it.

If you want `uv` in the image already (to prove step 1's dependency source),
pass `--python /usr/bin/python3`: uv's managed CPython builds are glibc and do
not run on Alpine.

Fast feedback without paying for an agent run — drive the service directly:

```sh
docker compose up --build -d assistant
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"fetch","arguments":{"path":"/"}}}' \
| docker compose exec -T -e AGDEVWORLD_TOOL_BASE_URL=http://web assistant \
  python3 assistant/agdevworld_assistant/tool_service.py
```

Done when: that prints four tools and an `HTTP 200 text/html` head.

## Step 5 — Prove it in the browser, both profiles

`docker compose up --build -d web assistant`, then `http://localhost:8090`.

- **local** (OpenCode + ollama, the committed default): ask something that
  forces a real `fetch` plus a view change, e.g. *"read /api/guide and then
  switch to the tasks view"*. Verified 2026-08-13 on this Mac: `web` (8090),
  `assistant` (8091) and ollama (11434) are all up.
- **sonnet** (Claude Code): select it only through the ignored overlay — set
  `AGENT_FRONT_PROFILE=sonnet` in `agdevworld/.env` and recreate the assistant
  (the entrypoint regenerates `/app/.local/agents.local.toml` on every start).
  Needs `ANTHROPIC_API_KEY`; every run costs money, so keep the prompt short.
  Switch the value back afterwards.
- Evidence: the chat reply plus the view actually switching, and
  `docker compose exec assistant ls /records` / `docker compose logs assistant`
  for the `assistant.run.v1` record. The container log does not survive
  `up --build`; take the evidence before the next rebuild.

The `/api` contract does not change in this phase, so the frontend needs no
edit. If a run fails, that failure is a result — record the stderr tail and the
harness meta in the report rather than working around it.

Done when: both profiles really perform a `fetch` and a `switch_view` through
the Python service, and `report.md` records the two runs.
