# Report — Step 3: agent instruction for MinIO fallback

Status: done.

## What changed

- `agforge/README_DEV.md`: added a new "Agent instruction: no S3
  configured" section (placed before "Hard rules", per plan.md's suggested
  location — in `README_DEV.md` rather than a separate `AGENTS.md`, since
  this is the single agent-facing doc agforge already has).
  - Tells the agent: if `AGFORGE_S3_*` is unset and the prompt names no
    alternative storage, don't improvise — start `pj-clusterintent`
    devenv's MinIO instead.
  - Reproduces the three concrete steps from problem.md #3: `docker
    compose up`, `mc mb` + scoped policy `agforge-rw` + dedicated user
    `agforge` using devenv root creds, then record endpoint/keys in
    `agforge/.local/.env`.
  - Explicitly calls out that the `nctl` user's key cannot be reused
    (`nctl-outbox-rw` policy is scoped to `nctl-outbox` only) and that this
    dead end already cost time once, per plan.md's instruction to note it.

## Verification

- Re-read `problem.md` #3 and cross-checked the three steps and the
  `nctl` dead-end wording against what actually happened there — matches.
- Confirmed this doesn't touch code (no S3-unavailable code fallback is
  added, matching plan.md's premise: "the only handling for the
  unavailable case is the agent instruction in Step 3 — no code
  fallback").

## Notes for next steps

- No code changes in this step; `generate.py`'s existing behavior (exit
  with a clear "missing in .local/.env" message when `AGFORGE_S3_*` keys
  are absent) is what triggers an agent to consult this new instruction.
