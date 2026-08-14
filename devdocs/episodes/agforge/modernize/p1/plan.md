# agforge modernize — implementation plan

Realize `braindump.md`. Rebuild agforge's `create-` topic handling into the same
"short concatenated prompt + workspace building" shape as agautolab (renewed),
split it into a front / generator pair, and register `plan.md` as a Plane Work.

This is a destructive phase. The existing `create-` topic path (one charter-based
run) may be replaced outright; no backward compatibility is required. The DM and
`:8092` HTTP charter paths are out of scope and stay as they are.

## Decisions

- Chat log file is `chatlog.md` (same name as autolab)
- `N` increments once per time the topic is served
- Both front and generator use the `sonnet` profile. No cheap-model test runs
- Plane Works carry no `AUTO` label (autolab's `next_work` must not pick them up)
- Built-in tools are handed over through `PATH`. No absolute paths in guides or code

## Prohibitions (these only)

- Do not put the `AUTO` label on Plane issues, and do not create a project whose
  description carries the `[AUTO]` marker
- Do not commit or log credentials from `.local/`
- Do not point a deployment or dependency source at a local path or gitea
  (the standing rule in `devenv.md`)

Everything else — function decomposition, file layout, test granularity, how far
to refactor — is the implementer's call.

---

## Step 1 — workspace and role_run

**Build**

- `src/agforge/role_run.py`, shaped like autolab's `src/agautolab/role_run.py`.
  `run_role(role, prompt, *, cwd, timeout, record)` goes
  `agag.agent_config.resolve_role` → `agag.harness.run_harness` and writes an
  `ag.agent-run.v1` record to `.local/agent/<role>/run-NNNN.json`.
- Add `[roles.front]` to `agents.toml`. Both `front` and `generator` use
  `profile = "sonnet"`.
- Tool grants: `front` gets `Read,Write,Edit,Glob,Grep`; `generator` reuses
  `agent_run.CLAUDE_ALLOWED_TOOLS` as is.

**Hints**

- If a role has no entry in `ROLE_ALLOWED_TOOLS`, `build_argv` omits
  `--allowedTools` entirely and claude_code sits waiting for an interactive
  permission answer until the timeout. autolab's `role_run.py` carries a comment
  about exactly this. Add every new role to that table.
- `run_harness` launches with `env = {**os.environ, **agent.environment, ...}`
  (pyagag `src/agag/harness.py`). **That is the PATH injection point.** The
  existing `agent_run._local_tool_environment()` already prepends `.local/bin`;
  generalize it into a function in `role_run` that also prepends `scripts/`, and
  share it with `resolve_generator()`.
- `scripts/generate.sh` `cd`s to the agforge root itself, so it works from a
  topic workspace as cwd, and its exec bit is already set. With `PATH` in place,
  the bare `generate.sh` in `create_generator/tools.md` becomes true as written.
- Build workspace paths with `agag.zulip._safe_topic_component`, the way
  autolab's `topic_workspace` does.

**Verify**

- Under the `stub` profile (fake harness), `run_role` writes its record
- `generate.sh` resolves through `PATH` from inside a workspace (one manual check
  is enough)

## Step 2 — the new create-topic workflow

**Build**

- `src/agforge/create_topic.py`. Point `zulip_listener.main`'s topic handler at
  it instead of the current `zulip_chat.react_topic`.

**Flow** (same discipline as autolab's `zulip_listener.handle_topic`)

```
ACK "Message received. Please wait for the reply."   ← agag topic_write
 N = highest existing number under .local/topics/<ch>/<topic>/ + 1
 create <N>/front/, write chatlog.md
 run front:
   "The chatlog is placed in the working directory.
    You are <bot full_name> in the chatlog."
   + agent/guides/create_front/guide.md
 post the front's answer to the topic
 if <N>/front/required_items.md exists:
   create <N>/generator/, copy in required_items.md and
   agent/guides/create_generator/tools.md
   run generator with agent/guides/create_generator/guide_plan.md as the prompt
   plan.md → register a Plane Work (Step 3)
   idea.md → post its contents to the topic verbatim
   post the generator's answer
```

**Hints**

- After the ACK, **every path must post something to the topic before returning.**
  An ACK followed by silence leaves the bot as the last poster, which hides the
  topic from the sweep until a human posts again. autolab carries a step name
  through the handler and posts `failed during <step>: ...`.
- Format the chat log the way autolab's `format_chatlog` does (`[name] body`,
  own messages as `name (you)`). A shared-code candidate.
- `chatlog.md` is only a dump, and the front's answer is relayed verbatim. What
  it wrote in the workspace (whether `required_items.md` exists) is what drives
  the branch.
- Never delete generation directories. Cutting a new `N` is precisely what stops
  a previous generation's `required_items.md` / `plan.md` from being re-executed.
- The `SWEEP_ACK` constant and ack-stripping logic in the current `zulip_chat.py`
  can be reused as is.
- One topic now costs two agent runs, both on sonnet.

**Verify**

- Fake Zulip client + `stub` profile over three paths: (a) no
  `required_items.md` → one post, (b) present → generator runs, (c) exception
  mid-way → `failed during ...` is posted
- One real round trip in a `create-` topic in `#FreeForge`

## Step 3 — Plane Work registration

**Build**

- `src/agforge/plane.py`, local to agforge for now (shared out in Step 5). It
  needs: config loading, project lookup/creation, issue upsert, and `plan.md`
  splitting.

**Routing**

- Channel `pj-<name>` → the Plane project of that name
- Anything else (`#FreeForge` and friends) → the `FreeForge` project, created if
  absent
- If `pj-<name>` does not exist in Plane, fall back to `FreeForge` and say so in
  one line on the topic. Not a failure

**Hints**

- Credentials live at `pj-agdev/.local/plane-credentials.env`. agforge's root has
  the same parent (`pj-agdev`) as agautolab's, so autolab's `PLANE_ENV`
  expression (`PROJECT_ROOT.parent / ".local" / "plane-credentials.env"`) reaches
  it unchanged.
- Port from `agautolab/src/agautolab/project_init.py` (`PlaneConfig`,
  `load_plane_config`, `_request_json`, `_rows`, `_normalized_name`) and
  `mission.py` (`split_document`, `description_html`, `find_issue_by_external`,
  `ensure_issue`, `starting_state_id`, `issue_label`). **Drop `labels` from
  `ensure_issue`** — that is the one place the `AUTO` label gets attached.
- External key: `external_source = "agforge"`,
  `external_id = "<channel>/<topic>"`. autolab uses `external_source =
  "agautolab"`, so the key spaces do not collide. Re-serving updates through the
  same key, so a topic keeps one Work however far `N` climbs.
- `find_issue_by_external` answers **404** when the key is unknown, not an empty
  list.
- `starting_state_id` picks ready → todo → the `unstarted` group → backlog.
  ProjectA's vocabulary is Backlog / Ready / In Progress / Done / Cancelled.
- Plane CE v1.4.1 quirks autolab already hit: the `?parent=` filter is ignored,
  the `sub-issues` endpoint 404s, and `description_stripped` is sometimes None.
  Most of that is moot here since no parent/child issues are created, but issue
  listing does need cursor pagination.
- When creating a project, keep the `[AUTO]` marker out of its description, or
  `next_work` starts scanning it.

**Verify**

- A create topic in `#FreeForge` produces a Work in the `FreeForge` project with
  no labels (check in the Plane UI)
- Serving the same topic twice does not duplicate the Work
- One run from a `pj-*` channel, both with and without the matching Plane project

## Step 4 — end-to-end and wiring

- Swap the listener through launchd:
  `launchctl kickstart -k gui/$(id -u)/com.agdev.agforge-zulip`.
  Log: `agforge/.local/out/zulip-listener.log`
- `AGFORGE_ZULIP_LOG_ONLY=1` is the free observer mode; use it to confirm wiring
  without paying for runs
- Resolving a finished topic (`✔ create-…`) takes it out of the sweep
- Leave `report1.md` … per step (AG Standard Style)

## Step 5 — share the common code (converge with agautolab)

pyagag is a shared dependency that both agforge and agautolab reference straight
from GitHub main, and agautolab is shipped to nodes by Ansible. Do this **after
Step 4 works**, as a refactor that changes no behavior.

- Move into `agag`: `topic_workspace` / generation numbering / `format_chatlog` /
  `next_record_path` / `guide()` / front prompt composition / the "ACK → run the
  steps → always reply → re-check for human posts that arrived during the run"
  skeleton / the Plane client from Step 3
- Keep out of `agag`: sub-work generation keys, `next_work`, `start.flag` /
  `cancel.flag`, project clones
- Move autolab onto the same base, and introduce the `(N)` generation directory
  while doing it (this is where `braindump.md`'s "autolab has no N" note gets
  fixed; splitting it into its own episode is fine)
- Touching pyagag costs a push → `uv lock --upgrade-package pyagag` round trip.
  Keeping the Plane client local to agforge in Step 3 is what keeps that round
  trip out of the implementation loop
- Afterwards, push to GitHub and then run `setup_autolab_node.yml`. Not the gitea
  mirror
