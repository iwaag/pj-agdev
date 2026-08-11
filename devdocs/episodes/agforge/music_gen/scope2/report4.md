# Step 4 Report — Tool Giving to agforge

Date: 2026-08-11 (Asia/Tokyo)

## Result

agforge request agents can now discover and run ACE Studio's CLI for desires
that require sung vocals or lyrics. The implementation is committed in the
`agforge` submodule as `0fc8484` (`feat: expose ACE Studio CLI to request
agents`).

The committed charter guidance is deliberately lean:

- ACE Studio is the sung-vocal/lyrics path, distinct from the instrumental
  music-generation service;
- the running desktop app is controlled through `$ACE_STUDIO_CLI`;
- the CLI documents itself through `help` and `help --search`;
- structured `--json` commands are preferred.

`service/GUIDE.md` now advertises sung vocals with lyrics and explicitly says
that this path uses stock voices rather than cloning or uploading voices.

## Local path and grants

The host-specific absolute executable path is not committed. It is stored in
the ignored file `agforge/.local/ace-studio.env` as `ACE_STUDIO_CLI`. The
runner reads only that allowlisted key with a non-shell parser and injects it
into the selected harness environment for each request.

Both harness permission surfaces were extended for `$ACE_STUDIO_CLI`:

- OpenCode's deny-by-default Bash map permits the quoted and unquoted variable
  invocation forms;
- Claude Code's explicit allowed-tools list contains the corresponding forms.

A live smoke run used the deployed `local` profile (OpenCode with
`ollama/qwen3.6:35b-a3b-coding-nvfp4`) to execute
`"$ACE_STUDIO_CLI" status project --json`. It succeeded in two turns and
reported the current new temporary project. The ignored transcript is:

```text
agforge/.local/out/scope2-tool-grant-smoke.agent.jsonl
```

This verifies the actual local-profile tool grant rather than only inspecting
configuration text. The run did not use an unsafe permission mode.

## Verification

```text
uv run pytest -q
60 passed in 4.25s
```

The suite includes checks that the charter exposes the tool, the quoted path
with spaces is parsed correctly, and unrelated local environment keys are not
imported.

## Next

Proceed to the end-to-end request. The first run will intentionally receive no
cache-extraction recipe; additional Tool Giving will be added only if its
observed failure requires it.
