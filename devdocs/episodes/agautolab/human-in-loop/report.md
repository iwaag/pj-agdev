# Episode report — human-in-loop, scope 1

A human can now open `http://<host>:8791/monitor/` and see what the autolab is
doing, without SSH. Read-only; no intervention controls, as scoped.

Steps: [report1](report1.md) (job layer over HTTP), [report2](report2.md)
(monitor page), [report3](report3.md) (live verification).

## What was built

- **Gateway routes** (`agautolab/agent/gateway.py`, still stdlib-only and
  single-file): `GET /jobs`, `GET /jobs/<job>`,
  `GET /jobs/<job>/evidence/<iter>/<file>`, and `GET /monitor/`. `/status`
  gained cumulative cost, the devstyle 3-line report and a mission headline.
  The bearer requirement was dropped from every `GET`; `POST /mission`, the
  only route that starts anything, still authenticates.
- **Monitor page** (`agautolab/agent/monitor/`, 3 files, no build step, no
  dependency): header, jobs table, evidence browser, sessions table, drive
  log tail, polling every 3 s.
- Responses carry a `"kind": "autolab.monitor.v1"` envelope, so scope 3 can
  point agdevworld at the same feed.

The braindump asked for three things in order: confirm what progress
information already exists, drop what a human does not need, and present the
rest in the lightest possible browser view. All three are answered below.

## What is shown, and what is omitted

Everything shown already existed on disk. Nothing new is produced by the
agents; scope 1 was exposure and presentation only.

**Shown.** Mission headline · driver running/finished + exit code · the
`STATUS:` line from mediator NOTES · the devstyle 3-line report · cumulative
cost across all sessions and this run's subtotal · per-session result / turns
/ cost / duration · per-job status, phase, `iteration / max`, gates `n/m`
**with the failing gate commands spelled out**, cost rollup, evidence count ·
per-iteration time, cost, turns, duration, exit code, gate results, and a
link to every raw artefact · the drive log tail.

**Omitted from the overview, one click away as a link.** `prompt.txt`,
`diff.patch`, `claude_output.json`, `adapter_result.json`, `gates.json`
output tails. These are tens of kilobytes each and drown the numbers that
drive a decision; every one is a link in the evidence row.

**Omitted entirely.** Job `NOTES.md` (it restates `state.json` +
`gates.json`, both of which are rendered), and `job.yaml`'s `goal` (the
mission headline is the human-facing statement of intent; the per-job goal is
the mediator's translation of it).

**Cost gets top billing** — top-right of the header, and a column in the jobs
table. Agentify measured mediator cost at 3.7x implementation cost, so the
mediator total and the per-job implementation totals are shown as two separate
numbers rather than one blended figure.

## Scope 2: recommend closing it

The plan asked whether polling already satisfies "realtime progress display".
It does. Session JSON is written once at session end; `state.json` and
`evidence/iter-NNNN/` once per iteration. The drive log is the only
append-only stream in the system, and the page tails it every 3 s. A push
transport would carry the same three files at the same three moments.

The one genuine gap is not a transport problem: during an iteration (60–160 s
observed) the job layer emits nothing, because the coding agent's turns only
reach disk when `claude_output.json` lands. If that blind spot matters, the
work is to make the adapter stream turns to disk — and only then would a push
transport earn itself. Recommend closing scope 2 and, if wanted, opening the
within-iteration visibility question on its own terms.

## Scope 3 handoff

`autolab.monitor.v1` is the contract. The three endpoints carry strictly more
than the page renders (phase, `consecutive_no_progress`, `awaiting_approval`,
`push`, timeouts, per-gate exit codes, per-iteration `mtime`), so agdevworld
can present it beautifully without losing information — and can link back to
the same evidence passthrough for the raw artefacts.

## What live verification found

Six bugs, none of which `curl` could have shown. Two needed a browser render,
two needed something actually running, and two needed a *real paid* mission —
each layer of realism bought a bug the layer below could not reach:

1. A 6-column table at `width: 100%` spread its slack across every column, so
   the cost drifted halfway across the screen from the job name.
2. A failing gate command rendered inside the gates cell squeezed that column
   to four characters wide and broke the command one character per line —
   i.e. the layout failed exactly when a human most needs to read it.
3. The in-flight session rendered as a red `unparsed` row, because `claude`
   creates its output file at start and only fills it at the end. It now
   reads `in progress` while a driver is alive.
4. A stale devstyle report was shown under a freshly submitted mission, next
   to a STATUS line that correctly called the notes stale.
5. A job the mediator had just created — `job.yaml` written, `state.json` not
   yet — showed a red *"state.json missing or unparsable"*. The most normal
   moment in a job's life was displayed as a fault. Now `not started`.
6. The devstyle 3-line report was truncated mid-sentence, because real
   `NOTES.md` is hard-wrapped prose and the parser read one line per answer.
   Unreachable with a stub, because the stub's notes were written unwrapped
   by the same hand that wrote the parser.

A seventh was found simply by reading the rendered header: `mission_first_line`
was literally `# Mission`, and the line after it stopped mid-sentence because
mission prose is hard-wrapped. `/status` now reports the first paragraph.

Two lessons worth keeping. For a presentation layer, `curl`-level verification
proves the data is right and proves nothing about whether a human can read it —
every one of these survived a green endpoint check. And a test double only
exercises the states its author thought of: bugs 5 and 6 are both about what
the real system looks like *in between* its named states, and both were
invisible until a real mission ran.

## Constraints

- Monitoring reads never write and never take a job's `.lock`. Half-written
  JSON degrades to a row with an `error` note, never a 500 — verified against
  a deliberately corrupted job.
- Nothing under `.local/` was committed.
- All code lives in the `agautolab` submodule.
- Path traversal on both new file-serving routes was checked over a raw
  socket, because curl normalises `..` away before sending.

`uv run pytest -q` → 51 passed (10 new tests).

## Style report

- Style chosen: instant-ramen
- Why: scope 1 was exposure of data that already existed on disk — three
  endpoints and one page, with the real risk sitting in "is it readable",
  not in "is it designed right". Cheap deterministic checks (curl, pytest,
  a headless render) covered it, and the browser render is what actually
  found the bugs.
- Was it right in hindsight: yes, with one correction — the first two curl
  rounds declared the page done while it was, in fact, unreadable in two
  places. Rendering it should have come before, not after, the endpoints
  looked green.

## End-to-end proof

One real mission was run with the user's cost approval: a Roman-numeral CLI,
`max_sessions: 1`. The mediator session cost **$0.6263** (17 turns, 112 s) and
the job converged at iteration 1 of 3 with 6/6 gates for **$0.2027** (8 turns,
24 s) — **$0.83** total. The whole lifecycle was watched on the page: mission
headline, driver running → finished (exit 0), the live session showing
`in progress` then its final cost, the job appearing and converging, evidence
links resolving, and cumulative cost moving from $1.7415 to $2.3678.

The mediator chose `instant-ramen` and its own devstyle report is on the page:
*"mission explicitly bounded itself … textbook small/reversible work"* /
*"yes — converged in 1 iteration at minimal cost, no plan/approve overhead
needed for a problem this narrow and well-specified."*
