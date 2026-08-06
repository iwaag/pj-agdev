# Report — Step 4: record deferred work in devdocs/todo_done.md

Status: done.

## What changed

- `devdocs/todo_done.md`: added two TODO lines for the two scope-outs
  plan.md flagged:
  - Resolving the SwarmUI access point from pj-clusterintent instead of a
    hand-set `.local/.env` value.
  - Folding the agforge bucket/policy/user creation into the declarative
    `minio-init` in `pj-clusterintent/devenv/nautobot/docker-compose.yml`,
    replacing Step 3's manual `mc` steps.
  Both dated 2026-08-06 and note they were scoped out of this episode's
  plan.md, matching the existing entry's style (dated, with a "recorded
  from" pointer).

## Verification

- Reread plan.md's Step 4 list and confirmed both lines were transcribed
  faithfully (same content, referencing the episode's own
  `README_DEV.md` MinIO-fallback instruction added in Step 3 rather than
  a generic "Step 3" pointer, since todo_done.md outlives this episode's
  numbering).

## Notes for next steps

- Step 5 is the final verification + `report.md` (this episode uses
  `report5.md` per the numbering the user asked for) against plan.md's
  Goal/acceptance-criteria section.
