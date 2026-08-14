# Step 3 — the runcreate- topic handler

## What was built

- `agforge/src/agforge/runcreate_topic.py` — autolab's `handle_run`
  discipline on agforge's vocabulary. `handle_runcreate(client, channel,
  topic)`: ack → `works.next_work()` (None ⇒ post `"no work"`, return) →
  `prepare_workspace` → `run_generator` → deliver → one final summary post.
  The chatlog is never read; `agag.topics.serve_topic` is deliberately not
  used — a `runcreate-` topic is a button, not a conversation. The handler
  carries autolab's `step` string; any exception posts
  `failed during <step>: …`, so after the ack every path posts before
  returning (the final post is both the report and the sweep's off-switch).
- `prepare_workspace(work)` — `.local/agentws/<work id>/generator/`
  (`mkdir parents, exist_ok`), writes `plan.md` as
  `compose_document(name, description_html(description))` (the exact inverse
  of what `register_plan` split), copies
  `agent/guides/create_generator/tools.md` (the same file the create flow
  copies), and ensures `result/` and `intermediate/`. Persistent and
  overwrite-in-place: no dirty check, no deletion, a re-trigger refreshes
  `plan.md`/`tools.md` and leaves `result/`/`intermediate/` alone.
- `run_generator(workspace)` — reuses the existing `generator` role (already
  in `role_run.ROLE_ALLOWED_TOOLS`, so no interactive-permission hang) with
  the `runcreate_generator/guide.md` prompt, timeout 1200 s (autolab's work
  run; the create generator uses 900 s), record under
  `.local/agent/runcreate/`.
- `zulip_listener.py` — the single-prefix wiring became `dispatch()` (shape:
  autolab's), routing `runcreate-` first, everything else to
  `create_topic.handle_topic`. `sweep_serve` now gets the tuple
  `SWEEP_PREFIXES = ("runcreate-", "create-")`; `runcreate-` works in any
  subscribed channel and carries no project.
- `deliver_result()` is Step 4's seam; in this step it only relays the
  generator's answer into the summary.

## Verification

`tests/test_runcreate_topic.py`, fake client, all agent runs monkeypatched
(the stub-profile `run_role` path itself is already pinned by p1's
`test_role_run.py`):

- (a) no eligible work → ack then `"no work"`, and no workspace is created
- (b) success → workspace holds `plan.md`/`tools.md`/`result/`/
  `intermediate/`, summary posted; a re-trigger overwrites `plan.md` in
  place and keeps `result/` contents
- (c) exceptions in the generator and in selection → `failed during
  <step>: …` is the last post
- (d) `dispatch` routes `create-` / `runcreate-` correctly; the sweep tuple
  covers both prefixes

```
121 passed in 3.89s
```

## Deviations from the plan

None in substance. The plan's pseudocode had the ACK inside the handler and
result delivery inline; delivery is factored behind `deliver_result()` so
Step 4 lands in one place.
