# Step 1 Report — Assistant backend service

Date: 2026-08-05

## What was built

- `agdevworld/assistant/server.mjs` — a plain Node HTTP service (no framework,
  no dependencies, ~120 lines) exposing:
  - `POST /api/chat` with body
    `{ "messages": [{"role":"user"|"assistant","content":"..."}], "context": "<cluster summary text>" }`
    returning `{ "reply": "..." }`.
  - `GET /healthz` returning `{ "ok": true }` for container checks.
- `agdevworld/assistant/Dockerfile` — `node:26-alpine`, copies the single file,
  runs it on port 8091.
- `agdevworld/compose.yaml` — new `assistant` service (port `8091:8091`),
  `extra_hosts: ["host.docker.internal:host-gateway"]` so the same file works
  on Linux, env-overridable `OLLAMA_URL` / `OLLAMA_MODEL`.

## Behavior

- Builds a system prompt from a short role description ("assistant inside
  agdevworld, answer questions about these cluster nodes") plus the `context`
  string when non-empty; states "no cluster summary available" otherwise.
- Forwards `[system, ...messages]` to ollama `POST /api/chat` with
  `stream: false` and returns `message.content` as `reply`.
- Stateless: history is sent whole by the browser each request. Nothing below
  the HTTP contract leaks the engine choice — this is the engine-agnostic seam
  for the next episode.
- Error contract for the UI:
  - `400 { "error": "bad_request", "detail": ... }` for malformed bodies.
  - `502 { "error": "assistant_offline", "detail": ... }` when ollama is
    unreachable, returns a non-2xx status, or an unexpected shape.

## Model and endpoint

- Ollama runs natively on the host at `http://localhost:11434`; verified via
  `GET /api/tags`. Available models included `glm-4.7-flash:latest`,
  `qwen3.6:35b-a3b-coding-nvfp4`, `qwen3-vl:latest`, `gemma3:latest`.
- Default model: `glm-4.7-flash:latest` (fast, ~200k context, tool-capable for
  later episodes). Override with `OLLAMA_MODEL` at compose time.
- From the container, ollama is reached as `http://host.docker.internal:11434`
  (default `OLLAMA_URL`).

## Verification

```sh
docker compose up --build -d assistant
curl -s localhost:8091/api/chat -d '{"messages":[{"role":"user","content":"hi"}],"context":""}'
# -> {"reply":"Hello. I am ready to assist you with information about the cluster nodes. ..."}
```

## Notes for later steps

- No secrets exist in this service; the cagent bearer token slot (next
  episode) belongs here server-side, never in the frontend bundle.
- Responses are non-streaming by design; add SSE later only if latency hurts.
