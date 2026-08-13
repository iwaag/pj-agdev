# Phase 2, step 3 — a real run: `local` (opencode) with tools

**Done, first attempt.** Through the Python service, on ollama, the front agent
fetched `/api/guide` and switched the view; the action came back in the reply
and both tool calls are in the transcript.

## The per-run environment

As the plan warned, `run_harness` has no `env=` parameter and mutating
`os.environ` in a threaded server is a race. `ResolvedAgent` is frozen with a
plain-dict `environment`, so each request replaces the agent with a copy:

```python
agent = dataclasses.replace(agent, environment={
    **agent.environment,
    "AGDEVWORLD_TOOL_BASE_URL": tool_base_url or TOOL_BASE_URL,
    "AGDEVWORLD_ACTIONS_FILE": str(actions_path),
})
```

`run_harness` merges `agent.environment` over `os.environ`, so the per-run
values win over the container-wide ones and two concurrent chats cannot see
each other's actions file. The actions file lives in a
`tempfile.TemporaryDirectory()` per run, whatever the harness.

## cwd and MCP, per harness

`_launch_conditions(agent, run_dir)` returns the cwd and the harness-specific
keyword arguments, and is the only place that branches on harness:

- **opencode** — `cwd=/app`, no extra argv. `opencode.json`'s
  `mcp.agdevworld.command` is the relative `["python3",
  "assistant/agdevworld_assistant/tool_service.py"]` and opencode spawns it
  with its own cwd, so the project root is the requirement.
  `opencode_config=` was deliberately not used: it would free the cwd only at
  the price of making that command absolute, and the same file is read by
  native runs.
- **claude_code** — `claude-mcp.json` written into the run's temporary
  directory, `cwd=` that directory, `extra_args=["--mcp-config", …,
  "--strict-mcp-config"]`, `allowed_tools=` the four
  `mcp__agdevworld__*` names. No `--model`: `agag.build_argv` raises on it, and
  the profile owns the model.

**The judgement call, kept as it was:** claude_code still runs in a per-run
temporary cwd. It has no workspace in agdevworld — every capability it has
arrives through MCP, and both things it must reach (the tool service in the
config, the actions file in the environment) are absolute paths. A throwaway
cwd is therefore the smallest ambient authority that still works, and changing
it would buy nothing.

## Timeout, transcript, actions

`AGDEVWORLD_AGENT_TIMEOUT_MS` (300 s default) divided by 1000 in `settings.py`,
because `run_harness` takes seconds. 300 s still sits below nginx's 310 s, so
the browser gets this service's own timeout record rather than a proxy error.
Transcript stays `<records>/<id>.agent.jsonl`.

One deliberate improvement over the JavaScript: a malformed line in the actions
JSONL is skipped with a stderr note instead of raising. The JS let it kill the
request — the run had already happened and the reply was already earned, and
one unreadable line is not worth losing it.

## Evidence — the container, `local` profile, ollama up

Prompt: *"Read /api/guide with the fetch tool, then switch to the tasks view.
Reply in one sentence."*, with `context` = "The screen shows the nodes view."

```json
{"reply": "Guide card fetched (HTTP 200) and switched to the tasks view.",
 "actions": [{"action": "switch_view", "view": "tasks"}],
 "run": {"role": "front", "profile": "local", "harness": "opencode",
         "provider": "ollama", "model": "ollama/qwen3.6:35b-a3b-coding-nvfp4",
         "outcome": "done"}}
```

26.4 s wall clock. The record in `/records`:
`num_turns 2`, `duration_ms 26420`, `cost_usd 0.0`,
`usage {input 17210, output 157, …}`, `actions ["switch_view"]`, and the
transcript path. Grepping the 7-line transcript for tool names finds
`agdevworld_fetch` once and `agdevworld_switch_view` once — the tools really
ran, through the Python tool service, from the Python server.

## Tests (four more, 42 total)

The interesting one needs no model: the `fake` harness command is a four-line
shell script that appends an action to `$AGDEVWORLD_ACTIONS_FILE`, appends a
deliberately malformed line after it, and echoes `$AGDEVWORLD_TOOL_BASE_URL`.
The reply proves the tool base URL reached the process, the single returned
action proves the actions file did and that the bad line was skipped. A second
script echoes the actions path, and the test asserts the file and its directory
are gone once the run returns. The remaining two pin the launch conditions:
opencode → project root and empty kwargs; claude_code → temp cwd, the exact
`extra_args` and `allowed_tools`, and an `mcpServers.agdevworld` entry whose
argument is an absolute `tool_service.py`.
