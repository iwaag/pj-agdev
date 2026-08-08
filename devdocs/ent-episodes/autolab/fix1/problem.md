# autolab — problems surfaced by the human-in-loop monitor (2026-08-08)

Source episode: `devdocs/episodes/agautolab/human-in-loop/` (report.md and
report1–3.md). Scope 1 of that episode shipped a read-only monitoring page,
and it succeeded. Neither problem below was caused by it — the page only made
them visible, which is arguably the first useful thing it did.

Both are in `agautolab`, both are out of scope for human-in-loop (which was
exposure and presentation only, no changes to the loop).

## 1. An interrupted iteration leaves a permanent hole in the audit trail

`run_once.py` increments and **saves** the iteration counter before it starts
the adapter:

```python
iteration = state.iteration + 1
state.status = RUNNING
state.iteration = iteration
state.error = None
state.save(job_dir)          # run_once.py:471 — counter is now durable
...
_write_evidence(...)         # run_once.py:373 — evidence only at the end
```

`evidence/iter-NNNN/` is created at the end of the iteration. So any death in
between — session killed, machine interrupted, adapter hard-timeout at the
wrong moment — advances the counter permanently and writes nothing. The
iteration is invisible afterwards: no `prompt.txt` saying what was asked, no
`error.txt` saying what went wrong, no timestamp saying when it happened.

**Observed.** `.local/jobs/snake-web` has `state.json` `iteration: 3` and only
`evidence/iter-0001/` and `evidence/iter-0003/` on disk. `iter-0001` finished
at `2026-08-07T18:36:19Z`; `iter-0003` started at `18:44:21Z`. Nothing on disk
accounts for those eight minutes.

The cause of *that particular* gap cannot be established after the fact —
someone may simply have deleted the directory. What is established is the
mechanism that permits it (durable counter, later evidence) and that a job
in this state exists.

**Impact.** `AGENT_GUIDE.md` presents `evidence/iter-NNNN/` as the audit
trail — "this is your audit trail: check nobody touched the tests/gates". The
trail is complete for iterations that finish and empty for iterations that
were interrupted, i.e. it is missing exactly where a human most wants to look.
The monitor now shows the discrepancy honestly (`iteration 3 / 10` next to
`2 on disk`) but has nothing to show *about* it, because nothing was recorded.

**Improvement direction.** Create `evidence/iter-NNNN/` at the top of the
iteration and write `prompt.txt` plus a start timestamp immediately, so an
interrupted iteration leaves a directory that says what was attempted and
when. A finished iteration then fills in the rest exactly as today. Optionally
have the next `run-once` notice a previous iteration directory with no
`adapter_result.json` and drop an `error.txt` recording that it was
interrupted.

## 2. A coding agent tried to bind the gateway's own port

`snake-web` `evidence/iter-0003/adapter_result.json` records 9 permission
denials, **8 of which are attempts to run `python3 -m http.server 8791`** —
the coding agent trying to serve `target/` so it could verify the game in a
browser, which is exactly what `AGENT_GUIDE.md` tells it to do ("Serve the
exact checkout you mean to prove, e.g. `python3 -m http.server <port>` inside
`target/`").

8791 is the gateway's own default port (`AUTOLAB_GATEWAY_PORT`).

On agstudio the attempts were denied by the job's `--allowedTools`, so nothing
happened. On a node where the gateway is running and the job is granted
`Bash(python3:*)`, the coding agent would bind — or fail to bind — the port
the gateway is on.

**Impact.** Before this episode that would have been a confusing verification
failure. Now the gateway also serves `/monitor/`, so a port collision takes
out the only window a human has into the run — the failure mode is "I can no
longer see what is happening", which is the precise thing scope 1 was built to
prevent.

**Improvement direction.** Name the reserved ports where the agent will read
it: a line in `AGENT_GUIDE.md`'s verification advice stating that 8791 (and
whatever `AUTOLAB_GATEWAY_PORT` is set to) belongs to the gateway and jobs
must pick something else. Cheap and sufficient. A stronger version passes the
gateway's port into the job so the guidance cannot drift from reality.

## Not problems (deliberate, already documented)

- **Unauthenticated read surface.** Scope 1 dropped the bearer requirement
  from every `GET`, so `/jobs`, the evidence passthrough and `/monitor/` are
  open, and the gateway binds `0.0.0.0` by default. This was the plan's
  explicit choice ("security kept deliberately thin; auth will be designed
  system-wide in a later phase"), not an oversight. Worth carrying into that
  later phase: evidence files are raw agent output — `prompt.txt`,
  `diff.patch`, `claude_output.json` — and are exactly the kind of artefact a
  secret can end up inside. A scan of the current evidence for the gitea token
  and for `user:pass@` style URLs came back clean, and `push.json` records
  git's own output, which has the credentials stripped. So there is nothing
  leaking today; the concern is the class of artefact now on an open port.
- **Within-iteration silence.** During an iteration (60–160 s observed) the
  job layer emits nothing, because the coding agent's turns only reach disk
  when `claude_output.json` lands. This is why the human-in-loop episode
  recommends closing scope 2 (realtime display) as satisfied by polling and,
  if the blind spot matters, opening adapter-level turn streaming as its own
  item. It is a known limit with a recorded recommendation, not an unresolved
  defect.
