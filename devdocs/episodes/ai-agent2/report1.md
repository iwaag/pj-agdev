# Step 1 Report — Generalize MainScene into a parameterized panel-grid scene

Status: complete (compile-checked; visual pass deferred to Step 4 per plan)

## What was done

- Replaced `src/scenes/MainScene.ts` with `src/scenes/PanelGridScene.ts`, a
  reusable grid scene parameterized entirely through a `PanelGridConfig`
  constructor argument: scene key, title, loading/unavailable/subtitle/footer
  texts, an optional `switchTo` hint, and a `loadRows()` provider returning
  `PanelRow[]` (`{id, name, status, detail?}`).
- Row status is now a self-contained `PanelRowStatus` (`{emoji, color, label}`)
  instead of a hard-coded `ClusterStatus` lookup, so Step 2 can style workspace
  rows by `activity_class` without touching the scene. An optional `detail`
  string renders after the status label (intended for the workspace's `node`).
- `src/views.ts` holds the two concrete configs: `nodes` (wired to
  `loadExistingNodes()` with the original status palette) and `workspaces`
  (empty row provider until Step 2).
- `src/clusterState.ts`: `filterExistingNodes()` became
  `filterExistingTargets(envelope, kind)`; `loadExistingNodes()` now calls it
  with `'node'`. `NodePanelModel` renamed to `TargetPanelModel` (breaking-change
  episode, no alias kept).
- `src/viewSwitcher.ts` is the single switching seam: `registerGame()`,
  `currentView()`, and `switchView(key)` (validates the key, sleeps the current
  scene, `scene.run()`s the target — run wakes a sleeping scene or starts a
  dormant one). All later steps (keyboard, AI) go through this one function.
- `src/main.ts` registers both `PanelGridScene` instances; Phaser auto-starts
  only the first (`nodes`), then `registerGame(game, 'nodes')` primes the seam.
- Manual switch for testing: each scene shows a clickable `⇄ <other view>`
  label at the top-left, plus a `V` keyboard shortcut. The keyboard handler
  ignores keystrokes while the chat panel's textarea (or any input) has focus,
  since Phaser listens window-wide. Sleeping a scene disables its input, so
  only the visible scene's handlers fire.
- Kept the two-layer container trick (layout `anchor` + tweened `floatLayer`)
  unchanged, per the plan's hint about resize/tween interaction.

## Verification

- `npm run build` (tsc + vite) passes cleanly after deleting `MainScene.ts`.
- Behavior on `scene.switch`-style sleep/wake round trips (float tweens,
  resize on both views) is scheduled for the Step 4 manual pass, as the plan's
  acceptance for visuals is exercised there against the running app.

## Notes / deviations

- Used `sleep` + `run` on the `SceneManager` instead of a scene-local
  `scene.switch`, because the seam lives at module level (outside any scene).
  Semantics are the same: state is preserved, no re-fetch on toggle.
- The workspace view currently renders zero panels with subtitle
  "0 workspaces are present" — expected until Step 2 supplies data.
