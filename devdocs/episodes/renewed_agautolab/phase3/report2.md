# Phase 3 Step 2 Report — agautolab mission topic front path

Done. agautolab commit `6f44d6d` (GitHub `main`). The listener is now a
`sweep_serve` handler running the front in stable topic workspaces.

## The new flow (`handle_topic(client, channel, topic)`)

1. **Ack** — `topic_write("Message received. Please wait for the reply.")`
   first, before any work. This makes the bot the last poster, so a later
   sweep skips the topic while the run is in flight (the self-stabilization
   property from the plan).
2. **Workspace** — `.local/topics/<channel>/<topic>/front/` under the
   agautolab root, components validated with `_safe_topic_component`, reused
   across runs. The `<N>` versioning and `topic_dump` are gone from this path.
3. **Chatlog** — full topic history (`num_before=1000`) formatted by the kept
   `format_chatlog` and written as `front/chatlog.md`.
4. **Plane read-back** — new `mission.write_mission_workspace()`: via
   `find_issue_by_external` (`<channel>/<topic>`), writes `mission.md`
   (title as `# heading` + description, inverting `split_document`) and the
   non-cancelled Sub-Works in sequence order as `task1.md`, `task2.md`, ….
5. **Prompt** — "The chatlog is placed in the working directory. You are
   `<bot full name>` in the chatlog." (+ the mission-and-tasks line when
   Plane files were written) + verbatim
   `agent/guides/mission_front/guide_mission_topic.md`. This also fixes the
   known `guides/front/` → `guides/mission_front/` breakage.
6. **Launch** — `run_role("front", prompt, cwd=<front dir>)` directly from
   the listener; `POST /window` is out of this path. The `front` pin in
   `ROLE_WORKSPACES` is removed (caller cwd wins); the gateway now passes
   `agent/front` explicitly so `/window` behaves as before. Run records
   continue as `ag.agent-run.v1` via `run_role(record=…)`, numbered under
   `.local/agent/front/`.
7. **Reply** — every exit path `topic_write`s; failures report
   `failed during <step>: …` after the ack.

`main()` keeps `subscribe_project_channels` + its 60 s reconciliation thread
(the sweep can only see subscribed channels) and `AUTOLAB_ZULIP_LOG_ONLY=1`
as a passive sweep observer (`observe_topic` logs matches, acts on nothing).

## Plane CE v1.4.1 verification (live, plan asked for this)

- `GET .../issues/?parent=<id>` **ignores the filter** — it returned the full
  issue list including the parent itself. Not usable.
- `GET .../issues/<id>/sub-issues/` → **404**. Not usable.
- Therefore: children come from the full issue list (cursor pagination
  followed via `next_page_results`/`next_cursor`), filtered client-side on
  the `parent` field. List rows carry `description_html`, so no per-issue
  detail reads are needed.
- `description_stripped` is **unreliable** (observed `None` on an issue whose
  `description_html` has content). Plain text is recovered from
  `description_html` by inverting our own `description_html()` writer
  (`html_to_text`), tolerating stray tags.
- State vocabulary confirmed: Backlog/backlog, Todo/unstarted,
  In Progress/started, Done/completed, Cancelled/cancelled — `state_groups()`
  maps state id → group; cancelled children are skipped by group, not name.

## Deleted (backward compatibility not required)

`accept`, `handle_message`, `call_window`, `window_prompt`,
`absolute_dump_notice`, `dump_directory`, `coding_prompt`, `run_coding`,
`register_mission`, the `topic_dump` import, and the `AUTOLAB_NODE_URL`
plumbing. `run_coding`/`register_mission` return in step 3 rebuilt on the
new `coding/` contract; between steps 2 and 3 the listener replies but does
not yet mutate Plane (nothing is deployed until step 5). The old-dump
machinery still in `mission.py` (`register_dump`, `latest_dump_directory`,
`task_files`) and `agent/front/new_mission.py` are step 3 rewrite targets.

## Tests

- `tests/test_zulip_listener.py` rewritten to the new contract (ack-first
  ordering, workspace stability + traversal rejection, prompt content,
  bot-line marking, failure reporting, guide refusal, records numbering,
  subscription reconciliation).
- `tests/test_mission.py` gained read-back tests: `html_to_text` /
  `compose_document` round-trip against `split_document`, `sub_works`
  cancelled-filter + sequence sort, `write_mission_workspace` file output
  (thin external-lookup object upgraded from the list row) and the no-Work
  no-op.
- `tests/test_role_run.py`: the front fixed-workspace test now asserts the
  caller's cwd wins.

`uv run pytest -q` in agautolab: **49 passed** (was 39 passed + 4 known
failures before this step; the old-contract tests were rewritten, not
preserved, per the plan).
