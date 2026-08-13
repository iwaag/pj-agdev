# Phase 3 Step 3 Report — response handling (new_mission.md and flags)

Done. agautolab commit `67cedc0` (GitHub `main`).

## The response path (`handle_front_response`, after the front run)

Order per the plan: `new_mission.md` → `start.flag` → `cancel.flag`; every
action taken becomes a section of the final topic post.

**`new_mission.md`:**
1. `mission.upsert_work()` — if a Work exists, the new `update_issue()`
   (`PATCH .../issues/<id>/`, name + description_html) updates it; otherwise
   `ensure_issue` creates it. PATCH was verified live against Plane CE
   v1.4.1 (probe issue in the scratch `Spike` project: name, description,
   and state PATches all return 200 and stick).
2. `mission.cancel_sub_works()` — every non-cancelled Sub-Work is PATCHed to
   the `cancelled`-group state (`state_id_for_group`, resolved by group not
   name, mirroring `starting_state_id`). Nothing is ever deleted.
3. `.../topics/<channel>/<topic>/coding/` is created, `new_mission.md`
   copied in, and `run_role("coding", <verbatim guide_task_split.md>,
   cwd=<coding dir>)` runs with its own `ag.agent-run.v1` record under
   `.local/agent/coding/`.
4. Every `task[N].md` in `coding/` is registered as a Sub-Work keyed
   `<channel>/<topic>@<rev>#<N>`. `<rev>` is a counter persisted as the
   `generation` file in the topic directory (chosen over `updated_at`:
   deterministic, human-readable, survives restarts).

**`start.flag`:** `transition_work(…, "started")` → In Progress.

**`cancel.flag`:** `cancel_sub_works` + `transition_work(…, "cancelled")`,
then the topic is resolved — *after* the final reply is posted, so the whole
conversation moves under the `✔` name and the sweep goes quiet.

## Implementer decisions worth recording

- **Command files are consumed** (unlinked) once acted on. The workspace is
  stable and reused, so a leftover `new_mission.md`/flag would replay on
  every later run; the mission's canonical text lives in Plane and returns
  as `mission.md` on the next read-back. Chatlogs and the generation counter
  stay — those are the continuity the plan wants kept.
- **Stale `task[N].md` in `coding/` are cleared before the split run**, so
  what gets registered afterwards is exactly the current generation's split,
  not a mix with an earlier one.
- `register_dump()`'s "ignored non-task file" reporting is gone: `coding/`
  legitimately contains `new_mission.md`, so non-task files are simply not
  tasks.

## Deleted (old dump contract)

`mission.register_dump`, `latest_dump_directory`, `resolve_dump_directory`,
`topic_key`, `current_project` (and the `AUTOLAB_PROJECT` override that
existed for it), the `tasks/<N>.md` file pattern, and
`agent/front/new_mission.py` (the front no longer runs a registration
script; the listener does the registration itself).

## Guide contract fixes

- `mission_front/guide_mission_topic.md`: the `new_misson.md` typo the plan
  flagged was already fixed in an earlier commit (`ca1f963`); verified no
  `misson` remains anywhere.
- `mission_coding/guide_task_split.md`: rewritten — "create one file per
  task named `task[N].md`" (`task1.md`, `task2.md`, `task3.md`, …), states
  that the mission is in `new_mission.md` in the working directory, and the
  broken example list (`task.md, task2.md, task.md`) is gone. Guide, code
  (`TASK_FILE = task(\d+).md`), and tests now agree on exactly `task[N].md`
  starting at 1.

## Tests

`tests/test_mission.py` rewritten around a fuller `FakePlane` (external
lookup, list, states, POST, PATCH): upsert update/create paths,
cancel-only-live-children, quiet zero without a Work, transition by group,
missing-group error, generation-keyed registration, empty split, and the
step-2 read-back tests. `tests/test_zulip_listener.py` gained the response
path: full new_mission sequence (stale-split clearing, generation persist,
command consumption), counter increments, both flags, resolve-after-reply
ordering through `handle_topic`, and failure reporting.

`uv run pytest -q` in agautolab: **56 passed**.
