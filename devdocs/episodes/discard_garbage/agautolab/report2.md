# Report 2 — stub `role_run.py`

Plan step 2. 110 lines → 111, but the half that launched a harness is gone.

## Kept, working

`ROLE_ALLOWED_TOOLS` and `_opencode_config()` verbatim — sub-agent
configuration, so a reader of the stub still sees which tools each role was
granted and which permission file it maps to.

Resolution is real. Every `run_role` call still reads `agents.toml`, the
ignored `.local/agents.local.toml` overlay, and a project's own
`.local/projects/<name>/agents.toml`, and still returns the canonical
`ag.agent-run.v1` identity. Verified:

```
front    -> local  / opencode    / ollama    / ollama/qwen3.6:35b-a3b-coding-nvfp4
mediator -> sonnet / claude_code / anthropic / anthropic/claude-sonnet-5
role 'nope'      -> AgentConfigError E_UNKNOWN_PROFILE: unknown role 'nope'
profile 'bogus'  -> AgentConfigError E_UNKNOWN_PROFILE: unknown profile 'bogus'
```

That last pair is the point of keeping this layer alive: the preserved TOML is
still checkable through the node's own entrance.

## Removed

`run_harness()` — the launcher. `prompt`, `timeout` and `transcript` are now
accepted and ignored; the `__main__` CLI at the bottom of the module is gone,
since the gateway is the only remaining caller and it calls in-process.

## Two deviations from the plan

1. **`agag.harness` is still imported**, for `identity()` and
   `write_run_record()` only — never `run_harness()`. The plan said to drop the
   import, written before I had read the module: those two functions *are* the
   `ag.agent-run.v1` record contract. Hand-rolling the record here would have
   made the stub's records diverge from every other agent's the first time the
   contract changed.

2. **`outcome` is `"done"`, not `"stub"`.** The plan's `"stub"` would have made
   `POST /window` answer `502` on every call, because the gateway returns
   `200 if record["outcome"] == "done" else 502` — that breaks the response
   contract the plan itself requires to hold for `agdevworld/assistant`. The
   record instead carries a separate `"stub": true` field, and the canned reply
   text says plainly that no agent ran. A reader cannot mistake it for a real
   run; a consumer cannot mistake the node for a broken one.

`write_run_record()` drops unknown keys, so `_reload_record()` restores
`project` and `stub` after it writes — the same re-read the old code did for
`project` alone.

## Also decided here

`check_available=False` unconditionally. The old code re-resolved with
availability checking whenever the harness was not `fake`, which asks whether
`opencode` or `claude` is installed on this machine. A stub that never launches
a binary must not demand one be present. Unknown roles and profiles still
raise, which is the check that has meaning here.
