# Report — Step 2: agdevworld reaches agforge

## What was done

- Extended `agdevworld/assistant/server.mjs` with a same-origin passthrough:
  `/api/forge/<rest>` → `${AGFORGE_URL}/api/<rest>` (method, body, status,
  and content-type forwarded; unreachable upstream maps to 502
  `forge_offline` with a readable detail, mirroring the existing
  `assistant_offline` style).
- Added `AGFORGE_URL` to the assistant service in `compose.yaml`, defaulting
  to `http://host.docker.internal:8092` (generic Docker host alias, same
  pattern as the existing `OLLAMA_URL` default — no real hostnames
  committed; real values override via env).
- No nginx.conf or vite.config.ts changes were needed: both already forward
  all of `/api/` to the assistant service, so the passthrough works for the
  production-style (8090) and dev (5173) origins alike.

## Acceptance check

- Rebuilt the assistant container, then from the agdevworld origin:
  `POST http://localhost:8090/api/forge/requests {"desire":"a blue
  triangle"}` returned 202 with a request id, and polling
  `GET .../api/forge/requests/{id}` reached `done` with a presigned image
  URL. ✅

## What held / what surprised

- The existing "browser → nginx → assistant" seam absorbed the new route
  with zero config changes outside server.mjs + compose env — the
  `location /api/` prefix proxy was already broad enough.
- The agforge service currently runs natively on the host (started via
  `service/serve.sh`), so the container reaches it through
  `host.docker.internal`, exactly like ollama. If agforge is later
  containerized, only `AGFORGE_URL` changes.
