# Step 5 — Thin the gateway window and remove `/guide`

Status: **done**

## Result

`POST /window` now passes the request text unchanged to the real `front` role.
The gateway no longer prepends a capability card, empty job-state snapshot, or
instructions for the deleted development loop.

The following obsolete pieces were removed together:

- `WINDOW_PROMPT`;
- `MISSION_BLOCK` and `apply_mission_block()`;
- the empty `start_mission()` and `window_state()` seams;
- `/guide`, `read_guide()`, and `agent/GUIDE.md`.

A successful front answer is persisted and returned verbatim. The single
entrance, non-blocking exclusivity lock, 400/409/502 mapping, and numbered
window run records remain. `/status`, `/jobs`, and `/projects` remain in the
route table for the agdevworld proxy; their deleted-loop read side is still
explicitly marked as stub data.

`README.md` now describes the rebuilt real window and retained empty read
surface instead of claiming that all role runs are canned.

## Verification

- `uv run pytest -q` — 5 passed.
- An isolated HTTP server test verified `/healthz`, `/status`, and `/jobs`,
  confirmed `/guide` returns 404, and exercised a successful `/window` reply.
- A direct window test proved the exact input text reaches `run_role` and the
  exact reply is persisted in the numbered JSON record.
- `python3 -m py_compile agent/gateway.py`: passed.
- Repository search found no surviving production references to the removed
  guide, prompt, mission block, or state helpers.
- `git diff --check`: passed.

Implementation commit: `1d3fc96` (`Make the gateway window a thin front
entrance`).
