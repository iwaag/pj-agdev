# Phase 2, step 2 — `/api/chat` end to end on the `stub` profile

**Done.** `POST :8093/api/chat` resolves `front`, runs it, records it, and
answers with the `{reply, actions, run}` envelope. `uv run pytest`: 38 passed.

## What was written

| Module | What it holds |
|---|---|
| `settings.py` | paths, records dir, the ms→s timeout, `read_guide()` |
| `chat.py` | `ROLE_PROMPT`, `compose_system`, `compose_prompt`, `valid_messages`, `resolve_front`, `run_front` |
| `records.py` | the stdout line and the durable file, for runs and notes |
| `overlay.py` | the `.local/agents.local.toml` generator |
| `server.py` | routing, body read, JSON reply; `handle_chat` / `handle_note` are plain functions taking a payload, which is what the tests call |

`ROLE_PROMPT` was copied verbatim — asserted, not assumed: a throwaway script
pulled the template literal out of `server.mjs` with a regex and compared it to
the Python constant. Identical.

## The overlay: one phase-3 item pulled forward

`assistant-py` runs `python -m agdevworld_assistant.server` and so never runs
`entrypoint.mjs`, which is what writes `/app/.local/agents.local.toml` for the
JavaScript container. Without that file the container has no harness command
and no ollama base URL, and every chat is a clean 502 — correct behaviour, but
it makes the step unprovable. So `overlay-generator.mjs` (28 lines) is ported
now, in `overlay.py`, called once from `main()`. It keeps the property that
matters: no API key value enters the file, only `anthropic_api_key_env`.

One line is new rather than ported: `[local.harness.fake] command = "/bin/cat"`
(overridable with `AGENT_HARNESS_FAKE_COMMAND`). `agag.agent_config` defaults
commands only for `opencode` and `claude_code`, so without it the `stub`
profile raises `E_UNAVAILABLE` and cannot be run at all. `/bin/cat` makes the
harness hand the composed prompt back as the reply, which is exactly what makes
this step assertable.

## The traps, as met

- **`run_harness` never raises for a bad run.** `run_front` reads
  `meta["outcome"]`, not the exit code: `!= "done"` → `ChatFailure` → 502 plus
  a `failed` record. A zero exit code with an error envelope or with no output
  is a failure in `agag` too, and reaches the same branch.
- **`extract_event_text` does not strip.** The reply is `.strip()`ed before it
  leaves; the transcript keeps the raw text.
- **The record.** `{"schema": "ag.agent-run.v1", **meta}` with `id`, `started`
  and `actions` kept — written directly rather than through
  `agag.harness.write_run_record`, whose key whitelist drops `actions`. The
  stdout line (`kind: assistant.run.v1`) stays, so `docker compose logs` reads
  the same as before.

`actions` is `[]` in this step by construction: the actions file is a per-run
launch condition and belongs to step 3. The key is present so the record shape
does not change when step 3 fills it.

## Evidence — the real container, `AGENT_FRONT_PROFILE=stub`

```
$ curl -s -X POST localhost:8093/api/chat -H 'content-type: application/json' \
    -d '{"messages":[{"role":"user","content":"which view is open?"}],
         "context":"The screen shows the nodes view."}'
```

`run` came back
`{role: front, profile: stub, harness: fake, provider: ollama, model:
ollama/qwen3.6:35b-a3b-coding-nvfp4, outcome: done}` and the 12,301-character
`reply` is the composed prompt itself: the role prompt, then the screen line,
then the capability card, then

```
=== CONVERSATION SUPPLIED BY THE BROWSER ===
USER:
which view is open?

Answer the latest USER message. Use the agdevworld tools whenever the request needs current state or a UI action.
```

The record in `/records`:

```json
{
  "schema": "ag.agent-run.v1",
  "id": "a0cb807b-…", "started": "2026-08-13T07:02:06.100Z", "outcome": "done",
  "role": "front", "profile": "stub", "harness": "fake",
  "provider": "ollama", "model": "ollama/qwen3.6:35b-a3b-coding-nvfp4",
  "transcript": "/records/a0cb807b-….agent.jsonl", "duration_ms": 4, "actions": []
}
```

`transcript` is `agag`'s own key and comes for free; the JS record did not have
it. `POST /api/note` → 201 and an `<id>.note.json` beside it. `{"messages":[]}`
→ 400 `bad_request`; a non-JSON body → 400 `bad_request`.

Note that `model` is the profile's declared model even on `stub`: the `fake`
harness never contacts it. `agents.toml` requires every profile to name a
declared model, and this is what "agent ≠ model" looks like in a record — the
identity is `profile stub / harness fake`.

## Tests (`tests_py/test_chat.py`, 20 cases)

Composition (screen present and absent, the `USER:`/`ASSISTANT:` blocks, the
fixed trailing instruction), eight validation rejections, and three runs
against a temporary `agents.toml` + overlay: the `stub` round trip (reply ==
prompt, transcript == prompt), a command that exits 1 (502, `failed` record
that still carries `profile`), and a missing config (502 with `E_SCHEMA`, and a
record that claims **no** harness because nothing was resolved).

`/bin/false` was the first choice for the failing command and is absent on
macOS; the tests write a two-line `sh` script instead, which works on both this
Mac and Alpine.
