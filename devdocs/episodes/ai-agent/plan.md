# AI Assistant — Implementation Plan

Goal (this episode only): a chat panel on the right side of agdevworld where the
user can ask questions about the current cluster snapshot in plain text and get
answers from a local LLM. No view switching, no cagent proxying yet — but the
architecture must not block them next episode.

Decisions already made (see braindump discussion):

- The agent runs **server-side**: a small `assistant` service in
  `agdevworld/compose.yaml`. Reason: the next episode ("act on behalf of the
  user toward cagent") needs a place to hold the cagent bearer token, and that
  place cannot be the browser. Starting server-side avoids a rewrite.
- **No agent framework.** Step 1 needs no tool calls: build the prompt, call
  ollama `/api/chat` once, return the answer. Engine selection is deliberately
  deferred to the view-operation episode. Keep the frontend↔assistant chat
  protocol engine-agnostic so only the assistant's internals change later.
- **Chat UI is a DOM overlay**, not Phaser-rendered. Text input, scrolling and
  copy/paste are free in HTML and painful on canvas.

Constraints (kept minimal — everything else is implementer's discretion):

- Never put a cagent credential or any secret in frontend code, the bundle, or
  committed files. (Not needed this episode anyway.)
- Do not commit `public/cluster/state.json` (already gitignored practice).
- Backward compatibility is not required; replace freely.

## Step 1 — Assistant backend service

Create a minimal HTTP service (suggested: plain Node, no framework, ~100
lines; TypeScript optional) exposing one endpoint:

```
POST /api/chat
{ "messages": [{"role":"user"|"assistant","content":"..."}], "context": "<cluster summary text>" }
→ { "reply": "..." }
```

- It builds a system prompt from `context` plus a short role description
  ("assistant inside agdevworld, answer questions about these cluster nodes")
  and forwards to ollama's `/api/chat`, non-streaming, returning the reply.
- Conversation history lives in the browser and is sent whole each request;
  the service stays stateless. This is the engine-agnostic seam.
- Configuration via env vars: `OLLAMA_URL`, `OLLAMA_MODEL`. On the existing
  ollama server, verify the model name first (`GET /api/tags`).
- Add it to `compose.yaml` as service `assistant` (e.g. port 8091 internal).
  From a container, the host's ollama is `host.docker.internal` (add
  `extra_hosts: ["host.docker.internal:host-gateway"]` on Linux).
- Return a clear error body when ollama is unreachable so the UI can show
  "assistant offline" instead of a generic failure.

Verify: `curl -s localhost:8091/api/chat -d '{"messages":[{"role":"user","content":"hi"}],"context":""}'`
returns a reply.

## Step 2 — Chat panel UI

- Add a fixed-position panel on the right side of `index.html` / a new
  `src/chatPanel.ts`: message list + text input + send button, styled to match
  the dark background (`#0d0f14`). Keep Phaser's `#app` full-screen underneath;
  the panel is an absolutely-positioned sibling div.
- Show user/assistant messages, a pending indicator while waiting, and the
  offline error state from Step 1.
- Wire requests to `/api/chat`:
  - Dev: add a Vite `server.proxy` entry for `/api` → the assistant service.
  - Production container: add a `location /api/` proxy_pass in the nginx
    config of the `web` image (a custom `nginx.conf` will need to be added —
    the current Dockerfile serves static files only).

Verify: `npm run dev` (or `docker compose up dev`), type a question, get an
answer rendered in the panel.

## Step 3 — Cluster context injection

- Reuse the existing snapshot pipeline: `loadExistingNodes()` /
  `parseDriftEnvelope()` in [src/clusterState.ts](../../agdevworld/src/clusterState.ts)
  already load and validate the `nctl.drift.v1` envelope
  (`/cluster/state.json` with fallback to `/state.sample.json`).
- Build the `context` string in the frontend from the parsed envelope, not the
  raw JSON: node name, status, and each diff's `code`/`severity`/`message`.
  Rationale: the raw snapshot will grow, and small local models degrade with
  large JSON blobs. A compact plain-text summary (one line per node plus the
  summary counts) is enough for "answer questions about the nodes".
- Note: `filterExistingNodes()` drops not-yet-confirmed nodes for the panel
  display; for the assistant it is probably better to include *all* node
  targets (including unconfirmed ones) so it can answer "why is X missing?".
  Implementer's call — a second, unfiltered accessor is fine.

Verify: ask "which nodes are drifting and why?" against the sample snapshot
and check the answer names `node-gamma` / `hostname_mismatch`.

## Step 4 — Container refresh and report

- Rebuild the user-checkable container per
  [README_DEV.md](../../agdevworld/README_DEV.md): `docker compose up --build
  -d web assistant`, confirm `http://localhost:8090` serves the app and the
  chat works end-to-end through nginx.
- Write `report.md` (or `report[step].md`) in this directory: what was built,
  the chat protocol shape, model/endpoint used, and anything painful that the
  next episode (view operations, cagent proxying) should know.

## Hints and known facts

- Frontend stack: Vite 8 + TypeScript + Phaser 4, no UI framework. Entry:
  [src/main.ts](../../agdevworld/src/main.ts), single `MainScene`.
- `compose.yaml` already has `web` (nginx, :8090) and a `dev` profile
  (Vite HMR, :5173).
- Snapshot shape: `nctl.drift.v1` envelope — `data.targets[]` with
  `target.kind/slug/name/id`, `status`
  (`converged|converging|drifting|unknown`), `diffs[].code/severity/message`,
  plus `data.summary` counts. See `public/state.sample.json`.
- The live snapshot is refreshed via `CAGENT_URL=... npm run cluster:fetch`;
  the assistant never talks to cagent this episode.
- Streaming responses are a nice-to-have; skip them first, add SSE later if
  answer latency feels bad.
