# Roadmap — the agdevworld assistant in Python

Replace the nine files of `assistant/` (1,540 lines of implementation, 615 of
tests) with Python plus `agag` (pyagag). The frontend (`src/`, Phaser/TS) and
the `agents.toml` contract stay as they are. This is a destructive episode:
backward compatibility is not required, and the JavaScript implementation is
deleted at the end.

## Why

688 of those lines (45%) are a re-implementation of pyagag, maintained twice.

| JS | lines | matching `agag` |
|---|---|---|
| `assistant/agent-config.mjs` | 297 | `agag.agent_config.load_config` / `resolve_role` |
| `assistant/harness.mjs` | 202 | `agag.harness.build_argv` / `run_harness` / `write_run_record` |
| `assistant/zulip.mjs` | 189 | `agag.zulip.ZulipClient` / `topic_write` |

The remaining 852 lines (`server.mjs` 581, `tool-service.mjs` 136,
`plane-passthrough.mjs` 129, `autolab-projects.mjs` 160,
`overlay-generator.mjs` 28) are agdevworld's own and port straightforwardly.

## Discretion, and the few prohibitions

Design, decomposition and library choice belong to the implementer. Only these
are fixed.

- Keep credentials and `.local/` out of commits, images and stdout. No local
  absolute paths in non-ignored files.
- Do not change `ag.agent-config.v1` (the `agents.toml` schema). It is shared
  with agautolab and agforge; changing it is outside this episode.
- Add no silent harness or model fallback. A resolution or authentication
  failure stays a 502 and a record, as it is today.
- You may change the `/api` contract, but change the frontend in the same
  phase if you do. No phase ends with a broken UI.

Write `phase<N>/report.md` (or `report<N>.md` once a phase is split into steps)
when a phase completes. Failures are results too.

## Established facts (read from the code, 2026-08-13)

| Fact | Where |
|---|---|
| HTTP is the only seam to the frontend | `nginx.conf:7-8` proxies `/api/` to `assistant:8091`; `vite.config.ts` proxies to `ASSISTANT_URL` (default `localhost:8091`) |
| The web image carries no runtime node | `Dockerfile` builds on `node:26-alpine` and serves from `nginx:alpine` |
| The assistant image does need runtime node | opencode 1.18.10 and claude-code 2.1.226 are `npm install -g`. After the port the image becomes python + node |
| nginx read timeout is 310s | longer than the 300s agent default (`AGDEVWORLD_AGENT_TIMEOUT_MS`). Keep that ordering |
| UI actions travel through a file | the tool service appends JSONL to `AGDEVWORLD_ACTIONS_FILE` and the server reads it after the run. Language-neutral, so the two sides may be in different languages mid-port |
| MCP uses no SDK | `tool-service.mjs` hand-writes JSON-RPC over stdio (`initialize`, `tools/list`, `tools/call`, `ping`). The Python standard library covers it 1:1 |
| Records live in the `/records` volume | `ASSISTANT_RECORDS_DIR=/records`, `assistant.run.v1` / `assistant.note.v1`. The container log does not survive `up --build` |
| There is a Python precedent | `agautolab/agent/gateway.py` serves the same kind of surface in 334 lines with nothing but `ThreadingHTTPServer`. Read it first |
| How pyagag is consumed | same as agautolab and agforge: `[tool.uv.sources] pyagag = { git = "…iwaag/pyagag", branch = "main" }`. The import package is `agag` |

### Using `agag.harness.run_harness()`

`run_harness(agent, prompt, *, cwd, timeout, allowed_tools=…, extra_args=…,
opencode_config=…, transcript_path=…)`. The current JS launch conditions map
onto it like this.

- claude_code: put `--mcp-config <tmp>/claude-mcp.json --strict-mcp-config` in
  `extra_args` and `mcp__agdevworld__{fetch,wait,switch_view,show_image}` in
  `allowed_tools`. `--model` inside `extra_args` raises — model selection
  belongs to the resolved profile. Rewrite the `command` in the generated
  `claude-mcp.json` to the Python tool service.
- opencode: its MCP configuration is in `opencode.json`, not in argv. The
  current JS gets it read by setting cwd to the project root; `opencode_config=`
  makes cwd free instead. `mcp.agdevworld.command` there needs rewriting too.
- `run_harness` keeps the real cwd and the inherited `PWD` aligned, and derives
  `AGENT_PROVIDER_OLLAMA_BASE_URL` from `agent.provider_base_url`.
- Today only claude_code runs in a per-run temporary directory. Keeping that is
  a judgement call; if you change it, say why in the report.

---

## Phase 1 — the MCP tool service in Python

Independent of pyagag and of the server process, so it can be proven on its own
first.

- Port `tool-service.mjs`: `fetch`, `wait`, `switch_view`, `show_image`, the
  same-origin restriction, the 1 MB clip, the 60s cap, the actions JSONL.
- Repoint the MCP command in `opencode.json` and in the `claude-mcp.json` that
  `harness.mjs` writes. The server stays JavaScript.
- Set up the Python side here too (uv + pytest). Where `pyproject.toml` lives
  (repository root or `assistant/`) is yours to decide.

Done when: a browser chat on both the `local` and `sonnet` profiles really
performs a `fetch` and a `switch_view`.

## Phase 2 — the Python server and `/api/chat`

The core, and where pyagag pays off.

- Resolve the role through `agag.agent_config`, run `front` through
  `agag.harness`, write the run into `/records`.
- Port the role prompt, the per-request re-read of `GUIDE.md`, the shaping of
  the browser-supplied conversation (`composePrompt`), and the collection of UI
  actions.
- A temporary split is fine: let nginx route `/api/chat`, `/api/guide` and
  `/api/note` to the new service and everything else to the JS one. All four
  views must still work at the end of the phase.
- Keep the record keys (profile, harness, provider, model, outcome, actions).
  Converging on agautolab's shape is part of the point.

Done when: chat runs through Python on both profiles and leaves records in
`/records`.

## Phase 3 — the remaining routes, and the cutover

- The autolab passthrough (finite node list, `403` on `/evidence/`, project and
  profile reads), the Plane passthrough (server-side `state_name` resolution),
  forge / freeforge / missions (delegated to `agag.zulip`), and project starts
  (Gitea + Plane + Zulip).
- Move what `entrypoint.mjs` and `overlay-generator.mjs` do — generating
  `.local/agents.local.toml` from deployment environment values on every start.
  Preserve the property that no API key itself enters the generated file
  (`anthropic_api_key_env` only).
- Make the assistant image python + node. Which one is the base is yours.
- Delete the JS assistant (nine files plus tests) and the temporary nginx split.

Done when: `docker compose up --build -d web assistant` serves all four views
and chat, and no `assistant/*.mjs` remains.

## Phase 4 — settling

- Rewrite the Commands / Files / Assistant sections of `README_DEV.md`. Note
  that the test entrance moves from `npm test` (which only ever ran the
  assistant tests) to `uv run pytest`, leaving `npm run build` (tsc) as the
  frontend's only check.
- `assistant/GUIDE.md` is language-neutral and should mostly survive untouched.
  Fix only what the port proved wrong.
- If shared machinery emerged, push it down into pyagag — an MCP stdio server
  skeleton is the candidate. Deciding not to is fine; put the reason in the
  report.
