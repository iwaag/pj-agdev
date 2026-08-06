# Report — Step 3: assistant action + image bubble

## What was done

- Extended `ROLE_PROMPT` in `agdevworld/assistant/server.mjs` with a
  `generate_image` action following the `switch_view` pattern:
  `{"action":"generate_image","desire":"<short English image prompt>"}`.
  The prompt explicitly tells the model to keep the desire on one line with
  no double quotes, braces, or backslashes — pre-empting the known
  `extractAssistantActions` regex/JSON fragility with small local models.
- `chatPanel.ts`: new `generateImage(desire?)` on the panel handle. It adds
  a "generating image…" bubble immediately, POSTs `/api/forge/requests`,
  polls every 3 s (10 min deadline), then swaps the bubble for an `<img>`
  (max-width 100%) on `done` or an error bubble with `detail` on `failed`.
  The flow is fully detached from `send()` and never touches the send
  button, so chat stays usable while generating. Clicking the image opens it
  full-size in a new tab (cheaper than imitating detailPopup, same benefit).
  If the presigned URL fails to load in the browser, the `<img>` error event
  turns the bubble into a readable error instead of a broken-image icon.
- `main.ts`: dispatches `generate_image` from the action callback. A
  missing/empty `desire` (mangled JSON case) falls back to the latest user
  message, as the plan suggested.

## Checks

- `npm run build` (tsc + vite) passes; only the pre-existing Phaser
  bundle-size advisory.
- Against the rebuilt containers with the real model (glm-4.7-flash):
  - "draw a castle at sunset" → clean
    `{"action":"generate_image","desire":"a majestic castle at sunset…"}`
    plus one confirming sentence. ✅
  - A prompt containing double quotes ("…sign that says \"HELLO WORLD\"") →
    the model followed the no-quotes instruction and emitted
    `desire:"A friendly robot holding a sign that says HELLO WORLD"` —
    parseable, action survives extraction. ✅

Browser-level verification (bubble rendering, non-blocking chat, failure
bubble) is Step 4's job.

## What held / what surprised

- The `switch_view` action pattern extended cleanly; no changes to
  `extractAssistantActions` were needed.
- glm-4.7-flash obeyed the "no double quotes inside desire" instruction on
  the first try, so the latest-user-message fallback is belt-and-braces
  rather than the primary path.
