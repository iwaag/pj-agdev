# Step 2 Report: Load and filter cluster nodes

Implemented the browser-side seam between the drift snapshot and the Phaser
scene.

## Result

- Added `src/clusterState.ts` with the `nctl.drift.v1` data types, runtime
  envelope validation, snapshot loading, and node filtering.
- The loader first requests `/cluster/state.json` with caching disabled. It
  falls back to `/state.sample.json` for HTTP 404 or Vite's development-only
  200 HTML history fallback; other HTTP and data errors remain visible instead
  of silently hiding a broken live snapshot.
- A target is included only when `target.kind` is `node` and none of these
  not-confirmed codes is present:
  - `missing_actual_node`
  - `realized_device_missing`
  - `no_realized_object`
  - `waiting_for_manual_initial_access`
- The derived panel model retains the target identity/name and drift status.
- `MainScene` now loads that model and exposes the filtered count in its
  temporary Step 2 title. Step 3 replaces this temporary hello-world surface
  with the actual panels.

## Acceptance proof

The seven-target sample intentionally contains four confirmed node targets,
one missing node, one node awaiting manual initial access, and one service.
The filter returned exactly these four nodes, matching the hand count:

1. `node-alpha` — converged
2. `node-beta` — converging
3. `node-gamma` — drifting
4. `node-delta` — unknown

The ignored live snapshot produced five confirmed nodes: three converged and
two unknown.

## Verification

- `npm run build` — TypeScript and Vite production build passed.
- Direct sample parse/filter assertion — exactly four nodes and all four
  status values in the expected order.
- Direct live snapshot parse/filter check — five nodes.
- `git diff --check`

Vite emitted only its existing advisory that the Phaser bundle is larger than
500 kB; the build completed successfully.

Submodule implementation commit: `b25122f` (`Load and filter cluster node
snapshots`).
