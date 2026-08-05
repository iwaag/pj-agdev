# Step 3 Report — Cluster context injection

Date: 2026-08-05

## What was built

Changes are confined to [src/clusterState.ts](../../agdevworld/src/clusterState.ts)
and [src/main.ts](../../agdevworld/src/main.ts); the chat panel and backend are
untouched (the `getContext` seam from Step 2 absorbed this step).

- `clusterState.ts`:
  - The snapshot fetch/parse (live `/cluster/state.json`, fallback
    `/state.sample.json`) was split out as `loadDriftEnvelope()`;
    `loadExistingNodes()` now composes it, unchanged in behavior.
  - `DriftDiff` gained optional `severity` / `message` fields (already present
    in the `nctl.drift.v1` payload, previously dropped by the type).
  - New `summarizeClusterContext(envelope)` builds the compact plain-text
    context: a `Status counts: …` line from `data.summary`, then one line per
    target — `- <kind> <name>: <status> — code (severity): message; …`.
- `main.ts` loads the envelope once at startup, keeps the summary in a
  variable, and the chat panel's context provider reads it per request.

## Implementer's calls (allowed by the plan)

- The summary includes **all** targets, not just confirmed nodes and not just
  `kind === 'node'` (services appear too, labeled by kind). This lets the
  assistant answer "why is X missing?" for `missing_actual_node` /
  `waiting_for_manual_initial_access` targets that the visual panel hides.
- The scene still calls `loadExistingNodes()` itself, so the snapshot is
  fetched twice at startup. It is a tiny local static file; sharing one fetch
  was not worth coupling the scene to the chat bootstrap.
- If the snapshot fails to load, the chat context silently stays empty (the
  backend then tells the model no summary is available); the scene already
  surfaces the load error visually.

## Verification

Per the plan, verified against the **sample** snapshot: the live
`public/cluster/state.json` was temporarily moved aside, then via Playwright
the question "Which nodes are drifting and why?" was sent from the panel.
Answer rendered:

> node node-gamma is drifting due to a hostname mismatch.

— names `node-gamma` and the `hostname_mismatch` cause as required. The live
snapshot was restored afterward (and re-verified present).
