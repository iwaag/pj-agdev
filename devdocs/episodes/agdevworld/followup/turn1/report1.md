# Step 1 report — gateway project/profile read side

## Outcome

The agstudio autolab gateway now exposes `GET /projects` as an
`autolab.projects.v1` envelope. It lists the available profiles and every
directory-backed project with the effective `coding` and `director` profile,
including whether each value came from project settings or the shared default.
A malformed project settings file produces an error on that project row rather
than failing the listing.

Job summaries and job details now retain the optional top-level `project` field
from `job.yaml`, including in the gateway's dependency-free scalar-parser
fallback.

## Verification

- `uv run pytest -q`: 95 passed.
- Live `GET http://localhost:8791/projects`: returned profiles `local`,
  `sonnet`, and `stub`, plus `project-agent-setting-smoke`, `scifi`, and
  `yokai` with effective role selections.
- Live `GET http://localhost:8791/jobs`: project-linked rows included
  `project: project-agent-setting-smoke`.
- `nctl status --json` before the service work reported `ok: true`; Nautobot,
  intent-catalog, and its worker were healthy.

## Operational note

The gateway was stopped at the start of this step. The documented bare
`python3 agent/gateway.py` command could not import the declared shared `agag`
dependency in this shell, so the live instance was started through the project
environment with `uv run python agent/gateway.py`. The durable documentation
correction is scheduled for Step 4.

After this finding, the human authorized replacing sibling-source `pyagag`
dependencies with GitHub sources. Both agautolab and agforge now declare the
`pyagag` `main` branch as their uv source; each lockfile pins the resolved
commit. This keeps normal installs reproducible without requiring a particular
sibling checkout layout while retaining an explicit upgrade operation.
