# Report — Step 2: detail popup (DOM overlay)

Status: done.

## What changed

- New `src/detailPopup.ts` — DOM overlay popup, same pattern/styling family
  as `chatPanel.ts` (injected CSS, absolutely-positioned sibling of `#app`).
  Sits over the canvas area, clear of the 340px chat gutter.
  - Node view: header (name, kind, colored status badge), an INTENT section
    (key/value list from the `intent_effect_summary` diff's `desired.node`
    object when present), a DIFFS section with per-diff code, severity chip,
    message, and side-by-side DESIRED / ACTUAL JSON panes.
  - Workspace view: all `WorkspaceRow` fields as a key/value list.
  - Both views end with a collapsible RAW JSON `<details>` section holding
    the full source record.
  - All content is rendered via `textContent` (no innerHTML with data), so
    snapshot strings cannot inject markup.
  - Close behaviors: ✕ button, Esc, outside click, and re-click of the same
    panel toggles closed (implemented via a short-lived "dismissed" marker,
    since the outside-click pointerdown fires before the panel's pointerup).
    One popup at a time by construction (single element, content replaced).
- `src/main.ts` — `handleSelection` now calls `showDetailPopup(selection)`
  instead of logging.

## Verification

Headless-browser test (playwright-core vs `npm run preview`, live snapshot):

- click node panel → popup opens with real data (`agdnsmasq`, INTENT section
  with lifecycle/node_type, 2 diffs incl. desired vs actual, RAW JSON) ✓
- Esc closes ✓ / outside click closes ✓ / same-panel re-click toggles ✓
- workspaces view popup shows `pj-clusterintent workspace @ agstudio, IDLE` ✓
- screenshot reviewed — layout and severity chips render as intended.

Container rebuilt per README_DEV rule: `docker compose up --build -d web`
succeeded, container Up, `curl -I http://localhost:8090/` → 200 (nginx).
Note: the live snapshot currently in `public/cluster/` is baked into this
local image, as README_DEV documents.

## Notes

- The popup keys nodes by target id/slug; workspaces by slug.
- Step 3 will add the "Ask agent" button into this popup.
