# Phase 4 Step 4 Report — `run-` topic handling

## Subscription

`subscribe_project_channels` now reconciles `#general` exactly like a `pj-*`
channel (every active realm user, bots included). Without that, Zulip delivers
nothing for the channel and the sweep cannot see `run-` topics at all.

## Dispatch

`main()` sweeps with `topic_filter=(MISSION_TOPIC_PREFIX, RUN_TOPIC_PREFIX)`
(`run-`), and the handler is a new `dispatch(client, channel, topic)`:

- `run-*` → `handle_run`, in any channel — a run topic carries no project of
  its own, the project comes from the chosen Work.
- otherwise a `pj-*` channel is required; a `mission-*` topic anywhere else is
  logged and ignored. Previously `project_from_channel` raised, which with
  `#general` swept would have posted an error into it on every sweep.

`AUTOLAB_ZULIP_LOG_ONLY=1` still swaps in the passive observer, now for both
prefixes.

## `handle_run`

After the ack, in order:

1. `next_work()` → `None` posts `no work` and stops.
2. Dirty check on `.local/work/` inside the chosen project's `main` clone
   (`work_directory(slug)`): a non-empty one posts `work dirty` naming
   `<slug>/main`, and stops **without** deleting anything — manual cleanup is
   the accepted recovery, so the directory is only this run's to delete after
   the check passes.
3. `.local/work/work.md` ← `compose_document(name, description_html(...))`,
   i.e. `# <title>` then the description.
4. `run_work(workspace)` — the `coding` role with
   `guide("run_coding", "guide_run_coding.md")`, cwd the `main` clone,
   `WORK_TIMEOUT_SECONDS = 1200`, and its own `ag.agent-run.v1` record under
   `.local/agent/run/run-NNNN.json` (mirroring `front`/`coding`).
5. `report_work(project_id, issue_id, report, success)` (new, in `mission.py`):
   comments `.local/work/report.md` on the Work when present, moves it to the
   `completed` group when `.local/work/success.flag` exists, and returns
   `(label, commented, completed)`. A missing report adds a `no report` line.
6. One outcome post per exit path, carrying what happened —
   `running "<title>" in <slug>`, the agent's own output, and
   `work PD-7: commented yes|no, Done yes|no`.
7. `finally`: the work directory is removed, including on the failure paths
   reached after it was created. What survives an interpreter crash is exactly
   what the dirty check exists to catch.

The chatlog is never read: a `run-` topic is a button, not a conversation.

The guide the run uses (`agent/guides/run_coding/guide_run_coding.md`, written
by the developer) is committed with this step, along with two earlier
uncommitted guide edits (`guide_task_split.md` leading blank line,
`guide_task_run.md` — an unused leftover — deleted).

## Tests

agautolab suite: **77 passed** (7 new).

- happy path: ack → run in `<projects>/demo-project/main` → `report_work` with
  the report text and success → outcome line → `.local/work/` gone, workspace
  intact.
- `work.md` content is in place before the run starts.
- `no work`, `work dirty` (leftover preserved, no run), `no report`
  (`commented no, Done no`).
- a raising run still posts `failed during work run: …` and still cleans up.
- `dispatch` routing: `run-` in `#general` and in a `pj-` channel, `mission-`
  in a `pj-` channel, `mission-` in `#general` ignored.
- the subscription test now expects `#general` to be reconciled.
