# Step 1 Report — Service implementation

Completed 2026-08-11.

Implemented the public `music-gen` workspace as a small FastAPI service around
the existing ACE-Step REST API. `POST /generate` accepts a required prompt and
optional duration, seed, and steps; it submits and polls ACE-Step, stores the
completed WAV, and returns an HTTP audio URL. The service also exposes
`/healthz` and a self-describing `/guide`.

Deployment-specific endpoints and paths are environment variables and are not
committed. Generated audio and local environments are ignored.

Validation: `uv run pytest -q` passed (2 tests), `compileall` passed, and
`git diff --check` passed.

Commit in `music-gen`: `14be49e Add ACE-Step music generation HTTP service`.
