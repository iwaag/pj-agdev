# Step 4 Report — Verify and refresh the user-checkable container

Status: complete for everything verifiable without a human at the screen; the
in-browser visual pass is ready for the user at http://localhost:8090

## Verification performed

Build and containers:

- `npm run build` (tsc + vite) passes (run after every step).
- `docker compose up --build -d web`: image rebuilt, container up,
  `curl -I http://localhost:8090/` returns HTTP 200 (nginx).
- `docker compose up --build -d assistant`: rebuilt so the new `ROLE_PROMPT`
  is live; `/healthz` returns `{"ok":true}`.
- Note: the live `public/cluster/state.json` snapshot was present at build
  time, so it is baked into the local web image (documented behavior in
  README_DEV). No `public/cluster/workspaces.json` existed yet, so the
  workspace view serves sample data until the next `npm run cluster:fetch`.

Snapshot endpoints on the running container:

- `/cluster/state.json` → 200 `application/json` (live drift snapshot).
- `/cluster/workspaces.json` → 200 `text/html` — nginx's SPA fallback mirrors
  the Vite dev quirk; the loader's Content-Type check catches this and falls
  back to the sample, as designed in Step 2.
- `/workspaces.sample.json` → 200 `application/json`.

Assistant end-to-end (live ollama, glm-4.7-flash):

- "show me the workspaces" →
  `{"action":"switch_view","view":"workspaces"}` + confirmation sentence.
- Japanese "ノード一覧を見せて" →
  `{"action":"switch_view","view":"nodes"}` + confirmation in Japanese.
- Plain Q&A ("how many nodes are converged?" against a synthetic summary) →
  `"2"`, no JSON residue.
- Combined with the Step 3 extractor unit cases (strip, fence cleanup,
  malformed-JSON tolerance, JSON-only fallback), the full chat → action →
  `switchView()` chain is exercised except for the final in-browser render.

## Remaining manual pass (user)

Open http://localhost:8090 and check: both views render (nodes live, workspaces
sample), the ⇄ label / V key toggles, resize lays out correctly on both, float
animations look right after a sleep/wake round trip, chat "show me the
workspaces" / "ノードを見せて" switches both directions, and normal Q&A bubbles
are clean. Nothing observed in this session suggests any of these will fail,
but they were not observed in a real browser.

## Follow-up candidates

- Nav scene overlaid via `scene.launch` instead of per-scene switch labels.
- More actions: focus/highlight a specific panel, refresh snapshot on demand.
- Real ollama tool calling when the model changes (protocol seam is ready —
  swap the ROLE_PROMPT instructions and reuse `extractAssistantActions`
  shape or replace it below the seam).
- Run `CAGENT_URL=... npm run cluster:fetch` to produce the first live
  `workspaces.json` and rebuild the web image to bake it in.
- Workspace panels could surface `freshness`/`gap_codes` as a secondary hint
  (currently only `activity_class` and `node` are shown).

## Episode summary

All four steps are done. `MainScene` became the config-driven `PanelGridScene`
registered twice (`nodes`, `workspaces`); `switchView()` in `viewSwitcher.ts`
is the single switching seam used by the click label, the V key, and the AI;
`nctl.workspaces.v1` data flows cagent → `scripts/fetch-cluster-state.mjs` →
`public/cluster/workspaces.json` → `loadWorkspaceRows()` → activity-class-
styled panels, with a three-row sample fallback; and the assistant switches
views via a forgiving inline-JSON action protocol defined above the
engine-agnostic seam. Hard constraints held: no snapshot/credential is
committable (`public/cluster/` ignored), and only code below the seam knows
the engine is ollama.
