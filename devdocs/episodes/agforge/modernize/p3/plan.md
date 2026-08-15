# p3 plan: agforge CLI, toolsets, tools/ folders, failure.flag

Realize `braindump.md`. The guides are already committed (`19fa4ea change guide`);
this plan changes the code and specs to match them. Destructive phase: no
backward compatibility required anywhere.

Naming decisions (guide/toolset files are the source of truth over braindump
spelling): files are `toolset-*.md` (hyphen), the CLI is
`agforge toolsets --list`, `agforge image generate`, `agforge video generate`.

The only standing prohibition, from the braindump itself: do not add guide
text to work around generation failures. New usage information belongs in CLI
`--help` output and `agent/toolsets/*.md` (that is Tool Giving, fine).
Everything else is implementer's discretion — this is a private experimental
environment.

## Step 1 — `agforge` CLI skeleton and tool grants

- New `src/agforge/cli.py` with subcommands; register
  `agforge = "agforge.cli:main"` in `[project.scripts]` of `pyproject.toml`.
- `agforge toolsets --list`: scan `agent/toolsets/toolset-*.md`, print one
  line per file: name (no extension) plus the body of its leading
  `# Description` section. This output is what the front copies into
  `toolsets.csv`, so keep it one-line-per-toolset and stable.
- `agforge image generate ...`: rewire the existing `agforge.generate` main
  as a subcommand (same flags, same "presigned URL on the last line"
  contract). Keep `scripts/generate.sh` working or delete it and update the
  image toolset doc — implementer's choice; nothing else references it after
  this phase except `runcreate_topic.upload_result`, which imports the module,
  not the script.
- Bare-name reachability for subagents: add a `scripts/agforge` shell shim in
  the style of `scripts/generate.sh` (`cd "$(dirname "$0")/.." && exec uv run
  agforge "$@"`). `role_run.tool_environment` already prepends `scripts/` to
  PATH for every role, so no other wiring is needed.
- Tool grants in `src/agforge/role_run.py` — this is load-bearing:
  - front is currently `Read,Write,Edit,Glob,Grep` and the new guide tells it
    to run a Bash command. Add `Bash(agforge:*)`. Without it the front hangs
    on a permission prompt until timeout (known trap, see the comment above
    `ROLE_ALLOWED_TOOLS`).
  - add `Bash(agforge:*)` to `CLAUDE_ALLOWED_TOOLS` (generator) too.
- Fix the copy-paste bug in `agent/toolsets/toolset-video.md`: its
  `# Description` says "speech"; make it video (this text surfaces in
  `toolsets --list`). Also "othre" → "other".

## Step 2 — `agforge video generate --prompt "..."`

New module (suggested `src/agforge/comfy_video.py`), prompt-only, no other
parameters for now.

- Workflow file: `.local/resources/comfywf/video/minimax_h3_t2v_turbo.json`,
  already exported in **API format** (verified: a dict of
  `id -> {class_type, inputs}`). It is git-ignored; fail with a clear message
  if missing.
- Inject the prompt into the node with `class_type ==
  "MiniMaxH3ImageToVideo"` (`inputs.prompt`). Match by class_type, not node
  id — ids change on re-export.
- Randomize `RandomNoise.inputs.noise_seed` per run, otherwise every video
  comes out identical (the file carries a fixed seed).
- Duration is fixed at 5 s by a `PrimitiveFloat` node; leave it alone.
- Submit: `POST {AGFORGE_COMFYUI_URL}/prompt` with body
  `{"prompt": <workflow dict>}`; response carries `prompt_id`. Poll
  `GET /history/<prompt_id>` until it has an entry; its `outputs` contain the
  `SaveVideo` node's `{filename, subfolder, type}` (the prefix is
  `video/MiniMax_H3`, so expect subfolder `video`). Download via
  `GET /view?filename=...&subfolder=...&type=output`. When in doubt, run once
  and inspect the history JSON — the endpoint answers plain GETs.
- Endpoint: add `AGFORGE_COMFYUI_URL=http://agpc.local:8188` to `.local/.env`
  and read it like the SwarmUI URL. Verified live 2026-08-15 (ComfyUI 0.33.1
  answered `/system_stats`); Nautobot desired state places `comfyui-agpc`
  there. Nautobot's observation of the service is stale — trust the probe.
- Deliver like image: add `.mp4`/`.webm` to `generate.CONTENT_TYPES`, reuse
  `upload_and_presign`, print the presigned URL as the last line.
- Generation takes minutes; give the HTTP polling a generous budget (~600 s
  total fits inside the runcreate generator's 1200 s run budget).

## Step 3 — create flow: `toolsets.csv` → `tools/`

In `src/agforge/create_topic.py`, `handle_generator`:

- Drop the single-file `tools.md` copy (the source file is already deleted).
- If the front wrote `toolsets.csv` in its generation dir, copy each listed
  toolset from `agent/toolsets/` into `generator_dir/tools/`. Accept lines
  with or without the `.md` extension and with the `--list` description tail;
  skip unknown names with a log line rather than failing (agent-first: keep
  the run going).
- No `toolsets.csv`, or nothing resolvable → empty `tools/`. The guide
  already routes that case: the generator asks back, writes `idea.md`, or
  declines.
- The new ask-back behavior in `guide_plan.md` needs no code: the generator's
  answer is already posted verbatim, plan.md/idea.md absent is already legal.

## Step 4 — Plane `[TOOLS]` footer, runcreate `tools/`, `failure.flag`

Decision taken with the developer: the tools list rides in the Work's
**description footer**, not a comment — `next_work` already reads the
description, and comments would need a new list API in agag.plane.

- `plane.register_plan`: append one final line to the description,
  `[TOOLS] toolset-image, toolset-video` (the toolsets actually placed in
  `tools/` for this generation; omit the line when there were none).
- `runcreate_topic.prepare_workspace`:
  - parse and strip the `[TOOLS]` line; write `plan.md` without it; build
    `tools/` from the named files. No footer (hand-made Work) → copy all
    toolsets; unknown name → skip with a log line.
  - delete the `tools.md` copy and the `TOOLS_FILE` constant.
  - remove a leftover `failure.flag` here, so a re-trigger starts clean.
- After the run, if `failure.flag` exists in the workspace: treat the run as
  failed — `report_work(..., success=False)` so the Work stays selectable,
  and say so in the topic summary and origin delivery. Exit code stays the
  first-class failure signal; the flag is the agent's own verdict on top.

## Step 5 — specs, tests, deploy

- `README_DEV.md` Map: replace the `generate.sh` entry with the `agforge`
  CLI, mention `agent/toolsets/` and the `toolsets.csv` → `tools/` flow.
- Update the docstring diagrams in `create_topic.py` and
  `runcreate_topic.py` (both still say `tools.md`).
- Tests (existing style: deterministic shell, no live services):
  `toolsets --list` output; csv → `tools/` copy incl. lenient name
  resolution; `[TOOLS]` footer append/parse/strip round-trip; `failure.flag`
  → success=False branch; video subcommand's clear error when
  `AGFORGE_COMFYUI_URL` or the workflow JSON is missing. Live ComfyUI is
  checked by hand, not by pytest.
- Deploy: commit → push (localrule), then reload both launchd jobs that load
  this package:
  `launchctl kickstart -k gui/$(id -u)/com.agdev.agforge-zulip` and
  `launchctl kickstart -k gui/$(id -u)/com.agdev.agforge`.
- Verify end-to-end with one FreeForge topic that requests a short video;
  watch `agforge/.local/out/zulip-listener.log` and the Plane Work. Every DM
  or `create-` message is a paid run — one round is enough.
- Write `p3/report.md`.

## Hints and known traps

- `tool_environment` PATH injection is per-role and already covers both
  roles; if the shim works for the generator it works for the front.
- `run_harness` merges `os.environ`; when testing the shim by hand, remember
  the launchd jobs have their own PATH (the plist sets it).
- `generate.load_env`/`upload_and_presign` exit via `sys.exit`; the video
  path will be called from `runcreate` context too if a plan says so — the
  existing `upload_result` SystemExit-to-ListenerError wrapper shows the
  pattern if you need it elsewhere.
- Old Works created before this phase carry no footer and their descriptions
  were composed from plan.md verbatim; the all-toolsets fallback covers them.
  No migration needed (destructive phase).
- The comfy workflow also decodes audio (`VAEDecodeAudio`) — the MP4 should
  arrive with sound; check it once during the live verification.
