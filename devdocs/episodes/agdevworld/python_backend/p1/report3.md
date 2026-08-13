# Phase 1, step 3 — the MCP command repointed, the JS service deleted

Done. Both call sites now launch the Python service, `assistant/tool-service.mjs`
and its test are gone, `npm test` is still green (44 cases, down from 48 — the
four deleted ones), and `git grep tool-service.mjs` is empty.

## The two call sites

| Site | Now | Why |
|---|---|---|
| `opencode.json` → `mcp.agdevworld.command` | `["python3", "assistant/agdevworld_assistant/tool_service.py"]` | OpenCode runs with cwd = the agdevworld root, so the relative path resolves both at `/app` in the container and in a native run. `timeout: 65000` left alone — it must stay above the 60 s `wait` cap |
| `assistant/harness.mjs:9-11,138` | `command: AGDEVWORLD_PYTHON ?? 'python3'`, `args: [<abs>/assistant/agdevworld_assistant/tool_service.py]` | Claude Code runs with cwd = a per-run temp directory, so the path stays absolute, resolved from `import.meta.url` exactly as before. The interpreter is a bare `python3` with an env override — no venv path, which would break the native workflow |

`process.execPath` (the node binary) is what the `command` no longer is; that
was the only line in `harness.mjs` that had to change besides the constant.

## Also removed / updated

- `assistant/tool-service.mjs`, `assistant/tests/tool-service.test.mjs` — deleted.
- `package.json`'s `test` script left alone, as instructed; it globs
  `assistant/tests/*.test.mjs` and simply finds one file fewer.
- `README_DEV.md` line 27 now names `assistant/agdevworld_assistant/tool_service.py`
  and mentions `uv run pytest`. The full rewrite stays a phase-4 job.
- `.dockerignore` gained `**/.venv`, `**/__pycache__`, `**/.pytest_cache`. Not in
  the plan, but `assistant/Dockerfile` does `COPY assistant/ ./assistant/`, and
  without this the macOS-built virtualenv from step 1 would be baked into the
  Linux image. Cheap to fix here, confusing to debug in step 4.

## Evidence

```
$ npm test
ℹ pass 44   ℹ fail 0

$ git grep tool-service.mjs
(empty)

$ printf '…tools/list…' | python3 assistant/agdevworld_assistant/tool_service.py
→ fetch, wait, switch_view, show_image
```

The absolute path `harness.mjs` computes was checked to exist from the same
`dirname(import.meta.url)` base the harness uses.

No fallback was introduced: with the `.mjs` file deleted there is nothing to fall
back to, so a Python service that fails to start fails the run, as required.

Both harness paths are only *claimed* to work until step 5 runs them for real —
that is what step 5 is for. Step 4 first proves the interpreter exists in the
image.
