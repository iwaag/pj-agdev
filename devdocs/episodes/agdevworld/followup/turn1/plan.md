# Turn 1 plan — agent backend selection for autolab projects, from agdevworld

Episode: `agdevworld/followup` — grow proven workflows with in-system agents and
extend the frontend's input/output. This is a turn-based episode: finish the
turn, write a report, and leave multiple ideas for the next turn.

Turn-1 desire (braindump line 4): let a user, from agdevworld, select the agent
backend for an autolab auto-development project.

## Decisions already made with the human (do not re-litigate)

- **Write path is conversational**: changing a selection goes through the
  autolab front agent (`POST /window`), which edits the project file itself.
  No REST write endpoint.
- **Read path is deterministic REST**: new gateway GET route(s) expose
  projects, their current role profiles, and the available profiles.
- **UI shows, conversation changes**: the agdevworld autolab view displays
  projects and their current profiles (read-only). The only way to change a
  selection is asking the prime agent in chat; no click-to-change selector this
  turn. This keeps the front agent's window as the single entrance for the
  write.
- **Roles in scope**: `coding` and `director` (the two roles a project
  `agents.toml` carries).
- **Node scope**: agstudio only. agautolab1 rollout is a next-turn idea.

## What already exists (the selection mechanism is done; only exposure is missing)

- Profiles live in `agautolab/agents.toml`: `local` (opencode + ollama),
  `sonnet` (claude_code + claude-sonnet-5), `stub` (fake). Machine overlay in
  `.local/agents.local.toml`.
- Per-project selection: `agautolab/.local/projects/<name>/agents.toml` with
  `[roles] coding=... director=...`. Loader:
  `src/agautolab/project_settings.py` (`load_project_roles`, validation,
  `PROJECT_AGENT_ROLES = {"coding","director"}`). Precedence and live evidence:
  episode `devdocs/episodes/agautolab/project_agent_setting/` (89 tests pass).
- Project registry is just directories under `agautolab/.local/projects/` plus
  the hand-written `projects.md` list. Existing projects: `scifi`, `yokai`,
  `project-agent-setting-smoke`.
- Gateway (`agautolab/agent/gateway.py`, stdlib-only, no auth, port 8791):
  read routes + `POST /window` (runs the `front` role, `answer_window`
  ~line 655) + `POST /jobs/<job>/summarize/<iter>`.
- agdevworld assistant passthrough (`agdevworld/assistant/server.mjs:262-306`)
  forwards any method/path to a registered node; only paths containing
  `evidence` are 403'd. **A new gateway route is reachable from the browser and
  from the prime agent's `fetch` tool with zero assistant code changes.**
- Frontend: autolab view is a chip/row grid (`src/views.ts:108-174`,
  `src/scenes/PanelGridScene.ts`), DOM popup with action-button precedent
  (`src/detailPopup.ts:375-441` — summarize button: POST, then poll). Typed
  client in `src/autolabState.ts`.

## Gaps this turn closes

1. Gateway exposes no projects/profiles data, and `job_yaml_fields`
   (`gateway.py:285-308`) drops the `project:` field, so agdevworld cannot even
   show which project a job belongs to.
2. The front role cannot write: `ROLE_ALLOWED_TOOLS["front"]` in
   `src/agautolab/role_run.py:20-21` is `Read,Glob,Grep,Bash(cd:*)` + nested
   director runs. It must gain edit capability before the conversational write
   path can work. Front's default profile is `local` (opencode), so the
   opencode permission surface matters too: `agent/opencode-front.json`.
3. agdevworld has no project display and no selector.

## Steps

### Step 1 — gateway read side (agautolab)

- Add `GET /projects`: enumerate `.local/projects/*/`, return for each project
  its name and current `coding`/`director` values (via `load_project_roles`;
  absent file → role defaults, and say which is which, e.g.
  `{"coding": {"profile": "local", "source": "project"|"default"}}`).
  Include the list of available profiles (parse `agents.toml` `[profiles.*]` —
  reuse the agag loader if importable from the gateway's stdlib-only context,
  otherwise a small TOML read; `tomllib` is stdlib since 3.11). Use a versioned
  envelope like the existing ones (`autolab.projects.v1`).
- Surface `project` in `job_yaml_fields` so job rows and detail show it.
- Malformed project files: return the error visibly per-project, don't 500 the
  whole listing (in-between states are the product — see human-in-loop ex1
  report).
- Tests in the existing pytest suite (currently 89 passing; keep them green).

Done when: `curl :8791/projects` shows real projects with current + available
profiles, and a job row for a project-linked job carries its project name.

### Step 2 — front agent gains the selection capability (agautolab)

- Extend `ROLE_ALLOWED_TOOLS["front"]` with `Edit,Write` (project-wide is fine
  for this phase; scoping to `.local/projects/**` is optional polish), and
  mirror the permission in `agent/opencode-front.json`.
- Tool Giving, not implantation: update the front capability card
  (`agent/GUIDE.md`) with a short paragraph — projects carry
  `.local/projects/<name>/agents.toml`, valid roles are `coding`/`director`,
  valid profiles come from `agents.toml`, and the front agent may edit that
  file when a user asks to change a project's backend. Let the agent do the
  edit its own way; do not script it.
- Live smoke: `POST /window` with e.g. "Set project yokai's coding profile to
  sonnet", then confirm the file changed and `GET /projects` reflects it. The
  front default profile is `local` (ollama) — this smoke is free.

Done when: a window request changes a role in a real project file and the read
route shows the new value.

### Step 3 — agdevworld display + conversational change

- `src/autolabState.ts`: add types + fetcher for `/api/autolab/<node>/projects`;
  add `project` to `AutolabJobRow`/detail.
- Autolab view: show projects and their current coding/director profiles,
  read-only. Simplest fit to existing vocabulary: a projects section (chips or
  rows) in the autolab view, and/or project info inside `detailPopup.ts` when a
  job belongs to one. Implementer's choice. No click-to-change control.
- Conversational change path: the prime agent already reaches everything
  through its `fetch` tool — it reads `GET /projects`, relays a worded request
  to `POST /api/autolab/<node>/window`, and confirms by re-reading. Update the
  assistant capability card (`assistant/GUIDE.md` and the system-prompt copy in
  `assistant/server.mjs:57-60`) so it knows the projects route and the "ask the
  node's window to change it" recipe — a capability description, not a scripted
  procedure.

Done when: against the live agstudio gateway, the view shows real projects with
current profiles, and one chat sentence to the prime agent flips a profile,
visible in the UI after refresh.

### Step 4 — end-to-end proof, docs, turn close

- One live end-to-end pass: pick a project, flip `coding` local→sonnet and back
  through chat with the prime agent, confirm via `GET /projects`, the file, and
  the refreshed view.
- Update `agdevworld/README_DEV.md` (autolab section) and `agautolab` docs the
  implementation touched.
- Write `turn1/report.md`.
- Per the episode's turn protocol, write `turn1/ideas.md` with several
  candidate next turns. Seeds: roll out to agautolab1 (gitea push + ansible);
  start missions/jobs from agdevworld; per-job profile override at submission;
  gateway auth; node-freshness check (deploy-source HEAD vs node checkout);
  register autolab in nintent so the node picker derives from cluster state.

## Constraints (minimum set)

- Never commit anything under `.local/` or real hostnames/tokens; `AUTOLAB_NODES`
  stays in the ignored `.env`.
- Keep the passthrough's `evidence` 403 as-is.
- Generated docs in English (devpolicy/styles.md); no absolute local paths in
  committed files.
- No backward-compatibility burden — this is a destructive phase; reshape
  payloads/routes freely.
- Unauthenticated conversational writes are accepted for this experimental
  phase (consistent with the existing zero-auth gateway stance).
- Deus Ex Machina note (devdocs/README_DEV.md): if you edit a project's
  `agents.toml` directly instead of going through the front agent (e.g. while
  debugging), leave the one-line "did X for agent Y — handoff candidate" note
  in the episode doc. The note is the whole obligation.

## Hints, gotchas, free advice

- **Test through the container, not bare node**: on this Mac a native `node`
  process gets `EHOSTUNREACH` to LAN; drive the passthrough via
  `localhost:8091` (assistant container). (`.local/devenv.md`)
- The gateway runs natively, started by hand:
  `cd agautolab && nohup python3 agent/gateway.py > .local/agent/gateway/serve.log 2>&1 &`.
  Restart it after gateway changes; it is not under compose/launchd.
- `POST /window` replies containing a `<<mission ...>>` block start a mission
  (one at a time). A settings conversation shouldn't emit one, but if a smoke
  gets a 409 from `/window`, a mission is likely running — check `/status`.
- Known issue from memory: the outer harness's project instructions can leak
  into in-system agent runs on this machine and kill them on permission
  denials. If a live front run dies oddly, suspect that before suspecting your
  change.
- Don't confuse two "backend" selectors: `agdevworld/README_DEV.md:45` says the
  *prime agent's own* backend has no per-request selector — that statement is
  about the assistant, stays true, and is not this feature. In autolab
  vocabulary the thing being selected is a **profile** (harness+model pair);
  prefer "profile" in code and payloads, "backend" only in user-facing prose.
- `role_run.py` resolves with `check_available=False` first, then re-resolves
  with availability checking for non-fake harnesses — keep that behavior if
  you touch it; it's what makes `stub` work in tests.
- Cheap verification order: pytest (gateway + project_settings) → curl the new
  route → free `/window` smoke (front=local/ollama) → UI. Claude-profile runs
  cost real money; one sonnet-side confirmation at most is plenty.
- Ad-hoc screenshots without adding dependencies:
  `npx --yes playwright@latest screenshot --viewport-size=1280,800 --wait-for-timeout=2000 http://localhost:5173/ shot.png`.
