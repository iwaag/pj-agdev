# ex3 step 3 — diagnosable infra failures + transcript capture

Work item 3 of [plan.md](plan.md): close ex2's two observation gaps —
the undiagnosable empty-output flake, and opencode's final-message-only
headless output hiding the agent's tool calls from ENT review.

## What changed (agforge repo)

### stderr kept in infra-failure details (`service/agent_run.py`)

- Nonzero exit: detail is now `agent exited N: <output tail>; stderr
  tail: <stderr tail>` (stderr part present only when non-empty,
  ANSI-stripped, last 800 chars).
- Empty-stdout exit-0 (the ex2 flake): `agent produced no output;
  stderr tail: …` — the next occurrence carries evidence.

### Transcript capture (ollama backend → raw JSON events)

- `build_argv` now runs `opencode run --format json`. Probed live
  against opencode 1.18.10 first: the stream is one JSON object per
  line, `{"type": "text"|"tool"|"step_start"|"step_finish", "part":
  {...}}`, with the agent's words in `part.text` of `text` events and
  per-step `cost` in `step_finish`.
- The raw stdout stream is saved per job to
  `.local/out/<request_id>.agent.jsonl` (override:
  `AGFORGE_TRANSCRIPTS_DIR`) — **also on timeout and nonzero exit**, so
  a failed run still leaves its partial transcript as evidence.
- New `extract_event_text(raw)` leniently pulls the marker-scannable
  text out of the stream: `text` events contribute `part.text`,
  `step_finish` events are counted as turns and their costs summed;
  any non-event line passes through unchanged. No schema — plain-text
  output (claude backend fallback, the test stub, an older opencode)
  degrades to identity, exactly as the plan asked.
- Charter examples cannot fake an outcome: only `text` event content is
  marker-scanned, and the URL check from step 2 backstops `RESULT_URL`.

### Per-job log line (`service/request_service.py`)

Now logs backend, duration, cost (`total_cost_usd` — claude meta as
before, summed `step_finish` cost for ollama), turns when available,
transcript path, and the step-2 `url_check` evidence
(content-type/size), plus the agent's final output as before.

## Tests (deterministic, no live services)

- fake_agent grew `FAKE_AGENT_STDERR`; new tests pin both stderr-tail
  paths (nonzero exit, empty-stdout exit-0).
- `extract_event_text`: event stream → joined text + turns/cost stats;
  plain text → identity; end-to-end run over a JSON-event stub output
  parses the outcome.
- Transcript: written and pointed at by `meta["transcript"]` on
  success, and still present (with partial output) after a nonzero-exit
  infra failure. Tests redirect via `AGFORGE_TRANSCRIPTS_DIR`.

`uv run pytest -q` → **30 passed** (was 23).

## Notes

- The live probe that pinned the event shape: `echo 'Reply with
  exactly: PING_OK' | opencode run --format json -m ollama/qwen3.6:…`
  answered in ~15 s with `step_start` / `text` / `step_finish` lines
  (tokens and cost included in `step_finish`).
- Step 4 will confirm transcripts capture real tool calls during the
  live acceptance runs.
