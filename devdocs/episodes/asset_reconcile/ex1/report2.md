# asset_reconcile ex1 — Step 2 report

Date: 2026-08-08. Outcome: **complete**.

The reviewed operator mission is saved as [mission.md](mission.md). It keeps
the browser-gallery client goal nearly verbatim for the coding agent while
placing orchestration duties on the mediator.

## Mission contract

The mission explicitly requires the mediator to:

- clone the direction repository separately from the empty coding target,
  create a plan-phase job with no pre-authored gates, and use `push: true`;
- stop at exit 40 and review `PLAN.md`, `proposed_gates.yaml`, and exactly
  three technical-only PNG manifest entries;
- reject and re-plan if requirement traceability, non-trivial asset/switching
  gates, or context separation is missing;
- reconcile all assets during the same `awaiting_approval` window before
  approving, with at most two agforge attempts per image and no byte
  conversion;
- commit/push director envelopes and request IDs to the direction repository,
  but leave delivered target bytes uncommitted for the coding agent's first
  implement iteration;
- approve, converge, independently audit the committed revision, install only
  the verified product into the gateway serve directory, and finish through
  the standard NOTES `STATUS` contract.

The mission also names the exact endpoints and evidence required for later
operator verification, including the served and direction revisions.

## Reconcile tooling

The already-tested one-shot director and bounded mechanical reconcile scripts
were added to `gallery-direction` at Gitea revision `b914c3e`. This makes the
node-side path self-contained without deploying a new agautolab revision.
`candidates/` remains ignored, while `reviews/` is tracked so successful and
failed evidence survives the mission.

Before pushing, the source test suite passed 9/9. It covers direction working
directory isolation, technical-field preservation, explicit candidate review,
PNG decoding and dimensions, response-schema handling, selected-status-only
mutation, and readable envelope persistence. The copied scripts also passed
`py_compile`.

No agautolab code change was needed. The mediator charter already supports an
optional external asset pipeline, plan rejection/approval, Gitea operations,
and generous explicit tools without `skip_permissions`.
