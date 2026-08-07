# agforge agentify — plan

Goal: make agforge's request service live up to its stated concept — a
**fully prompt-only** endpoint where an internal agent reads the caller's
desire, assembles the concrete generation parameters itself (resolution and
other quantitative requirements included), verifies the result against what
the desire asked for, and honestly refuses/fails when it can't satisfy it.

Background: today `POST /api/requests {"desire": ...}` passes the desire
verbatim to `scripts/generate.sh` as the SwarmUI prompt. Numeric parameters
come only from `params/defaults.toml` / `.local/.env` — a size stated in the
desire text is decoration, not control
([request_service.py:43-50](../../../../agforge/service/request_service.py#L43-L50),
[generate.py:160-188](../../../../agforge/scripts/generate.py#L160-L188)).
This mismatch is what asset_reconcile will trip over.

Policy: experimental environment, breaking-change phase. `generate.sh` /
`generate.py` stay **unchanged** — they are the verified low-level tool the
agent drives via its existing CLI flags. The public HTTP contract also stays
unchanged (desire in, artifacts out), so agdevworld and the coming director
need no changes. What gets replaced is the service's internal `run_job` path;
per repo policy do not keep a legacy verbatim path behind a flag — the agent
path becomes *the* path.

## Shape of the internal agent

Keep it clusterintent-executer sized: a bounded pipeline in plain Python with
exactly **one LLM one-shot** for interpretation, everything else mechanical.

1. **Interpret** (LLM, `claude -p --output-format json`, one shot):
   input = desire text; output = strict JSON:
   `{"prompt": "<cleaned creative prompt>", "width": int|null,
     "height": int|null, "refuse": false}` or
   `{"refuse": true, "reason": "<one sentence>"}`.
   - The agent extracts quantitative requirements out of the desire and
     returns them as fields; the creative prompt it returns should no longer
     contain them (a diffusion model doesn't need "512x512" as prose).
   - null width/height = desire stated no size → config defaults apply.
   - Refuse is for desires agforge cannot honor (e.g. asks for video/music
     today, or dimensions outside sane bounds). Refusal must carry the reason.
2. **Validate** (code): ints within bounds (e.g. 64–2048), round to the
   nearest multiple of 64 (SD-family requirement) — record when rounding
   changed the number, since exact-size callers will then get a resize below.
3. **Generate** (code): run `generate.sh` with `--width/--height` when set.
4. **Verify** (code, no LLM): decode the local output file
   (`stderr` line `local: <path>`), check actual dimensions against the
   requested ones. On mismatch: retry once; still wrong → if the aspect
   ratio matches, a deterministic resize to the exact requested size is
   acceptable (record it); otherwise `failed` with an honest detail.
5. **Respond**: same job dict as today. New failure detail prefixes so
   callers can tell classes apart textually: `refused: ...`,
   `unsatisfied: ...` (verify gave up), plus existing pipeline errors.
   Contract stays `working|done|failed` — no schema change.

Subjective quality is explicitly **not** this agent's job — the caller
(director) judges taste. This agent only makes quantitative intent real.

## Steps

### Step 1 — interpreter one-shot

`service/interpret.py` (or a module the service imports): prompt template +
the `claude -p` call + strict JSON parsing/validation. Model
`claude-sonnet-5` pinned; on malformed JSON retry the call once, then fail
the job (`failed`, detail `interpreter error: ...`).

Done: a small CLI (`uv run service/interpret.py "<desire>"`) prints the
validated JSON for: a plain desire, a desire with "512x512", a desire with
weird size ("513 by 300ish"), and a refusable desire.

### Step 2 — pipeline wiring

Replace `run_job`'s body: interpret → validate → generate (with flags) →
verify → respond. Keep the whole job under the existing 900 s budget
(interpreter well under a minute; one retry generation still fits).

Done: service starts, `/healthz` ok, a desire with an explicit size returns
a presigned URL whose image is exactly that size (needs live SwarmUI + MinIO
— this is the real acceptance; do it against the local devenv).

### Step 3 — tests

`tests/` beside the service (agforge has none yet — start small):

- Interpreter contract tests with a **fake LLM** (env var or injected
  callable pointing at a stub script): field extraction, null passthrough,
  refusal, malformed-JSON retry.
- Pipeline tests with a **fake generate.sh** (writes a PNG of a
  configurable size): happy path, wrong-size→retry→resize, wrong-aspect →
  `unsatisfied`, refusal short-circuits before generate.
- One live smoke (manual, not CI): real SwarmUI, desire "…, 512x512",
  assert the downloaded artifact is 512×512.

Done: `uv run pytest -q` green with no live services; live smoke recorded in
the report.

### Step 4 — docs + report

- Update `agforge/README_DEV.md`: the service section now describes the
  agent path (interpret → generate → verify → refuse semantics, failure
  detail prefixes); note that `generate.sh` remains the direct low-level
  tool for humans/scripts.
- `report.md` in this folder: interpreter cost per request, observed
  latency, live-smoke evidence, and anything that should feed back into
  asset_reconcile (which is the first real consumer — its Step 3 dimension
  check is effectively this episode's external acceptance test).

## Hints

- The known-good headless pattern (flags, JSON output capture, cost fields)
  is agautolab's `claude_code` adapter — copy its invocation, not its
  machinery. Prompt on stdin avoids shell-quoting grief.
- The interpreter's system prompt should enumerate what agforge *can* do
  today (single still image, PNG/JPEG, size range) so refusals are grounded;
  keep that capability list in one place — it will grow (music/video) and
  `artifacts[].kind` is already future-proofed for it.
- `generate.py` prints `local: <path>` to **stderr** and the URL as the last
  **stdout** line — the verify step can use the local file directly instead
  of re-downloading the presigned URL. Pillow inline-dep or `sips` both work
  for dimension checks; Pillow also does the aspect-preserving resize.
- Interpreter cost should be around a cent per request (short prompt, tiny
  JSON out) — log `total_cost_usd` per job like the autolab adapter does, so
  the report can state it instead of guessing.
- SwarmUI rejects requests without `model`; that stays config-owned
  (`AGFORGE_SWARMUI_MODEL`) — the interpreter must NOT pick models.
- Keep `.local/.env` defaults as they are; with the agent path live they are
  the fallback for size-silent desires, which is their originally intended
  role.
- Poll-loop/timeout discipline per local policy: every external wait (LLM
  call, SwarmUI, download) needs its own hard timeout; fail loudly, never
  hang the worker thread.

## Out of scope

Music/video kinds, model selection by the agent, multi-image requests,
persistent job store (in-memory + re-request stays), subjective quality
judgment, any change to `generate.sh`/`generate.py` or the HTTP contract.
