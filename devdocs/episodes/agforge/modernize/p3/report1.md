# p3 report 1 — the `agforge` CLI skeleton and its tool grants

Step 1 of `p3/plan.md`. The result is one command name, `agforge`, reachable
by its bare name from every role's workspace, carrying the two subcommands
the new guides and toolsets already assume.

## What was built

- `src/agforge/cli.py` — the whole CLI. `build_parser()` assembles
  `toolsets` and `image generate`; each subparser carries its own `run`
  default, so `main()` is three lines and adding `video` in Step 2 touches
  one place.
- `agforge toolsets --list` scans `agent/toolsets/toolset-*.md` and prints
  one line per file:

  ```text
  toolset-image, General image generation & editing tools
  toolset-music, General music generation & editing tools
  toolset-speech, General speech generation & editing tools
  toolset-video, General video generation & editing tools
  ```

  `describe_toolset` takes the body of the leading `# Description` section
  (down to the next heading) and collapses it to one line. A file without
  that heading is still listed, with an empty description — the front should
  see every toolset that exists, and a malformed one is evidence, not a
  reason to hide it. The name is the first comma-separated field; that is
  the contract Step 3's `toolsets.csv` reader will hold to.
- `agforge image generate …` is the existing `agforge.generate` main, not a
  copy of it: `generate.py` grew `add_arguments(parser)` and `run(args)`,
  and its own `main()` is now those two called in sequence. Same flags, same
  "presigned URL on the last line" contract, one definition.
- `scripts/agforge` — the shell shim, in `generate.sh`'s style
  (`cd "$(dirname "$0")/.." && exec uv run agforge "$@"`).
  `role_run.tool_environment` already prepends `scripts/` to PATH for every
  role, so nothing else needed wiring. Verified from an unrelated cwd:

  ```sh
  PATH="$PWD/scripts:$PATH" sh -c 'cd /tmp && agforge toolsets --list'
  ```
- `agforge = "agforge.cli:main"` in `[project.scripts]`.

## Tool grants

The load-bearing part. `Bash(agforge:*)` was added to both:

- `ROLE_ALLOWED_TOOLS["front"]`, which was `Read,Write,Edit,Glob,Grep` while
  its new guide tells it to run `agforge toolsets --list`. Without the grant
  the front would have sat on a permission prompt until its 360 s timeout —
  the trap the comment above that table warns about.
- `CLAUDE_ALLOWED_TOOLS`, the generator's grant, which `agent_run` shares
  with the request service.

## Decisions

- `scripts/generate.sh` stays. The plan left it to the implementer;
  `service/charter.md` still names it as the request service's generation
  tool, and keeping it is one line where deleting it is a second entrance's
  worth of edits for no gain in this phase. Nothing new points at it — the
  toolset documents name `agforge image generate`.
- `agforge toolsets` without `--list` is a usage error, not an empty answer.
  There is nothing else that subcommand does yet, and a silent success would
  read to an agent as "no toolsets exist".

## Corrections to the plan

`agent/toolsets/toolset-video.md` did **not** say "speech" in its
`# Description` — commit `19fa4ea` already had it as "General video
generation & editing tools". Only the `othre` → `other` typo needed fixing,
and it was.

## Test state

`uv run pytest -q` → 116 passed, 8 failed. All eight are
`tests/test_runcreate_topic.py` failures that predate this step (verified by
stashing the step's changes and re-running): they want
`agent/guides/create_generator/tools.md`, which the guide commit already
deleted. Steps 3 and 4 remove that copy from the code, and Step 5 rewrites
those tests.
