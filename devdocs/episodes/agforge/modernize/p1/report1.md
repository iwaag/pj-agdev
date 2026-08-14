# Step 1 — workspace and role_run

## What was built

`agforge/src/agforge/role_run.py`, shaped like agautolab's. It owns three
things that used to be scattered or absent:

- `run_role(role, prompt, *, cwd, timeout, profile, transcript, record)` —
  resolve → `agag.harness.run_harness` → `ag.agent-run.v1` record. The
  caller's `cwd` always wins; no role is pinned to a fixed workspace, because
  the listener points each role at its own generation directory.
- `ROLE_ALLOWED_TOOLS` — `front` gets `Read,Write,Edit,Glob,Grep`, `generator`
  gets the former `agent_run.CLAUDE_ALLOWED_TOOLS` grant (moved here, still
  re-exported from `agent_run`).
- `tool_environment()` — the PATH handover, generalized from
  `agent_run._local_tool_environment()`. It now prepends **both** `.local/bin`
  and `scripts/`, and `resolve_agforge_role()` merges it into every role's
  environment, so the `:8092` charter path and the topic path share one
  handover.

`agents.toml` gained `[roles.front]`; both `front` and `generator` are on
`profile = "sonnet"` in the committed config.

## Why `generate.sh` needed no absolute path

`run_harness` launches with `env = {**os.environ, **agent.environment, ...}`.
That is the injection point. With `scripts/` on `PATH`, the bare `generate.sh`
already written in `create_generator/tools.md` is true as written, from any
cwd — `generate.sh` itself `cd`s to the agforge root. `Bash(generate.sh:*)`
was added to the generator's grant so the bare name is also permitted, not
only the `scripts/…` spellings.

## Verification

Both Step 1 checks pass, plus the suite:

```
75 passed in 3.81s
```

Under the `stub` profile (fake harness), `run_role` writes its record:

```json
{"schema": "ag.agent-run.v1", "request_id": "run-0001", "role": "generator",
 "profile": "stub", "harness": "fake", "provider": "ollama",
 "model": "ollama/qwen3.6:35b-a3b-coding-nvfp4", "duration_ms": 21,
 "outcome": "done"}
```

`generate.sh` resolves through `PATH` with a topic workspace as cwd:

```
cwd: …/topics/FreeForge/create-x/1/generator
command -v generate.sh -> …/agforge/scripts/generate.sh
```

New tests: `tests/test_role_run.py` (record writing, the tool-grant table
covering every role in `agents.toml`, the PATH handover, and the config-path
seam below). The three moved `_local_tool_environment` tests now exercise
`role_run.tool_environment` and assert both PATH entries.

## Failure worth recording: the refactor pointed the test suite at a real agent

First cut had `resolve_generator()` delegate to `resolve_agforge_role()`,
which read `role_run.AGENTS_CONFIG` directly. `tests/test_service.py`
redirects **`agent_run`'s** config pair at the `fake` harness — so the
delegation quietly bypassed the fixture and the suite began launching real
`claude-sonnet-5` runs. Symptom was a hung `pytest`; four paid processes were
already alive when it was caught, and were killed.

The fix is not a comment: `resolve_agforge_role()` now takes
`config_path` / `overlay_path`, and `resolve_generator()` passes its own
module-level pair explicitly. `tests/test_role_run.py` pins it —
`test_resolve_generator_obeys_the_config_paths_it_is_pointed_at`.

Generalizable lesson for Steps 2–5: **any new resolver seam must be reachable
by the tests' redirection, or the fake-harness discipline silently stops
holding.** A hanging test suite in this project should be read as "something
launched a real agent", not as "a slow test".

## Deviations from the plan

None in substance. One addition: the config-path parameters above, which the
plan did not anticipate.
