# ex3 step 4 — live validation: the tool was used, the URL check earned its keep

Work item 4 of [plan.md](plan.md). Service restarted on ex3 code
(old PID 49511 → new PID 52113, jobs vanish by contract), then the ex2
acceptance trio plus the new-tool case were run live over HTTP against
the default ollama backend (qwen3.6:35b via opencode 1.18.10), plus a
deliberate no-marker check. Every run left a per-job transcript.

## Results

| case | desire | outcome | wall clock | cost |
|---|---|---|---|---|
| 1 plain | watercolor fox, no size/format | done (jpeg, defaults kept) | 31 s | $0 |
| 2 yardstick, run 1 | 256x256 png wolf emblem | **failed by URL verification (HTTP 403)** | 38 s | $0 |
| 2 yardstick, run 2 | same | done, PNG 256×256 verified | 42 s | $0 |
| 3 impossible medium | 30-second jazz tune | failed honestly + own-words problem.md | 25 s | $0 |
| 4 new tool path | 300x300 png paper-crane icon | done, PNG 300×300 verified | 36 s | $0 |
| 5 no-marker | prose-only stub via HTTP (:8093) | failed cleanly: "finished without a RESULT marker" | — | $0 |

Latency is unchanged from ex2 (40–44 s band; refusal faster). Delivered
artifacts for cases 2b/4 were downloaded and measured: really PNG,
really the requested pixels.

## What the agent did with the offered tool (the headline question)

**Used it, correctly, unprompted beyond the charter.** All three
format runs called it:

- Yardstick run 2, the clean shape: `generate.sh --width 256 --height
  256` → `uv run service/transform.py --format png --width 256
  --height 256 <file>` → `file` verify → correct URL. One line where
  ex2 needed a convert/verify/re-upload improvisation.
- Case 4 showed the intended judgment chain in the agent's own words:
  "Since 300 isn't a multiple of 64, I'll generate at 320x320 …then
  resize to 300x300 in post-processing." Delivered 300×300 PNG.
- **Mild misuse (finding):** in case 4 the agent first did the resize+
  convert itself with `sips` into `/tmp/crane.png`, then *also* ran
  transform.py over that already-processed file — redundant double
  processing, harmless outcome. The charter doesn't say the tool does
  the whole job in one step; candidate wording fix.

## URL-verification hits

Yardstick run 1 is the ex2 incident class reproduced live: the
transcript shows a flawless run (generate → transform.py → verified
PNG), transform.py printed a valid URL — and the agent **retyped the
URL in its final message with a 25-char signature** (valid ones are 28
base64 chars). Ex2 would have delivered this as `done`; ex3's runner
GET got 403 and the caller received:

    failed: RESULT_URL failed verification (HTTP 403) — the agent
    likely mistranscribed the presigned URL

On the three successful deliveries the check recorded free evidence:
`url_check={'ok': True, 'status': 200, 'content_type': 'image/png',
'size_bytes': 26398}` (and jpeg/234 KB for case 1).

## Transcript samples / observability

Per-job `.local/out/<request_id>.agent.jsonl` captured every run,
tool calls included (`tool_use` events with command + status + output).
The per-job log line now reads e.g.:

    job e0aa…: agent backend=ollama cost_usd=0.0 duration_ms=41919
    num_turns=6 transcript=….agent.jsonl url_check={'ok': True, …}

Permission denials are visible in transcripts too: `bash
scripts/generate.sh …` (not in the allowlist — only the direct/`sh`
forms are) and piped `file … | head -1` were denied by opencode; the
agent recovered by itself each time. Friction, not failure.

## Other findings

- **Problem-path deviation:** case 3's report landed in
  `…-<full 32-char request_id>/problem.md` instead of the charter's
  exact `…-<request_id[:8]>/` path. Content rule fully honored (quotes
  the desire, what was tried, why impossible — in its own words);
  location rule paraphrased. Charter wording candidate.
- The agent writes intermediates to `/tmp` sometimes (case 4) instead
  of `.local/out/` — harmless, observation only.

## Next hardening list (candidates for ex4 — none earned twice yet)

1. **URL transcription remains the weakest link** (1 of 3 live URL
   deliveries corrupted, even with the charter's exact-copy wording).
   The runner now *catches* it; the next step would be *surviving* it —
   e.g. runner falls back to the last presigned URL printed in the
   transcript's tool output when the final-message URL fails
   verification. That starts taking delivery out of the agent's words;
   decide deliberately in ex4.
2. Charter: "transform.py does resize+convert+upload in one step" (the
   case-4 double processing), and harder wording on the exact problem
   path (case-3 deviation). Both single observations so far — charter
   fixes only if they recur.
3. opencode allowlist: add `bash scripts/generate.sh *` and consider
   the pipe friction (`file X | head -1` denied). Recoverable, cheap.

## Episode close

All four plan work items delivered: the earned tool is offered and was
used correctly live; both ex2 failure classes are now caught by the
runner (URL corruption → verification failure with a transcription
detail; infra failures keep stderr); every run leaves a reviewable
event transcript with cost/turns; live behavior validated over HTTP
with the trio + tool case + no-marker check. `uv run pytest -q`: 30
passed, no live services. Step reports: [report1.md](report1.md),
[report2.md](report2.md), [report3.md](report3.md).
