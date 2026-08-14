# Phase 4 Plan — Work execution (`run-` trigger topics)

Realizes `braindump.md`. Decisions already made by the developer:

- Only newly generated projects get the `[AUTO]` description marker and `AUTO`
  work labels; existing projects are left untouched.
- Selection condition is state **group** `unstarted` (new projects get Plane's
  default vocabulary, where the unstarted state is named `Todo`, not `Ready` —
  verified live on an init-created project).
- `run-` topics are trigger-only: the chatlog is never read; a topic fires
  whenever the last poster is not the autolab bot.
- `#general` becomes a listen target for all agents; `mission-` topics keep
  working only in `pj-*` channels and are silently ignored elsewhere.
- Backward compatibility is NOT required. Destructive phase in a private
  experimental environment; rewrite freely, delete dead code, adjust tests to
  the new contract.

Constraints are deliberately minimal: keep secrets out of tracked files and
logs, and deploy pyagag changes through GitHub (the agstudio gitea mirror goes
stale — never use it as a dependency source). Everything else is implementer
discretion.

## Step 1 — pyagag: multi-prefix sweep

`sweep_serve` / `sweep_topics` take a single `topic_filter: str` today. Widen
it to `str | tuple[str, ...]` — `str.startswith` already accepts a tuple, so
the change is mostly the type and a test. Push to GitHub `main`, then refresh
the git dependency in `agautolab` (`pyproject.toml` tracks the branch; a
`uv lock --upgrade-package pyagag` or equivalent refresh is enough).

## Step 2 — agautolab: project bootstrap additions (`project_init.py`)

1. **devlog repo**: in `init_project`, add `ensure_gitea_repo(gitea,
   f"{project}-devlog")` and `ensure_clone(..., project_root / "devlog")`,
   mirroring `-direction`. Nothing writes to it yet — this phase only creates it.
2. **`.gitignore` seeding**: after each clone (`main`, `direction`, `devlog`),
   ensure the repo's `.gitignore` contains a `.local/` line; create or append
   only when missing, then commit and push. Reuse the askpass environment from
   `ensure_clone` for the push. Keep it idempotent — a second `init_project`
   run must not create a second commit. Side benefit: the first commit
   establishes `main` in otherwise-empty repos.
3. **`[AUTO]` marker**: `ensure_plane_project` currently creates projects with
   `description: ""`. Write a description that both carries the marker and
   records the local slug, e.g. `[AUTO] autolab project: <project>`. The slug
   part matters: Plane stores a prettified display name
   (`plane_project_name`), and `next_work` must map the Plane project back to
   the local workspace directory `.local/projects/<slug>/main`. Parsing the
   slug out of the description is the simple, robust path (fallback:
   `_normalized_name` matching against `PROJECTS_ROOT` directory names).

## Step 3 — agautolab: Plane label, comment, and `next_work` (`mission.py`)

New Plane API code (endpoints confirmed present on this Plane CE v1.4.1 via
read-only probes; write payload shapes still need one live confirmation):

- **Labels**: `GET/POST .../projects/<id>/labels/` works. Ensure a label named
  `AUTO` exists per project (create lazily, cache the id), and attach it to
  every issue autolab creates — simplest is inside `ensure_issue`, which covers
  both the mission Work and registered Sub-Works. Attachment is expected to be
  `"labels": [<label_id>, ...]` on the issue POST/PATCH; verify on first write.
- **Comments**: `GET .../issues/<id>/comments/` works; `POST` with
  `comment_html` (escape plain text the way `description_html()` does).

**`next_work()`** — returns `(project_slug, work_name, description,
project_id, issue_id)` or `None`:

1. List workspace projects; keep those whose description starts with `[AUTO]`
   (case-insensitive). Recover the slug as decided in Step 2.
2. Per project: `list_issues` + `state_groups` (both exist). Keep issues that
   carry the `AUTO` label, whose state group is `unstarted`, and that have no
   sub-work (no other issue's `parent` points at them — literal reading;
   excluding only non-cancelled children is also acceptable, implementer's
   choice, the rationale is just "don't double-execute a parent").
3. Order by `created_at` ascending, then by the Sub-Work serial number — the
   trailing `#<N>` of the external id (`<channel>/<topic>@<rev>#<N>`); issues
   without a parseable `#<N>` sort last within the same timestamp.
4. Return the first match; description as plain text via `html_to_text`.

## Step 4 — agautolab: `run-` topic handling (`zulip_listener.py`)

**Subscription**: extend `subscribe_project_channels` to reconcile `#general`
the same way it does `pj-*` channels (every active user, bots included). This
is what makes `#general` visible to the sweep — Zulip delivers nothing for
unsubscribed channels.

**Dispatch**: switch `main()` to
`sweep_serve(..., topic_filter=(MISSION_TOPIC_PREFIX, RUN_TOPIC_PREFIX))` with
`RUN_TOPIC_PREFIX = "run-"`. In the handler: `run-` topics go to the new
`handle_run` regardless of channel; `mission-` topics proceed only when the
channel starts with `pj-` and are silently ignored otherwise (today
`project_from_channel` raises, which would post an error into `#general`).

**`handle_run(client, channel, topic)`** — after the usual ack, in order:

1. `next_work()`; on `None` post `no work` and stop.
2. Dirty check: the chosen project's `main` workspace must have no
   `.local/work/` (or an empty one). Otherwise post `work dirty` and stop —
   manual cleanup is the accepted recovery for now.
3. Write `.local/work/work.md`: title + description via `compose_document`.
4. Run the coding agent in the `main` workspace:
   `run_role("coding", guide("run_coding", "guide_run_coding.md"),
   cwd=<main>, timeout=..., record=next_record_path(RECORDS_ROOT / "run"))`.
   The `coding` role already has `WORKING_ALLOWED_TOOLS` and no workspace pin,
   so the caller's cwd wins. A fresh timeout constant is fine (task splitting
   uses 600 s; real work runs longer — start around 1200 s and adjust).
5. Afterwards: if `.local/work/report.md` exists, post its content as a Plane
   comment on the work; if `.local/work/success.flag` exists, transition the
   work to group `completed` (`update_issue` + `state_id_for_group` exist).
   If there is no report, the outcome is just `no report`.
6. Post the outcome to the topic — every exit path after the ack posts
   something, same discipline as `handle_topic`. Include what happened:
   work label (`issue_label`), commented yes/no, Done yes/no.
7. Delete `.local/work/` — also on failure paths reached after it was created.
   Whatever survives an interpreter crash stays for the dirty check to catch;
   "think about it later" per the braindump.

Tests: extend the agautolab suite for `next_work` filtering/ordering (pure
logic over fixture rows — no live Plane needed) and the dispatch routing;
rewrite whatever old tests the new contract breaks.

## Step 5 — Verification (E2E)

Use the `sonnet` profile for `coding` first (`.local/agents.local.toml` may
still pin `local`); `AUTOLAB_ZULIP_LOG_ONLY=1` is the cheap way to watch sweep
decisions without paying for runs.

1. **Regular flow**: create a fresh `pj-*` channel, post a `mission-*` topic,
   approve a mission with a couple of tasks. Confirm: three gitea repos
   including `<project>-devlog`, `.gitignore` with `.local/` in all three
   clones, `[AUTO] autolab project: <slug>` description, `AUTO` label on the
   Work and Sub-Works, Sub-Works in `Todo`.
2. **Run trigger**: create topic `run-1` in `#general`, post `run` as the
   developer. Confirm: ack, one Sub-Work executed in the project's `main`
   workspace, report comment on the work in Plane, work `Done` on success,
   outcome posted, `.local/work/` gone. Post `run` again — the next Sub-Work
   by creation order runs.
3. **Edge cases**: `run` with no eligible work → `no work`; pre-seeded stale
   `.local/work/` → `work dirty`; a failing work (no `success.flag`) stays
   `unstarted` and gets a comment (or `no report`) — note it will be selected
   again on the next trigger, which is accepted since triggers are manual.
4. **Isolation**: a `mission-*` topic in `#general` is ignored; `run-` still
   fires. (`create-` topics in `#general` will now reach agforge and cost a
   run each — don't create any there while testing.)

## Step 6 — Deploy

pyagag via GitHub (done in Step 1). agautolab: commit → push to GitHub and to
the agstudio gitea (localrule: push every commit, then reflect onto consumers)
→ `ansible-playbook -i inventories/generated/production.yml
playbooks/agent/setup_autolab_node.yml --limit agautolab1` from
`pj-clusterintent/ansible_agdev`. Restart the local listener:
`launchctl kickstart -k gui/$(id -u)/com.agdev.agautolab-zulip`.

## Useful facts and pitfalls found during planning

- Init-created Plane projects carry the default state set
  `Backlog / Todo / In Progress / Done / Cancelled` (groups
  `backlog/unstarted/started/completed/cancelled`). `Ready` exists only on the
  hand-made ProjectA. Never match state names; `state_groups` /
  `state_id_for_group` already do it right.
- Live-probed on this Plane: `/labels/` and `/issues/<id>/comments/` both
  exist and paginate like `/issues/`; issues expose `labels: []` (list of
  label ids) and `created_at`.
- `list_issues` already returns `parent`, `state`, `external_id`,
  `description_html` for every issue — `next_work` needs no per-issue reads.
  `description_stripped` is unreliable on this Plane (observed `None`);
  `html_to_text` is the working inverse.
- Plane project display names are prettified; the local workspace path needs
  the original slug — hence the slug-in-description convention (Step 2.3).
- The run executes in the shared clone `.local/projects/<slug>/main` — the
  same directory every later run reuses. Uncommitted leftovers are continuity
  by design here, but nothing in this phase commits or pushes the work
  results; that is a known gap for a later phase, not this one. Note
  `WORKING_ALLOWED_TOOLS` contains no `git`, so the coding agent could not
  push even if the guide asked — fine for now.
- The listener is single-threaded and serial: a long work run delays further
  sweeps but loses nothing (events queue up; the post-run sweep catches up).
  A `run-` post arriving during a run simply re-fires after completion —
  self-limiting, since the bot's outcome post makes it the last poster.
- Crash between ack and outcome post leaves the topic dormant until a human
  posts again (same accepted behavior as mission topics), and may leave
  `.local/work/` dirty — recovery is manual deletion, reported by the
  `work dirty` post.
- Every run keeps writing an `ag.agent-run.v1` record (`write_run_record`) —
  Agent ≠ Model policy; `RECORDS_ROOT / "run"` mirrors the existing
  `front`/`coding` layout.
- `agautolab1` deploys from the agstudio gitea; expect the ansible run to pick
  up any not-yet-deployed earlier-phase changes too.
