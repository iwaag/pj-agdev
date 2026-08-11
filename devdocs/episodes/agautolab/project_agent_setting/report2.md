# Step 2 report — coding jobs and run evidence

`Job` now parses the optional non-empty `project:` field from `job.yaml`.
Coding resolution uses this precedence:

1. explicit `job.yaml` `profile` override;
2. `.local/projects/<project>/agents.toml` `[roles].coding`;
3. the shared `agents.toml` coding-role default.

There is no fallback after a selected value fails. Project-settings errors and
shared agent-contract errors put the job in the visible `error` state.

Every iteration's existing `evidence/iter-NNNN/adapter_result.json` now records
`project` (nullable for unlinked jobs) and the resolved `profile`. Tests prove
both project selection and the explicit job override precedence.
