# Report 1 — delete the implementation

Plan step 1. `git rm` only; no file was edited in this step, so the tree does
not import or run at its end (step 2–4 restore that).

## Removed

| Path | Lines |
|---|---|
| `src/agautolab/adapters/` (4 files) | 264 |
| `src/agautolab/run_once.py` | 529 |
| `src/agautolab/loop.py`, `detach.py` | 85 |
| `src/agautolab/job.py`, `state.py`, `gates.py`, `review.py`, `status.py` | 535 |
| `src/agautolab/mission_witness.py` | 170 |
| `src/agautolab/cli.py` | 110 |
| `agent/drive.sh`, `agent/session.sh` | 95 |
| `agent/monitor/` (3 files) | 501 |
| `devenv/systemd/autolab@.service` | 24 |
| `tests/` (18 files) | 1782 |
| `AGENT_GUIDE.md`, `agent/README.md`, `agent/CHARTER.md`, `styles/README.md` | 384 |

21 tracked files remain, down from 55.

## Notes

- `devenv/systemd/` is now empty and gone with its only file; `devenv/gitea/`
  stays, as planned — it is local infrastructure, not loop implementation.
- Nothing outside `agautolab` was touched. The deployed `agautolab1` node and
  the agstudio Gitea mirror still carry the old implementation until the
  push/playbook decision in step 8.
- The tree is deliberately broken at this commit: `agent/gateway.py` still
  imports `agautolab.role_run` and `project_settings`, which survive, but
  `pyproject.toml` still declares the `autolab` script pointing at the deleted
  `cli.py`. Step 5 fixes the packaging; steps 2–4 fix the modules.
