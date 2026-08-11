# Step 5 report — tests and live evidence

## Automated verification

`uv run pytest -q` in `agautolab` completed with **89 passed**. The focused
project-settings suite covers selection precedence, a missing file, malformed
content, unknown roles, unknown profiles, direction-workspace discovery, and
the project/profile fields in coding and director records.

## Local environment check

Before live runs, `uv run --project nctl nctl status --json` reported `ok: true`:
Nautobot 3.1.3 was reachable and authenticated, intent REST/GraphQL were
available, one worker was running, and there were no pending jobs. The manually
started agautolab gateway on port 8791 was not running, so evidence used the
same common `role_run` CLI directly rather than the HTTP entrance.

## Live records

- Director-attached `yokai`: a `role_run director` smoke request resolved
  `project=yokai`, `profile=local`, `harness=opencode`, and the local Ollama
  model. It returned the requested smoke marker with `outcome=done`. The
  normalized record and raw transcript remain under the ignored
  `.local/agent/director/` evidence directory.
- Non-director coding job: a real local/OpenCode iteration resolved
  `project=project-agent-setting-smoke`, `profile=local`, and recorded the full
  identity in `adapter_result.json`. It exposed an unrelated existing issue:
  OpenCode wrote the requested file in the agautolab checkout rather than the
  job's `target/`, so the target-scoped gate failed. Raw JSONL and gate output
  remain in the ignored job evidence; the misplaced generated file was removed.
- A second non-director iteration changed the same project selection at run
  time to `profile=stub` and converged through the fake harness in one
  iteration. Its record proves the project file is reread rather than cached.

ENT follow-up candidate: investigate why the OpenCode coding adapter's tool
working directory can escape the supplied `target/` even though the harness
process receives that cwd. This did not affect project/profile resolution.

## Post-episode follow-up

The cwd issue was subsequently reproduced as a stale inherited `PWD`: Python's
`subprocess(cwd=...)` changed the real cwd but retained the parent's `PWD`, and
OpenCode used that value for its project/tool context. The follow-up now uses
two documented defenses: the shared pyagag harness synchronizes `PWD` with cwd,
and the OpenCode adapter always supplies its native `--dir`. Regression tests
cover both boundaries. A local/OpenCode iteration launched from the parent
agautolab checkout then converged in one run: its write and bash events both
used the job's `target/`, and no file appeared in the parent checkout.
