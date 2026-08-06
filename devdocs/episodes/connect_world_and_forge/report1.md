# Report — Step 1: agforge request service

## What was done

- Verified the premises before writing code: SwarmUI and MinIO (addresses per
  `agforge/.local/.env`) both answered, and `scripts/generate.sh "premise
  verification test"` produced a fetchable presigned URL (HTTP 200,
  image/jpeg).
- Added `agforge/service/request_service.py` (stdlib-only, uv inline-script
  style) plus `agforge/service/serve.sh`, implementing the plan's contract
  verbatim:
  - `POST /api/requests {"desire": ...}` → `202 {"request_id"}`
  - `GET /api/requests/{id}` → `working | done | failed`, `artifacts:
    [{kind:"image", url}]`, `detail` on failure
  - `GET /healthz`
- In-memory job dict guarded by a lock; each request runs
  `scripts/generate.sh "<desire>"` via `subprocess` on a daemon thread and
  takes the final stdout line as the presigned URL. Port 8092 by default
  (`AGFORGE_SERVICE_PORT` to override).
- Documented the service (port, contract, run command, jobs-vanish-on-restart
  caveat) in `agforge/README_DEV.md`.

## Acceptance checks

- `POST {"desire":"a red circle"}` then polling reached `done` with a
  presigned URL for the generated image. ✅
- Empty desire → job reaches `failed`, `detail` carries generate.py's
  "prompt is empty" usage error. ✅ (Design note: the service accepts the job
  and lets the pipeline reject it, matching the plan's wording that an empty
  desire "reaches failed"; a missing/non-string `desire` is instead a 400.)
- Broken SwarmUI URL (temporarily pointed `.local/.env` at a dead port,
  restored afterwards) → `failed` with the stderr tail (ConnectionError
  traceback) in `detail`. ✅
- Unknown request id → 404; non-JSON body → 400 with detail. ✅

## What held / what surprised

- The verified pipeline really was reusable byte-for-byte; the service adds
  no generation knowledge at all — the whole file is ~150 lines of plumbing.
- No external dependencies were needed: `ThreadingHTTPServer` + `subprocess`
  + a locked dict covered everything. The uv inline-script header is kept
  (empty deps) purely for stylistic consistency with `scripts/`.
- Minor wrinkle: on failure the stderr tail is a Python traceback tail
  (last 800 chars), which is useful for a developer but noisy for end users.
  Left as-is per the plan ("surfacing the error is the job"); a friendlier
  mapping can come with the future agent backend.
