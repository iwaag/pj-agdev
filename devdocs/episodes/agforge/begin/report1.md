# agforge begin — step 1 report: workspace scaffold

Status: done.

## What was done

Created the `agforge` workspace scaffold (agforge is a git submodule of
pj-agdev, repo `iwaag/agforge`, committed there as `8a1eb11`):

- `agforge/README_DEV.md` — agent entry point: what agforge is
  (asset-generation workspace, "Easier Next Time"), the target one-command
  pipeline shape, where local config lives, the `.local/.env` keys later
  steps will use, and the two hard rules (no secrets/images in git; never
  write to `nctl-outbox`).
- `agforge/.gitignore` — ignores `.local/`, `out/`, and common image
  extensions as a belt-and-braces guard against committing generated images.
- `agforge/.local/devenv.md` — local-only notes seeded with the actual MinIO
  endpoint/key location (from pj-clusterintent `nctl.toml [storage]`) and the
  presigned-URL hostname caveat. Git-ignored, not committed.
- `agforge/scripts/` — empty (with `.gitkeep`); pipeline scripts land here in
  steps 3–5.
- `agforge/.local/out/` — created as the local image output dir.

Also committed in pj-agdev alongside this report: the already-staged submodule
registrations (`.gitmodules`, `agdevworld`, `agforge` gitlinks) and the
`devdocs/overview.md` agforge section, since they are the preparation this
episode builds on.

## Done criterion

A fresh agent opening `agforge/` finds README_DEV.md first, which points to
`scripts/`, `.local/devenv.md`, `.local/.env`, and the episode docs. Verified
by inspection; nothing executable exists yet by design.

## Notes

- No surprises. MinIO connection details were already documented in
  pj-clusterintent, so step 2 can reuse them directly.
