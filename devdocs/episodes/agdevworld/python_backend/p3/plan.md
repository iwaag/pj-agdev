# Phase 3 plan — the remaining routes, and the cutover

Five steps. Steps 1–3 port the remaining routes onto `assistant-py` (proving
each on `:8093` before nginx moves anything); step 4 is the cutover and the JS
deletion; step 5 is the whole-system proof and the report. Write `report<N>.md`
per step (or one `report.md` at the end — your call).

## Prohibitions (all of them)

- No credentials, no `.local/` content, no local absolute paths in committed
  files.
- Do not touch `agents.toml`'s schema (`ag.agent-config.v1`).
- No fallback. A resolution, launch, upstream or credential failure is its
  error envelope plus (where applicable) a record — never a silent downgrade.
- No step ends with a broken UI: all four views (nodes, workspaces, autolab,
  tasks) and chat must work through `http://localhost:8090` at the end of
  every step.
- Until step 4 deletes them, do not rewrite records the JS service wrote.

Everything else — module layout, naming, what stays one file vs. three, test
style, how much of the JS comment prose survives — is yours.

## What phase 2 already carried forward

- `overlay.py` is ported and `server.py` calls `write_overlay()` at boot, so
  `entrypoint.mjs` has no Python analog to write — it just gets deleted in
  step 4.
- The record writer, chat, note and guide routes are done and proven on
  `local` + `stub`. The claude_code launch conditions remain unproven for lack
  of an `ANTHROPIC_API_KEY`; that gap survives this phase unchanged unless a
  key appears.

## What is actually live right now

Check before each proof rather than assuming: the nautobot server in
`pj-clusterintent` (or `nctl`, see `pj-clusterintent/nctl/README.md`) knows the
cluster's state, and `.local/devenv.md` maps the local services. As of
planning: Zulip at `https://agstudio.local:8543` (self-signed), Gitea and Plane
per the compose defaults, ollama on the host, the agstudio autolab gateway on
`:8791`. agautolab1 being down is normal — the nodes route treats that as an
answer, not an error.

---

## Step 1 — the HTTP passthroughs: forge, autolab, Plane

Pure `urllib`/stdlib ports of `handleForge`, `handleAutolab` (+ `handleAutolabNodes`)
and `plane-passthrough.mjs`. No Zulip, no secrets, so no compose change yet.

Behavior to preserve, per route:

- **`/api/forge/<rest>` → `AGFORGE_URL/api/<rest>`.** Default
  `http://host.docker.internal:8092`, trailing slash stripped. Body and
  content-type forwarded, upstream status and content-type returned verbatim,
  unreachable → 502 `forge_offline`. The JS set no timeout; give it one —
  forge answers in 20–105 s, so 120 s is a sensible bound.
- **`/api/autolab/nodes`** — GET only, probe each configured node's
  `/healthz` with a 2 s timeout, `{kind: "autolab.nodes.v1", nodes: [...]}`.
  A down node is `reachable: false` in a 200, never an error. The JS probed
  concurrently (`Promise.all`); `ThreadPoolExecutor` keeps the frontend's
  polling snappy once there is more than one node.
- **`/api/autolab/<node>/<rest>`** — node from `AUTOLAB_NODES`
  (`name=url,...`; `or`-semantics, not `??`: an **empty string means the
  default** `agstudio=http://host.docker.internal:8791`, because compose
  passes `""` when unset). Unknown node → 404 `unknown_node` listing the
  configured names. Paths matching `(^|/)evidence(/|$)` → 403
  `evidence_not_proxied` — this safety device is about reach, keep it. Proxy
  timeout is **60 s** (the 10 s it once was turned an open door into a wrong
  `node_offline`; don't regress it). Unreachable → 502 `node_offline`.
- **`/api/plane/...`** — the whole of `plane-passthrough.mjs`: the two path
  regexes (project-scoped `/projects/<uuid>/issues|states/...` and the bare
  default-project form needing `PLANE_PROJECT_ID`), 503 `plane_unconfigured`
  when config is missing, 404 `plane_path_not_proxied` otherwise, methods
  GET/POST/PATCH only, and the **`state_name` resolution**: on POST/PATCH with
  a `state_name` key, list the project's states, match case-insensitively,
  replace with `state`/id or answer 400 `unknown_plane_state`. Upstream path
  gets a trailing slash appended (Plane redirects without it); the query
  string is forwarded. `X-API-Key` never reaches the browser.

**The one real stdlib trap:** `urllib.request.urlopen` raises `HTTPError` on
any status ≥ 400 — but these are passthroughs, and an upstream 404/422 must be
forwarded verbatim, body included. Catch `HTTPError` and treat it as the
response (`error.code`, `error.read()`, `error.headers`), or drop to
`http.client` directly. Write one small `proxy_fetch()` helper and all three
routes share it; the JS grew three copies of the same buffer-and-forward tail
for want of one.

Testability: the JS modules took a `fetchImpl` parameter; the same move works
in Python (inject the URL-opening callable). `tests_py/` already shows the
house style.

Prove each on `:8093` with curl (nodes list, one node passthrough, the
evidence 403, a Plane issue list, a `state_name` POST if convenient). nginx
does **not** move yet — `/api/autolab/` cannot flip until the workflow trio in
step 3 exists, and flipping routes one at a time buys nothing. Frontend
behavior is unchanged, so the four-views rule holds trivially.

Done when: the passthrough routes answer identically (status, envelope, kind
fields) on `:8093` and `:8091` for the same requests, and `uv run pytest` is
green.

## Step 2 — Zulip: freeforge and missions

Port `handleFreeForge` and the missions half of `handleAutolabWorkflow`,
delegating the client to `agag.zulip.ZulipClient` — this is the roadmap's
payoff step, `zulip.mjs` mostly evaporates.

What `agag.zulip` already gives you: `ZulipClient.from_env(path)` (reads
`ZULIP_URL/EMAIL/API_KEY`, optional `ZULIP_CA_BUNDLE`, and already defaults to
an unverified TLS context for this realm's self-signed cert),
`send_to_channel`, `create_channel(name, description, principals)`,
`resolve_topic(message_id, topic)` (already no-ops on the `✔ ` prefix, and
`RESOLVED_TOPIC_PREFIX` is exported), `users()`, and `ZulipError`.

What it does **not** give you — the three small things left to port:

- **Topic names.** `stampedTopicName(prefix)` →
  `f"{prefix}-{YYYYMMDD-HHMMSS}-{secrets.token_hex(3)}"`; `create-*` for
  freeforge, `mission-*` for missions, channel `pj-<project>`.
- **The active-user filter.** `users()` returns deactivated members too; the
  JS kept `is_active !== false`. Filter before passing as `principals`.
- **The one-retry.** `zulip.mjs` retried exactly once on a socket-level
  failure (not on HTTP errors) because the first call after a container start
  was seen to lose its TLS socket while Zulip was fine. `agag` doesn't retry.
  A three-line wrapper (`except ZulipError` where the message carries no
  `HTTP `) preserves a behavior that was learned the hard way; recommended.

Route mechanics to keep: lazy client construction on first use (the server
must boot and serve chat without the credentials mount — tests depend on
that), 405 on non-POST, the exact request validations and response kinds
(`freeforge.request.v1`, `freeforge.resolve.v1`, `autolab.mission.v1`,
`autolab.mission-resolve.v1`), `ZulipError` → 502 `zulip_unavailable`.
`ZULIP_ENV_PATH` defaults to `/run/secrets/zulip.env`.

**Compose:** add the two secret mounts to `assistant-py` (they currently exist
only on `assistant`):

```yaml
      - ../.local/zulip/devworld-assistant.env:/run/secrets/zulip.env:ro
      - ../agautolab/.local/gitea/autolab-agent.token:/run/secrets/gitea.token:ro
```

(The Gitea token is step 3's, but one compose edit beats two.)

Prove on `:8093` against the real realm: one freeforge request (watch the
`create-*` topic appear in #FreeForge and agforge answer if it is up), one
mission post into an existing `pj-*` channel, resolve both. nginx still does
not move.

Done when: both pairs round-trip against the live Zulip from `:8093`, and unit
tests cover topic naming, validation, and the error mapping without a network.

## Step 3 — project start, and the nginx flip

Port `autolab-projects.mjs` — the last JS-only capability — then move the
remaining prefixes to the Python service.

The port, in provisioning order (any step's failure aborts the rest;
`ProjectStartError(step, ...)` → 502 `project_start_failed` with the `step`
field, so the human can pick up from the evidence):

1. **Gitea** — token read **from file at request time**
   (`GITEA_TOKEN_PATH`, default `/run/secrets/gitea.token`), create the
   `<name>` + `<name>-direction` pair under `GITEA_ORG` (default `autodev`),
   seed the direction repo with `GUIDE.md` / `concept.md` / `.gitignore` via
   the contents API (base64 bodies). 30 s timeout per call.
2. **Plane** — create the project (identifier from `planeIdentifier`:
   initials of word parts plus numeric parts, upper-cased, max 12 —
   "whack-a-mole-2" → "WAM2"; port the function and its tests), then list its
   states and return `{id, identifier, states: {name: id}}`. 60 s timeouts.
3. **Zulip** — `create_channel("pj-<name>", ..., principals=<active users>)`,
   reusing step 2's client and filter.

Route mechanics: `PROJECT_NAME = ^[a-z0-9][a-z0-9-]{1,38}$`, non-empty
`concept`, and the **preflight**: collect `missing` from the Gitea and
Plane-workspace configs and answer 503 `project_start_unconfigured` before
touching anything. Response is 201 `{kind: "autolab.project.v1", project,
gitea, plane, zulip}` as today. The step-1 `proxy_fetch()` helper and injected
transport serve here too.

Prove on `:8093` with a throwaway name (e.g. `p3-smoke-1`): repos exist in
Gitea, project + states come back from Plane, `#pj-p3-smoke-1` appears in
Zulip with everyone subscribed. Leaving the debris is fine — this environment
is experimental — but note the name in the report.

**Then flip nginx**: `/api/forge/`, `/api/freeforge/`, `/api/autolab/` and
`/api/plane/` all move to `assistant-py:8093` (keep `proxy_read_timeout 310s`
where chat had it; the autolab window POSTs can hold 60 s, so give that
location a read timeout comfortably above 60 s too). The JS service now serves
nothing the UI reaches, but stays up one more step as the rollback path.

Done when: `docker compose up --build -d web assistant assistant-py` — all
four views populate through the flipped nginx, a browser chat can drive a
`fetch` against a passthrough route, and a project start round-trips.

## Step 4 — cutover: one service, one image, no JavaScript

The destructive step. Recommended shape — the Python service simply **becomes
`assistant`**: same service name, `PORT: 8091`, `command` as `assistant-py`
has now. That single move lets nginx collapse back to the original two-location
form (`location /api/ { proxy_pass http://assistant:8091; ... }` — delete every
`location =` from the split), keeps `vite.config.ts`'s default
`ASSISTANT_URL=localhost:8091` working so the dev HMR profile reaches the
Python service with **zero** frontend edits, and keeps 8091 the known host
port. Delete the `assistant-py` compose entry and the 8093 mapping.

- **Image.** Make `assistant/Dockerfile` python + node; which is the base is
  yours (roadmap). Two facts to weigh: the harnesses arrive by `npm install -g
  opencode-ai@1.18.10 @anthropic-ai/claude-code@2.1.226`, so runtime node is
  non-negotiable; and on Alpine, uv must be pointed at the system interpreter
  (`uv sync --frozen --python /usr/bin/python3`) because its managed CPython
  is glibc. Staying on `node:26-alpine + apk add python3 uv git` is the
  smallest diff and already proven; switching the base only pays if it buys
  something — say what, if you do. `git` stays: uv shells out to it for the
  pyagag git source. `CMD` becomes the venv python running the server module;
  `entrypoint.mjs` is gone and `write_overlay()` at boot replaces it. Keep the
  property that no API key value enters the generated overlay
  (`anthropic_api_key_env` only) — `overlay.py` already does.
- **Delete** the nine `.mjs` files, `assistant/tests/*.test.mjs`, and
  `assistant/package.json` (nothing else imports them; check with a grep
  before the `rm`, not after). `GUIDE.md`, `agents.toml`, `opencode.json`
  stay. `README_DEV.md` rewriting is phase 4's — leave it stale.
- The `assistant_records` volume carries over untouched; the JS-written
  records simply remain as history.

Done when (the roadmap's phase gate): `docker compose up --build -d web
assistant` serves all four views and chat, and
`git ls-files 'assistant/*.mjs'` is empty.

## Step 5 — the full sweep, and the report

Prove the collapsed system end to end, then write it down.

- `uv run pytest` green; `npm run build` (tsc) green — the frontend's only
  check now.
- Through `http://localhost:8090`: the four views, a `stub` chat, a `local`
  chat that performs a `fetch` and a `switch_view`, a note, and one
  passthrough of each family (autolab node, Plane issues, forge or freeforge
  depending on what is up — check liveness first, per the top of this plan).
- One `docker compose logs assistant` read: records on stdout, logs on
  stderr, nothing leaking a credential.
- `sonnet`: attempt only if `ANTHROPIC_API_KEY` exists by then; otherwise
  restate the standing gap in one line as phase 2 did. Do not synthesize a
  pass, do not spend money working around it.

The report is `report5.md` (or fold everything into one `report.md`): per-step
outcomes, the routes' proof commands, the smoke-project name left behind, the
image decision and why, and anything the port proved wrong — `GUIDE.md`
claims, JS behaviors deliberately not preserved (say which and why), and
whatever phase 4 should pick up. Failures are results too.
