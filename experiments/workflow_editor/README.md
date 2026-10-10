# Workflow and project editor (experiment, `workflow_editor` p1, p2/pre1, p3/pre1)

A standalone MVP that edits Git-backed project and workflow definitions from a
browser UI while the same YAML files stay editable in any text editor or agent
IDE. The file contract is in [docs/contract.md](docs/contract.md); workflow
runs (execution records) are in [docs/runs.md](docs/runs.md).

**Writers take turns.** UI edits and external edits are assumed not to overlap.

## Layout

| Path | Purpose |
| --- | --- |
| `shared/` | Models, validation, canonicalization and digests; `run.ts`, the run reducer (service, CLI and browser) |
| `server/` | Local service: YAML round-trip, Git inspection, file persistence, watching, project creation and registration; `runs.ts`, run folders and operations |
| `cli/wfe.ts`, `cli/run.ts` | `wfe`, the command-line surface over the same modules (`wfe help`, `wfe run help`) |
| `src/` | Browser UI (TypeScript, Vite, DOM cards and SVG edges) |
| `examples/` | Synthetic project and workflow files; `invalid/` for validation tests |
| `scripts/seed.ts` | Builds the local fixture repositories and workspaces |
| `test/` | `node --test` suites |
| `checks/` | Browser checks and the update measurement (`measure.ts`) |

## Fixture

```sh
npm ci
npm run seed -- --reset
```

The seed creates bare source repositories, a project `pj-demo` with `devdocs`,
`study/*`, `wedo/*` and `assets/shared` submodules (relative URLs), and two
workspaces `a` and `b` cloned from it, under `pj-agdev/.local/workflow-editor/`
(ignored). Workspace A leaves `assets/shared` uninitialized. The registry of
workspaces is `registry.json` there; it is machine-specific and never tracked.
Local file transport for submodules is enabled per command
(`-c protocol.file.allow=always`), not in any Git config file.

## Start the editor

Development (two processes):

```sh
npm run service   # local service on http://127.0.0.1:8095
npm run dev       # Vite on http://127.0.0.1:5175, proxying /api
```

Single process, serving the production build:

```sh
npm start         # builds, then serves UI and API on http://127.0.0.1:8095
```

The page opens on the projects list (`#/`). The service reads the registry at
`pj-agdev/.local/workflow-editor/registry.json` by default
(`--registry <file>` or `WFE_REGISTRY` to change; `--area`, `--port`,
`--poll-ms` (definitions, default 1000), `--git-poll-ms` (Git state, default 3000)). `wfe serve` builds the UI and starts the service for the
registry it is given.

The service binds to 127.0.0.1 only and answers only to `127.0.0.1` /
`localhost` host names. Browser writes are accepted from its own origin and
the Vite dev origin; clients without an `Origin` header (curl, scripts) are
local processes and may write too.

## Projects: create and register

A project is created or registered from the browser's home page (`#/`,
"Create project" / "Register workspace") or with `wfe create` /
`wfe register`. Both run the same operations (`server/create.ts`,
`server/registry.ts`):

- **Create** makes a Git repository with `project.yaml`, `.gitignore`
  (`.local/`), an empty `.local/` and `devdocs` as a submodule, then registers
  it. devdocs comes from a new local source `sources/<id>-devdocs.git` in the
  authoring area, or from a given existing repository. The submodule URL is
  relative to the project root. Two commits are made with the person's Git
  identity (the new source's initial commit and the root's); a missing
  identity stops creation before anything is written. An occupied destination
  is refused. A creation that stops partway reports what was done and is
  continued with resume ("Continue creation" / `--resume`).
- **Register** records the Git root containing a directory. Repeating it
  changes nothing. What the project lacks is reported with its fix.

The browser creates projects only beneath the service's authoring area
(`--area`, default: the registry's directory); `wfe create` is the caller's
own process and takes any destination. A missing registry is an empty setup
state; a malformed one is shown as an error and never overwritten.

## Authoring area (person + IDE agent)

```sh
node cli/wfe.ts setup ../../.local/workflow-editor-p2 --port 8097
```

creates or refreshes an ignored authoring area, separate from the p1 fixture:

| File | Content |
| --- | --- |
| `AGENTS.md` | the IDE agent's guide, from `templates/AGENTS.md` |
| `CLAUDE.md` | `@AGENTS.md`, so Claude Code reads the same guide |
| `START.md` | the person's steps, from `templates/START.md` |
| `wfe` | launcher pinning the area's registry, area and port |
| `registry.json` | the area's workspaces (created empty if missing, never rewritten) |
| `.claude/settings.json` | Claude Code permissions for `wfe`, Git and edits in the area (created once, then kept) |
| `sources/` | local repositories that projects use as submodules |

The machine-specific paths are filled in only in these generated files. A
generated Markdown file whose first-line stamp was removed counts as edited
by hand, and setup keeps it. Setup never creates a project. The person opens
the area in VS Code and starts the agent there; `START.md` gives the service
command, the URL and a first prompt.

## Command line

`wfe help` lists the commands; `wfe help <command>` says what each reads or
changes, its inputs and its result. No command needs the running service.

```sh
node cli/wfe.ts help          # from the checkout (or: npm run wfe -- help)
```

| Command | Purpose |
| --- | --- |
| `create`, `register`, `list`, `status` | projects, workspaces, Git state |
| `add-repo` | `git submodule add`, as the project view does |
| `workflow new`, `validate`, `approve`, `arrange` | workflows: template, validation, approvals, auto-arrange |
| `run create`, `list`, `show`, `check`, `start`, `complete`, `ask`, `answer`, `delegate`, … | workflow runs (docs/runs.md) |
| `serve` | build the UI and start the service for this registry |

`--registry` / `WFE_REGISTRY`, `--area` / `WFE_AREA` and `--port` /
`WFE_PORT` select the registry, area and service port, with the same defaults
as the service.

## Runs

A run is one execution of a workflow, recorded in
`devdocs/<workflow-id>/runs/<run-id>/`: the person's `braindump.md` (or an
agent's `request.md`), the executor's `plan.md` and reports, a fixed byte copy
of the workflow and its transitive delegates in `definition/`, and
`run.json`, whose current state must equal the replay of its history by
`shared/run.ts`. `wfe run create` makes one; `wfe run start/complete/wait/
ask/answer/take-up/delegate/…` append one history entry each; `wfe run show`
and the browser's run view (`#/ws/<ws>/run/<workflow>/<run>`) show it.
Nothing executes nodes; the executor records what it does, and the tools
enforce readiness (a join waits for every predecessor; failures never satisfy
a dependency). Files are saved, never committed. See
[docs/runs.md](docs/runs.md).

## Checks

```sh
npm test        # contract, persistence and Git fixture tests
npm run check   # type check, tests and production build
```

Browser checks drive the real UI with `playwright-core` and its cached
Chromium. The p1 checks need a fresh seed, the service and the dev server,
and write screenshots to `pj-agdev/.local/workflow-editor/screenshots/`.
`WFE_FIXTURE=<dir>` and `WFE_URL=<url>` point them at a private seed
(`npm run seed -- --root <dir>`) and service instead:

```sh
npm run seed -- --reset && node checks/step2.ts
npm run seed -- --reset && node checks/step3.ts
npm run seed -- --reset && node checks/step4.ts
node checks/e2e.ts   # the p1 acceptance scenario; reseeds by itself
```

These start their own service on a temporary area and registry (after
`npm run build`):

```sh
node checks/setup.ts                  # home view: create, register, registry states
node checks/measure.ts --label <name> --out <file.json>   # update latency, load, probes
```

## Not in p1

Workflow execution, agent chat, Gitea, agdevworld integration, migration of
existing projects, remote workspace discovery, conditional branches, loops,
retries, author authentication, OS-level readonly enforcement and concurrent
editing. The editor never commits or pushes after a project's initial
commits; Git publishing is done by hand.
