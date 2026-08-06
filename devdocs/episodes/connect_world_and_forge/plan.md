# Plan — connect_world_and_forge

Goal (from braindump.txt): an agdevworld user asks the assistant for an image;
the request travels to agforge, agforge generates it, and the image appears on
the agdevworld screen.

## Design decisions (settled in discussion, not up for re-derivation)

- **The boundary between agdevworld and agforge is an intent-level HTTP API,
  not a parameter API and not agent-to-agent chat.** agdevworld sends a desire
  (prompt text) and receives result artifacts. It knows nothing about models,
  sizes, steps, or SwarmUI. Everything generation-specific is agforge's
  responsibility, resolved agforge-side (defaults.toml / .local/.env) unless a
  future caller explicitly overrides — this episode adds **no** override
  fields beyond the desire text.
- **Contract shape** (async job style, so a future slow agent backend fits
  without changing callers):

  ```
  POST /api/requests      { "desire": "<prompt text>" }
                          -> 202 { "request_id": "..." }
  GET  /api/requests/{id} -> { "status": "working" | "done" | "failed",
                               "artifacts": [ { "kind": "image", "url": "<presigned URL>" } ],
                               "detail": "<human-readable, present on failed>" }
  ```

  `desire` is the only required input. `kind` exists so agforge can later
  return music/video without breaking callers. Field names above are the
  contract; add fields freely, don't rename these.
- **Backend today is deterministic**: the service wraps the already-verified
  `agforge/scripts/generate.sh` (see ent-episodes/swarmui-flow/report5.md — it
  runs clean with no improvisation). An agent behind the same seam is a
  future episode, out of scope here.
- **Display**: image bubble inside the existing chat panel. No new Phaser
  scene, no gallery, no persistence.

## Non-goals

- Saving/cataloguing generated images (presigned URL expiry losing the image
  is acceptable).
- Auth, rate limiting, multi-user concerns — experimental cluster, no
  production traffic.
- Backward compatibility — destructive phase; change signatures, protocols,
  and docs outright rather than patching around them.

## Prohibitions (the full list — everything else is implementer's discretion)

- Never commit endpoints, hostnames, credentials, or generated images
  (agforge hard rule; `.local/` is the place for real values).
- Never write to the `nctl-outbox` bucket; agforge uses its `agforge` bucket.

## Step 1 — agforge request service

Add a small HTTP service to `agforge/` (suggested: `service/` directory)
implementing the contract above.

- Simplest solid approach: keep an in-memory job dict, run each request as
  `subprocess` → `scripts/generate.sh "<desire>"` on a worker thread, capture
  the final stdout line as the presigned URL. This reuses the verified
  pipeline byte-for-byte instead of re-implementing it; importing
  `generate.py` functions directly is also fine if it stays this simple.
- Python with uv inline-script deps matches the existing agforge style;
  stdlib `http.server`/`ThreadingHTTPServer` is enough. A `GET /healthz` is
  cheap and mirrors the assistant service.
- Failure mapping: nonzero exit from generate.sh → `status: "failed"` with
  stderr tail in `detail`. Don't retry; surfacing the error is the job.
- Jobs may vanish on restart — acceptable, note it in README_DEV.
- Document the service (port, contract, how to run) in
  `agforge/README_DEV.md`, restructuring freely.

Acceptance: from a clean checkout with a working `.local/.env`,
`curl -X POST .../api/requests -d '{"desire":"a red circle"}'` then polling
`GET` reaches `done` with a fetchable image URL; a request with an empty
desire or a broken SwarmUI URL reaches `failed` with a useful `detail`.

## Step 2 — agdevworld reaches agforge

Give the browser a same-origin path to the agforge service to avoid CORS.

- Suggested route: extend `assistant/server.mjs` with a passthrough (e.g.
  `/api/forge/*` → `AGFORGE_URL` from env, plus compose.yaml env entry).
  This matches the existing "browser → nginx → assistant" flow and keeps
  nginx.conf untouched. An nginx-level proxy is also acceptable if preferred,
  but nginx's static config makes env-driven upstreams clumsier.
- `AGFORGE_URL` is an endpoint: real value goes in git-ignored env/.local,
  not committed defaults pointing at real hostnames.

Acceptance: `curl` against the agdevworld origin (port 8090) can create and
poll an agforge request end to end.

## Step 3 — assistant action + image bubble

- Add a `generate_image` action to `ROLE_PROMPT` in `assistant/server.mjs`,
  following the existing `switch_view` pattern:
  `{"action":"generate_image","desire":"..."}`.
  - Watch out: unlike `switch_view`, the desire is free text embedded in
    JSON. Small local models (glm-4.7-flash) may mangle quotes/newlines and
    `extractAssistantActions`' regex is `{[^{}]*}` — nested braces or broken
    escaping will drop the action. Test with prompts containing quotes. A
    pragmatic fallback if it proves flaky: have the action carry no desire
    and use the latest user message as the desire.
- In `chatPanel.ts` / `main.ts`: on `generate_image`, immediately add a
  "generating…" bubble, POST the request, poll `GET` every few seconds
  (generation takes tens of seconds), then swap in an `<img>` bubble with
  `max-width: 100%` on `done`, or an error bubble with `detail` on `failed`.
  **Do not block the chat**: the send button must stay usable while
  generation runs; the existing synchronous send flow must not await the
  image.
- Optional, only if trivial: click the image to open it full-size (the
  detailPopup overlay pattern is available to imitate).

Acceptance: typing "draw a castle at sunset" in the chat produces, without
any further interaction, an image visible in the panel; chat remains usable
while it generates; a failure shows a readable error bubble.

## Step 4 — end-to-end verification and report

- Run the full path from a browser against the composed stack. Include at
  least: one success, one prompt containing double quotes, one forced failure
  (e.g. wrong SwarmUI URL).
- Verify the presigned URL actually renders in the browser used for
  agdevworld. Known trap: the URL's host is whatever
  `AGFORGE_S3_ENDPOINT` says (e.g. `agstudio.local:9100`) — it must be
  resolvable from the browser's machine, not just from where agforge runs.
  If it isn't, the cheap fix is proxying the image through the Step 2
  passthrough; record whichever reality you find in `.local/devenv.md`.
- Write `report.md` (or per-step reports if steps were reported separately):
  what held, what surprised, per devpolicy. Record scoped-out follow-ups
  (agent access point on agforge; artifact persistence; voice-driven flow)
  in `devdocs/todo_done.md`.

## Premises (verify early, they gate everything)

- SwarmUI at `AGFORGE_SWARMUI_URL` and MinIO at `AGFORGE_S3_ENDPOINT` are up
  and `scripts/generate.sh "test"` succeeds today, before any new code.
- ollama with the configured model is reachable from the assistant container
  (existing chat works).
- If S3 is unconfigured, follow the existing agforge README_DEV instruction
  (devenv MinIO + scoped `agforge-rw` user); do not improvise storage.
