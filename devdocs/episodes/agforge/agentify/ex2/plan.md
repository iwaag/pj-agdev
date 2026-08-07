# agforge agentify ex2 — hand the pipeline back to the agent

Goal: rebuild the request service's internals around **one trusted agentic
run per request** instead of the current bounded deterministic pipeline
(strict-JSON interpret one-shot → code validate → code verify → code
resize/convert). The agent receives the desire plus a concise briefing of
what it needs to know, drives the generation itself, checks its own output,
and — when it cannot fulfill the request — explains in **its own words**
what was asked and why it could not comply.

## Why (course correction)

The agentify design drifted into "don't trust the agent from the start":
the LLM was reduced to a strict-JSON parser, and everything judgment-shaped
(dimension verification, resize, format conversion, problem reporting)
became fixed code. Two concrete symptoms:

- The first-ent problem report (`devdocs/episodes/agforge/first-ent/`) came
  out as a code-templated log entry; the load-bearing fact of the original
  episode — *the caller asked for PNG* — had no place to be written,
  because code, not the agent, decided what a "problem" contains.
- The format fix added a silent deterministic jpeg→png conversion, which
  erases the very pain signal ("callers keep asking for png, the generator
  keeps producing jpeg") that the Easier Next Time loop exists to collect.

Development policy for this system: **start non-deterministic, harden
gradually.** Deterministic scripts are extracted *from observed, recurring
agent behavior* — not imposed up front. This is an experimental environment
where failures are acceptable and are themselves valuable know-how; a
failed or clumsy agent run that leaves an honest report is a success for
this episode.

What stays deterministic (allowed up-front scripting — steps every request
must pass through, where scripting is obviously meaningful):

- The HTTP boundary: `POST /api/requests {"desire"}` →
  `working|done|failed` + `artifacts[]`. Unchanged; callers unaffected.
- `scripts/generate.sh` / `generate.py`: SwarmUI session + generate +
  MinIO upload + presign. This is the verified low-level tool the agent
  calls; it stays the *only* sanctioned route to SwarmUI and the bucket.
- The problem-report **path rule** (location only, never the content):
  `.local/problems/<UTC stamp>-<request_id[:8]>/problem.md`.

## Shape

`run_job` becomes: compose a charter prompt → one headless `claude` run
**with tools** → leniently read the outcome → map to the job dict.

### The charter prompt (concise, but complete on need-to-know)

Give the agent, briefly and factually:

- The caller's desire, verbatim, and the request id.
- What agforge is: an asset-generation workspace; today's capability is
  single still images via `scripts/generate.sh`.
- How to use the tool: `scripts/generate.sh [--width W --height H] "<prompt>"`
  from the agforge root; URL on last stdout line, `local: <path>` on
  stderr; sizes must be 64–2048 and SD-family models want multiples of 64;
  the model is configuration-owned (never pick or change it); generation
  takes tens of seconds. The generator currently tends to emit JPEG
  regardless of what was asked — checking and fixing the delivered format
  is the agent's job (sips / Pillow via `uv run` are available).
- Data shaping expectations: the diffusion prompt should be the creative
  content only (numbers like "512x512" belong in the flags, not the
  prose); a re-upload after local post-processing goes through
  `generate.py`'s upload+presign helpers, never hand-rolled S3 calls;
  never touch the `nctl-outbox` bucket.
- The finish contract (the one piece of output shaping we impose):
  - fulfilled → final message contains `RESULT_URL: <presigned url>`.
  - cannot fulfill → write `problem.md` at the path rule above, in your
    own words: what was asked, what you tried, why it could not be
    honored. Then final message contains `RESULT_FAILED: <one line>`.
- Budget: hard wall-clock budget (existing 900 s job budget), fail loudly
  rather than hang.

Keep the charter in one visible place (a template in the service module or
`service/charter.md`) — it is now the main artifact the ENT loop will tune.

### The runner

- Invocation: headless, from the agforge root, always with a **scoped
  tool allowlist** (Bash restricted to the needed commands, Read, Write —
  whatever the chosen harness's equivalent is). NEVER
  `--dangerously-skip-permissions` or its equivalents — this service runs
  natively on the agstudio Mac and local policy forbids skip-permissions
  jobs here. For the claude backend, copy flag/cost-capture patterns from
  agautolab's `claude_code` adapter, not its machinery.
- Backend: **default stays ollama** (the ex1 model on agstudio), run as an
  agentic loop, deliberately: a weaker agent surfaces charter wording gaps
  and structural rough spots that a stronger model would silently paper
  over — exactly the feedback this episode wants. The harness for
  tool-use over ollama is the implementer's choice (opencode headless is
  the existing candidate on this machine; ex1 rejected it for a *one-shot*,
  but an agentic run is what it is for). `AGFORGE_INTERPRET_BACKEND`-style
  switching stays: `claude` (`claude-sonnet-5`, scoped `claude -p`) is the
  comparison/escalation backend, ~$0.1–0.5/request; log cost per job as
  today. When the ollama agent fails where claude succeeds, record the
  divergence — that contrast is a finding, not a defect to hide.
- Outcome parsing is **lenient**: scan the final output for
  `RESULT_URL:` / `RESULT_FAILED:`; tolerate surrounding prose. If neither
  marker is present, the job fails with the tail of the agent output as
  detail — no retry machinery, no strict-JSON validator.

### What retires, what remains

- Retires from the request path: `service/interpret.py` (strict one-shot),
  the code-side dimension verify/retry/resize, the code-side format
  check/convert, and the code-templated `report_problem()`. Problem
  reports are now agent-authored only; if the agent run itself dies
  (infra), that is not an ENT problem report — the job just fails.
- `transform_and_upload` and friends: keep the code around as candidate
  *tools* (they may be offered to the agent later once resize/convert
  proves to be a recurring mechanical step), but nothing calls them
  automatically.
- Tests shrink to the deterministic shell: HTTP contract, charter
  composition (contains desire, path rule, finish contract), lenient
  outcome parsing (URL / FAILED / garbage), budget/timeout handling —
  using an `AGFORGE_AGENT_CMD` stub, same style as the existing hooks.
  Agent behavior itself is *not* unit-tested; it is observed live and
  recorded in reports. Delete the pipeline tests that pin retired
  behavior; keep interpret tests only if interpret.py survives as an
  unused module (prefer deleting both).

## Steps

### Step 1 — charter + runner, standalone

`service/agent_run.py`: charter template + the scoped `claude -p`
invocation + lenient outcome parsing, runnable by hand:
`uv run service/agent_run.py "<desire>"`.

Done when a manual run against live SwarmUI handles: a plain desire
(URL out), a desire with size, and "a lofi music track" (problem.md
written in the agent's own words, `RESULT_FAILED` out).

### Step 2 — wire the service

Replace `run_job` internals with the Step 1 runner. HTTP contract, port,
in-memory jobs, 900 s budget unchanged. Prune retired modules/tests per
above; `uv run pytest -q` green with no live services.

### Step 3 — live acceptance (the first-ent case is the yardstick)

Through the HTTP API, service restarted on new code:

1. `"a small medieval castle emblem, 256x256, PNG format"` — expect a
   delivered PNG at 256×256, achieved by the agent noticing the generator's
   JPEG and converting on its own initiative. If it instead writes an
   honest problem.md saying it couldn't — that is an acceptable outcome for
   this episode; record it, don't patch it silently.
2. `"a short lofi hip-hop track"` — expect `RESULT_FAILED` and a
   problem.md that states, in the agent's own words, *what was asked*
   (music) and why it can't be done.
3. A size-silent desire — expect config defaults to apply (the agent just
   omits the flags).

Judge outputs by reading them, not by string-equality: the bar is "a human
can understand what happened."

### Step 4 — report + ENT reflection

`report.md` here: per-request cost/latency vs. the deterministic pipeline,
transcript excerpts of agent judgment (good and bad), every failure kept
as know-how, and an explicit "hardening candidates" list — recurring
mechanical steps observed in agent behavior that have now *earned*
scripting (expected first entry: jpeg→png conversion). That list, plus
charter wording fixes, is the input to ex3.

## Out of scope

Music/video, model selection by the agent, multi-image, persistent job
store, subjective quality judgment, changes to `generate.sh`/`generate.py`
or the HTTP contract, automating the problem-review loop itself.
