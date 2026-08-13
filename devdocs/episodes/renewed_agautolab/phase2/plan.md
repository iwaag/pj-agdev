# Phase 2 Implementation Proposal

How to realize `braindump.md` (mission splitting). As in phase 1, backward
compatibility is not required.

## Measured preconditions (2026-08-13, agstudio local)

The Plane CE `v1.4.1` issue API was measured directly, confirming that both the
sub-work and the idempotency foundations exist. Verified in the disposable
`Phase1 Smoke 20260813` project; the probe issues were deleted afterwards.

| Checked | Result |
|---|---|
| sub-work | `POST …/issues/` with `"parent": "<issue uuid>"` in the body creates one |
| external key | `external_source` / `external_id` are stored on the issue |
| duplicate create | A POST with the same `(external_source, external_id)` returns **409** plus `{"error":…, "id": "<existing issue uuid>"}` |
| lookup | `GET …/issues/?external_id=X&external_source=Y` returns the issue object directly (404 when absent) |

**This is the real duplicate-creation guard.** A local marker file disappears
with `.local/`, and because `topic_dump` increments `N` on every trigger, a
marker placed in a version directory cannot stop the second firing of the same
topic. A key held by Plane stops both.

Other preconditions, confirmed by reading the code:

- `agent/guides/` already exists but is **untracked by git** (`?? agent/guides/`).
  It needs to be committed.
- `agents.toml` already has `[roles.coding]` (profile = sonnet) and
  `agent/opencode-coding.json` exists. However, `role_run.py` has no `coding`
  entry in `ROLE_ALLOWED_TOOLS` or `ROLE_WORKSPACES`.
- `agag.zulip.serve()` **swallows handler exceptions**. Today's `handle_message`
  replies nothing to the topic when it fails midway. The more steps are added,
  the more this hurts.
- `topic_dump()` returns
  `.local/topics/<channel>/<topic>/<N>/chatlog.txt is the log of…`.
  That `<N>/` directory is the working directory for mission splitting.

---

## The whole picture

Per message in a `mission-*` topic, the listener takes six steps in order.

```
1. topic_dump            → .local/topics/<ch>/<topic>/<N>/chatlog.txt
2. init_project(project) (idempotent, unchanged)
3. POST /window  = front → writes mission.md into the same <N>/
4. run_role("coding")    → writes tasks/1.md, 2.md, … into the same <N>/
5. new_mission.py <N>/   → mission.md becomes a Plane task, tasks/*.md its sub-work
6. topic_write           → front's answer plus the result of step 5
```

Steps 3 and 4 are non-deterministic (agents); step 5 is deterministic (a script).
**The reply from step 3 is not inspected** (as the braindump specifies). When
`mission.md` is absent, steps 4 and 5 report that nothing was there and stop —
the presence of the file is the only thing that carries the decision.

This is a deliberate shackle relative to phase 1, and should be recorded as one.
In phase 1 `new_mission.py` was a **tool given** to the front agent, with
`--help` as its only specification. In phase 2 it becomes a **script the
listener calls**, and the agents only go as far as writing files. That lands on
the "If you do that, just write scripts" side of terms.md; treat it not as a
retreat from Tool Giving but as a decision to take the Plane write side-effect
out of the agents' hands.

---

## Step 1. Change how the prompt is composed

`src/agautolab/zulip_listener.py`, `window_prompt()`.

- Drop the hardcoded English text; read
  `agent/guides/front/guide_mission_topic.md` and return
  `f"{dump_notice}\n\n{guide}"` and nothing else. Resolve guides from
  `GUIDES = AGAUTOLAB_ROOT / "agent" / "guides"`. Raise if the guide cannot be
  read — never start silently without it.
- **Keep** `absolute_dump_notice()`. Per `warning.md` it is an ad-hoc measure
  against a local-model defect, to be removed when the front leaves the `local`
  profile. Phase 2 tests on sonnet, but step 7 goes back to local, so keeping it
  makes the separation easier.
- The current prompt's "do not ask for path clarification unless you first run
  `pwd`" clause disappears. That was local-model reinforcement; if it is still
  needed, **put it in the guide file**, not back into the code.
- Commit `agent/guides/`. Left untracked, the files are missing from a deploy to
  agautolab1 and the listener dies at startup.

The current `guide_mission_topic.md` — "if the last message is the mission
request, create mission.md in the same directory as the chat log; otherwise
reply with what happened" — works as designed. Only the title/description
extraction convention (step 3 below) needs to be appended.

## Step 2. Make the coding role launchable from the listener

`src/agautolab/role_run.py`.

- `ROLE_ALLOWED_TOOLS["coding"] = WORKING_ALLOWED_TOOLS`. **Required.** As it
  stands, `allowed_tools=None` means `build_argv` omits `--allowedTools` and
  claude_code sits waiting for interactive permission until the timeout.
- Do **not** add `coding` to `ROLE_WORKSPACES`. The braindump runs coding in the
  front workspace ("don't worry about it this time"), so let the caller pass
  `cwd=FRONT_WORKSPACE`. Pinning it here makes it harder to peel off later.
- Write a run record. Pass `.local/agent/coding/run-NNNN.json` to
  `run_role(..., record=…)` (the same numbering as the gateway's
  `next_window_id()` is fine). The devpolicy rule that every run records which
  backend served it is not a promise limited to gateway runs; a run the listener
  starts directly needs the same record.

The listener calls `run_role("coding", prompt, cwd=FRONT_WORKSPACE, timeout=…)`
directly, not through the gateway `/window`. `/window` is the front's single
entrance; growing a role parameter on it would break Single Entrance.

The coding prompt (English, composed the same way as step 1):

```
<front-relative path of mission.md> is the file that describes the mission.
<contents of agent/guides/coding/guide_task_split.md>
```

## Step 3. Respecify `new_mission.py`

Replace the "mission name + description" arguments with **one dump directory**.

```
uv run new_mission.py .local/topics/pj-foo/mission-bar/3
```

- When omitted, use the newest dump directory (`current_project()` in
  `mission.py` already globs the same tree; lift it one level to return the
  newest version directory).
- The project name comes from the `pj-*` segment of the given path. Keep the
  `AUTOLAB_PROJECT` override — it earns its keep in the step 5 manual check.
- No `mission.md` → **exit 0 printing "no mission"**. That is not an error; it is
  the normal path where the front judged the chat was not a request.
- No `tasks/` → zero sub-work, still normal.
- Print one line per action, for humans and for topic readers:
  `created PS20260813-4 "…"` / `created sub-work PS20260813-5 "…"` /
  `already registered …`.

**File-to-issue conventions** (write the same thing into the guides):

- Title = the first Markdown heading line (`# …`); if absent, the first
  non-empty line. Truncate at 255.
- Description = the rest of the file, put into `description_html` with the
  existing `<p>` + `<br>` conversion from `mission.py`.
- Process `tasks/` as `1.md, 2.md, …` in **numeric order**. Avoid the string sort
  that puts `10.md` before `2.md`. Ignore non-numeric names and say so in the
  output.

**Idempotency** (Plane-side keys, measured):

| issue | external_source | external_id |
|---|---|---|
| mission | `agautolab` | `<channel>/<topic>` |
| sub-work | `agautolab` | `<channel>/<topic>#<N>` |

Look it up first with `GET …?external_id=…&external_source=agautolab`; if it
exists, do not create it and use its id as the parent. When a POST returns 409,
take the `id` out of the response and continue — that absorbs a race between the
GET and the POST.

The point is that the version directory `<N>` is **not** part of the
`external_id`. When the same topic fires again and a new mission.md appears
under `<N+1>`, no second task appears in Plane.

## Step 4. Replace `zulip_listener.handle_message()`

It calls the six steps above in order. Only the implementation notes here.

- **Always reply.** Wrap each step in a try and `topic_write` how far it got plus
  the failure when something breaks. Because `serve()` swallows exceptions, the
  only symptom today is silence, and a human will not go read the log.
- **Concatenate the reply**: the front's answer verbatim, a blank line, then the
  `new_mission.py` output. "Do not check the reply content" means do not check
  it, not discard it.
- **Timeout budget.** Today it is 300 s at `/window` and 360 s at the listener.
  Stacking another 600 s for the coding run makes one message up to 16 minutes,
  during which the listener cannot process the next `mission-*` (`serve()` is
  single-threaded). Serial is fine for now, but keep the numbers as constants in
  one place and reply "timed out" to the topic when exceeded.
- **Exclusion.** The gateway's `window_lock` only protects the front. Coding is
  started inside the listener process, so it does not contend; but if the Omni
  Agent pokes `/window` by hand, only the front collides. Passing the 409 back to
  the topic is enough.

## Step 5. Workflow check by the Omni Agent (no trigger, no in-system agent)

The braindump sentence breaks off mid-way, so it is read as: **without the
listener, the front, or coding, the Omni Agent drives "create a new project →
create a task with sub-work" by hand** as the first verification. Once that
passes, every later failure is isolated outside the deterministic layer — that
is, on the agent side.

```sh
cd pj-agdev/agautolab
uv run python -c 'from agautolab.project_init import init_project; print(init_project("phase2omni"))'
mkdir -p agent/front/.local/topics/pj-phase2omni/mission-probe/1/tasks
# write mission.md and tasks/1.md, 2.md by hand
cd agent/front && uv run new_mission.py .local/topics/pj-phase2omni/mission-probe/1
uv run new_mission.py .local/topics/pj-phase2omni/mission-probe/1   # second run: nothing is added
```

Eyeball one parent and two sub-work items in the Plane UI. This is Deus Ex
Machina, so leave the one-line note in the report: "did X for agent
front/coding — handoff candidate".

## Step 6. Workflow check by the autolab agent (sonnet, fixed)

Pin `front` and `coding` to `sonnet` in `.local/agents.local.toml`, then write a
request in a `mission-*` topic of a `#pj-<name>` channel. Cost is unlimited (per
the braindump).

What to watch:

1. `<N>/mission.md` appears (front)
2. `<N>/tasks/*.md` appear, and how coarse the split is (coding)
3. Plane gets a parent plus sub-work
4. A reply comes back to the topic
5. A second message to the same topic **adds no Plane task**

Also confirm the run records under `.local/agent/window/` and
`.local/agent/coding/` carry the profile and the cost. Record everything,
failures included, from `report1.md` onwards.

## Step 7. Retest with the local agent

Put `front` / `coding` back on `local` (opencode + ollama) and run once or twice.
**Do not go deep** (per the braindump). As `warning.md` records, the local model
has a known defect where it rewrites the path it is given. The same failure shape
should appear on the coding side; harvest it as Failure Farming evidence and
record it, without piling more text into the prompt.

---

## Decisions worth making up front

These can be left to the implementer, but deciding early avoids rework.

1. **One mission per topic** is assumed (`external_id = <channel>/<topic>`).
   Accepting a second mission in the same topic means changing that key. If that
   day comes, "use a separate topic" is expected to be the cheaper operation.
2. **If coding decides not to split** (no `tasks/`), the result is a task with
   zero sub-work. Treat that as a normal outcome.
3. **Running coding in the front workspace** is the point the braindump
   explicitly set aside this time. As long as `.local/topics/` lives under the
   front, separating them comes bundled with moving the dump location to a shared
   directory. A phase 3 candidate.
4. **The role of `new_mission.py --help` changes.** It is no longer the front's
   only interface specification (the listener calls it). It is still what the
   Omni Agent and a human use in step 5, so keep it concise.

## What not to touch

- The gateway's `/status`, `/jobs`, `/projects` (proxied by the agdevworld
  assistant).
- `/window`'s single entrance, exclusive lock, 400/409/502, and run record.
- `subscribe_project_channels()` (the linchpin of `pj-*` subscription).
- `init_project.py`, `topic_dump` / `topic_write` (no pyagag change needed this
  time).

## Files to change

| File | Change |
|---|---|
| `agent/guides/**` | commit; append the mission title/description conventions |
| `src/agautolab/zulip_listener.py` | `window_prompt()` reads the guide; `handle_message()` becomes the six steps |
| `src/agautolab/role_run.py` | add `ROLE_ALLOWED_TOOLS["coding"]` |
| `src/agautolab/mission.py` | register from a dump directory, `parent`, external-key idempotency |
| `agent/front/new_mission.py` | one directory argument |

No pyagag change is expected. Commit and push agautolab.
