# Phase 3, step 5 — the full sweep, and the phase report

The collapsed system — one Python `assistant`, one image, no JavaScript —
proven end to end through `http://localhost:8090`. Phase 3 is done.

## The sweep

- `uv run pytest` → **116 passed** (was 44 at the end of phase 2; steps 1–3
  added 72). `npm run build` (tsc + vite) → green; the frontend's only
  check now, the usual non-failing chunk-size advisory aside.
- **Four views** through the collapsed nginx, screenshotted via the UI's
  cycle control: nodes (6 cluster nodes), workspaces (2), autolab (5
  projects on agstudio, live through the passthrough), tasks (1 ready task,
  live from Plane).
- **Chat**: one `stub` run (profile `stub`, harness `fake`, `outcome:
  done` — the composed prompt echoed back, proving the whole route without a
  model), and one `local` run that fetched `/api/autolab/nodes` through the
  passthrough and answered with a `switch_view` action (`harness: opencode`,
  `provider: ollama`, `outcome: done`, 2 turns, $0.00).
- **A note** (`/api/note` → 201 `assistant.note.v1`, id `7a2141ab…`).
- **One passthrough per family**: autolab `agstudio/status` 200;
  `plane/issues?per_page=1` 200; forge up (host `:8092/healthz` 200) and
  `GET /api/forge/requests/does-not-exist` forwarded the upstream 404
  verbatim; the evidence guard answered its 403. Freeforge's live
  round-trip was proven in step 2 against the real realm (created, answered
  by agforge, resolved).
- **One logs read** (`docker compose logs assistant`, then the streams
  separately): the run and note records are the only stdout
  (`assistant.run.v1` with profile/harness/provider/model/usage,
  `assistant.note.v1`); access logs and warnings are stderr; a grep for
  key/token/authorization strings over the whole log found nothing.
- **sonnet**: `ANTHROPIC_API_KEY` is absent in the container, so the
  claude_code launch conditions remain unproven — the same standing gap
  phase 2 reported, carried unchanged, no synthesized pass.

## Per-step outcomes (details in report1–4.md)

1. **Passthroughs** — forge/autolab/Plane in `passthrough.py` around one
   `proxy_fetch()` that treats `HTTPError` as the response; proven
   request-for-request identical against the JS service on `:8091`.
2. **Zulip** — freeforge + missions on `agag.zulip` (`workflows.py`); topic
   names, active-user filter and the one-retry are the only local code.
   Finding: Docker DNS answers the realm's LAN hostname with every host
   interface and urllib walks them serially (~120 s/call, invisible under
   Node's happy-eyeballs); fixed with a `ZULIP_LAN_HOST` host-gateway alias,
   hostname kept in the ignored `.env`.
3. **Project start + flip** — `projects.py` (Gitea → Plane → Zulip, failure
   names its step); nginx sent all UI-reached `/api/` to the Python service.
4. **Cutover** — the Python service became `assistant` (port 8091), nginx
   collapsed to two locations, the 14 `.mjs` files + `assistant/package.json`
   + the root `npm test` script deleted; `git ls-files 'assistant/*.mjs'`
   empty.

## The image decision

Stayed `node:26-alpine` + `apk add python3 uv git`, CMD now the venv python.
Runtime node is non-negotiable (the harnesses arrive by `npm install -g`),
uv already targets the system interpreter on Alpine, and the image has been
proven since phase 2 — a base swap would have bought nothing. `git` stays
for uv's pyagag git source.

## What the port proved wrong, and deliberate deviations

- **The guide's "lowercase-hyphen name" for project starts overpromises on
  this Plane** (1.4.1): hyphenated names are rejected with "Project name
  cannot contain special characters", and single-word names collapse to
  one-letter identifiers that collide (`p3smoke2` failed on `p3smoke1`'s
  `P` — behind a misleading "name is already taken" 409). True of the JS
  implementation too; the existing humanized Plane projects came from a
  different flow. Phase 4 should either humanize the Plane name/identifier
  or narrow the card's claim.
- **Deviation**: a network-level Gitea/Plane failure during project start
  answers `project_start_failed` with its `step`, where the JS let it escape
  to a bare 500 — an explicit step beats an anonymous one.
- **Deviation (cosmetic)**: node probe failure `detail` uses Python
  exception class names (`ConnectionRefusedError`) instead of Node codes
  (`ECONNREFUSED`); the field was always free-form.

## Debris (experimental environment, intentional; names for cleanup)

Gitea `autodev/`: `p3-smoke-1(+-direction)`, `p3smoke1(+-direction)`,
`p3smoke2(+-direction)`, `flipproof(+-direction)`. Plane: `p3smoke1` (`P`),
`flipproof` (`F`). Zulip: `#pj-p3smoke1`, `#pj-flipproof`, and the two
resolved `✔ create-20260813-*` topics in #FreeForge plus one resolved
`✔ mission-*` topic in #pj-spike.

## For phase 4

- `README_DEV.md` rewrite (left stale on purpose).
- The Plane naming issue above (humanize or narrow the card).
- The `ANTHROPIC_API_KEY`/sonnet gap, whenever a key appears.
- `.local/devenv.md` documents the new `ZULIP_LAN_HOST` requirement for
  anyone recreating `.env`.
