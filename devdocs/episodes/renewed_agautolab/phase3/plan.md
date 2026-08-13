# Phase 3 Plan — Pull-based listener and topic workspaces

Realizes `braindump.md`. Decisions already made by the developer:

- Workspace root is `agautolab/.local/topics/<channel>/<topic>/{front,coding}/` (stable, reused; the `<N>` versioning is gone).
- `POST /window` on the gateway stays as-is; it simply leaves the mission path.
- Work and Sub-Work are never deleted; cancellation is a state transition to `Cancelled`.
- The `start.flag` / `cancel.flag` mechanism is in scope.
- Backward compatibility is NOT required. This is a destructive phase in a private experimental environment; rewrite freely, delete dead code, adjust tests to the new contract.

Constraints are deliberately minimal: keep secrets out of tracked files and logs, and deploy pyagag changes through GitHub (the agstudio gitea mirror goes stale — never use it as a dependency source). Everything else is implementer discretion.

## Step 1 — pyagag: sweep primitives and `sweep_serve()`

Add to `pyagag/src/agag/zulip.py`:

1. Topic enumeration per subscribed channel. Zulip's `GET /api/v1/users/me/<stream_id>/topics` returns topic names newest-first; you will need a stream-name→id lookup (`GET /api/v1/get_stream_id?stream=<name>`, or reuse the channel listing the subscribe loop already fetches).
2. A "last poster" check: `topic_history(channel, topic, num_before=1)` already exists; compare `sender_id` with `whoami()`.
3. `sweep_serve(client, handler, *, topic_filter)` — the new loop, alongside the existing `serve()` (which DM-based listeners keep using):
   - Register the event queue exactly as `serve()` does; message events only set a `dirty` flag — their payload is not processed.
   - When dirty: clear the flag, then scan all subscribed channels for topics that (a) pass `topic_filter` (prefix match), (b) are unresolved — do not start with `RESOLVED_TOPIC_PREFIX` (`"✔ "`), (c) whose last poster is not this bot. Call `handler(channel, topic)` for each match.
   - Sweep once on every queue (re-)registration — startup and `QueueExpired` recovery. This is what makes downtime and queue expiry lossless; no periodic timer is needed.
   - The loop stays single-threaded and serial, like today.

Self-stabilization property worth preserving: the handler's first action (the ack, Step 2) makes the bot the last poster, so a topic in progress is skipped by later sweeps; a human posting during processing re-arms it, and the post-run sweep reprocesses with the fuller chatlog. A crash after the ack leaves the topic dormant until a human posts again — accepted for now.

Ship: tests in pyagag, push to GitHub `main`, bump/refresh the dependency in `agautolab/pyproject.toml` (agforge later in Step 4).

## Step 2 — agautolab: mission topic front path

Rework `handle_message` in `agautolab/src/agautolab/zulip_listener.py` into a `sweep_serve` handler:

1. **Ack**: immediately `topic_write` in English, e.g. "Message received. Please wait for the reply."
2. **Workspace**: create `agautolab/.local/topics/<channel>/<topic>/front/` (validate components with the existing `_safe_topic_component`; reuse the directory across runs — leftovers are continuity, not garbage).
3. **Chatlog**: dump the full topic log as `chatlog.md` directly in `front/` (existing `topic_history(num_before=1000)` + `format_chatlog`; the `topic_dump` helper with its `<N>` allocation is obsolete — remove or bypass it).
4. **Plane read-back** (new code in `mission.py`): via `find_issue_by_external` with external id `<channel>/<topic>`, if a Work exists write it to `front/mission.md` (title as `# heading`, then description — invert `split_document`). If it has Sub-Works, write them in order as `front/task1.md`, `front/task2.md`, … Listing children needs verification against Plane CE v1.4.1: try `GET .../issues/?parent=<id>` first, fall back to the sub-issues endpoint; check what field carries a usable plain-text description (`description_stripped` vs `description_html`). Skip `Cancelled` children.
5. **Prompt**: "The chatlog is placed in the working directory. You are `<bot full name>` in the chatlog." plus, when Plane files were written, "The current mission and tasks are also placed in the working directory." Then append the verbatim content of `agent/guides/mission_front/guide_mission_topic.md`.
6. **Launch**: `run_role("front", prompt, cwd=<front dir>, ...)` directly from the listener (same pattern `run_coding` already uses). Remove the `POST /window` call from this path. `ROLE_WORKSPACES` in `role_run.py` currently pins `front` to `agent/front/` and overrides the caller's cwd — remove the pin (or make caller cwd win); the gateway's `/window` should keep working for its own uses.
7. Post the outcome back to the topic (`topic_write` on every exit path, as today).

## Step 3 — agautolab: response handling (new_mission.md and flags)

After the front run returns, inspect the `front/` directory:

**`new_mission.md` present:**
1. Update the topic's Work: new `update_issue()` in `mission.py` (`PATCH .../issues/<id>/`, name + description_html). If no Work exists yet, create it (existing `ensure_issue`).
2. Cancel all existing non-cancelled Sub-Works: resolve the `cancelled`-group state id (mirror `starting_state_id`) and PATCH each child.
3. Create `.../topics/<channel>/<topic>/coding/`, copy `new_mission.md` in, run `run_role("coding", <verbatim guide_task_split.md>, cwd=<coding dir>)`.
4. Register every `task[N].md` found in `coding/` as a Sub-Work of the Work. The old external key `<channel>/<topic>#<N>` would collide with cancelled generations — include a generation marker, e.g. `<channel>/<topic>@<rev>#<N>` where `<rev>` is a counter persisted in the topic directory (or the Work's updated_at — implementer's choice, just keep it collision-free).
5. `register_dump()` / `new_mission.py` were built for the old `<N>`-dump contract; rewrite or replace them to read `task[N].md` from the coding dir. Delete what the new flow no longer needs.

**`start.flag` present:** transition the Work to `In Progress`. (Actual task execution is a later phase; `guide_task_run.md` already exists for it.)

**`cancel.flag` present:** transition the Work and all its non-cancelled Sub-Works to `Cancelled`, and resolve the topic (`resolve_topic` exists on `ZulipClient`; a resolved topic stops matching the sweep, which is the desired end state).

Both flags and `new_mission.md` may coexist; a sensible order is new_mission → start/cancel. Report every action taken in the final topic post.

**Guide contract fixes** (the guides and code must agree on filenames; current text still disagrees):
- `mission_front/guide_mission_topic.md` says `new_misson.md` (missing "i") — the listener would never find the file. Fix to `new_mission.md`.
- `mission_coding/guide_task_split.md` says "create directory named task[N].md" and lists examples `task.md, task2.md, task.md` — should be files `task1.md, task2.md, task3.md, …`. Align the guide, the registration code, and tests on exactly `task[N].md` starting at 1.

## Step 4 — agforge: adopt the pull loop

Switch `agforge/src/agforge/zulip_listener.py` to `sweep_serve` with the `create-` prefix filter plus its existing DM handling (DMs stay on the event payload — either keep a thin event branch or run `serve()` alongside; implementer's choice). Per-match behavior is unchanged except the new common ack post. Bump its pyagag dependency.

## Step 5 — Verification and deploy

Unit tests first (the 43 existing agautolab tests encode the old contract — rewrite them to the new one, don't preserve it). Then E2E in a dedicated channel per phase-1/2 convention (e.g. `#pj-phase3e2e`):

1. Fresh `mission-*` topic, no Work in Plane → ack, chatlog-only prompt, front run, reply.
2. Topic whose Work + Sub-Works already exist → `mission.md`/`task[N].md` appear in `front/`, prompt mentions them.
3. `new_mission.md` round trip → Work updated, old Sub-Works `Cancelled`, new ones registered with the generation key.
4. Post again while a run is in flight → after completion the sweep reprocesses with the fuller chatlog.
5. Stop the listener, post, restart → the startup sweep picks the topic up (the headline win of pull mode).
6. `cancel.flag` → Work + Sub-Works cancelled, topic resolved, sweep goes quiet.

Deploy: pyagag via GitHub; agautolab commit → push to GitHub and to the agstudio gitea (`localrule.md`: push every commit, then reflect onto consumers) → `ansible-playbook -i inventories/generated/production.yml playbooks/agent/setup_autolab_node.yml --limit agautolab1` from `pj-clusterintent/ansible_agdev`. Restart the local launchd listeners (`com.agdev.agautolab-zulip`, `com.agdev.agforge-zulip`) with `launchctl kickstart -k`.

## Useful facts and pitfalls found during planning

- **The listener is currently broken**: `zulip_listener.guide()` still resolves `guides/front/` and `guides/coding/`, which were renamed to `mission_front/`/`mission_coding/` (rename is on disk, uncommitted). Step 2's prompt rework subsumes the fix.
- Zulip delivers no events for unsubscribed channels; `subscribe_project_channels` + its 60 s reconciliation thread must survive the rework. The sweep can only see subscribed channels for the same reason.
- Timeouts today: window 360 s, coding 600 s, register 180 s — reuse or adjust freely; the run is serial, so a long agent run just delays the next sweep (events queue up, nothing is lost).
- `AUTOLAB_ZULIP_LOG_ONLY=1` (passive observer mode) is worth preserving in the new loop — it is the cheap way to watch sweep decisions without paying for agent runs.
- `warning.md` (episode root): `absolute_dump_notice()` is a workaround for a local-model path-rewriting defect. With cwd now being the topic workspace itself, relative paths ("in the working directory") may make it unnecessary — retest with the `local` profile before deleting it.
- `.local/agents.local.toml` currently pins `front` and `coding` to the `local` (ollama) profile; use `sonnet` for E2E first, then try `local`, as phase 2 did.
- Plane: config via `load_plane_config` (`pj-agdev/.local/plane-credentials.env`, header `X-API-Key`). Existing building blocks in `mission.py`: `find_plane_project`, `starting_state_id`, `find_issue_by_external`, `ensure_issue`, `split_document`, `description_html`. Missing and needed: issue PATCH, children listing, cancelled-state resolution.
- Role plumbing: `ROLE_ALLOWED_TOOLS` gates claude_code tool permissions — a role missing from it blocks on interactive permission until timeout (phase-2 lesson). opencode roles read `agent/opencode-<role>.json`; check whether those configs constrain paths that the new `.local/topics/` cwd needs.
- Every run must keep writing an `ag.agent-run.v1` record (`write_run_record`) — Agent ≠ Model policy; record locations under `.local/agent/` can move if the topic workspace is a better home.
- `agautolab1.local` currently resolves to 192.168.0.220 (not the Nautobot-desired .130) and runs a stale checkout; expect the first ansible run to also pick up earlier phases' changes.
