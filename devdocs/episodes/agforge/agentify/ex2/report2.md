# ex2 step 2 report — wire the service

Status: **done**. `run_job` is now: charter → one agent run → lenient
outcome → job dict. HTTP contract, port (:8092), in-memory jobs, and the
900 s budget are unchanged. `uv run pytest -q`: **14 passed**, no live
services.

## What changed

- `service/request_service.py` — shrank from a 5-stage pipeline to a
  thin shell: `run_job` calls `agent_run.run_request(desire, request_id,
  budget_seconds=900)` and stores the returned job dict. Per-job log
  line carries backend / cost / duration / turns, plus the agent's final
  output (the observable behavior this episode collects). All PIL/boto3
  imports left the service module.
- Retired from the request path, per plan:
  - `service/interpret.py` (strict one-shot) — **deleted**, with
    `tests/test_interpret.py` and `tests/fake_llm.py` (plan's preferred
    option: delete both).
  - Code-side dimension verify/retry/resize, format check/convert, and
    the code-templated `report_problem()` — gone from the service.
  - `tests/test_pipeline.py` and `tests/fake_generate.py` — deleted;
    they pinned retired behavior.
- `service/candidate_tools.py` — new home for `transform_and_upload`,
  `image_size`, `image_format`: kept as candidate agent tools, called by
  nothing (they re-enter only if live runs prove resize/convert is a
  recurring mechanical step).
- `tests/test_service.py` + `tests/fake_agent.py` — the deterministic
  shell only, via the `AGFORGE_AGENT_CMD` stub (same style as the old
  hooks): charter composition (desire verbatim, request id, path rule,
  finish contract, budget, no unfilled placeholders, problems-dir
  override, charter reaches the agent verbatim), lenient outcome parsing
  (URL amid prose, markdown-decorated FAILED, last-marker-wins, garbage
  → tail detail, non-http RESULT_URL rejected), infra failures (nonzero
  exit), budget timeout (fails loudly in seconds), `run_job` mapping,
  and the HTTP contract end to end (healthz, 202 → poll → done, 400,
  404) on an ephemeral-port server.
- `README_DEV.md` — the agent-path section now describes
  charter/run/lenient-parse, agent-authored problem reports, the
  `AGFORGE_AGENT_BACKEND` switch (`ollama` default via opencode,
  `claude` as comparison/escalation), and the new `.local/.env` keys.

## Notes

- Failure `detail` no longer has `refused:`/`unsatisfied:`/`interpreter
  error:` prefixes — it is the agent's own one-line reason (or the
  runner's infra error). agdevworld treats `detail` as human-readable
  text, so no caller change is needed; worth stating in the final report.
- The service has NOT been restarted on the new code yet — that is
  step 3's first move.
