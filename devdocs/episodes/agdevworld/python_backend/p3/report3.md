# Phase 3, step 3 — project start, and the nginx flip

Done. `/api/autolab/projects` is ported, and nginx now sends every `/api/`
path the UI reaches to the Python service. The JavaScript service is still
running, reachable only through the `location /api/` remainder — the
rollback path, deleted in step 4.

## What was built

`assistant/agdevworld_assistant/projects.py` — the last JS-only capability,
ported from `autolab-projects.mjs` in provisioning order (Gitea → Plane →
Zulip; any step's failure aborts the rest, `ProjectStartError(step, ...)` →
502 `project_start_failed` with the `step` field):

1. **Gitea** — token read from file at request time (`GITEA_TOKEN_PATH`,
   default `/run/secrets/gitea.token`), `<name>` + `<name>-direction` under
   `GITEA_ORG` (default `autodev`), direction repo seeded with
   `GUIDE.md`/`concept.md`/`.gitignore` via the contents API (base64), 30 s
   per call.
2. **Plane** — project create (identifier from `plane_identifier()`,
   "whack-a-mole-2" → "WAM2"), then the state list, returning
   `{id, identifier, states: {name: id}}`. 60 s timeouts.
3. **Zulip** — `create_channel("pj-<name>", ...)` with step 2's client and
   active-user filter.

Route mechanics kept: `PROJECT_NAME`, non-empty `concept`, the preflight
(503 `project_start_unconfigured` listing `missing` before touching
anything), 201 `{kind: "autolab.project.v1", project, gitea, plane, zulip}`.
Step 1's `proxy_fetch` serves all the HTTP here too. One deliberate JS
deviation: a *network*-level Gitea/Plane failure now becomes
`project_start_failed` with its step, where the JS let it escape to a bare
500 — an explicit step beats an anonymous one.

**nginx** — `/api/forge/`, `/api/freeforge/`, `/api/autolab/`, `/api/plane/`
now proxy to `assistant-py:8093`. Chat keeps its 310 s read timeout; the
autolab location gets 130 s (window POSTs hold 60 s, project starts chain
30–60 s calls), forge 130 s (its upstream bound is 120 s), freeforge/plane
90 s.

## Proof

`uv run pytest` — 116 passed (20 new in `tests_py/test_projects.py`,
mirroring `tests/autolab-projects.test.mjs` plus the route's validation,
preflight, and both 502 mappings).

Live:

- On `:8093`: `p3smoke1` provisioned end to end — Gitea
  `autodev/p3smoke1` + `-direction` (seeds verified via the contents API),
  Plane project `da18de64…` identifier `P` with all five state ids, Zulip
  `#pj-p3smoke1` with principals `[10, 8, 9, 11, 12, 13, 14]`.
- Through the flipped `:8090`: `flipproof` provisioned end to end (Plane
  `27521536…`, identifier `F`, `#pj-flipproof`).
- Through `:8090` after `docker compose up --build -d web assistant
  assistant-py`: `/api/autolab/nodes`, `/api/plane/issues`, `/api/guide`,
  `/` all answer; the app renders (screenshot, nodes view populated); and
  one `local`-profile browser chat fetched `/api/autolab/nodes` through the
  passthrough and answered with a `switch_view` action —
  `profile: local, harness: opencode, provider: ollama, outcome: done`.

## Environmental findings (also true of the JS implementation)

- **Plane rejects hyphens in project names now**: `p3-smoke-1` → HTTP 400
  "Project name cannot contain special characters." The JS sends the same
  payload, so `/api/autolab/projects` cannot create hyphenated projects on
  this Plane (1.4.1); the existing "Whack A Mole" etc. were created by a
  different (humanizing) flow. Phase 4 candidate: humanize the Plane name
  the way that flow did.
- **Identifier collisions answer a misleading 409**: `p3smoke2` failed with
  "The project name is already taken" — the real clash was its identifier
  `P` with `p3smoke1`'s. Worth knowing before trusting Plane's message.

## Debris left behind (experimental environment, intentional)

- Gitea: `autodev/p3-smoke-1(+-direction)` and `autodev/p3smoke2(+-direction)`
  — created before their Plane steps failed; `autodev/p3smoke1`,
  `autodev/flipproof` pairs from the successful runs.
- Plane: projects `p3smoke1` (identifier `P`), `flipproof` (`F`).
- Zulip: channels `#pj-p3smoke1`, `#pj-flipproof`.
