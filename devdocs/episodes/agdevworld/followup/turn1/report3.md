# Step 3 report — agdevworld display and conversational change

## Outcome

The agdevworld autolab client now reads `GET /api/autolab/<node>/projects`
with typed project, role-selection, profile-source, and available-profile
records. Job rows/details also carry their optional project association.

The autolab view separates read-only project cards and job cards into
`projects` and `jobs` tabs on the selected node. Each project card shows its
effective coding and director profiles; malformed rows use a visible
project-error state. Project cards open a read-only detail popup, and the
footer explicitly directs profile changes to conversation. Job cards keep
their existing drill-down behavior and show their project association when
present.

Both copies of the prime agent capability description now include the projects
route and the conversational change path: inspect the selection, ask the
node's window to edit it, and confirm with a fresh read. No direct write route
was added, and the evidence-path guard was unchanged.

## Verification

- `npm test`: 28 passed.
- `npm run build`: TypeScript and Vite production build passed. The existing
  non-failing Phaser bundle-size advisory remains.
- Rebuilt the local web and assistant containers.
- The assistant passthrough returned the live `autolab.projects.v1` envelope
  for agstudio.
- A Playwright pass at 1280x800 opened the production-style web service,
  switched to autolab, and captured separate views showing three project cards
  with their coding/director profiles and 25 job cards.
- One ordinary chat sentence to the prime agent changed `yokai` coding from
  `sonnet` to `local`. The prime agent delegated the write to agstudio's
  `/window` and reported its confirmation read.
- The ignored project file, assistant passthrough `GET /projects`, and the
  refreshed rendered view all showed `coding = local`; director remained
  `local`.

No project settings file was edited by the Omni Agent.
