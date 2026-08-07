# ex3 step 2 — runner-side RESULT_URL verification

Work item 2 of [plan.md](plan.md): ex2 had two URL-fidelity incidents
(one delivered corrupted as `done`, one prevented only by charter
wording). The runner now performs one cheap deterministic GET of the
parsed `RESULT_URL` before delivering `done`. No judgment is taken from
the agent — the check is purely "does this URL answer".

## What changed (agforge repo, `service/agent_run.py`)

- New `verify_result_url(url)`: single `urllib.request` GET (stdlib —
  the runner stays dependency-free) with a 30 s timeout. GET, not HEAD,
  because MinIO presigned GETs may 403 on HEAD (plan hint). Returns
  `{"ok": True, "status", "content_type", "size_bytes"}` on 200, or
  `{"ok": False, "reason"}` on HTTP error / unreachable / timeout.
- `run_request` runs the check only when the outcome parsed as `done`.
  On failure the job becomes:

      failed: RESULT_URL failed verification (HTTP 403) — the agent
      likely mistranscribed the presigned URL

  — distinguishable as a transcription problem, per the plan. The
  check result is recorded in `meta["url_check"]` either way, so a
  successful run leaves content-type/size as free evidence (surfaced in
  the per-job log in step 3).
- `RESULT_FAILED` and no-marker outcomes never touch the network.

A corrupted MinIO signature answers 403 (SignatureDoesNotMatch), so the
ex2 incident class (28-char base64 signature retyped into a 30-char
non-multiple-of-4 string) is exactly what this catches — the by-eye
signature-length skill from ex2 is no longer needed.

## Tests (deterministic, no live services)

- The shared `agent` fixture now stubs `verify_result_url` to success,
  so the pre-existing tests' example URLs (`http://x.example/...`) stay
  off the network and keep passing unchanged.
- New section with the real verifier active:
  - local `http.server` serving `/good.png` → `done`, with
    `meta["url_check"]` carrying status/content-type/size;
  - same server answering 403 for any other path → `failed`, detail
    contains `HTTP 403` and `mistranscribed`;
  - connection-refused URL (`127.0.0.1:1`) → `failed` with
    `RESULT_URL failed verification`;
  - `RESULT_FAILED` outcome → no `url_check` in meta (no network).

`uv run pytest -q` → **23 passed** (was 19).

## Notes

- README_DEV's agent-path section documents the new step 4
  (verification) of the run shape.
- The 30 s check timeout is outside the 900 s agent budget; acceptable
  since the budget is nowhere near tight (ex2 numbers).
