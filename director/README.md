# director

The creative-direction agent. It used to be a two-subcommand function
(`compose` / `review`) with a hardcoded model and a harness that checked its
work. It is now a persona with one conversational entrance, a swappable
backend, and no gates in front of its judgment.

## The entrance

One place to express a desire (devpolicy/policy.md, **Single Entrance**),
reachable over three transports:

```sh
# HTTP — the window
python3 director/window.py                      # listens on 127.0.0.1:8094
curl -s localhost:8094/window -d '{"text":"would John say this?"}'
curl -s localhost:8094/guide                    # the capability card
curl -s localhost:8094/healthz

# CLI — same entrance, in-process
python3 director/director.py "is this twist too heavy?" \
  --direction .local/asset-reconcile/othello-direction \
  --manifest .local/asset-reconcile/othello-web/assets/manifest.json

# another agent — reconcile.py calls director.answer() directly
```

`direction` and `manifest` (body fields, CLI flags, or `DIRECTOR_DIRECTION` /
`DIRECTOR_MANIFEST`) say *which project* you are talking about. That is
addressing, not desire — there is no second place to ask for something.

The reply is the run record: which backend answered, what it cost, how long
it took, and the text. Ask for a pass/fail and the last line is
`VERDICT: pass — reason`, parsed into `record["verdict"]`. Nothing checks or
overrides that line; it is how a machine caller reads a director who is
otherwise speaking prose.

`GET /guide` serves `GUIDE.md`, the entrance guide — capability and cost
questions are answered from it, re-read from disk per request.

## The persona lives in files, not in code

Everything the director knows about the project is the markdown in the
direction workspace — `brief.md`, `persona.md`, anything else ending in
`.md` — concatenated fresh on every run. Edit those files and the next
answer changes. No restart, no code change, no prompt buried in Python.

This is load-bearing: during Phase 3 the director kept telling callers that
talking to it was free, and the cause was a line in `persona.md` saying
budget questions were not its call. The fix was one paragraph in the
workspace, by a human, with no deploy.

## The judgment is the director's

The old harness aborted a run when the delivered PNG was the wrong size and
stopped after exactly two attempts. Both were clamps in front of the agent
(review1.md, E3 class (b)), and both are gone:

- `inspect_image` + `compare_to_manifest` produce **observations**, handed to
  the director in the review message. A 512×512 file against a 1024×1024
  manifest entry is something it is told, not something that stops it — if
  the mood is right and it wants to deliver anyway, it delivers.
- **How many attempts to make is decided one attempt at a time**, by the
  director, with `DECISION: deliver | retry | stop` as the last line of its
  reply. On `retry` it writes the next request itself.
- A composed desire that omits the manifest's dimensions is an **advisory**
  in the evidence, and gets sent anyway.
- `--attempt-budget` (default 5) is the one bound left, and it is a **cost**
  bound, not a quality gate: when it bites, the verdict says so in exactly
  those words, because "the harness stopped the director" is a different
  fact from "the director stopped".
- A generation failure is handed to the director verbatim, and it says
  whether to go again.

```sh
python3 director/reconcile.py \
  --direction .local/asset-reconcile/othello-direction \
  --manifest .local/asset-reconcile/othello-web/assets/manifest.json \
  --request-id background --agforge-url http://localhost:8092
```

Evidence lands in the direction workspace: `candidates/`, `reviews/<id>.md`,
`reviews/<id>.envelopes.json`.

## Backend (Agent ≠ Model)

| variable | meaning |
|---|---|
| `DIRECTOR_BACKEND` | `claude` (default) or `ollama` |
| `DIRECTOR_MODEL` | model within the backend |
| `DIRECTOR_OLLAMA_URL` | default `http://127.0.0.1:11434` |
| `DIRECTOR_CLAUDE_CMD` | claude binary; **a glob is accepted** and resolves to the newest match |
| `DIRECTOR_RECORDS_DIR` | where run records go; default `<direction>/records/` |
| `DIRECTOR_DIRECTION`, `DIRECTOR_MANIFEST` | window defaults |
| `DIRECTOR_WORKSPACE_ROOT` | confines the paths a window request may name |

Resolved from the process environment first, then `pj-agdev/.local/.env` —
agforge's `AGFORGE_AGENT_BACKEND` pattern. The strong backend is the default
here, the opposite of autolab's window, because creative judgment is the
hard-task end of the spectrum.

The glob in `DIRECTOR_CLAUDE_CMD` is not decoration: the usual value points
into a version-numbered editor-extension directory that goes stale on every
update, which has already cost autolab two runs and agforge one.

## Records

Every run — window answer, compose, review, recompose — writes
`<direction>/records/run-NNNN.json` per `devpolicy/agent_records.md`: id,
backend (model + harness), outcome, cost/time when the backend reports them,
and on failure the backend's own words. A backend that cannot be reached
produces a `failed` record, not a traceback.

## Tests

```sh
python3 -m unittest test_director test_reconcile   # from director/
```
