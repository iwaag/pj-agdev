# Step 3 report — add the director window

## Result

Implemented `POST /director` in `agautolab/agent/gateway.py` and committed the
submodule change as `87a9acc` (`Add workspace-backed director window`).

The route:

- accepts the existing `{ "text": "..." }` request shape;
- invokes only Claude in one-shot `-p` mode;
- resolves the Claude binary through the existing PATH/pointer/glob logic;
- runs with the configured direction clone as its working directory;
- passes only `Read,Glob,Grep` through `--allowedTools`;
- sends exactly `First, read GUIDE.md. Then, follow this request.:\n` plus the
  request text, without injecting `GUIDE.md`, `concept.md`, or another system
  prompt;
- preserves Claude's returned result text in the response and record;
- serializes calls with an in-process lock; and
- writes every success or failure to `.local/agent/director/run-NNNN.json`,
  including backend, model, duration, cost, and the backend's failure text
  when available.

The workspace setting is centralized as `AUTOLAB_DIRECTOR_WORKSPACE`; the
ignored local configuration sets it to
`.local/direction/scifi-direction`. A relative value resolves from the
agautolab checkout, so no absolute developer path is tracked.

## Verification

- `python3 -m py_compile agent/gateway.py`: passed.
- `uv run pytest -q tests/test_gateway_window.py`: 15 passed.
- `uv run pytest -q`: 76 passed.
- Confirmed the installed Claude CLI documents comma- or space-separated
  `--allowedTools` values.
- Located the old gateway listener with `lsof` as PID `7342`, stopped that
  exact PID, and started the new gateway as PID `26160`.
- Confirmed PID `26160` owns port 8791 and `GET /healthz` returns HTTP 200.
- Confirmed the new route is active without spending a model call: an empty
  JSON object receives the expected HTTP 400 request-shape error.
