# Plan: cluster node detail popup + agent summary

Goal (from braindump.txt): click a node in agdevworld → popup with detailed
cluster info; let the chat agent summarize/explain it. Backward compatibility
is NOT required (breaking-change phase). Implementer has wide discretion —
everything below except "Hard rules" is advice, not mandate.

Hard rules (minimal):
- Never commit live snapshots or cagent credentials (`public/cluster/*`,
  tokens). This is the existing repo rule; keep it.
- cagent access stays read-only commands (`nctl actual`, downloads).

Useful context discovered during planning:
- The frontend is Phaser 2D + a DOM-overlay pattern (`#app` leaves a 340px
  right gutter, `chatPanel.ts` is a DOM overlay). Prefer DOM for the popup.
- `state.json` already carries rich unused data: `diffs[].desired/actual/
  sources`, `intent_effect_summary` (lifecycle, node_type, …). Step 1–2 need
  no clusterintent changes at all.
- Upstream `nctl actual --json --detail` (schema `nctl.actual.v2`, adds
  `devices[].facts_raw` + `detail_level`) is done and documented in
  `pj-clusterintent/devdocs/vision/fullstate_export/report.md` and
  `pj-clusterintent/nctl/docs/state-bundle.md`.
- Snapshots are static files baked into the nginx image; there is no live
  browser→cagent path. On-demand per-node fetch is out of scope — prefetch
  everything via `cluster:fetch`.
- `assistant/server.mjs` forwards to a small local Ollama model; the code
  comment at `clusterState.ts:171-174` warns it degrades on large JSON.
  Never feed `facts_raw` to the model raw — always digest to compact text.

## Step 1 — make nodes clickable and keep their data

Files: `src/scenes/PanelGridScene.ts`, `src/clusterState.ts`, `src/views.ts`.

- Widen `TargetPanelModel` / `filterExistingTargets` (`clusterState.ts:74-86`)
  so panels retain the full target (at least `diffs`), instead of flattening
  to `{id, name, status}`. Breaking the type is fine.
- Store the row on `PanelView` and add a click hit area. Hint: containers
  need an explicit `setInteractive(new Phaser.Geom.Rectangle(...),
  Phaser.Geom.Rectangle.Contains)`; attach it to the static `anchor`, not
  the tweened `floatLayer`, or clicks will miss while the panel floats.
- Emit a `nodeSelected(row)` callback up to `main.ts`.

Done when: clicking any panel logs/holds the selected target incl. diffs.

## Step 2 — detail popup (DOM overlay)

Files: new `src/detailPopup.ts`, `src/main.ts`, `index.html`/CSS.

- Build a DOM popup/panel modeled on `chatPanel.ts` (same styling approach).
  Show: name, status, per-diff desired vs actual, severity/message, and the
  `intent_effect_summary` node object when present. Raw JSON behind a
  collapsible "raw" section is enough — no need to prettify everything.
- Close on outside click / Esc / re-click. One popup at a time.
- Workspaces view: showing the `WorkspaceRow` fields (already fully typed,
  `clusterState.ts:112-125`) in the same popup is cheap — include it.

Done when: click node → popup with real data from the live snapshot;
`docker compose up --build -d web` serves it at :8090.

## Step 3 — agent "explain this node"

Files: `src/detailPopup.ts`, `src/main.ts`, `src/clusterState.ts` (or new
`src/summarizeNode.ts`), optionally `assistant/server.mjs`.

- Add `summarizeNode(target)` producing a compact plain-text digest, same
  spirit as `summarizeClusterContext` (`clusterState.ts:175`).
- Popup gets an "Ask agent" button. Two wiring options, implementer's choice:
  a) inject the digest into the chat context (`getContext` in `main.ts:8-20`)
     and programmatically send a question through the chat panel — reuses
     the existing `/api/chat` seam, visible in chat history;
  b) render the reply inside the popup itself.
  Option (a) is less code and matches the "single seam for AI actions"
  intent noted in `viewSwitcher.ts:1-3`.

Done when: clicking the button yields a sensible spoken-style explanation of
the node from the assistant.

## Step 4 — ingest `nctl actual --detail` (facts_raw)

Files: `scripts/fetch-cluster-state.mjs`, `src/clusterState.ts`,
`src/detailPopup.ts`, `README_DEV.md`.

- Append to the declarative `ARTIFACTS` table (~10 lines): command
  `nctl actual --json --detail`, schema `nctl.actual.v2`, output
  `public/cluster/actual.json`, plus a small validator like the existing
  ones. Frontend: loader with sample fallback (add a minimal
  `public/actual.sample.json`), match devices to targets by name/slug.
- Popup: merge in the interesting facts (GPU, memory, Docker containers —
  see report4.md upstream for what facts_raw actually contains); keep the
  full facts_raw under the raw section. Extend `summarizeNode` with a few
  hardware lines — selected fields only, never the whole dict.
- If full-cluster `--detail` output turns out too big, fall back to
  host-scoped `nctl actual HOST --detail` per node in the fetch loop; don't
  build server routes for this now.
- Update README_DEV.md snapshot section (third file, same do-not-commit rule).

Done when: `cluster:fetch` produces actual.json, popup shows hardware facts,
agent summary mentions them.

## Reporting

Write `report.md` (or per-step `report[n].md`) in this episode folder when
done — per devpolicy this is strongly recommended. Rebuild the web container
after visual milestones (README_DEV.md rule).
