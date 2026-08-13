# Step 4 — Reconnect `run_role` to `run_harness`

Status: **done**

## Result

`run_role()` once again launches the resolved harness through
`agag.harness.run_harness()` instead of returning the stub reply. It passes:

- the prompt and timeout;
- the role's explicit allowed-tools grant;
- the matching OpenCode config when the selected harness is OpenCode;
- the requested transcript path;
- the resolved role/profile/model and its local provider environment.

Availability checking is restored by using the resolver's normal default, so
a selected harness with no executable fails before a run is accepted.

The `front` and `mediator` roles are pinned to their dedicated
`agent/front/` and `agent/mediator/` working directories inside `run_role`.
Other roles retain their caller-supplied cwd, including a director's project
direction checkout.

Run output, normalized metadata, and exit status now come directly from the
real harness result. Optional canonical run-record writing remains supported;
the returned in-memory record also retains the project association.

## Verification

- `uv run pytest -q` — 3 passed.
- Tests prove fixed role cwd selection, allowed-tools and OpenCode config
  forwarding, transcript forwarding, mediator/Claude behavior, and that the
  resolver is no longer called with `check_available=False`.
- Live role resolution selected `opencode local` for `front` and confirmed the
  configured binary is available.
- `git diff --check`: passed.

Implementation commit: `23ed274` (`Reconnect role runs to the shared
harness`). A paid/model-backed prompt was deliberately deferred to the gateway
and end-to-end steps, where the complete prompt and HTTP contract are tested.
