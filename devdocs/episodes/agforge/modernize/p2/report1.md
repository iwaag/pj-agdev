# Step 1 — FORGEAUTO label at create time

## What was built

All in `agforge/src/agforge/plane.py`, reversing p1's "no labels, no
`[AUTO]`" guards on purpose:

- `ensure_label(config, project_id, name="FORGEAUTO")` — ported from
  `agautolab/src/agautolab/mission.py` (`ensure_label` + `_LABEL_CACHE`),
  verbatim in behavior: per-process `(project, name)` cache, create-on-first-
  use, race fallback to a re-listing, case-insensitive reuse.
- `register_plan` now passes `labels=[ensure_label(config, project_id)]` to
  `agag.plane.ensure_issue` at creation. Updates (`update_issue`) still touch
  only name/description, so a re-served topic keeps its label.
- `_fallback` gained the `[AUTO]` marker two ways: new projects are created
  with `FALLBACK_DESCRIPTION = "[AUTO] agforge request records: FreeForge"`,
  and an **existing** unmarked project is reconciled in place — the plan
  offered "patch by hand or reconcile, your call"; reconcile was chosen so the
  fix is code, not a one-time manual action. The PATCH uses a small local
  `_update_project` on `agag.plane`'s private HTTP helpers, since the shared
  client has no project update; a candidate to lift into pyagag in Step 6.

Module docstring rewritten: the file's opinion is now "two markers written on
purpose" instead of "two absences".

## Tests

`tests/test_plane.py`: the two p1 guard tests are inverted
(`test_a_registered_work_carries_the_forgeauto_label`,
`test_a_created_project_carries_the_auto_marker`), plus new coverage for the
description reconcile (patched when unmarked, untouched when marked) and the
label cache (create-once, case-insensitive reuse). The fake Plane grew
`/labels/` GET/POST. `wire()` clears `_LABEL_CACHE` so tests cannot leak
label ids into each other.

```
103 passed in 4.18s
```

## Live verification

Against the running Plane CE (no paid agent run needed for this step):

- `resolve_project(config, "FreeForge")` reconciled the live project's
  description to `[AUTO] agforge request records: FreeForge` and
  `ensure_label` created the `FORGEAUTO` label
  (`labels_by_name` → `{'forgeauto': '7259…'}`).
- The plan's manual check: agautolab's `next_work` now *scans* FreeForge
  (marker present, slug `freeforge`) but skips it — the project has no `AUTO`
  label — and returned `None` overall. FreeForge stays invisible to autolab.

## Deviations from the plan

- The plan's verify item "a `create-` round trip in `#FreeForge` produces a
  Work carrying `FORGEAUTO`" costs a paid front+generator run and is repeated
  verbatim as Step 5's first end-to-end item. Step 1 instead verified the
  Plane side directly (reconcile + label live, label-at-create pinned by unit
  test); the paid round trip is deferred to Step 5.
- Works created before this step carry no label; per the plan they are left
  alone (backfill by hand only if wanted).
