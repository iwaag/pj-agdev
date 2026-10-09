# Workflow and project editor (experiment, `workflow_editor` p1)

A standalone MVP that edits Git-backed project and workflow definitions from a
browser UI while the same YAML files stay editable in any text editor or agent
IDE. The file contract is in [docs/contract.md](docs/contract.md).

**Writers take turns.** UI edits and external edits are assumed not to overlap.

## Layout

| Path | Purpose |
| --- | --- |
| `shared/` | Models, validation, canonicalization and digests (service and browser) |
| `server/` | Local service: YAML round-trip, Git inspection, file persistence, watching |
| `src/` | Browser UI (TypeScript, Vite, DOM cards and SVG edges) |
| `examples/` | Synthetic project and workflow files; `invalid/` for validation tests |
| `scripts/seed.ts` | Builds the local fixture repositories and workspaces |
| `test/` | `node --test` suites |

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

Open the page and pick a workspace. The service reads the registry at
`pj-agdev/.local/workflow-editor/registry.json` by default
(`--registry <file>` or `WFE_REGISTRY` to change; `--port`, `--poll-ms`).

The service binds to 127.0.0.1 only and answers only to `127.0.0.1` /
`localhost` host names. Browser writes are accepted from its own origin and
the Vite dev origin; clients without an `Origin` header (curl, scripts) are
local processes and may write too.

## Checks

```sh
npm test        # contract, persistence and Git fixture tests
npm run check   # type check, tests and production build
```

Browser checks drive the real UI with `playwright-core` and its cached
Chromium. They need a fresh seed, the service and the dev server, and write
screenshots to `pj-agdev/.local/workflow-editor/screenshots/`:

```sh
npm run seed -- --reset && node checks/step2.ts
npm run seed -- --reset && node checks/step3.ts
npm run seed -- --reset && node checks/step4.ts
```
