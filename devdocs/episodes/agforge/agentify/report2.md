# agforge agentify — Step 2 report (pipeline wiring)

## What was built

`run_job` in `agforge/service/request_service.py` is now the agent
pipeline (the legacy verbatim path is gone, per repo policy):

1. **Interpret** — `interpret.interpret(desire)`; `InterpretError` →
   `failed` with `interpreter error: ...`; refusal → `refused: <reason>`.
   Interpreter cost/latency logged per job.
2. **Validate** — `validate_dimension`: out-of-bounds → `refused: ...`;
   multiple-of-64 rounding recorded (drives the resize decision later).
3. **Generate** — `generate.sh --width/--height` (unchanged script), run
   against a job-wide deadline: the whole job shares the original 900 s
   budget (`deadline - now` is each attempt's subprocess timeout).
4. **Verify** — local file from the `local: <path>` stderr line, actual
   pixels via Pillow. Mismatch → retry once, except when the generator
   produced exactly what it was told (retry can't help). Persistent
   mismatch: resize is acceptable for rounding-induced mismatch, a
   single-dimension request, or aspect ratio within 2 %; otherwise
   `failed` with `unsatisfied: ...`.
5. **Respond** — same job dict / HTTP contract as before. Deterministic
   resize (Pillow LANCZOS) re-uploads via `generate.py`'s own
   `upload_and_presign` (imported, not duplicated), so the returned URL
   always points at the verified image.

Service deps grew to `pillow, boto3, requests` (inline script metadata).
`AGFORGE_GENERATE_CMD` was added as the fake-generate test hook for Step 3.

## Done-condition evidence (live, local devenv: SwarmUI on agpc + MinIO)

- Service starts, `GET /healthz` → `{"ok": true}`.
- Desire "a koi pond with maple leaves, 768x448 please" → `done`, presigned
  URL, downloaded image **768×448 exactly** (deliberately non-default size;
  config default is 512×512, so this proves the desire's numbers control
  generation now).
- Desire "portrait of an astronaut, make it 513 by 300ish" → interpreter
  extracted 513×300, validator rounded to 512×320 for generation, verify
  saw the mismatch and the deterministic resize produced **513×300
  exactly**, re-uploaded; service log shows each recorded step. End-to-end
  well under the 900 s budget (~30 s wall clock).

## Incident during acceptance (caught and fixed)

The first acceptance run silently hit an **old service instance** still
listening on :8092 from before this episode — my new instance had died with
`Address already in use` in its log while `/healthz` answered from the old
process. Symptom that exposed it: a 768×448 desire came back 512×512
(verbatim path). Killed the stale PID, restarted with the new code, and
re-ran — all green as above. Lesson recorded for the report: after
deploying, verify the listener PID, not just `/healthz`.
