# ex2 step 3 report — live acceptance through the HTTP API

Status: **done**. Service restarted on the new code (old PID 47554
killed, new PID 49511, `/healthz` ok), all traffic through
`POST /api/requests` / polling `GET`, ollama backend
(opencode + qwen3.6:35b-a3b-coding-nvfp4) throughout. All three cases
ended in the expected state; two of them only after charter fixes that
the failures themselves motivated — recorded below, not hidden.

## Case 1 — the first-ent yardstick

Desire: `"a small medieval castle emblem, 256x256, PNG format"`

**Passed on the first try, the way the episode hoped.** The agent
generated (256×256 came back as JPEG), *noticed the format mismatch on
its own*, converted to PNG, verified 256×256, re-uploaded via the
`generate.py` helper, and delivered the PNG URL. Downloaded artifact
measured **256×256, format png**, HTTP 200. Wall clock 43.7 s. Agent
transcript (final message) shows the judgment chain explicitly:

> The file was generated as JPEG. I need to convert it to PNG at 256x256
> as requested, then re-upload. … PNG is 256x256 as required. Now I'll
> re-upload it to get a fresh presigned URL.

This is exactly the caller-asked-for-PNG signal that the old
deterministic jpeg→png conversion used to erase.

## Case 2 — impossible medium

Desire: `"a short lofi hip-hop track"`

- **Attempt 1: unexpected infra-class failure** — job failed with
  `agent produced no output`: opencode exited 0 with an empty stdout, no
  problem.md. Not reproducible; a manual rerun of the identical desire
  worked normally (16 s). Kept as know-how: the opencode/ollama harness
  can intermittently return an empty final message, and the runner
  correctly treats that as an infra failure (no ENT problem report), but
  the runner currently discards stderr in that path — a diagnosis gap
  listed for step 4.
- **Attempt 2 (HTTP): passed** — `failed` with detail
  `"Image-only system cannot generate music/audio tracks"` and an
  agent-authored `problem.md` (20260807-164433Z-c63cc91d) that quotes
  the desire, states what was attempted, and why it cannot be honored,
  in the agent's own words.

## Case 3 — size-silent desire

Desire: `"a serene mountain lake at sunset"`

- **Attempt 1: failed, two real charter gaps surfaced** (this is the
  weak-agent feedback the episode deliberately shopped for):
  1. The agent generated at **1024×768 — dimensions it invented**; the
     charter never said "no size in the desire → omit the flags".
  2. The final message described success in prose and **omitted the
     `RESULT_URL:` line entirely**, so the runner failed the job with
     the output tail as detail (lenient parsing behaved as designed).
- Charter fixes (both wording-only): "If the desire states no size, OMIT
  the --width/--height flags entirely … never invent dimensions", and
  "a final message without a RESULT line is treated as a failed request
  — always write the marker line yourself".
- **Attempt 2: passed** — the agent omitted the flags, config defaults
  applied: downloaded artifact measured **512×512 jpeg**, HTTP 200,
  wall clock ~44 s, and the final message explicitly reasons "The caller
  specified no particular size or format, so the configured defaults are
  appropriate."

## Reading the outputs (the human-judgment bar)

Every final transcript and problem.md above is understandable on its
own: what was asked, what the agent did, why it ended the way it did.
The bar "a human can understand what happened" is met in all six runs,
including the failed ones.
