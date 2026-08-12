# Report 3 — stub `agent/gateway.py`

Plan step 3. 1005 lines → 400. Every route in the old table still answers.

## Verified live

Started on `127.0.0.1:8799` and called every route:

| Request | Code | Body |
|---|---|---|
| `GET /healthz` | 200 | `{"ok": true}` |
| `GET /status` | 200 | `autolab.monitor.v1`, emptied, `stub: true` |
| `GET /jobs` | 200 | `{… "jobs": []}` |
| `GET /projects` | 200 | **real** — profiles `local, sonnet, stub`, every project row |
| `GET /log` | 200 | one line of stub text |
| `GET /guide` | 200 | `agent/GUIDE.md` verbatim |
| `GET /jobs/foo` | 404 | `no such job: foo` |
| `GET /jobs/foo/summarize/iter-0001` | 200 | `{"status": "absent"}` |
| `GET /jobs/foo/summarize/nope` | 400 | `bad iteration name` |
| `GET /jobs/foo/evidence/iter-0001/diff.patch` | 404 | `no such evidence file` |
| `POST /jobs/foo/summarize/iter-0001` | 404 | `no such iteration` |
| `GET /monitor/`, `GET /game/` | 404 | named as removed |
| `GET /nope` | 404 | `unknown route` |
| `POST /window {"text": …}` | 200 | canned reply + real front identity |
| `POST /window {"nope": 1}` | 400 | `body must be {"text": "..."}` |

The window record it wrote (`.local/agent/window/run-0066.json`) carries
`role: front, profile: local, harness: opencode, provider: ollama, model:
ollama/qwen3.6:35b-a3b-coding-nvfp4`, resolved for real, alongside
`stub: true` and `cost_usd: 0.0`.

`start_mission()` and `apply_mission_block()` checked directly: `202` on a
valid mission, `400` on empty text, `400` on `max_sessions=99`, and the block
is still cut out of the shown reply.

## What is real, what is empty

Real: `GET /projects`, and the front-role resolution behind `POST /window`.
Those two are why the resolution layer was kept alive in step 2 — they are
where a broken `agents.toml` becomes visible from outside the node.

Emptied, keeping shape: everything job-, mission- and evidence-shaped. Zeroes
and empty lists rather than absent keys, and `"stub": true` on every stub
document, so `agdevworld/assistant` reads an empty node rather than a broken
one.

Removed: every helper that walked `.local/` (`current_run`, `drive_running`,
`pid_alive`, `session_summaries`, `sessions_cost`, `game_info`, `job_summary`,
`job_detail`, `job_yaml_fields`, `evidence_iters`, `iter_cost`, the `summary_*`
family, `start_summarizer`), both static file servers, and the `SIGCHLD`
reaper. Nothing is spawned, so nothing needs reaping. `.local/agent/window/`
is now the only thing this server writes.

## One deviation from the plan

`POST /jobs/<job>/summarize/<iter>` answers **404, not the planned 202
`pending`**. A 202 promises prose that a stub will never produce, and the
assistant polls the matching GET until it turns `done` — it would poll
forever. 404 is what the route already says for an unknown iteration, and with
no jobs on the node every iteration is unknown. `GET /jobs/<job>` returns 404
for the same reason, so the pair stays consistent.

## Known dead seam

`start_mission()` is now unreachable through HTTP: it fires only from a
mission block inside the window's reply, and the reply is canned text that
contains no block. It is kept because the 202/400/409 contract is the part of
the entrance worth preserving, and because the first real implementation put
behind `run_role` makes it live again with no gateway change. Its 409 branch
is gone with the driver it guarded against; the docstring says so rather than
leaving a reader to wonder.
