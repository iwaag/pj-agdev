# Phase 4 plan — settling

Three steps, one `report.md` at the end. Nothing here is a port any more: the
system is Python, and this phase closes the three things phase 3 deliberately
left open plus the roadmap's own settling list.

## Prohibitions (unchanged)

- No credentials, no `.local/` content, no local absolute paths in committed
  files.
- Do not touch `ag.agent-config.v1`.
- No fallback anywhere.
- The UI must still work through `http://localhost:8090` at the end.

## Step 1 — the Plane naming defect (what the port proved wrong)

`p3/report5.md`: a project start whose name carries hyphens is rejected by
Plane 1.4.1 ("Project name cannot contain special characters"), and a
single-word name collapses to a one-letter identifier that collides with any
other single-word name — surfacing as a misleading 409 "name is already
taken". The card promises `<lowercase-hyphen name>`, so **humanize** rather
than narrow the card: keep the repo/channel name as the contract, and derive a
Plane-legal name and a distinct identifier from it. Prove against the live
Plane, then delete what the proof created.

## Step 2 — `README_DEV.md` and `GUIDE.md`

Rewrite the Commands / Files / Assistant sections of
`agdevworld/README_DEV.md` against the collapsed system: `uv run pytest` from
`assistant/` is the test entrance (`npm test` is gone; it only ever ran the
assistant tests), `npm run build` is the frontend's only check, and the file
list no longer names any `.mjs`. `GUIDE.md` is language-neutral and mostly
survives; touch only what step 1 changed.

## Step 3 — the pyagag question, the sweep, the report

Decide whether the MCP stdio server skeleton belongs in pyagag, and put the
reason in the report either way. Then `uv run pytest`, `npm run build`, and a
live pass through `:8090` (four views, chat, one passthrough) so the phase
does not end on documents alone.
