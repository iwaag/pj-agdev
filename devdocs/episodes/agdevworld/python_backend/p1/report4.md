# Phase 1, step 4 — Python in the assistant image

Done. `assistant/Dockerfile` gained one line, and the service answers from inside
the container.

```dockerfile
FROM node:26-alpine
WORKDIR /app
# The MCP tool service is Python and stdlib-only; the interpreter is all it needs.
# Which image is the base stays a phase-3 decision.
RUN apk add --no-cache python3
```

The image is `python3 3.14.5 [GCC 15.2.0]`, comfortably above the declared
`>=3.11` floor. No `uv`, no wheels, no build toolchain: the service imports only
`json`, `math`, `os`, `sys`, `time` and `urllib`.

## Evidence — the service driven directly, no agent run paid for

```sh
docker compose up --build -d assistant
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"fetch","arguments":{"path":"/"}}}' \
| docker compose exec -T -e AGDEVWORLD_TOOL_BASE_URL=http://web assistant \
  python3 assistant/agdevworld_assistant/tool_service.py
```

```
initialize: {'name': 'agdevworld-tools', 'version': '1.0.0'} 2025-03-26
tools:      ['fetch', 'wait', 'switch_view', 'show_image']
fetch:      HTTP 200 text/html | <!doctype html> | <html lang="en"> | <head> …
```

Four tools and a real `HTTP 200 text/html` head fetched from the `web` container
over the compose network — which also confirms the container-side
`AGDEVWORLD_TOOL_BASE_URL: http://web` still reaches nginx from the Python side.

## The phase-2 dependency risk, retired

Step 1 proved the `pyagag` git source resolves on this Mac; it was still unproven
inside the image. Rather than commit `uv` into the Dockerfile — phase 1 needs
none, and the base image is phase 3's decision — the resolution was probed in a
throwaway container built from the same image:

```sh
docker run --rm agdevworld-assistant sh -c \
  'apk add --no-cache uv git; cd /app/assistant && uv sync --python /usr/bin/python3'
```

```
Updated https://github.com/iwaag/pyagag.git (7cf02a44)
Built   pyagag @ git+https://github.com/iwaag/pyagag.git@7cf02a44
Installed 7 packages
```

So phase 2 can rely on: `uv` and `git` are plain `apk` packages on this base,
`--python /usr/bin/python3` is required (uv's managed CPython is glibc and will
not run on Alpine), and the GitHub source resolves from inside Docker. The
committed image is unchanged by this probe — `--rm`, nothing kept.

`.dockerignore` (step 3) keeps the macOS `.venv` out of the build context, so the
image carries source only.
