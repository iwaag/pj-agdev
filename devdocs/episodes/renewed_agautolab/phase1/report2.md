# Step 2 — Create the uv workspace and role workspaces

Status: **done**

## Result

`agautolab` is now the root of one uv workspace with `agent/front` and
`agent/mediator` as members. Each role directory has a minimal non-package
`pyproject.toml`; role-facing scripts can therefore live directly in that
directory and run as `uv run <script>.py` from the fixed role cwd.

The shared `uv.lock` now records all three workspace members. Dependency
resolution remains owned by the root rather than creating a lock or virtual
environment per role.

## Verification

- `uv lock`: resolved the root and both workspace members successfully.
- `uv sync --all-packages`: completed against the shared lock.
- `cd agent/front && uv run python -c ...`: ran with cwd `front`.
- `cd agent/mediator && uv run python -c ...`: ran with cwd `mediator`.
- `git diff --check`: passed.

Implementation commit: `1c5ce75` (`Create front and mediator uv workspaces`).

## Notes

The workspaces intentionally have no dependencies yet. Step 7's
`new_mission.py` can declare only what it actually needs while retaining the
root lock and the exact command promised to the front agent.
