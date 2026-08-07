# agforge agentify ex1 — local-LLM interpreter backend

Follow-up to [../report.md](../report.md). The interpreter's job — one
strict-JSON one-shot per request — is far below claude-class capability,
and at $0.070/request the pinned `claude-sonnet-5` was the pipeline's only
marginal cost. The interpreter can now run against the ollama server on
`agstudio` instead: same prompt, same validator, same retry and failure
classes, zero marginal cost, and comparable latency. The HTTP contract,
`generate.sh`/`generate.py`, and all failure prefixes are untouched.

## What changed

- `service/interpret.py`: `run_llm()` dispatches on
  `AGFORGE_INTERPRET_BACKEND` (`claude`, the default, or `ollama`). The
  ollama path is one `/api/generate` call with `format: json` and
  temperature 0. Config resolution is process env → `.local/.env` for the
  backend switch, `AGFORGE_OLLAMA_URL`, and `AGFORGE_OLLAMA_MODEL` — the
  endpoint and model are configuration only, never committed
  (`.local/` is git-ignored; verified with `git check-ignore`).
  `AGFORGE_INTERPRET_CMD` (the test hook) still overrides everything.
- `service/request_service.py`: the per-job interpreter log line now names
  the backend.
- `meta` from every backend carries `backend`; ollama meta reports the
  model and server-side duration instead of `total_cost_usd`.
- Tests: 6 new (backend resolution incl. `.local/.env`, unknown-backend
  error, unconfigured-ollama error, ollama happy path against a stubbed
  HTTP layer asserting the exact request shape, test-hook precedence).
  `uv run pytest -q`: **31 passed**, no live services.
- Docs: README_DEV backend section + env key list; local specifics in
  `agforge/.local/devenv.md`.

## Backend decision

- **Chosen: direct ollama API** with `qwen3.6:35b-a3b-coding-nvfp4`
  (already served on agstudio). Pre-implementation feasibility run pushed
  the *real* `build_prompt()`/`parse_interpretation()` through it: 4/4
  desires correct — exact sizes ("512x512"), fuzzy sizes ("513 by
  300ish" → 513×300), size-silent → null/null, wrong medium (piano
  melody) → refusal with a correct reason. First-attempt valid JSON every
  time at temperature 0.
- **Rejected: opencode route.** opencode's default model already points at
  the same ollama instance, so that path is the same model wrapped in an
  agent harness — session state and a JSON event stream to parse, no
  benefit for a one-shot. (Also ruled out per instruction.)
- **Rejected: `glm-4.7-flash` as the ollama model.** Returned empty output
  under `format: json` on every probe (thinking-mode interaction);
  recorded in `.local/devenv.md` as a do-not-use for this role.

## Numbers (vs. the parent report)

| | claude backend | ollama backend |
|---|---|---|
| Cost per request | $0.070 ± 0.001 | $0 |
| Interpreter latency | 2.1–4.5 s | 0.6–12.7 s (upper end = cold model load; warm ≈ 1–9 s) |
| End-to-end | ~30 s | ~15 s observed |

The parent report's "haiku-class model is the obvious lever" is hereby
pulled harder than planned: the lever went to $0.

## Live evidence (service restarted on new code, listener PID verified)

- CLI check: "a watercolor hummingbird, 513 by 300ish" →
  `{"prompt": "a watercolor hummingbird", "width": 513, "height": 300}`,
  meta `backend=ollama, attempts=1`.
- Full pipeline: 768×448 desire → `done`, downloaded artifact measured
  exactly 768×448; job log shows
  `interpreter backend=ollama cost_usd=None duration_ms=11902 attempts=1`.
- Refusal path: "please compose a short piano melody" →
  `failed / "refused: agforge can only generate still images, not audio or
  music."` — same failure class contract consumers already dispatch on.

## Operational notes

- The active backend on agstudio is now `ollama` (set in
  `agforge/.local/.env`). Fallback is one line: set
  `AGFORGE_INTERPRET_BACKEND=claude` (or delete the line) and restart the
  service.
- New retryable failure text: `interpreter error: ollama request failed:
  ...` (server down / model missing). First check `ollama ps`.
- Cold-start: after ollama idles the model out, the first interpretation
  pays ~10 s model load — well inside the 900 s job budget, but visible in
  per-job latency.
