# Phase 3, step 4 — cutover: one service, one image, no JavaScript

Done. The Python service **is** `assistant` now: same service name, `PORT:
8091`, the venv python as the container command. The JavaScript service, its
tests and its `package.json` are deleted; `git ls-files 'assistant/*.mjs'`
is empty (the roadmap's phase gate), and `docker compose up --build -d web
assistant` serves the app and chat.

## The moves

- **compose** — the `assistant` service took over `assistant-py`'s command
  and mounts (records volume, zulip.env, gitea.token, the `ZULIP_LAN_HOST`
  host-gateway alias from step 2) with `PORT: 8091`; the `assistant-py`
  entry and the 8093 mapping are gone. The `assistant_records` volume
  carried over untouched — the JS-written records remain as history.
- **nginx** — collapsed back to the original two-location form: one
  `location /api/` to `assistant:8091` with the 310 s read timeout (every
  other route's own upstream bound, ≤ 130 s, fits under it), one `location /`
  for the app. Every `location =` from the split is deleted.
- **Image** — stays `node:26-alpine + apk add python3 uv git`, per the
  plan's own weighing: the harnesses arrive by `npm install -g` so runtime
  node is non-negotiable either way, uv already targets the system
  interpreter (`--python /usr/bin/python3`, Alpine/glibc), and this exact
  image has been proven since phase 2 — switching the base buys nothing.
  `CMD` is now `/app/assistant/.venv/bin/python -m agdevworld_assistant.server`;
  `entrypoint.mjs` has no successor because `write_overlay()` at boot already
  does its job, and the overlay still carries `anthropic_api_key_env` only,
  never a key value.
- **Deleted** (after grepping for importers — only the root `package.json`
  test script referenced them): the 8 service `.mjs` files, the 6
  `assistant/tests/*.test.mjs`, `assistant/package.json`, and the root
  `npm test` script. `GUIDE.md`, `agents.toml`, `opencode.json` stay.
  `README_DEV.md` is left stale on purpose — rewriting it is phase 4's.
  `scripts/fetch-cluster-state.mjs` is the frontend's own and stays.

## Proof

- `git ls-files 'assistant/*.mjs'` → empty.
- `uv run pytest` → 116 passed. `npm run build` (tsc + vite) → green, the
  usual non-failing chunk-size advisory only.
- Through `http://localhost:8090` after `up --build -d web assistant`:
  `/api/autolab/nodes` (both nodes reachable), `/api/plane/issues` 200,
  `/api/guide` 200, `/` renders (screenshot, nodes view populated), and one
  browser-path chat answered through the collapsed nginx —
  `profile: local, harness: opencode, provider: ollama, outcome: done`.
- The stale `agdevworld-assistant-py-1` container from step 3 was removed
  by hand (`docker rm -f`); compose no longer knows the service, so `down`
  could not.
