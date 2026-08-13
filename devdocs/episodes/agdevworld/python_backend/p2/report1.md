# Phase 2, step 1 — `agag` in the image, and a Python service that answers

**Done.** `import agag` works inside the container, and a second service on
`:8093` answers `/healthz`, `/api/guide` and `/guide`.

## Image

`assistant/Dockerfile` gained `uv git` beside `python3`, and one build step
after the source copy:

```dockerfile
RUN cd /app/assistant && uv sync --frozen --python /usr/bin/python3
```

The plan's verification held exactly: inside the built image `uv 0.11.19
(aarch64-alpine-linux-musl)`, `git 2.54.0`, venv interpreter `Python 3.14.7`.
The sync installed 7 packages in **868 ms** with nothing compiled — pyagag is
pure stdlib, and the six others are pytest and its dependencies. Whole
`docker compose build assistant-py`: 12.5 s.

`git` really is required rather than a precaution: `pyagag` is a git source in
`uv.lock` (`iwaag/pyagag@7cf02a44`), and uv shells out to fetch it.

Two interpreters coexist as the plan asks. The venv (`/app/assistant/.venv`)
runs the server; the MCP tool service stays on the system `/usr/bin/python3`,
which is what `opencode.json` names and what the native workflow has. Nothing
was repointed.

## Service

`assistant/agdevworld_assistant/server.py` — `ThreadingHTTPServer`, the handler
shape borrowed from `agautolab/agent/gateway.py` (path split on `?`,
`send_json`/`send_text` helpers that always set Content-Length, `log_message`
to stderr, `SIGTERM` → exit). Two deliberate differences from that file:
`protocol_version = "HTTP/1.1"`, because nginx and the browser both keep the
connection alive here, and `PORT`/`HOST` from the environment rather than
`AUTOLAB_GATEWAY_*`.

`GUIDE.md` is re-read on every request. An `OSError` becomes the same
`'No capability card is installed on this assistant.'` string the JS returns,
plus one stderr line — not a 500.

## Compose

`assistant-py`: same build context and Dockerfile as `assistant`, the same
environment block plus `PORT: 8093`, `assistant_records:/records`,
`host.docker.internal` extra host, `8093:8093`, and

```yaml
    working_dir: /app
    command: ["/app/assistant/.venv/bin/python", "-m", "agdevworld_assistant.server"]
```

`-m` resolves because `uv sync` installs the project itself into the venv, so
the package is importable independently of cwd. `working_dir: /app` is set for
step 3's benefit (opencode's `opencode.json` MCP command is relative to the
project root), not because the import needs it.

The zulip and gitea secret mounts were **not** copied to `assistant-py`: no
route ported in this phase reads them. They stay with the JS service until
phase 3 takes those routes.

## Evidence

```
$ curl -s localhost:8093/healthz
{"ok": true}
$ curl -s localhost:8093/api/guide | head -1
# agdevworld assistant — entrance guide
$ curl -s -o /dev/null -w '%{http_code} %{content_type}\n' localhost:8093/guide
200 text/plain; charset=utf-8
$ curl -s localhost:8093/api/chat
{"error": "not_found"}
$ docker compose exec assistant-py /app/assistant/.venv/bin/python -c "import agag; print(agag.__file__)"
/app/assistant/.venv/lib/python3.14/site-packages/agag/__init__.py
```

The JS service was rebuilt on the changed image and still serves everything it
served before: `localhost:8091/healthz` → `{"ok":true}`, and the browser path
`localhost:8090/api/guide` → 200. `uv run pytest` (phase 1's suite): 17 passed.

## Note

`docker compose up -d assistant-py` printed a `No services to build` warning
here because the preceding `build` had just produced the image; it is not a
failure. The two services build the same Dockerfile into two tags
(`agdevworld-assistant`, `agdevworld-assistant-py`) sharing the same layers.
