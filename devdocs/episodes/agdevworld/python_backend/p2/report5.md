# Phase 2, step 5 — `sonnet`, and the phase report

**local: done. sonnet: still blocked on a credential, not on the port** — the
same wall phase 1 hit, at the same place, and now with the Python service in
front of it.

## Both profiles

| Profile | Harness | Outcome |
|---|---|---|
| `stub` | fake (`/bin/cat`) | **done** — the composed prompt returns as the reply (step 2) |
| `local` | opencode + ollama | **done** — `fetch` and `switch_view` really run, in the browser (steps 3, 4) |
| `sonnet` | claude_code | **not run** — no `ANTHROPIC_API_KEY` on this machine |

Checked again today rather than assumed: the shell variable is unset, no `.env`
under the project carries it, and `docker compose exec assistant-py` reports it
empty inside the container (compose forwards `${ANTHROPIC_API_KEY:-}`).

What the switch itself proves, at zero cost: with
`AGENT_FRONT_PROFILE=sonnet`, the regenerated overlay carries
`[roles.front] profile = "sonnet"`, and a chat answers

```
502 {"error":"assistant_offline",
     "detail":"E_UNAVAILABLE: secret environment variable 'ANTHROPIC_API_KEY' is unavailable"}
```

in **18 ms**, with a `failed` record and no process launched — `resolve_role`
reads the variable from the server process's environment and refuses before
`run_harness` is ever called. That is the no-fallback rule working: it does not
quietly become `local`. The profile was switched back to the committed default
afterwards; `.env` was never edited.

**What stays unproven, precisely:** the **claude_code launch conditions** of
step 3 — the `claude-mcp.json` written into the per-run temporary directory,
`--mcp-config --strict-mcp-config`, the four `mcp__agdevworld__*` allowed
tools, and the temporary cwd. Nothing else. Those conditions are unit-tested
(the file's content, the exact argv, the absolute tool-service path), but no
`claude` process has run them here. The opencode call site is proven end to
end. No pass was synthesised and no money was spent working around the gap.

## The record keys actually written

A done `local` run — every key, in file order:

```
schema (ag.agent-run.v1) · id · started · outcome · role · profile · harness ·
provider · model · transcript · num_turns · cost_usd · usage · duration_ms · actions
```

`transcript`, `num_turns`, `cost_usd` and `usage` come from `agag` itself;
`schema`, `id`, `started` and `actions` are this service's. Compared with the
JavaScript record, `schema` and `transcript` are new and nothing was lost.

Failure records are shorter and honest about what they know: a resolution
failure carries only `schema · id · started · outcome · failure` — no harness
or model, because nothing was resolved. A failed *launch* adds the five
identity keys plus `duration_ms`, since by then the agent was known.

A note is `schema (assistant.note.v1) · id · written · text` in
`<id>.note.json`.

Records are written directly rather than through
`agag.harness.write_run_record`, whose key whitelist drops `actions` — the one
key the browser's UI effects are recorded under.

## What the port proved wrong about `GUIDE.md`

**Nothing.** The card is language-neutral, as the roadmap expected, and every
claim in it that this phase touched still holds against the Python service:

- "Read from disk for every fresh front-agent run … served raw at
  `GET /api/guide`" — still literally true, now on both services.
- "A path outside `/api/` that does not exist answers `200` with this app's own
  HTML … Under `/api/` a wrong path answers `404`" — re-checked through nginx
  with the split in place: `/nope` → 200 HTML, `/api/nope` → 404.
- "no silent harness or model fallback" — the `sonnet` 502 above is the
  evidence.
- `wait` and `fetch` bounds, and the safety devices, belong to the tool service
  and passthroughs, which this phase did not touch.

So phase 4 inherits an empty fix list for the card. The one thing worth
carrying forward is not a card error but a card *gap*: nothing on it tells the
assistant that its own reply is recorded with a transcript path, and
`/api/note` is described as "the one thing you can leave behind" while the run
record is in fact the other. Whether to say so is phase 4's call.

## Phase 2 status

The phase's "done when" — chat runs through Python on both profiles and leaves
records in `/records` — is met for `local` (and for `stub`, which the plan
added) and pending for `sonnet` until a key is supplied. All four views work;
`uv run pytest` is green at 42 tests; the JS service still serves every route
it served before, and no record it wrote was touched.

Carried into phase 3: `overlay.py` (already ported here, because `assistant-py`
never runs `entrypoint.mjs`), the temporary nginx split, the single-target
`vite.config.ts` dev proxy, and the unproven claude_code launch.
