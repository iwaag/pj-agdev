# Step 1 — Widen the `front` role's permissions

Status: **done**

## What the plan asked

`front` had to be able to run `uv run new_mission.py`. Two independent places
restricted it, one per harness:

- `agent/opencode-front.json` — the OpenCode permission file. `bash` denied
  everything except `agautolab.role_run director *`.
- `src/agautolab/role_run.py`, `ROLE_ALLOWED_TOOLS["front"]` — the Claude Code
  `--allowedTools` string, carrying the same restriction.

Fixing one only would have produced a node that works on the `local` profile
and not on `sonnet` (or the reverse), which is the expensive kind of breakage.

## What was changed

**`src/agautolab/role_run.py`** — the mediator grant was extracted into a
module-level `WORKING_ALLOWED_TOOLS` constant, and both `front` and `mediator`
now point at it. They are no longer two strings that happen to agree; a future
permission fix cannot land on only one of them.

**`agent/opencode-front.json`** — the `permission.bash` map was replaced with
the mediator map verbatim (`"*": "deny"` plus the same allow list), and
`"external_directory": "allow"` was added, matching the mediator file. The
provider block is untouched, so the front profile still resolves the same
local model.

`--dangerously-skip-permissions` was not introduced. Both harnesses stay under
an explicit allow list, which is what the plan asked for.

## Verification

```
front == mediator: True     # ROLE_ALLOWED_TOOLS, via `uv run python -c ...`
bash equal: True            # permission.bash of the two opencode-*.json files
```

`uv run` resolved and imported the package, so the edit is syntactically live,
not just textually present.

## Notes

- The deny list is now "deny by default, allow a named set" in both harnesses.
  It is not minimal in the sense of "nothing denied" — the OpenCode file keeps
  its `"*": "deny"` fallback — but nothing on the working path is denied. The
  plan's `deny は必要最小限でよい` is satisfied without opening the shell
  wholesale.
- `role_run.py`'s module docstring still describes the module as a stub that
  never launches. That is still true after this step; Step 4 rewrites it.
