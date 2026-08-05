# Step 3 Report — AI-driven view switching

Status: complete (compile-checked; extractor logic unit-verified; live
end-to-end chat exercised in Step 4 if ollama is reachable)

## What was done

- `assistant/server.mjs`: extended `ROLE_PROMPT` with the action protocol —
  two named views (`nodes`, `workspaces`) and the exact reply syntax
  `{"action":"switch_view","view":"nodes"|"workspaces"}` on its own line plus
  one short confirming sentence, with instructions not to emit or mention the
  JSON otherwise. The prompt was moved above the ollama configuration so the
  engine-agnostic seam is explicit: the protocol definition knows nothing
  about the engine; only code below it does. No ollama tool calling, per the
  plan (glm-4.7-flash tool support uncertain).
- `src/chatPanel.ts`: added `extractAssistantActions(reply)` which finds
  action JSON objects anywhere in the reply (regex for a flat
  `{..."action":"..."...}` object, fenced or inline), parses them forgivingly
  (unparsable text stays visible), strips matched objects and any emptied
  code fences from the displayed text, and returns `{text, actions}`.
  `initChatPanel` now takes an optional `onAction` callback (same injection
  pattern as `getContext`); each extracted action is dispatched to it. If
  stripping leaves the bubble empty, it shows `OK.` instead of nothing. The
  raw reply (JSON included) stays in the conversation history sent back to
  the model, so the model sees its own protocol usage in later turns.
- `src/main.ts`: injects the action callback — `switch_view` with a string
  `view` goes through Step 1's `switchView()` seam; unknown actions are
  ignored silently. The chat context now leads with
  `Currently visible view: <nodes|workspaces>` so the model knows what is on
  screen (the plan's optional suggestion).
- `switchView()` itself already validates the view key, so a hallucinated
  view name is a silent no-op.

## Verification

- `npm run build` (tsc + vite) and `node --check assistant/server.mjs` pass.
- The extraction logic was exercised standalone against five cases: plain
  sentence + JSON line, JSON inside a ```json fence (fence residue removed),
  plain Q&A with no action, JSON-only reply (falls back to `OK.`), and a
  malformed action object (left visible, no action fired). All pass.
- Live acceptance ("show me the workspaces" switches the view; Japanese
  equivalent; clean Q&A) depends on a running ollama and is part of the
  Step 4 manual pass.

## Notes / deviations

- The displayed-text fallback `OK.` is a small addition beyond the plan so a
  JSON-only reply doesn't render an empty bubble.
- Actions execute before the bubble text is finalized; order is irrelevant
  today but keeps future actions (e.g. focus/highlight) visually in sync with
  their confirmation text.
