# ai-agent2 Plan — workspace view, scene switching, AI-driven UI control

Goal: add a desired-workspace list view alongside the existing desired-node view,
make the two switchable, and let the AI assistant switch them via chat.
This is a breaking-change episode: no backward compatibility required, refactor freely.

Ground rules (deliberately minimal):

- Experimental, non-production environment. Do not over-engineer security or
  destructive-action safeguards.
- Only hard constraints: never commit `public/cluster/*` snapshots or cagent
  credentials (already gitignored); keep the engine-agnostic seam in
  `assistant/server.mjs` (only code below the seam comment may know the engine
  is ollama).
- Everything else — naming, file layout, UI details — is implementer's discretion.
- Write `report[step].md` after each step (devpolicy).

## Step 1 — Generalize MainScene into a parameterized panel-grid scene

Turn `src/scenes/MainScene.ts` into a reusable grid scene and register it twice.

- Parameterize by config passed via constructor or Phaser's scene `init(data)`:
  scene key, heading texts, and a row-provider function returning
  `{id, name, status}[]`.
- Parameterize `filterExistingNodes()` in `src/clusterState.ts:76` (the
  `target.kind === 'node'` check is the only node-specific part).
- Register two instances in `src/main.ts` (currently `scene: [MainScene]` at
  line 22), e.g. keys `nodes` and `workspaces`. Only one starts active.
- Add and export a module-level `switchView(key: string)` that calls
  `game.scene.switch(...)`. All later steps (keyboard, AI) must go through this
  one function — that seam is the point of this step.
- Add a minimal manual switch for testing (keyboard key or clickable label).

Hints:

- `scene.switch` sleeps the old scene and wakes the new one, preserving state;
  `scene.start` rebuilds. Either works here; `switch` avoids re-fetch flicker.
  Note tweens keep running on slept scenes' timelines — verify float animations
  look right after a sleep/wake round trip.
- Keep the two-layer container trick (`anchor` for layout, `floatLayer` for
  tweens, `MainScene.ts:89-142`) — it prevents tween offsets from being baked
  into grid positions on relayout.
- The chat panel is a DOM overlay (`chatPanel.ts`), untouched by scene switches.

Acceptance: both views render (workspaces may be empty until Step 2) and toggle
via the manual switch; resize still lays out correctly on both.

## Step 2 — Workspace data: fetch, parse, sample

Bring `nctl.workspaces.v1` data into the frontend.

- clusterintent side needs no new code: `nctl workspaces --json` already emits
  everything the view needs. Row shape (`WorkspaceRow`,
  `pj-clusterintent/nctl/src/nctl_core/workspaces_render.py:37-50`):
  `slug, name, node, desired_presence, presence, identity, identity_reason?,
  activity_class?, activity_reasons, freshness, checked_at?, gap_codes`.
- Extend `scripts/fetch-cluster-state.mjs`: the cagent PROMPT (line 11) currently
  requests only `nctl drift --json`. Ask for both commands' output. Simplest
  robust shape: have cagent zip both JSON files into one upload, or issue two
  sequential cagent requests — implementer's choice. Save as
  `public/cluster/workspaces.json` next to `state.json`.
- Add a loader in `clusterState.ts` mirroring `loadDriftEnvelope()`
  (lines 94-106), validating `schema === 'nctl.workspaces.v1'`. Copy its
  fallback quirk: Vite dev's history fallback returns index.html with 200, so
  check Content-Type, not just status, before falling back to the sample.
- Create `public/workspaces.sample.json` (2-3 rows covering different
  `activity_class` values). The existing `state.sample.json` has no workspace
  targets — that's expected; the workspace view reads the new envelope, not drift.
- Wire the workspaces scene's row provider to it. Suggested status mapping:
  derive panel status/color from `activity_class` (active_development /
  behind_origin / idle) rather than gap codes — it's the field this envelope
  exists to surface. Showing `node` on the panel is cheap and useful.

Acceptance: workspace view shows live rows when `public/cluster/workspaces.json`
is present and sample rows otherwise.

## Step 3 — AI-driven view switching

Give the assistant a lightweight action protocol; skip ollama tool calling for
now (`glm-4.7-flash` tool support is uncertain; revisit when the model changes).

- `assistant/server.mjs`: extend `ROLE_PROMPT` (lines 17-20) to describe the
  available action and its exact syntax, e.g.: to switch the screen, include a
  fenced or single-line JSON object `{"action":"switch_view","view":"nodes"|"workspaces"}`
  in the reply, plus a short natural-language confirmation. Keep the seam:
  the protocol is defined above the ollama-specific code.
- `chatPanel.ts`: after receiving `data.reply` (line 91), scan for the action
  JSON, execute via the Step 1 `switchView`, and strip the JSON from the
  displayed text. `initChatPanel` will need the action callback injected from
  `main.ts` (same pattern as the existing `getContext` injection).
- Be forgiving in the parser: small local models mangle formats. Accept the
  object anywhere in the reply (regex for `{"action"...}` is fine); ignore
  unknown actions silently.
- Optionally include the current view name in the chat context so the model
  knows what's on screen.

Acceptance: typing "show me the workspaces" (or Japanese equivalent) switches
the view; normal Q&A replies still render cleanly with no JSON residue.

## Step 4 — Verify and refresh the user-checkable container

- `npm run build` for a compile check, then `docker compose up --build -d web`
  and confirm `http://localhost:8090` per `README_DEV.md` (remember the local
  image bakes in `public/cluster/` snapshots if present).
- Manual pass: live + sample data on both views, resize, manual switch,
  AI switch both directions, plain Q&A unaffected.
- Write the final report; note follow-up candidates (nav scene overlaid via
  `scene.launch`, more actions such as focus/highlight, real tool calling).
