# Phase 1, step 5 — proven in the browser

**local: done. sonnet: blocked on a credential, not on the port.**

## local (OpenCode + ollama, the committed default) — passed

A real browser (headless Chromium, 1280×800) at `http://localhost:8090`, typing
into the chat panel and pressing Send:

> Read /api/guide with the fetch tool, then switch to the tasks view. Reply in
> one sentence.

What the page showed afterwards:

| Evidence | Result |
|---|---|
| assistant bubble | "Guide loaded and view switched to tasks." |
| action bubble | `switch_view {"view":"tasks"}` |
| the canvas | went from **`cluster / now` — "6 nodes are present"** to **`tasks / plane` — "0 backlog / ready tasks"**. The view really switched; it is a Phaser scene swap, not a DOM class |

The same exchange driven through `POST /api/chat` returned:

```json
{"reply":"Guide loaded and view switched to tasks.",
 "actions":[{"action":"switch_view","view":"tasks"}],
 "run":{"role":"front","profile":"local","harness":"opencode",
        "provider":"ollama","model":"ollama/qwen3.6:35b-a3b-coding-nvfp4",
        "outcome":"done"}}
```

and the record in `/records` (`assistant.run.v1`) carries
`outcome done`, `num_turns 2`, `duration_ms 22882`, `actions ["switch_view"]`.

That both tools really ran through the **Python** service is visible in the
harness transcript beside it:

```
TOOL: agdevworld_fetch      {"path": "/api/guide"}
   -> HTTP 200 text/plain; charset=utf-8 | # agdevworld assistant — entrance guide …
TOOL: agdevworld_switch_view {"view": "tasks"}
   -> the browser will switch to tasks
```

The `.mjs` service no longer exists, so nothing else could have answered; the
`the browser will switch to tasks` wording and the actions line are the Python
service's own output.

Screenshots were taken before and after and are kept out of the repository —
they show real node names, and local cluster facts do not belong in committed
files.

## sonnet (Claude Code) — not run: no `ANTHROPIC_API_KEY` on this machine

The profile switch itself is ready (`AGENT_FRONT_PROFILE=sonnet` in the ignored
`agdevworld/.env`, then recreate the assistant so the entrypoint regenerates
`/app/.local/agents.local.toml`), but the run would fail at authentication:

- the shell has no `ANTHROPIC_API_KEY`,
- `docker compose exec assistant` reports the variable empty inside the
  container, and compose only forwards `${ANTHROPIC_API_KEY:-}`,
- no `.env` under the project carries it.

Per the phase prohibition there is no fallback, so this would be a 502 and a
recorded failure rather than a silent downgrade to `local`. Running it to farm
that failure would prove only that the key is missing — which is already known —
so the run is left for the developer to authorise with a key present.

What is still unproven by this gap, precisely: the **claude_code** call site of
step 3 — `assistant/harness.mjs` writing `claude-mcp.json` with
`command: python3` and the absolute `tool_service.py` path, launched from a
per-run temporary directory. The opencode call site is proven above. Everything
the two share (the service itself, the container interpreter, the actions file,
the origin guard) is proven.

Interim evidence for the claude_code side, short of a paid run: the generated
config names an interpreter that exists in the image (`python3 3.14.5`, step 4)
and a path that exists in the image at an absolute location independent of cwd —
step 4's container exchange ran exactly that file.

## Status

Steps 1–4 complete and green. Step 5 half complete: the phase's "done when" is
met for `local` and pending for `sonnet` until a key is supplied.
