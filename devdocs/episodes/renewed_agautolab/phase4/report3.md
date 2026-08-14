# Phase 4 Step 3 Report — labels, comments, and `next_work`

All in `mission.py`. Nothing here talks to Zulip; Step 4 is the caller.

## Labels

- `labels_by_name(config, project_id)` → lowercased name → id, from
  `GET .../projects/<id>/labels/?per_page=100`.
- `ensure_label(config, project_id, name="AUTO")` → the label id, creating the
  label on first use, with a process-wide `_LABEL_CACHE` keyed
  `(project_id, name.lower())`. A create that loses a race (400/409/422)
  re-reads the list instead of failing.
- `ensure_issue` now sends `"labels": [ensure_label(...)]` on the create body,
  so both the mission Work and every registered Sub-Work carry `AUTO`. Only
  the create path — an existing issue found by external key is returned
  untouched, so hand-made issues are never relabeled.

## Comments

`add_comment(config, project_id, issue_id, text)` posts to
`.../issues/<id>/comments/` with `comment_html`, escaped by the same
`description_html()` used for descriptions.

## `next_work()`

Returns `(project_slug, work_name, description, project_id, issue_id)` or
`None`. `list_plane_projects` was factored out of `find_plane_project` (which
now uses it) so the scan reads the project list once.

Per `[AUTO]` project — recognized and un-prettified by
`project_init.project_slug` — it reads `labels_by_name`, `list_issues` and
`state_groups`, then `eligible_works(issues, groups, label_id)` applies the
four conditions:

1. the issue's `labels` contain the project's `AUTO` label id,
2. its state's **group** is `unstarted` (never a state name),
3. it is nobody's `parent` — literal reading of "has no sub-work", so a parent
   with only cancelled children is still skipped; a parent is executed through
   its children and running it too would do the work twice,
4. (projects with no `AUTO` label at all are skipped outright.)

Order is `created_at` ascending, then the `#<N>` tail of the external id
(`sub_work_serial`, `1 << 30` when absent so unnumbered issues sort last
within one timestamp), then the id as a deterministic tie-break. Candidates
from all projects go into one list and the global minimum wins. Description
comes back as plain text via `html_to_text` — `description_stripped` is
unreliable on this Plane.

No per-issue reads: `list_issues` rows already carry `labels`, `parent`,
`state`, `created_at`, `external_id`, `description_html`.

## Tests

agautolab suite: **70 passed** (10 new). `FakePlane` grew a `/labels/` and a
`/comments/` route, and the `plane` fixture clears `_LABEL_CACHE`.

- label creation is idempotent and cached; an existing `auto` label is reused
  case-insensitively; a created Work carries the label id.
- `add_comment` escaping.
- `sub_work_serial` on `@2#3`, on a Work key, and on `None`.
- `eligible_works`: parent/started/unlabeled rows filtered out; ordering by
  creation then serial with the unnumbered row last.
- `next_work`: oldest across two `[AUTO]` projects (a hand-made project is
  ignored), `None` when nothing is eligible, and a project with no `AUTO`
  label skipped.

Live write shapes (`labels` on the issue POST, `comment_html`) are exercised
against the fake here; Step 5 confirms them against the real Plane.
