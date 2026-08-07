# agforge agentify ex3 — harden what earned it, see what the agent does

Goal: take the ex2 findings ([../ex2/report.md](../ex2/report.md)) and
(a) give the agent the tools it has now *earned* through recurring
behavior, (b) make the runner catch the two failure classes ex2 actually
observed, and (c) capture enough of the agent's run to review its
behavior afterwards. The one-agentic-run shape from ex2 stays; this
episode makes it sturdier and more observable, not more constrained.

This is an experimental environment. Failures are know-how; a run that
fails honestly and leaves evidence is a success. Backward compatibility
with ex2 internals is NOT required — rewrite/rename/delete freely
(`agent_run.py`, `charter.md`, `candidate_tools.py`, tests). Only the
HTTP contract stays as-is, because agdevworld already speaks it.

## Hard rules (the complete list — everything else is your judgment)

1. No `--dangerously-skip-permissions` / `opencode run --auto` or
   equivalents — this runs natively on the agstudio Mac (local policy).
   Scoped allowlists are fine and may be widened when a run needs it.
2. Never write to the `nctl-outbox` bucket; model choice stays
   configuration-owned (no `--model` from the agent).
3. Problem-report path rule stays: location fixed, content always the
   agent's own words.

## Work items

### 1. Offer the convert/resize tool (earned: observed in every ex2 format run)

jpeg→png convert → verify → re-upload appeared as the same mechanical
sequence in both backends. Turn `service/candidate_tools.py`
(`transform_and_upload`) into something the agent can call in one line —
e.g. `uv run service/transform.py --format png [--width W --height H]
<file>` printing the fresh presigned URL — and tell the agent about it
in the charter. The agent still *decides* whether to use it; do not move
the decision back into code. Delete the charter's fragile inline
`python -c` re-upload snippet once the tool exists. Keep bare
`upload_and_presign` reachable too (post-processing the agent invents
itself shouldn't force hand-rolled S3).

### 2. Runner-side URL verification (earned: 2 URL-fidelity incidents in ex2)

A corrupted `RESULT_URL` is currently delivered to the caller as `done`.
After parsing `RESULT_URL:`, the runner should GET the URL once (cheap,
deterministic, no judgment taken from the agent): non-200 → the job
fails with a detail naming what happened, ideally distinguishable as a
transcription problem. Consider logging content-type/size while you're
there — free evidence. MinIO presigned GETs answer plain `requests.get`;
HEAD may 403, use GET.

### 3. Diagnosable infra failures + transcript capture (ex2's observation gaps)

- `agent produced no output` / nonzero-exit paths must keep the harness
  stderr tail in the failure detail (ex2 saw one empty-stdout exit-0
  opencode flake and had nothing to diagnose with).
- opencode's default headless output is final-message-only. Switch the
  ollama backend to `opencode run --format json` (raw JSON events) or
  tee the event stream to a per-job file under `.local/out/` (e.g.
  `<request_id>.agent.jsonl`), so ENT review can see tool calls, not
  just the closing prose. Parse leniently; if the event format fights
  you, capturing the raw stream to disk and scanning the final text for
  markers is enough — don't build a schema.
- Log per-job: backend, duration, cost (claude meta has
  `total_cost_usd`; capture pattern already in `agent_run.py`), turns
  when available, and where the transcript file is.

### 4. Live validation + report

Rerun the ex2 acceptance trio through HTTP (service restarted on new
code) plus at least one case that exercises the new tool path, e.g.
`"a 300x300 png icon of a paper crane"` (300 is not a multiple of 64 —
generate at 320 or 256, resize, convert; the offered tool does all
three). Also deliberately re-check the no-marker case still fails
cleanly. `report.md` (or per-step reports if you split) with: what the
agent did with the offered tool (used it? ignored it? misused it? — all
three are findings), URL-verification hits, transcript samples, updated
cost/latency, and the next hardening list.

## Facts and hints from ex2 you should not have to rediscover

- Charter: `service/charter.md`, re-read on every request — wording
  changes need no service restart. It is the main tuning lever; prefer
  charter fixes over code until behavior recurs.
- The weak ollama agent (qwen3.6:35b via opencode 1.18.10) is the
  default *on purpose* — it surfaces charter gaps. Observed failure
  modes so far: retyping long presigned URLs lossily (high-entropy
  signature corrupted), inventing dimensions when the desire is
  size-silent, ending in prose without the marker line. Charter already
  has counter-wording for all three; keep them when rewriting.
- opencode specifics: reads the prompt on stdin; `NO_COLOR=1` still
  leaves some ANSI noise (runner strips it); permissions come from the
  committed `opencode.json` (deny-by-default bash map — extend patterns
  there when you add the new tool); model/binary via
  `AGFORGE_OPENCODE_MODEL`/`AGFORGE_OPENCODE_CMD` in `.local/.env`.
  Known flake: exit 0 with empty stdout, rare, retry-able.
- claude backend: `AGFORGE_AGENT_BACKEND=claude`, binary path in
  `.local/.env` (`AGFORGE_CLAUDE_CMD`, VSCode extension bundle path —
  breaks on extension updates). Observed: yardstick case $0.162,
  6 turns, 26 s, same judgment chain as ollama. Escalate per-request by
  env override; no divergence findings yet.
- Numbers to beat/expect (ollama backend): plain desire 40–44 s,
  format-fix 44 s, refusal 16–20 s, all $0. Generation itself is tens of
  seconds of that. Budget 900 s is nowhere near tight.
- SwarmUI still emits JPEG regardless of request; sizes must be 64–2048
  and SD wants multiples of 64. `sips` and Pillow (project dep, plain
  `uv run python` works) are both available for conversion.
- Presigned URLs must be signed against `agstudio.local:9100` (already
  handled by `generate.py`); a valid HMAC-SHA1 signature is 28 base64
  chars — the ex2 corruption was a 30-char non-multiple-of-4 string,
  which is how it was caught by eye. Your GET check makes that manual
  skill unnecessary.
- Tests: keep the ex2 pattern — deterministic shell only, via the
  `AGFORGE_AGENT_CMD` stub (`tests/fake_agent.py`); agent behavior is
  observed live, never unit-tested. `uv run pytest -q` must stay green
  with no live services. For the URL check, point the stub's
  `RESULT_URL` at a local `http.server` or monkeypatch the fetch.
- Service ops: `service/serve.sh` on :8092, hand-started, jobs vanish on
  restart; log at `.local/out/service.log`.

## Out of scope

Music/video, multi-image, persistent job store, subjective quality
judgment, changes to the HTTP contract, automating the problem-review
loop, retry machinery for agent runs (a failed run failing loudly is
still the contract).
