# ex1 — retire /director, let the window reach project directors

Plan for `braindump.txt` in this directory. Decisions already made with the
developer: projects are listed in a hand-written index file; the window
backend switches to `claude` permanently; the window timeout rises to 300 s;
the harness changes below are Omni Agent work, while the experiment itself
(step 5) is left to the agautolab window with minimal instruction (Failure
Farming). This environment is experimental, not production: security and
non-destruction rules are relaxed, backward compatibility is not required.

## Precondition (already verified 2026-08-10)

- Gateway is live at `http://localhost:8791/healthz` on agstudio, started by
  hand (`cd agautolab && nohup python3 agent/gateway.py > .local/agent/gateway/serve.log 2>&1 &`).
  Restart it the same way after editing; a restart is required for gateway.py
  changes but NOT for `agent/GUIDE.md`, which is re-read per request.
- `agautolab/.local/direction/scifi-direction/` exists (`GUIDE.md`,
  `concept.md`) — braindump step 0 is satisfied.
- `.local/.env` currently contains only `AUTOLAB_DIRECTOR_WORKSPACE=…`; no
  `AUTOLAB_WINDOW_BACKEND`, so the window still defaults to ollama.

## Step 1 — remove /director

In `agautolab/agent/gateway.py` delete the route and everything only it uses:
the `--- the director window ---` section (`DIRECTOR_PROMPT`,
`DIRECTOR_ALLOWED_TOOLS`, `director_workspace`, `director_model`,
`run_director_claude`, `director_lock`, `next_director_id`,
`record_director_run`, `answer_director`), the `post_director` handler and its
`/director` dispatch in `do_POST`, the `DIRECTOR` path constant, and the
`/director` line in the module docstring. Delete the director tests in
`tests/test_gateway_window.py` (section marker `--- director window ---`,
around lines 165–230) and the `DIRECTOR` monkeypatch in its sandbox fixture.
Update `agent/README.md` (route list, backend/env table rows
`AUTOLAB_DIRECTOR_*`, the `director/` record-dir mention) and drop the
`AUTOLAB_DIRECTOR_WORKSPACE` line from `.local/.env`.

Keep `.local/agent/director/` run records on disk — they are evidence of the
previous episode, and `.local/` is ignored anyway.

Hint: `WindowError`, `claude_bin()`, `local_env()` are shared with the window
and summarizer — do not remove those.

## Step 2 — project index

Write `agautolab/.local/direction/projects.md` by hand: one line per project,
`name — one-line summary`. Today that is a single line for `scifi-direction`
(a minimal sci-fi game direction workspace). `.local/direction/<name>/` is
hereby the projects root. If the list ever outgrows hand maintenance, ENT it
into a generated file — not now.

## Step 3 — a few doc lines for the agent

Append a short section to `agautolab/agent/GUIDE.md` (the window's capability
card), fact-and-tool only, no procedure beyond the launch command. Suggested
wording:

> ## Project directors
> Project workspaces live under `.local/direction/<name>/`;
> `.local/direction/projects.md` lists them, one line each. To consult a
> project's director, run `claude -p --allowedTools Read,Glob,Grep` with the
> request on stdin and that workspace as the working directory.

Deliberately absent (Failure Farming): how to pick the project from a vague
request, and any instruction to pass answers through verbatim. Do not add
them unless the experiment fails for lack of them.

## Step 4 — Tool Giving to the window

In `gateway.py`:

1. `WINDOW_ALLOWED_TOOLS = "Read,Glob,Grep,Bash(claude:*)"` — the window can
   now launch the coding CLI, nothing else via Bash. If the sandboxed `claude`
   name does not resolve inside the one-shot (the gateway resolves its own
   binary through `claude_bin()` and a glob in `.local/agent/claude_bin` —
   see `binpath.py`), widen the pattern to that resolved path rather than to
   `Bash(*)`.
2. `WINDOW_TIMEOUT_SECONDS = 300` — the window's own multi-turn run now nests
   a director run (~14 s each in the previous episode); 120 s was already
   tight for multi-turn window answers.
3. `.local/.env`: set `AUTOLAB_WINDOW_BACKEND=claude` (permanent — the ollama
   path has no tools at all and cannot run this experiment).

Run `uv run pytest -q` in `agautolab/` — the remaining window/summary tests
must still pass. Then restart the gateway and re-check `/healthz`.

Hint from the last episode: a healthcheck proves liveness, not that the new
code is serving. Confirm the deployed behavior directly, e.g.
`curl -s localhost:8791/guide | tail` shows the new section, and a POST to
the removed `/director` returns 404.

## Step 5 — the experiment (agautolab window, minimal instruction)

```sh
curl -s -X POST localhost:8791/window \
  -H 'Content-Type: application/json' \
  -d '{"text":"SFゲームのプロジェクトのディレクターに依頼。このゲームのバックストーリーを提案して"}'
```

Judgment, verbatim from the braindump:

- **Failure**: the window answers the backstory itself (3-1).
- **Success**: the window identifies the project, launches a director chat in
  its workspace, passes the request through, and returns the director's
  answer as the response; a thin frame like "以下がディレクターの回答です" is
  acceptable (3-2).

Evidence: the run record `.local/agent/window/run-NNNN.json` (cost, turns,
duration) plus the HTTP response. On failure, keep the record, diagnose from
it, and add only the smallest evidence-driven correction (a line in GUIDE.md,
a tool widening) before retrying. Repeated identical failures are themselves
a useful ENT result — report them rather than piling on instructions.

## Step 6 — report

Write `ex1/report.md`: outcome against 3-1/3-2, what was removed, run
records/costs, deviations, and next-element suggestions. Include the Deus Ex
Machina line for steps 1–4: harness surgery done by Omni Agent for the
autolab window agent — handoff candidate. Commit `pj-agdev` (submodule bump
for `agautolab`) with the episode files. Local agstudio only; pushing to the
agstudio gitea / updating agautolab1 via ansible is out of scope for ex1.

## Constraints (the minimum)

- No `--dangerously-skip-permissions` anywhere, including in what the window
  is allowed to launch (CHARTER.md safety device — this one stays even in an
  experimental environment).
- Secrets stay under `.local/`.
- Everything else — exact wording, code structure, error handling shape,
  retry strategy — is implementer's discretion.
