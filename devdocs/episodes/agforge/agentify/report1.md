# agforge agentify — Step 1 report (interpreter one-shot)

## What was built

`agforge/service/interpret.py` — the interpreter module + manual CLI:

- `interpret(desire) -> (interpretation, meta)`: one `claude -p
  --output-format json` shot (model pinned `claude-sonnet-5`), prompt fed on
  stdin per the agautolab `claude_code` adapter pattern. Strict JSON shape
  validation; on a malformed answer the shot is retried once, then
  `InterpretError` is raised (the service will map it to `failed` with
  detail `interpreter error: ...`).
- Output shapes exactly as planned: `{"prompt", "width", "height",
  "refuse": false}` with `null` dims meaning "config defaults apply", or
  `{"refuse": true, "reason"}`.
- The capability list (single still image, PNG/JPEG, 64–2048 px) lives in
  one `CAPABILITIES` constant inside the prompt template, ready to grow.
- `validate_dimension()` (Step 2's validate stage lives here too): bounds
  check 64–2048, rounding to the nearest multiple of 64, reporting whether
  rounding changed the number.
- `meta` carries `total_cost_usd` / `duration_ms` from the CLI JSON so the
  service can log per-job cost.

## Environment note

`claude` is not on PATH on this machine (it runs from a VSCode extension
bundle), so the binary path is resolved via `AGFORGE_CLAUDE_CMD` — process
env first, then `.local/.env`, then plain `claude`. The actual path was
recorded in git-ignored `.local/.env`. Test hook `AGFORGE_INTERPRET_CMD`
replaces the whole invocation with a stub command (for Step 3's fake-LLM
tests).

## Done-condition evidence (live CLI runs)

| Desire | Result | Cost / latency |
| --- | --- | --- |
| "a cozy cabin in a snowy forest at dusk" | prompt cleaned, `width/height: null` | $0.070 / 4.5 s |
| "a red dragon over a castle, 512x512" | size moved out of prompt, `512×512` | $0.070 / 2.7 s |
| "portrait of an astronaut, make it 513 by 300ish" | `513×300` (validate stage will round to 512×320 later) | $0.070 / 3.6 s |
| "a 30-second lofi hiphop track for studying" | `refuse: true`, reason names the missing capability | $0.070 / 2.9 s |

All first-attempt successes (no malformed-JSON retries observed).

## Observations

- Cost is ~$0.07 per request, not the ~1 cent the plan hinted — the pinned
  `claude-sonnet-5` one-shot carries a fixed prompt+system overhead. Worth
  revisiting (e.g. haiku-class model) only if request volume makes it
  matter; correctness first for now.
- Latency 2.7–4.5 s — well under the "interpreter under a minute" budget.
