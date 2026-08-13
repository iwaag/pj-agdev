# Phase 3, step 1 — the HTTP passthroughs: forge, autolab, Plane

Done. The three passthrough families now answer from the Python service on
`:8093` identically to the JavaScript service on `:8091`. nginx did not move;
the four views and chat still flow through `http://localhost:8090` unchanged.

## What was built

One new module, `assistant/agdevworld_assistant/passthrough.py`, wired into
`server.py` as a prefix-dispatch table checked after the exact-path JSON
routes (plus a `do_PATCH` for Plane):

- **`proxy_fetch()`** — the one shared upstream call. It catches
  `urllib.error.HTTPError` and returns it as the response (`error.code`,
  `error.read()`, `error.headers`), exactly the stdlib trap the plan named:
  an upstream 404/422 is forwarded verbatim, body included. Network-level
  failures (`OSError`) still raise and each route maps them to its own
  offline envelope. All handlers take an injectable `fetch` callable, the
  Python analog of the JS modules' `fetchImpl`.
- **`/api/forge/<rest>`** → `AGFORGE_URL/api/<rest>`, default
  `http://host.docker.internal:8092`, trailing slash stripped, body and
  content-type forwarded, upstream status/content-type verbatim, unreachable
  → 502 `forge_offline`. New 120 s timeout (the JS had none; forge answers in
  20–105 s).
- **`/api/autolab/nodes`** — GET only (405 otherwise), concurrent
  `ThreadPoolExecutor` probes of each node's `/healthz` with a 2 s timeout,
  `{kind: "autolab.nodes.v1"}`; a down node is `reachable: false` in a 200.
- **`/api/autolab/<node>/<rest>`** — `AUTOLAB_NODES` parsed with
  `or`-semantics (empty string means the default
  `agstudio=http://host.docker.internal:8791`), unknown node → 404
  `unknown_node` listing configured names, `(^|/)evidence(/|$)` → 403
  `evidence_not_proxied`, 60 s proxy timeout preserved, unreachable → 502
  `node_offline`.
- **`/api/plane/...`** — the whole of `plane-passthrough.mjs`: both path
  regexes, 503 `plane_unconfigured`, 404 `plane_no_default_project` /
  `plane_path_not_proxied`, methods GET/POST/PATCH only, `state_name`
  resolution (case-insensitive against the live states list, failed lookup
  forwarded verbatim, unknown name → 400 `unknown_plane_state`), trailing
  slash appended upstream, query string forwarded, `X-API-Key` never in any
  response. Network failure → 502 `plane_offline`.

The exact workflow paths (`/api/autolab/projects|missions|missions/resolve`)
are deliberately not routed yet; they arrive with steps 2 and 3.

## Proof

`uv run pytest` — 64 passed (17 new in `tests_py/test_passthrough.py`,
covering topic-for-topic what `tests/plane-passthrough.test.mjs` covered plus
the forge/autolab envelopes, all against an injected fetch, no network).

Live, after `docker compose up --build -d assistant-py`, each request run
against both `:8091` and `:8093` and compared (identical status, envelope and
kind fields; only JSON whitespace differs):

```
GET  /api/autolab/nodes                          -> 200 autolab.nodes.v1, agstudio+agautolab1 both reachable
GET  /api/autolab/agstudio/status                -> 200 autolab.monitor.v1 (stub gateway)
GET  /api/autolab/agstudio/jobs/1/evidence/x     -> 403 evidence_not_proxied
GET  /api/autolab/nope/status                    -> 404 unknown_node, lists agstudio, agautolab1
GET  /api/plane/issues?per_page=1                -> 200
GET  /api/plane/states                           -> 200 (5 states)
GET  /api/plane/workspaces                       -> 404 plane_path_not_proxied
GET  /api/forge/requests/does-not-exist          -> 404 verbatim upstream {"error":"not_found",...}
POST /api/plane/issues {"state_name":"Imaginary"} -> 400 unknown_plane_state
```

The last one doubles as the live `state_name` proof without debris: the
service had to fetch the real project's states to know the name is missing,
and no issue was created. Both autolab nodes happened to be up at proof time
(agautolab1 answering is the less common case, not a problem).

## Notes

- Node probe failure `detail` is the Python exception class name
  (`ConnectionRefusedError`, `TimeoutError`) where the JS surfaced
  `ECONNREFUSED`/`TimeoutError`. Same role, different vocabulary; the field
  was always free-form.
- The autolab passthrough forwards a body for every non-GET method (the JS
  skipped it only for GET too); forge additionally skips HEAD.
