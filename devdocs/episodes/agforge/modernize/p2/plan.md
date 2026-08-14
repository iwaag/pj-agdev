# agforge modernize p2 — implementation plan

Realize `braindump.md`. Give agforge a `runcreate-` topic that picks one Plane
Work labeled `FORGEAUTO`, executes it with the generator in a persistent
per-work workspace, and delivers the result (text reply or zip download URL)
back to the topic the request originally came from.

The model is agautolab's `run-` flow (`agautolab/src/agautolab/zulip_listener.py`
`handle_run`, `mission.py` `next_work`). This is a destructive phase; no
backward compatibility is required. p1's "no labels, no `[AUTO]`" decisions are
reversed on purpose.

## Decisions

- Work label is `FORGEAUTO`. The `FreeForge` project description gains the
  `[AUTO]` marker. Label filtering is what keeps autolab (`AUTO`) and agforge
  (`FORGEAUTO`) from picking up each other's Works
- The origin channel/topic is **not** recorded as a comment: p1 already stores
  it as the Work's `external_id = "<channel>/<topic>"`. Confirm early (Step 2)
  that the issue listing returns `external_id`; the comment idea from
  `braindump.md` is only the fallback
- Workspace is `agforge/.local/agentws/<work id>/generator/`. Persistent — no
  dirty check, no deletion, re-trigger overwrites in place
- A `runcreate-` topic is a button, not a conversation: never read the chatlog,
  any non-bot post fires exactly one execution (autolab's `run-` discipline;
  do not use `agag.topics.serve_topic`)
- Reuse the existing `generator` role and `sonnet` profile. The prompt is the
  existing `agent/guides/runcreate_generator/guide.md`, used as is
- On success the Work moves to the `completed` state group. Without this the
  same Work is re-selected on every trigger
- Work-selection code is ported **locally into agforge first** (same rhythm as
  p1 Step 3/5); sharing through pyagag is the optional last step, after
  everything works

## Prohibitions (these only)

- Do not commit or log credentials from `.local/`
- Do not point a deployment or dependency source at a local path or gitea
  (the standing rule in `devenv.md`)

Everything else — function decomposition, file layout, timeouts, test
granularity, what counts as "success" — is the implementer's call.

---

## Step 1 — FORGEAUTO label at create time

**Build**

- `ensure_label(config, project_id)` in `src/agforge/plane.py`, ported from
  `agautolab/src/agautolab/mission.py` (`ensure_label` + `_LABEL_CACHE`), with
  the name `FORGEAUTO`. `agag.plane` already has `labels_by_name` /
  `create_label`
- `register_plan` passes `labels=[...]` to `agag.plane.ensure_issue` (labels
  are opt-in there; today `plane.py` passes none — that was the p1 guard)
- The FreeForge fallback description gains `[AUTO]` (today `_fallback`
  deliberately omits it)

**Hints**

- The existing FreeForge project already exists with the old description.
  `_fallback` only sets the description at creation, so patch the live project
  once by hand (Plane UI or one `update` call) — or make `_fallback` reconcile
  the description, your call
- autolab's `next_work` scans `[AUTO]` projects but skips any project that has
  no `AUTO` label (`mission.py` `next_work`), so FreeForge stays invisible to
  autolab even after gaining the marker. Worth one manual check
- Works created before this step carry no label and will never be selected.
  Backfill by hand in the Plane UI if you want them runnable; otherwise ignore

**Verify**

- A `create-` round trip in `#FreeForge` produces a Work carrying `FORGEAUTO`
  (Plane UI)
- Re-serving the same topic updates the same Work and keeps the label

## Step 2 — work selection

**Build**

- `src/agforge/works.py` (name free): port `eligible_works` and `next_work`
  from `agautolab/src/agautolab/mission.py`, with label `FORGEAUTO` and
  external source `"agforge"`. Port `report_work` too (Step 4 uses it)
- Eligibility, as in autolab: carries the label, state group `unstarted`, not a
  parent of another issue; ordered by `created_at`. agforge creates no
  sub-works, so `sub_work_serial` and the parent check can be dropped or kept —
  keeping them costs nothing and survives future sub-works

**Hints**

- `agag.plane` provides everything underneath: `list_issues` (cursor
  pagination), `state_groups`, `state_id_for_group`, `update_issue`,
  `add_comment`, `html_to_text`
- **Resolve the one unknown now**: check that `list_issues` rows include
  `external_id`/`external_source`. If they do, the origin topic is
  `external_id.split("/", 1)`. If they don't, fetch the issue detail by id; if
  that also lacks it, fall back to `braindump.md`'s comment idea — write the
  origin as a comment at create time and add a `list_comments` GET to
  `agag.plane` (only `add_comment` exists today)
- autolab's selection scans every `[AUTO]` project in the workspace. Same here
  — a `pj-*` project's Works are eligible too once labeled, which is exactly
  the braindump's "other projects can be treated the same" point
- Selection is pure policy over row dicts — test it with fixture rows, no HTTP
  (autolab's tests do this)

**Verify**

- Unit: fixture rows → ordering, label filter, `unstarted` filter
- Manual: `next_work()` against live Plane returns the Step 1 Work

## Step 3 — the runcreate- topic handler

**Build**

- `zulip_listener.py`: replace the single-prefix wiring with a small
  `dispatch()` (shape: `agautolab/src/agautolab/zulip_listener.py`
  `dispatch`) and pass a tuple of prefixes to `sweep_serve` —
  `agag.zulip.sweep_serve` already accepts a tuple. `runcreate-` works in any
  subscribed channel; it carries no project
- `src/agforge/runcreate_topic.py`, shaped like autolab's `handle_run`:

```
ACK post
 chosen = next_work()  → None ⇒ post "no work", return
 ws = .local/agentws/<issue id>/generator/   (mkdir parents, exist_ok)
   write plan.md    = compose_document(name, html_to_text(description))
   copy  tools.md   = agent/guides/create_generator/tools.md (same file the
                      create flow copies)
   mkdir result/, intermediate/
 answer = run_role("generator",
                   guide("runcreate_generator", "guide.md"),
                   cwd=ws, timeout=…,
                   record=next_record_path(.local/agent/runcreate/))
 deliver result (Step 4)
 post one final summary to the runcreate- topic
```

**Hints**

- After the ACK, **every path must post to the topic before returning** —
  the sweep only re-fires when the last poster is not the bot, so the final
  post is both the report and the off-switch. autolab carries a `step` string
  through the handler and posts `failed during <step>: ...` on exception; copy
  that discipline
- `runcreate-` does not collide with the `create-` prefix match (different
  first letter), but route `runcreate-` first in `dispatch` anyway
- Reuse the `generator` role. A new role name must be added to
  `role_run.ROLE_ALLOWED_TOOLS` or claude_code hangs at the interactive
  permission prompt until timeout — reusing `generator` sidesteps that
  entirely, and the guide needs the same tools
- On re-trigger the workspace already exists: overwrite `plan.md`/`tools.md`,
  leave `result/`/`intermediate/` as they are. No dirty check — the braindump
  explicitly drops autolab's create/delete dance
- Timeout: autolab's work run uses 1200 s; the create-flow generator uses its
  own constant. Pick something in that range
- `run_role` already prepends `.local/bin` and `scripts/` to `PATH`, so
  `generate.sh` in `tools.md` works from the new workspace unchanged

**Verify**

- Fake Zulip client + `stub` profile: (a) no eligible work → "no work",
  (b) success path posts a summary, (c) exception mid-way →
  `failed during <step>` is posted, (d) `dispatch` routes `create-` /
  `runcreate-` correctly

## Step 4 — result delivery

**Build**

- After the run, scan `result/`:
  - **empty** → post the generator's answer text to the origin topic
    (channel/topic from the Work's `external_id`)
  - **non-empty** → zip it, upload, post the presigned URL to the origin topic
- Plane write-back via Step 2's `report_work`: comment (generator answer or a
  short summary) + `completed` state on success
- One summary line to the `runcreate-` topic either way

**Hints**

- Zip: `shutil.make_archive` is enough. Write the archive outside `result/`
  (workspace root or a temp dir) so it never contains itself
- Upload: reuse `generate.upload_and_presign` — it is content-type hardcoded
  to png/jpeg, so generalize the type mapping to accept `application/zip`
  (`transform.py` shows the pattern of reusing it for an arbitrary file). Env
  keys `AGFORGE_S3_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY` from `.local/.env`;
  the presign TTL parameter already exists — that is the "temporary" in
  "temporary download URL"
- "Success" needs a definition; nothing in the guide produces a flag file.
  Simplest honest rule: the run exited zero. `result/` non-empty is not a
  success signal — a pure-text answer (empty `result/`) is a legitimate outcome
- The origin `create-` topic may already be resolved (`✔`) — `topic_write`
  posts fine regardless, and the bot being last poster there cannot re-trigger
  the create sweep
- If the origin post itself fails (channel gone, etc.), still post the summary
  to the `runcreate-` topic — that post must survive everything

**Verify**

- Stub tests: empty `result/` → text goes to origin topic; non-empty → zip is
  built, contains the files, URL is posted; Plane fake records comment + state

## Step 5 — end-to-end (sonnet, FreeForge)

- Reload the listener: `launchctl kickstart -k gui/$(id -u)/com.agdev.agforge-zulip`;
  log at `agforge/.local/out/zulip-listener.log`. `AGFORGE_ZULIP_LOG_ONLY=1`
  confirms wiring for free before paying for runs
- Full loop, everything sonnet, everything through `#FreeForge`:
  1. `create-` request → Work with `FORGEAUTO` in Plane
  2. post in a `runcreate-` topic → ack, execution, summary
  3. `.local/agentws/<id>/generator/` holds plan.md / tools.md / result
  4. origin `create-` topic received the text or the zip URL; URL downloads
     and the zip opens
  5. Plane Work: comment present, state Done
  6. trigger again → "no work"
- Leave `report1.md` … per step (AG Standard Style)

## Step 6 (optional) — share the selection code through pyagag

Only after Step 5 works, as a behavior-preserving refactor; skip freely if the
round trip is not worth it now.

- Lift `ensure_label` / `eligible_works` / `next_work` / `report_work` into
  `agag` (parameters: label name, external source, project-marker predicate);
  move autolab and agforge onto it
- Touching pyagag costs: push to GitHub, then
  `uv lock --upgrade-package pyagag` in both consumers — that cost is why
  Steps 1–5 stay local
- autolab is deployed to nodes by Ansible afterwards: push to **GitHub**, then
  `setup_autolab_node.yml`. Not gitea
