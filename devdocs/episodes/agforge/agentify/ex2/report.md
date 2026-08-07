# agforge agentify ex2 — final report: the pipeline handed back to the agent

Outcome: **the course correction landed.** The request service now runs
one trusted agentic run per request (charter → headless agent with a
scoped tool allowlist → lenient `RESULT_URL:`/`RESULT_FAILED:` parsing).
The strict-JSON interpreter, the code-side verify/retry/resize/convert
stages, and the code-templated problem report are gone from the request
path. The HTTP contract, `generate.sh`/`generate.py`, the port, the
in-memory job store, and the 900 s budget are unchanged; callers are
unaffected. Step reports: [report1.md](report1.md),
[report2.md](report2.md), [report3.md](report3.md).

The first-ent yardstick behaves the way the episode was cut for: asked
for a 256×256 PNG emblem, the agent generated, noticed the generator's
JPEG on its own, converted, verified, re-uploaded, and delivered — and
when asked for music, it wrote a problem report in its own words that
finally contains the load-bearing facts (what was asked, what was tried,
why it cannot be done).

## Cost / latency vs. the deterministic pipeline

| | deterministic pipeline (parent/ex1) | ex2 ollama agent (default) | ex2 claude agent (comparison) |
|---|---|---|---|
| Marginal cost per request | $0 (ollama interpret) / $0.070 (claude interpret) | **$0** | $0.162 observed (1 run, 6 turns) |
| Wall clock, plain desire | ~15 s (ollama) / ~30 s (claude) | 40–44 s | — |
| Wall clock, size+format fix (yardstick) | n/a (convert was silent code) | 43.7 s | 26.0 s |
| Wall clock, impossible medium | seconds (interpret refusal) | 16–20 s | — |

The agentic loop costs roughly 2–3× the old pipeline's latency on the
ollama backend — the price of the agent driving generation, checking its
own output, converting, and re-uploading across multiple turns at zero
marginal cost. All well inside the 900 s budget.

## Agent judgment observed (good and bad)

Good — the yardstick run's chain, verbatim from the transcript:

> The file was generated as JPEG. I need to convert it to PNG at 256x256
> as requested, then re-upload. … PNG is 256x256 as required. Now I'll
> re-upload it to get a fresh presigned URL.

Good — the size-silent run after the charter fix:

> The caller specified no particular size or format, so the configured
> defaults are appropriate.

Good — the music problem report (agent-authored, own words): quotes the
desire, "There is no music generation, audio synthesis, or any form of
sound production capability in the current workspace."

Bad (all kept, all productive — each one bought a charter fix or a
hardening candidate):

1. **Corrupted presigned URL** (step 1, first run): the 35b model
   retyped the URL and dropped characters from the high-entropy
   signature (invalid base64 length). Object and upload were fine; only
   the final-message transcription broke.
2. **Invented dimensions** (step 3, case 3): size-silent desire, agent
   chose 1024×768 on its own because the charter never said "no size →
   omit the flags".
3. **Missing marker line** (step 3, case 3): perfect generation
   described in prose, no `RESULT_URL:` line; lenient parsing correctly
   failed the job with the tail as detail.
4. **Empty-output flake** (step 3, case 2, not agent judgment): opencode
   exited 0 with empty stdout once; unreproducible. The runner rightly
   classed it as infra (no ENT problem report), but discards stderr in
   that path, so there was nothing to diagnose with.

## Charter fixes made this episode (ENT input to ex3)

The charter (`service/charter.md`) is the tuned artifact; three wording
fixes were bought by live failures:

1. URL fidelity: "reproduce it exactly, never retype or shorten it."
2. Size-silent rule: "OMIT the --width/--height flags entirely … never
   invent dimensions the caller did not ask for."
3. Mandatory ending: "a final message without a RESULT line is treated
   as a failed request — always write the marker line yourself."

## Hardening candidates (earned by recurrence, for ex3)

1. **jpeg→png conversion** — the expected first entry, now observed as
   the same mechanical sequence (sips/Pillow convert → verify →
   re-upload) in both backends' yardstick runs. Candidate: offer
   `service/candidate_tools.py:transform_and_upload` to the agent as a
   sanctioned tool (NOT automatic code — the agent still decides).
2. **Runner-side URL verification** — a corrupted `RESULT_URL` is
   currently delivered as `done`. One cheap deterministic check (HTTP
   GET of the URL before finishing the job) would catch transcription
   corruption without taking any judgment away from the agent. Two
   URL-fidelity incidents (one corrupted, one prevented by charter
   wording) justify it.
3. **Stderr capture on empty-output/exit failures** — the runner should
   keep the harness stderr tail in the failure detail so the next
   empty-output flake is diagnosable.
4. (Observation gap, not a rule) opencode's default headless output is
   final-message-only; if deeper transcripts are wanted for ENT review,
   `opencode run --format json` event capture is the lever.

## Divergences between backends

None substantive: claude solved the yardstick in fewer turns and less
wall clock (26 s vs 43.7 s) with the same judgment chain and a valid
URL. No case arose where ollama persistently failed and claude
succeeded, so no escalation was exercised beyond the one comparison run.

## What retired, where it lives now

- `service/interpret.py`, its tests, and the pipeline tests: deleted
  (plan's preferred option).
- resize/convert helpers: parked uncalled in
  `service/candidate_tools.py`.
- Tests now pin only the deterministic shell (charter composition,
  outcome parsing, budget, HTTP contract) via the `AGFORGE_AGENT_CMD`
  stub: `uv run pytest -q` → 14 passed, no live services.

## Out-of-scope confirmations

`generate.sh`/`generate.py` untouched; HTTP contract untouched; model
selection stays configuration-owned (charter forbids `--model` and no
run attempted it); `nctl-outbox` never touched (charter rule + bucket
policy); no skip-permissions anywhere (scoped opencode.json allowlist /
scoped `--allowedTools`).
