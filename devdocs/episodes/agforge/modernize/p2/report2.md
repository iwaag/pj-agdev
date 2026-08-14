# Step 2 — work selection

## What was built

`agforge/src/agforge/works.py`, ported locally from
`agautolab/src/agautolab/mission.py` (Step 6 may later share it through
pyagag):

- `eligible_works(issues, groups, label_id)` — verbatim autolab policy:
  carries the label, state group `unstarted`, not a parent of another issue;
  ordered by `created_at`, then the `#<N>` serial tiebreak
  (`sub_work_serial`). The parent check and serial are kept even though
  agforge creates no sub-works today — they cost nothing and survive future
  ones, as the plan allowed.
- `next_work() -> Work | None` — scans every `[AUTO]`-marked project
  (`project_marked`, the same marker vocabulary autolab's `project_slug`
  reads) and skips any project without a `FORGEAUTO` label. Returns a small
  frozen dataclass `Work` instead of autolab's 5-tuple, because agforge needs
  a different payload: `project_id`, `issue_id`, `name`, `description`
  (`html_to_text`), and the external key pair.
- `Work.origin() -> (channel, topic) | None` — the origin topic, read
  straight off `external_id`. `partition("/")` keeps a topic that itself
  contains `/` intact. A hand-made or foreign-source Work returns None.
- `report_work(project_id, issue_id, report, success)` — verbatim from
  autolab: comment when there is a report, move to the `completed` state
  group on success (without which the same Work is re-selected on every
  trigger).

## The one unknown, resolved

The plan's Step 2 question — do `list_issues` rows include
`external_id`/`external_source`? — was checked first, live: **yes**. All five
existing p1 Works came back with both fields populated
(e.g. `external_id='FreeForge/create-20260814-tools-transparency'`,
`external_source='agforge'`). The `braindump.md` comment fallback is not
needed and was not built.

## Verification

Unit (`tests/test_works.py`, fixture rows, no HTTP — autolab's test shape):
ordering, label filter, `unstarted` filter, parent exclusion, origin parsing
(including a `/` inside the topic and the no-origin cases), `[AUTO]`-marker
gating, the FORGEAUTO-vs-AUTO label separation, and `report_work`'s
comment/complete calls.

```
113 passed in 4.01s
```

Manual, against live Plane:

1. `register_plan("FreeForge", "create-20260815-p2step2-check", …)` created
   F2-6 carrying `FORGEAUTO` — the Step 1 code path, exercised live.
2. `next_work()` returned exactly that Work; the five unlabelled p1 Works
   were correctly invisible. `origin()` parsed to
   `('FreeForge', 'create-20260815-p2step2-check')`.
3. `report_work(…, success=True)` returned `('F2-6', True, True)`; a second
   `next_work()` then returned `None` — the completed-state guard against
   re-selection, proven live. The synthetic Work is left in FreeForge as Done
   so it cannot shadow Step 5's end-to-end Work.

## Deviations from the plan

- `next_work` returns a `Work` dataclass rather than autolab's tuple shape
  (the plan left decomposition to the implementer).
- The plan's manual verify said "returns the Step 1 Work"; Step 1
  deliberately created no Work, so a synthetic one was created through
  `register_plan` and completed again after the check.
