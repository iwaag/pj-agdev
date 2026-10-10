# Workflow run contract (`ag.workflow-run.v1`, p3/pre1)

A **run** is one execution of a workflow: the input it was given, the fixed
definition it follows, and a record of what the executor reported. It lives in
devdocs beside the definitions and is version-controlled like them. The
definition contract (`ag.workflow.v1`, approvals, validation) is in
[contract.md](contract.md).

A run record is an operational record. It says what the executor and the
people involved recorded, in order. It is not authenticated or tamper-proof
evidence, and `running` means "the executor reported that work started", not
"a process is alive".

**Writers take turns**, as for definitions. One operation reads `run.json`,
checks it, and replaces it atomically. Two writers between that read and the
rename are not detected. The `--expect-seq` guard (below) refuses an operation
based on an outdated view; it is not a lock.

## Where things live

```text
devdocs/<workflow-id>/runs/<run-id>/
  braindump.md          the person's own input (or request.md, see Input)
  plan.md               the executor's plan (optional, free form)
  run.json              the record: current state and its history
  definition/
    <workflow-id>.yaml              the run's workflow, copied byte for byte
    <delegated-workflow-id>.yaml    every workflow it delegates to, transitively
  report*.md, …         whatever the executor reports; names are its choice
```

| Information | Authority |
| --- | --- |
| The person's words | `braindump.md` |
| A request an agent constructed | `request.md` (+ `original-input.md` when given) |
| How the work is approached | `plan.md` and reports — prose; the tools never parse it |
| The executed definitions | `definition/*.yaml`, fixed for the run's lifetime |
| Node states, questions, answers, relations, artifact references, acceptance, history | `run.json` |
| Current editable definitions | `devdocs/workflows/*.yaml` (not the run's) |

Every path in these files is project-relative POSIX or run-relative. Machine
paths, credentials and local process details stay out; local execution
settings belong under ignored `.local/` paths.

Saving a file never commits. Commit devdocs at meaningful milestones; when the
project is published, commit its updated `devdocs` gitlink in the project root
as well. A browser view follows saved files before any commit.

### Identifiers

| Identifier | Pattern | Notes |
| --- | --- | --- |
| Workflow id, node id | `^[a-z0-9][a-z0-9_.-]{0,63}$` | from the definition contract |
| Run id (= directory name) | `^run-[a-z0-9][a-z0-9_.-]{0,59}$` | `run-001`, `run-002`, … by default (next number after the highest `run-NNN`), or `run-<name>` |
| Run reference | `<workflow-id>/<run-id>` | unique in a project; two invocations of one workflow have two run ids |
| Question id | `^q[0-9]{1,6}$` | `q1`, `q2`, … in order of asking, per run |
| History sequence | integer, 1, 2, 3, … | strictly increasing, no gaps |

Timestamps are ISO 8601 UTC with milliseconds (`2026-10-10T12:34:56.789Z`,
JavaScript `toISOString()`). They come from the writer's clock and are
display facts only: nothing expires, fails or completes because of a time.

**Creating a run never overwrites.** The run directory is created exclusively;
an existing name is refused ("run-001 already exists") and nothing in it is
changed. A name that does not match the pattern is refused before anything
is written.

## Input

| Kind | File | Who wrote the words | Required facts |
| --- | --- | --- | --- |
| `braindump` | `braindump.md` | the person | `author` (the person's name) |
| `request` | `request.md` | an agent, on someone's behalf | `requester` (the agent), `entrustedBy` (reference), optional `onBehalfOf` |

`braindump.md` holds the person's own words. An agent that saves them is
recorded as `recordedBy`; that does not make them an agent's request. An agent
that writes its own request — rewording a person's input, or delegating — uses
`request.md` and records the reference to what entrusted it: a parent run and
node (`{kind: "run", workflow, run, node}`), a project file (`{kind: "file",
path}`), or a free reference such as a conversation (`{kind: "note", text}`).
When a derived request was built from a person's input, `--original <file>`
keeps that input beside it as `original-input.md`. No tool writes a human
author it was not given.

## Definition snapshot

At creation the workflow is read from `devdocs/workflows/`, validated with the
editor's rules (errors refuse the run; warnings are kept as facts), and copied
byte for byte to `definition/<id>.yaml` together with every workflow it
delegates to, transitively. The bundle keeps layout, approvals and comments.

`run.json` records, per bundled workflow: the bundle file, the source file it
was copied from, `sha256` of the copied bytes, the semantic definition digest
(`definitionDigest`, the same projection as definition approval), and the
approval states at that moment. The byte digest is what reading checks: a
bundle file that is missing or differs from its recorded `sha256` makes the
record **inconsistent**.

The bundle never changes. Later edits, renames or deletion of the source
workflow do not change the run's graph. The run view shows the snapshot and
compares it with the current source (same definition, changed, renamed,
deleted). A run on a changed definition is a new run (`--predecessor
<run-ref>` records the link).

A **delegated (child) run** gets its bundle from the parent's bundle — the
delegate target and its own transitive delegates — never from the current
source files. So a child created after the source was edited or deleted still
runs the parent's captured version, and the child's bundle is self-contained.

Definition approval stays a statement about a definition. Its state is
recorded and shown; it is not a gate, not permission to execute and not
acceptance of a result.

Repository context: at creation the record keeps, for the project root and
each repository the bundled workflows bind, the checked-out commit, the branch
and the number of uncommitted entries. That is context. It does not snapshot
repository contents, and a commit hash does not include uncommitted files.

## `run.json`

```json
{
  "schema": "ag.workflow-run.v1",
  "workflow": "build-game",
  "run": "run-001",
  "created": "2026-10-10T12:00:00.000Z",
  "input": { "kind": "braindump", "file": "braindump.md", "author": "A. Person", "recordedBy": "Omni Agent" },
  "executor": { "name": "Omni Agent", "backend": "claude-code / claude-opus-5-5" },
  "predecessor": null,
  "parent": null,
  "definition": {
    "root": "build-game",
    "workflows": {
      "build-game": {
        "file": "definition/build-game.yaml", "source": "devdocs/workflows/build-game.yaml",
        "sha256": "…", "definitionDigest": "sha256:…",
        "approvals": { "intent": "approved", "definition": "stale" }
      }
    },
    "warnings": []
  },
  "context": { "repositories": [ { "path": ".", "head": "1ad073e…", "branch": "main", "dirty": 0 } ] },
  "nodes": {
    "survey": { "state": "completed", "updated": "…", "started": "…", "ended": "…",
                "outcome": { "text": "…", "artifacts": ["devdocs/build-game/runs/run-001/report1.md"] },
                "notes": [], "wait": null, "children": [] }
  },
  "questions": {},
  "artifacts": [],
  "decisions": [],
  "cancelled": null,
  "execution": { "state": "in-progress", "counts": { … }, "ready": [ … ], "blocked": [ … ] },
  "started": "…", "ended": null, "updated": "…", "seq": 7,
  "history": [ { "seq": 1, "at": "…", "by": "Omni Agent", "via": "cli", "op": "run.create", … } ]
}
```

### One reducer, current state and history

Every state-changing operation is one **history entry** (`seq`, `at`, `by`,
`via`, `op`, its parameters, and the `change` it made). The current state is
exactly what `shared/run.ts` `replay()` computes from the history and the
bundled graph. An operation appends the entry and writes the replayed state
in the same atomic replacement of `run.json`.

Reading replays the history and compares it with the stored state. Missing,
malformed or inconsistent records are visible errors — never an empty or
successful run — and are never rewritten automatically: operations refuse a
record that does not read cleanly. `wfe run check` names the difference. The
CLI and the service use the same module, so they cannot disagree on rules.

`via` is `cli` or `browser`. `by` is the declared actor: the CLI defaults to
the run's executor and takes `--by <name>`; the browser asks for a name. Both
are declarations, as approvers are.

### Node states

| State | Meaning | Entered by |
| --- | --- | --- |
| `pending` | Work has not started | creation |
| `running` | The executor recorded that work started (reported progress, not process health) | `start` when ready; `start` again (resume) from `waiting` or `failed`; `take-up` |
| `waiting` | Work awaits an identified answer, child run or external result | `ask`, `delegate`, `wait` |
| `completed` | The executor recorded completion with an outcome | `complete` from `running` |
| `failed` | A recorded problem prevents continuation | `fail` from `running` or `waiting` |
| `cancelled` | Work was explicitly discontinued (final) | `cancel` from `pending`, `running`, `waiting` or `failed`; run cancellation |

- A node is **ready** when it is `pending` and every predecessor is
  `completed`. Only a ready node can start. A join therefore waits for all of
  its predecessors.
- `failed` and `cancelled` never satisfy a dependency. A pending node behind
  one is **blocked** (derived, shown, not stored as a state).
- Resuming a `failed` node (`start`) needs a reason and is recorded as such;
  nothing retries by itself.
- `complete` needs an outcome text and may name artifacts. A delegate node
  completes only when its latest child run's execution is `completed`; the
  operation reads the child and records its state and sequence as evidence.
  A missing, failed or cancelled child is refused with that fact.
- `progress` adds a note to a `running` or `waiting` node without changing
  its state. It updates the node's `updated` time.

Independent branches may be performed one after another; nothing runs nodes
by itself, and no timer changes a state.

### Waiting

A waiting node records `wait: {reason, holder, on}` where `on` is one of
`{question: "q1"}`, `{child: {workflow, run}}` or `{external: "<reference>"}`,
and `holder` names who or what holds the next move: the person a question is
addressed to, the child run, or the named external party. The view derives the
current holder: once a question has an answer that is not yet taken up, the
holder is the executor.

### Questions

`ask` records a question with a stable id, its text, to whom it is addressed,
and optionally its node; a running node then waits on it. A node waits on one
thing at a time; asking from an already waiting node is refused.

| Record | Effect on the node |
| --- | --- |
| `answer` (text; `from` who gave it, `by` who recorded it) | none — the node keeps waiting. Several answers may be recorded; each names its question. An agent relaying the person's reply from the IDE records `from` = the person, `by` = itself |
| `take-up` (who took it up, which answer) | the node waiting on that question resumes `running` |
| `withdraw` (reason) | the question is closed without an answer; a node waiting on it resumes `running` |

An answer to another question leaves a node waiting. Recording an answer is
not taking it up, taking it up is not completing the node, and none of these
is accepting a result.

### Delegated runs

`delegate <run> <node>` (on a `running` delegate node) creates the child run
`devdocs/<target>/runs/<child-run>/` with a `request.md`, `entrustedBy:
{kind: "run", workflow, run, node}`, `parent: {workflow, run, node}` and the
bundle from the parent; then the parent node waits on the child and lists it
in `children`. The child is written first: if the parent update then fails,
the child names a parent that does not list it, and both views show that.
Children of one node keep their history; a new delegation needs the node
`running` again.

The parent node's completion requires the child's recorded `completed`
execution (see Node states). Taking up a child's result is `start` (resume)
on the parent node, then `complete`.

### Execution summary (`execution`)

Derived after every operation; the counts keep mixed facts visible.

| `state` | When |
| --- | --- |
| `cancelled` | the run was cancelled (`cancel` without a node) |
| `completed` | every node is `completed` |
| `not-started` | every node is `pending` |
| `in-progress` | some node is `running` or `waiting`, or some node is ready |
| `stopped` | none of the above: nothing runs, waits or is ready, and some node is `failed` or `cancelled` |

`execution` also lists `counts` per state, `ready` and `blocked` node ids, the
`active` (running) and `waiting` nodes with holders, and `failed` nodes.
Execution succeeds only when every node is `completed`. Run `started` is the
first node start, `ended` the operation that made the state `completed`,
`stopped` or `cancelled` (cleared again if a later resume reopens it).

### Acceptance

`decide <run> --decision accepted|rejected --by <name> --evidence <ref>`
records a decision on the result, with actor and evidence. `accepted` is only
recorded on a `completed` execution; `rejected` at any time. A completion
record, an answer, or a definition approval never creates a decision.

### Artifacts

`attach` records a project-relative path (usually a report in the run
folder), optionally with its node and a title. `complete --artifact` does the
same for a node's outcome. A path that leaves the project is refused; a path
that does not exist when attached is recorded with a warning and shown as
missing.

## Operations

All operations are in `server/runs.ts` (files) over `shared/run.ts`
(reducer, readiness, summary, validation). `wfe run …` and the service's
HTTP routes call them; neither needs the other running.

| Operation | `wfe run` | HTTP (`/api/workspaces/<ws>/…`) | Browser |
| --- | --- | --- | --- |
| Create a run (snapshot, input) | `create <workflow> --braindump <file>` / `--request <file> --entrusted-by …` | — | — (input comes through the IDE; see below) |
| List runs | `list [<workflow>]` | `GET runs` | project view → Runs |
| Inspect a run, its definition, ready nodes, history | `show <run> [--history] [--rev <commit>]`, `check` | `GET runs/<wf>/<run>` | run view |
| Start / resume, progress note | `start`, `progress` | `POST runs/<wf>/<run>/ops` | — |
| Wait, complete, fail | `wait`, `complete`, `fail` | same | — |
| Cancel a node or the run | `cancel [<node>]` | same | run view → Cancel run |
| Ask, take up, withdraw | `ask`, `take-up`, `withdraw` | same | — |
| Answer | `answer <run> <q>` | same | run view → question → Answer |
| Delegate (child run) | `delegate <run> <node>` | same | — (links to both directions) |
| Attach an artifact | `attach <run> <path>` | same | — (reports listed and readable) |
| Decide on the result | `decide <run> --decision …` | same | run view → Accept / Reject |

The browser offers the person's operations: answering, deciding on the
result, and stopping the run. Execution records (start, complete, wait, …)
are the executor's reports of its own work; the browser shows them and does
not make them, so a click cannot claim work. The person can still record
anything with `wfe run … --by <name>`. Creating a run starts from the person's
words given in the IDE, where the conversation with the executor happens.
Submitting an answer in the browser stores it; it does not launch or wake the
IDE agent. The person continues the conversation in VS Code.

`test/runs.test.ts` ("operation parity") runs every operation, including
delegation, once through the CLI module and once over HTTP, and requires the
same record apart from route and times.

`--expect-seq <n>` (browser: always sent) refuses an operation when the
record's last sequence is not `n`, so an answer typed against an outdated view
is not applied silently.

## Access

Repository bindings (`readonly` / `editable`) in the run's bundled
definition are declarations the executor checks itself before changing a
repository a node uses; nothing enforces them at the OS level. Writing the run
folder (`run.json`, plans, reports) is the reporting capability every run has.
It does not grant write access to a repository bound `readonly`, and devdocs
being `readonly` in a workflow does not forbid recording that workflow's run.
The definition has no allowed-command schema: restrictions supplied for one
run (commands, repositories, anything else) are written into its `plan.md`
and self-checked the same way.

## Setup and entry point

`wfe setup <area>` writes the agent guide (`templates/AGENTS.md`) and the
person's `START.md` with the execution prompt, the run folder pattern, the
CLI (`wfe run help`) and the browser link. It keeps the registry, the
projects, the runs and any generated file whose stamp was removed.

## Observation

The service watches `devdocs/*/runs/*/run.json` with the definition poll
(default 1 s, stat-based; a file is re-read only when its size, modification
time or inode changed) and lists each run folder's top-level files by stat,
without reading report bodies. It sends `run` change events with the run
reference; views re-read that run. Every (re)connection re-reads everything.
An open definition draft is not touched by run events.

No-update duration and an open browser connection say nothing about the
executor's health. Workflow progress and process health are separate.

## Future integration boundary

Run, node and question ids, parent/child references, holders and evidence
references are stable so that later adapters can link them to conversations,
messages (Zulip) and individual agent execution records (Observer,
`devpolicy/agent_records.md`). devdocs keeps durable input, plans,
definitions and results. Authority and synchronization are specified when
those adapters exist; there is no second state authority now.
