# Report — Step 1: make nodes clickable and keep their data

Status: done.

## What changed

- `src/clusterState.ts`
  - Exported `DriftTargetRef` / `DriftDiff` / `DriftTarget` and widened
    `DriftDiff` with the previously ignored `desired` / `actual` / `sources`
    fields.
  - `TargetPanelModel` now carries `entry: DriftTarget` (the full drift entry
    including diffs) instead of only the flattened `{id, name, status}`.
    Breaking change, as allowed by the plan.
- `src/scenes/PanelGridScene.ts`
  - `PanelRow` gained an opaque `payload?: unknown` so views can carry their
    full source record through the generic grid.
  - `PanelGridConfig` gained `onSelect?: (row: PanelRow) => void`.
  - Each panel's static `anchor` container (not the tweened `floatLayer`, per
    the plan's hint) gets a `Phaser.Geom.Rectangle` hit area +
    `useHandCursor`, firing `onSelect` on `pointerup`.
- `src/views.ts`
  - `nodesViewConfig` / `workspacesViewConfig` are now factory functions
    taking an `onSelect(selection)` callback. Introduced the discriminated
    union `PanelSelection` (`{view:'nodes', target: DriftTarget}` |
    `{view:'workspaces', row: WorkspaceRow}`); both views attach their full
    record as `payload`.
- `src/main.ts`
  - Passes a `handleSelection` callback into both view configs; for this step
    it logs the selection (`console.log('panel selected:', selection)`).

## Verification

- `npm run build` (tsc + vite) passes.
- Headless-browser check (playwright-core against `npm run preview`, live
  snapshot present): clicking a node panel logs
  `panel selected: {view: nodes, target: Object}` — the full drift entry with
  diffs is held by the handler. Workspaces view uses the same path.

## Notes for next steps

- `handleSelection` is the single seam Step 2's popup will hook into.
- No clusterintent-side changes were needed, as predicted by the plan.
