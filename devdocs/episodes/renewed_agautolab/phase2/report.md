# Phase 2 Report

Mission splitting, as planned in `plan.md`. Executed 2026-08-13 on agstudio.
Every step of the plan was carried out; nothing was left out.

agautolab commit `1a7d01d` ("Split a mission topic into a Plane task with
sub-work"), pushed to GitHub `origin/main`. No pyagag change was needed, as
expected. Nothing was deployed to agautolab1.

## What now happens per message in a `mission-*` topic

```
1. topic_dump            → agent/front/.local/topics/<ch>/<topic>/<N>/chatlog.txt
2. init_project(project)
3. POST /window  = front → writes mission.md into the same <N>/
4. run_role("coding")    → writes tasks/1.md, 2.md, … into the same <N>/
5. new_mission.py <N>/   → mission.md becomes a Plane task, tasks/*.md its sub-work
6. topic_write           → front's answer + coding's answer + step 5's output
```

Steps 4 and 5 are skipped or report "nothing was there" when `mission.md` is
absent. The front's reply is never inspected; the file on disk is the whole
decision, as the braindump asks.

## Step 1. Prompt composition

`window_prompt()` is now `f"{dump_notice}\n\n{guide}"`, reading
`agent/guides/front/guide_mission_topic.md` through a new `guide()` helper
resolved from `GUIDES = AGAUTOLAB_ROOT / "agent" / "guides"`. A missing or
empty guide raises `ListenerError` — the listener refuses to run with no
instruction text rather than sending a bare sentence.

`absolute_dump_notice()` was kept, per `warning.md`. The hardcoded English is
gone, including the "do not ask for path clarification unless you first run
`pwd`" clause; it was **not** moved into the guide file, and the local retest
in step 7 did not need it.

`agent/guides/` turned out to be **already committed** (commit `99c4d3d`,
"change guide"), so the plan's precondition was stale by one commit. Only the
title/description conventions were appended to both guides.

## Step 2. The coding role

`ROLE_ALLOWED_TOOLS["coding"] = WORKING_ALLOWED_TOOLS` added.
`ROLE_WORKSPACES` was deliberately left without a `coding` entry, so the
listener passes `cwd=FRONT_WORKSPACE` itself. Run records are written to
`.local/agent/coding/run-NNNN.json` with the gateway's numbering
(`next_record_path()`), and they carry role, profile, harness, model, outcome,
duration and cost — verified for both profiles below.

The listener calls `run_role("coding", …)` in-process; `/window` was not given
a role parameter.

## Step 3. `new_mission.py`

One optional dump-directory argument; with none, the newest version directory
is used (`latest_dump_directory()`). The project name comes from the `pj-*`
segment of the path, with the `AUTOLAB_PROJECT` override kept. The file→issue
conventions (first heading as title, truncated at 255; the rest as
`description_html`; `tasks/N.md` in numeric order; non-numeric names ignored
and reported) are implemented in `mission.split_document()` /
`mission.task_files()` and written into both guide files.

Idempotency is Plane-side, exactly as measured:

| issue | external_source | external_id |
|---|---|---|
| mission | `agautolab` | `<channel>/<topic>` |
| sub-work | `agautolab` | `<channel>/<topic>#<N>` |

`find_issue_by_external()` looks the pair up first; `ensure_issue()` absorbs a
409 by re-reading the pair. The dump version `<N>` is not part of the key.

`--help` was kept concise; it is now the human/Omni interface only.

## Step 4. `handle_message()`

Six steps, each behind one `step = "…"` label, all inside one `try`. On any
failure the topic still gets an answer of the form
`failed during <step>: <error>` appended to whatever earlier steps produced.
The reply is the front's answer, coding's answer and `new_mission.py`'s output,
joined by blank lines — the front's answer is relayed verbatim, not discarded.

Timeouts are three constants in one place: `WINDOW_TIMEOUT_SECONDS = 360`,
`CODING_TIMEOUT_SECONDS = 600`, `REGISTER_TIMEOUT_SECONDS = 180`. Measured
reality is far below them (see below), but `serve()` remains single-threaded
and serial.

`uv run pytest -q`: **43 passed** (was 28; the mission and listener suites were
rewritten around the new contract, including numeric task ordering, the 409
race, and the "second dump version registers nothing" case).

## Step 5. Omni Agent workflow check (no trigger, no in-system agent)

Ran by hand as `plan.md` specifies: `init_project("phase2omni")`, hand-written
`mission.md` plus `tasks/1.md`, `2.md` and a decoy `notes.md`, then
`new_mission.py` twice.

```
created P2-1 "Probe the phase 2 registration path"
ignored non-task file in tasks/: notes.md
created sub-work P2-2 "Write the probe files by hand"
created sub-work P2-3 "Run new_mission.py twice"
```

The second run printed the same three lines with `already registered`, and a
**third** run against a hand-made version `2/` directory of the same topic also
registered nothing new — the version number really is outside the key. Plane
confirms three issues, with P2-2 and P2-3 carrying P2-1's uuid as `parent`. A
dump directory with no `mission.md` printed `no mission` and exited 0.

> Deus Ex Machina note: did the mission-registration workflow by hand for
> agents front/coding — handoff candidate. (It is exactly what steps 6 and 7
> then had the agents do unaided.)

## Step 6. Workflow check by the autolab agent (sonnet)

`front` and `coding` pinned to `sonnet` in `.local/agents.local.toml`; both
launchd services kickstarted. Channel `#pj-phase2sonnet`, three messages.

| Topic | Result |
|---|---|
| `mission-readme` | front wrote `mission.md`; coding judged it too small to split; `created P3-1`, zero sub-work |
| `mission-readme` (2nd message) | front wrote no `mission.md`; split skipped; `no mission`; **no new Plane issue** |
| `mission-pipeline` | front wrote `mission.md`; coding wrote `tasks/1.md`…`6.md`; `created P3-2` plus six sub-work |

Plane holds 8 issues in `Phase2sonnet`: P3-1, P3-2, and P3-3…P3-8 all
parented to P3-2. All five watch items from the plan passed. The reply landed
in the topic each time, carrying both agents' answers followed by the
registration lines.

Run records: `window/run-0011…0013` and `coding/run-0001…0002`, all
`profile=sonnet`, `model=anthropic/claude-sonnet-5`, `outcome=done`.

Cost and wall clock per message (sonnet):

| Step | Duration | Cost |
|---|---|---|
| front (`/window`) | 8–12 s | $0.06–0.11 |
| coding | 32–34 s | $0.15–0.20 |

The split coding produced was one sub-task per bullet of the request — six for
a six-clause mission. Coarse enough to be readable, and it declined to split
the one-clause mission rather than manufacturing sub-work. Decision 2 of the
plan ("no `tasks/` is a normal outcome") was exercised on the first message.

## Step 7. Retest with the local agent

`front` and `coding` put back on `local` (opencode + `qwen3.6:35b-a3b-coding`),
services kickstarted, one request in `#pj-phase2local` / `mission-backup`.

`front` and `coding` put back on `local` (opencode + `qwen3.6:35b-a3b-coding`),
services kickstarted, two requests in `#pj-phase2local`. Not gone into deeply,
per the braindump.

**Run 1 (`mission-backup`) worked on the first try.** The front wrote
`mission.md` (18.9 s, $0), coding wrote four task files (58.8 s, $0,
`outcome=done`), and `new_mission.py` created P4-1 with P4-2…P4-5 beneath it.
The split was 4 sub-tasks against sonnet's 6 for a comparable request, with
shorter descriptions (2 sentences vs 5 bullets). Usable, thinner.

**Run 2 (`mission-metrics`) reproduced the `warning.md` defect on the coding
side.** The front wrote `mission.md` correctly — and, notably, reported it
back as the absolute path it had been handed. Coding, handed the plain
front-relative path `.local/topics/pj-phase2local/mission-metrics/1/mission.md`
to a file that had just been written, answered:

> The mission file at `.local/topics/…/mission.md` does not exist — the
> `topics` directory has not been created yet. Without the mission content, I
> cannot create the sub-task files.

Same shape as the front's phase-1 failure: the path is correct, the working
directory is correct, the file is there, and the local model reconstructs the
path against a guessed root and then reports the file missing. `run-0004.json`
records `outcome=done` in 34.6 s — the harness cannot see this failure, because
the agent failed *articulately*.

The failure is contained by the design: no `tasks/` meant zero sub-work, and
`new_mission.py` still registered `P4-6 "Add metrics endpoint to project"`.
A message that should have produced sub-work produced a bare task instead —
degraded, not broken, and visible in the topic.

So, two local runs: coding 1 success / 1 path failure; the front 2/2 with the
absolute-path workaround in place. Harvested as Failure Farming evidence, with
**no text added to any prompt or guide** in response. `warning.md`'s caution
about single-digit samples applies to these numbers too.

**Both roles are still on the `local` profile** in
`.local/agents.local.toml` — that is where step 7 leaves them, and where phase
3 should find them.

## What was learned that the plan did not predict

1. **The front cannot see its own history.** On the second message to
   `mission-readme` the front reported that the chat log claims `mission.md`
   and P3-1 already exist "but that file doesn't actually exist in this
   directory". It is correct: `topic_dump` had given it a fresh empty `2/`.
   Every re-fire of a topic starts an agent that is blind to what earlier
   versions did. This is precisely why the duplicate guard has to live in
   Plane, and it makes that choice load-bearing rather than merely tidy.
2. **Coding reasons about the wrong project.** Running in the front workspace
   (plan decision 3, "don't worry about it this time"), it inspected
   `agent/front/` and wrote *"the project here — `agautolab-front`, a small
   Python/uv package…"* while deciding whether to split a mission that belongs
   to `pj-phase2sonnet`. It reached a sensible answer anyway, but its evidence
   was the wrong repository. Moving the dump to a shared location and giving
   coding the project's own clone is the phase 3 item, and this is the concrete
   symptom to point at.
3. **`agent/guides/` was already committed**, so the plan's "left untracked,
   the deploy dies" risk was already retired.
4. **A local-model failure can be recorded as `outcome=done`.** Run 2 of step 7
   ended with a well-written explanation of why it could do nothing, exit code
   0, and a clean run record. Nothing short of reading the reply — or noticing
   the absent `tasks/` — distinguishes it from a deliberate decision not to
   split. Any future "did the split happen?" check has to look at the files,
   not the record.

## Not touched, as instructed

`/status`, `/jobs`, `/projects`; `/window`'s single entrance, lock, status
codes and record; `subscribe_project_channels()`; `init_project.py`;
`topic_dump` / `topic_write`.

## Residue on this machine

Plane projects `Phase2omni` (P2), `Phase2sonnet` (P3), `Phase2local` (P4) and
their Gitea repositories/clones were created by the checks and are left in
place as evidence. Zulip channels `#pj-phase2sonnet` and `#pj-phase2local`
likewise. Delete them when the evidence is no longer wanted.
