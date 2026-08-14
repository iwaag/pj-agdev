# Phase 4 Step 2 Report — project bootstrap additions

All three changes are in `project_init.py`; `init_project` now loops over the
three `(repo, workspace)` pairs instead of repeating itself:

```
main      <- <project>
direction <- <project>-direction
devlog    <- <project>-devlog          (new)
```

Each pair runs `ensure_gitea_repo` → `ensure_clone` → `ensure_gitignore`.

## devlog repo

Created and cloned exactly like `-direction`. Nothing writes to it in this
phase; the repository and the clone are all that exist.

## `.gitignore` seeding — `ensure_gitignore(config, workspace)`

Reads the clone's `.gitignore`, and when no line is exactly `.local/`, appends
it (creating the file when absent), then `git add` → `git commit` (identity
passed per-invocation with `-c user.name/-c user.email`, so no global git
config is touched) → `git push origin HEAD:main`. Returns whether it
committed; a second `init_project` finds the line and does nothing, so no
second commit appears. In an empty repository this first commit is what
establishes `main`.

Clone and these commands now share one helper `_git()`, which carries the
askpass environment (`GIT_ASKPASS`, `AUTOLAB_GITEA_TOKEN_VALUE`,
`GIT_TERMINAL_PROMPT=0`) that used to be inline in `ensure_clone`, and turns a
non-zero exit into a `ProjectInitError` with the captured stderr. The token
only ever reaches git through that environment — nothing is written to a
tracked file or logged.

## `[AUTO]` marker

`ensure_plane_project` creates with `description: auto_description(project)` —
`[AUTO] autolab project: <slug>`. Existing projects are untouched: the
description is only sent on the create path.

`project_slug(row)` is the inverse used by Step 3: `None` when the description
does not start with `[AUTO]` (case-insensitive), otherwise the text after the
`:`. When the description carries the marker alone (hand-edited, or an older
convention) it falls back to normalizing the prettified Plane name, which is
correct for every name `plane_project_name` produces.

## Tests

agautolab suite: **60 passed** (3 new).

- `test_init_project_runs_every_idempotent_step_in_order` rewritten for the new
  order and the devlog triple.
- `test_ensure_gitignore_seeds_commits_and_is_idempotent` — first call writes
  `.local/\n` and runs add/commit/push, second call runs no git command.
- `test_ensure_gitignore_appends_to_an_existing_file` — `dist/\n` becomes
  `dist/\n.local/\n`.
- `test_auto_description_carries_marker_and_slug` — round trip, lowercase
  `[auto]`, name fallback, and `None` for a hand-made project.
