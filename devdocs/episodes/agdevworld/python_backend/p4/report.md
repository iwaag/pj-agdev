# Phase 4 — settling

The port is finished; this phase closed the three things phase 3 left open and
the roadmap's own settling list. Nothing was left undone, and one thing was
deliberately not done (the pyagag push-down — reason below).

## Step 1 — the Plane naming defect, fixed rather than documented away

`p3/report5.md` handed phase 4 a choice: humanize the Plane name/identifier, or
narrow the card's `<lowercase-hyphen name>` claim. Humanized. The hyphenated
name is the contract in Gitea, Zulip and every mission briefing; making Plane
the exception is cheaper than making the human learn a second naming rule.

`projects.py`:

- `plane_name("p4-naming-check")` → `"p4 naming check"`. Plane 1.4.1 refuses a
  hyphen in a project name; the words are what a human reads on the board.
- `plane_identifier` keeps the initials rule for multi-word names
  (`whack-a-mole-2` → `WAM2`, which is what keeps `<name>-N` families apart),
  but a **single-word name now keeps its own letters** (`quiz` → `QUIZ`,
  12 max). The old rule gave every single-word project the same one letter —
  that is what made `p3smoke2` fail on `p3smoke1`'s `P`.
- A failed create now names both fields it sent
  (`project create (name='…' identifier='…') -> HTTP 409: …`). Plane answers an
  identifier clash with a message about the *name*, which is what sent the
  phase-3 smoke test looking for a project that did not exist.

Proven against the live Plane, both directions, and cleaned up after itself:

| what | result |
|---|---|
| pre-fix shape (`name="p4-naming-check"`, `identifier="P"`) | `400 {"non_field_errors":["Project name cannot contain special characters."]}` |
| the fix (`"p4 naming check"` / `PNC`) | `201`, five states returned |
| a 12-character identifier (`p4lengthcheck1` → `P4LENGTHCHEC`) | `201` — the truncation bound is real, not assumed |
| both proof projects | `DELETE` → `204`; **no Plane debris this phase** |

Residual, stated rather than hidden: two names that derive the same identifier
still collide — two single-word names sharing a 12-character prefix, or two
multi-word names with the same initials. There is no retry-with-a-suffix, on
purpose (no silent fallback); the failure now says exactly which identifier was
refused, which is enough to pick another name.

`GUIDE.md` got the one sentence this proved necessary, on the
`/api/autolab/projects` line: the hyphenated name is the contract everywhere
except inside Plane, where it becomes the same words with spaces under a
derived identifier, and colliding identifiers fail with both fields named.
Nothing else on the card was wrong — it is language-neutral, as the roadmap
expected, and survived the port untouched.

## Step 2 — `README_DEV.md`

Rewritten where the collapsed system made it false; the sections the port did
not touch (autolab project profiles, Plane task dispatch, safety devices,
cagent convention) are unchanged.

- **Commands** — `uv run pytest` from `assistant/` is now named as the test
  entrance. `npm test` is gone (it only ever ran the assistant's tests), so
  `npm run build` is the frontend's only check and the file says so.
- **Files** — every `.mjs` entry is gone. The Python modules are listed one by
  one (`server`, `chat`, `passthrough`, `workflows`/`projects`,
  `overlay`/`records`/`settings`, `tool_service`, `tests_py/`), plus
  `pyproject.toml`. `scripts/fetch-cluster-state.mjs` is called out as what it
  is: the last JavaScript outside `src/`, a developer command rather than part
  of the service.
- **Assistant** — opens with what the service now is (stdlib
  `ThreadingHTTPServer` + pyagag) and why the image is still node-based; lists
  the routes the one process serves; adds the `stub` profile (`harness =
  "fake"`), the phase-3 environment variables that were missing (`GITEA_*`,
  `ZULIP_ENV_PATH`), the file-read-at-request-time property of the Gitea token
  and Zulip credentials, and the `ZULIP_LAN_HOST` requirement with its reason.
  No hostname, key or local path was written into it.

## Step 3 — the pyagag question: no push-down, and why

An MCP stdio server skeleton stays in agdevworld for now.

- **One consumer.** `grep` for `tools/call` / `jsonrpc` across agautolab and
  agforge finds nothing: agdevworld is the only agent in the system that *is*
  an MCP server. pyagag's three modules (`agent_config`, `harness`, `zulip`)
  each earned their place by being duplicated in two or three projects first;
  this would be the first module extracted before a second caller exists.
- **The generic half is small.** Of `tool_service.py`'s 272 lines, the reusable
  part is the ~45-line read-dispatch-write loop plus `initialize`/`ping`. The
  rest is agdevworld's own: the same-origin guard, the 1 MB clip, the 60 s cap,
  and the actions-JSONL channel. Extracting 45 lines would add a cross-repo
  version boundary to the file that is easiest to prove locally — phase 1
  proved it on its own precisely because it depends on nothing.
- **The trigger is named instead.** When a second agent needs a stdio MCP
  server (agautolab's window is the plausible one), the skeleton moves then,
  with two callers to shape it. The `agag.harness` precedent says a module is
  worth its boundary once it is maintained twice — that is the whole reason
  this episode existed.

## The sweep

- `uv run pytest` → **119 passed** (116 at the end of phase 3; the three new
  ones cover the humanized name, the single-word identifiers, and the error
  that names both fields). `npm run build` → green, the usual non-failing
  chunk-size advisory aside.
- `docker compose up --build -d web assistant`, then through
  `http://localhost:8090`: the four views' data sources all 200
  (`/cluster/state.json`, `/cluster/workspaces.json`, `/api/autolab/nodes`
  with both nodes reachable, `/api/plane/issues`), plus
  `/api/autolab/agstudio/projects` 200.
- **Chat** on `local`: "fetch /api/autolab/nodes … then switch the view to
  nodes" → the right two nodes in prose plus a `switch_view` action; record
  `assistant.run.v1`, `harness: opencode`, `provider: ollama`, `outcome: done`,
  2 turns, 27.7 s, $0.00.
- **A note** → 201 `assistant.note.v1`.
- The rebuilt image carries the fix (`plane_name` present in the container).

## Standing gap, unchanged

`ANTHROPIC_API_KEY` is still absent in the container, so the `sonnet` /
claude_code launch conditions remain unproven — the same gap phases 2 and 3
reported, carried forward rather than synthesized. Everything else in the
roadmap's phase 4 list is done.

## Episode state

The roadmap is complete: the assistant is Python plus pyagag, no `.mjs`
remains in the service, the documents describe what is actually there, and the
one defect the port exposed is fixed with live evidence.
