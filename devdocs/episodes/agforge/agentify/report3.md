# agforge agentify — Step 3 report (tests)

## What was built

`agforge/tests/` (first tests in the repo) plus a minimal `pyproject.toml`
so `uv run pytest -q` works from the repo root (deps mirror the service
scripts' inline metadata; pytest lives in the dev dependency group).

- `fake_llm.py` — `AGFORGE_INTERPRET_CMD` stub printing claude-style outer
  JSON; per-call result sequences via a counter file (drives the retry
  tests).
- `fake_generate.py` — `AGFORGE_GENERATE_CMD` stub with generate.sh's
  observable contract (`local: <path>` on stderr, URL as last stdout line);
  writes a real PNG (stdlib-only encoder) either obeying `--width/--height`
  or forcing sizes per call; a marker-file option lets tests prove
  generate was never reached.
- `test_interpret.py` (14 tests) — field extraction, null passthrough,
  refusal (and refusal-without-reason rejected), malformed-JSON
  retry-once-then-succeed and twice-then-fail, non-integer dimension
  rejected, `validate_dimension` bounds/rounding table.
- `test_pipeline.py` (8 tests) — happy path exact size, size-silent desire
  falls through to defaults, wrong-size → one retry → success,
  rounding (513×300 → generate 512×320 → Pillow resize back to exactly
  513×300, upload monkeypatched, no pointless retry), wrong aspect after
  retry → `unsatisfied:`, refusal and out-of-bounds size short-circuit
  before generate (marker file untouched), interpreter error fails the job
  without generating.

## Done-condition evidence

- Offline: `uv run pytest -q` → **25 passed in 2.13 s**, no live services
  involved (fresh `.venv` created by uv on first run).
- Live smoke (manual, real SwarmUI + MinIO): desire
  "a watercolor hummingbird, 512x512" → `done`, presigned URL, downloaded
  artifact measured **512×512** with `sips`. Interpreter cost for the smoke
  job: $0.0698, 2.6 s (from the service log).

## Notes

- `.gitignore` gained `.venv/`, `__pycache__/`, `uv.lock`.
- The fakes deliberately test through real subprocess boundaries (same code
  path as production) rather than injecting Python callables.
