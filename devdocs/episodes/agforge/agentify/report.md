# agforge agentify — final report

The request service now lives up to its prompt-only concept: an internal
agent interprets the caller's desire, assembles the concrete generation
parameters itself, verifies the produced pixels against what the desire
asked for, and refuses/fails honestly when it can't satisfy it. The legacy
verbatim path is gone; `generate.sh`/`generate.py` and the HTTP contract
are untouched, so agdevworld and the coming director need no changes.

Per-step details: [report1.md](report1.md) (interpreter),
[report2.md](report2.md) (pipeline wiring + live acceptance),
[report3.md](report3.md) (tests), [report4.md](report4.md) (docs).

## Numbers

- **Interpreter cost**: $0.070 ± 0.001 per request (`total_cost_usd` from
  the `claude -p` JSON, logged per job). Notably above the plan's ~1¢
  guess — the pinned `claude-sonnet-5` one-shot carries fixed
  prompt/system overhead. A haiku-class model is the obvious lever if
  volume ever makes this matter.
- **Interpreter latency**: 2.1–4.5 s observed (7 live shots, all
  first-attempt valid JSON — the retry path never fired outside tests).
- **End-to-end**: ~30 s wall clock per request against the local devenv
  (SwarmUI on agpc, MinIO on agstudio), far inside the 900 s job budget.

## Live evidence

- `/healthz` ok after deploy; 768×448 desire (deliberately non-default;
  defaults are 512×512) returned an artifact measuring exactly 768×448 —
  proof the desire's numbers now control generation.
- "513 by 300ish" → interpreted 513×300 → generated at rounded 512×320 →
  deterministic resize → downloaded artifact exactly 513×300.
- Smoke: "a watercolor hummingbird, 512x512" → exactly 512×512.
- `uv run pytest -q`: 25 passed in ~2 s, no live services.

## Feedback for asset_reconcile (first real consumer)

- Its Step 3 dimension check should now pass by construction: `done`
  artifacts either measured exactly right or were deterministically
  resized to the requested size before presigning. If it still sees a
  mismatch, that's a bug here — please report, don't work around.
- Sizes are only honored when stated in the desire *text* (any phrasing;
  the interpreter normalizes). Size-silent desires get config defaults
  (currently 512×512), which reconcilers should treat as unspecified, not
  as a promise.
- New failure classes to dispatch on textually: `refused: ...` (don't
  retry — agforge cannot honor the desire, e.g. music/video or dimensions
  outside 64–2048), `unsatisfied: ...` (generation couldn't match the
  desire; retrying may help, taste won't), `interpreter error: ...` and raw
  infra errors (retryable).
- Exact odd sizes (not multiples of 64) are delivered via resize, so pixel
  content is interpolated — if reconcile ever cares about native-resolution
  generation, request multiples of 64.

## Operational notes

- During Step 2 acceptance a stale pre-episode service instance was still
  holding :8092 — `/healthz` answered while the new code's process had died
  with `Address already in use`. After any deploy, verify the listener PID,
  not just `/healthz`.
- The `claude` binary path on this machine lives in `.local/.env`
  (`AGFORGE_CLAUDE_CMD`) and points into a versioned VSCode extension
  bundle; it breaks on extension updates (recorded in `.local/devenv.md`).
