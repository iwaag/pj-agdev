# Plan — `gemini_cli` as a fourth harness

Reconciles the developer's ask of 2026-09-04: *can Gemini CLI be added as a
profile for autolab and front?* This Mac has `gemini` 0.58.0 on PATH with its
API key already configured. AI-drafted from the Omni Agent's investigation;
the decisions below were taken in that conversation.

## Why this is not a config-only change

A profile is a `(harness, model)` pair, and the harness vocabulary is closed
inside pyagag: `CANONICAL_HARNESSES = {"claude_code", "agcode", "fake"}` in
`agag/agent_config.py`. Any other spelling is `E_UNKNOWN_HARNESS` at load
time, and `build_argv` / the output extractors in `agag/harness.py` branch on
the harness name. So the work is one pyagag commit that teaches the package a
fourth harness, followed by a pin move and two `agents.toml` edits in
pj-agdev. This is the same shape as the `agcode` addition and the `opencode`
removal: the pin and the profiles move together, and there is no shim.

The `fake`-harness-plus-wrapper-script route was considered and rejected: the
run record would say `harness = "fake"`, the intrinsic capabilities would be
empty, and the wrapper would be a second place where argv is spelled.

## What was verified on agstudio (2026-09-04)

- Headless mode works with the prompt on stdin:
  `echo "<prompt>" | gemini -p "" -o json --skip-trust -m gemini-2.5-flash`.
  `-p` is required to leave interactive mode; its argument is *appended* to
  stdin, so `-p ""` keeps the prompt exactly as run_harness wrote it.
- `--skip-trust` is mandatory. Without it, a workspace the developer never
  trusted interactively exits 55 with "not running in a trusted directory"
  and forces the approval mode back to `default`.
- `-o json` prints one document: `{"session_id", "response", "stats"}`.
  `response` is the final answer; `stats.models.<model>.tokens` carries
  `input`, `prompt`, `candidates`, `total`, `cached`, `thoughts`, `tool`;
  `stats.tools` carries call counts. **There is no cost field.**
- `-o stream-json` prints JSONL: `{"type":"init", "model"}`,
  `{"type":"message","role":"user"}`, … and last
  `{"type":"result","status":…,"error"?:{…},"stats":{"total_tokens",
  "input_tokens","output_tokens",…}}`. The result line is the last line, as
  with the other two harnesses.
- **A failed run exits 0.** The API-overload run ended with
  `"status":"error"` on the result line and exit code 0. The exit code is not
  a failure signal for this harness; the result document is.
- The default model returned HTTP 503 for the whole session; `gemini-2.5-flash`
  (reported by the CLI as `gemini-3.5-flash` in `stats`) answered after five
  retries, about 90 s. The CLI retries with backoff on its own, so a run can
  sit silently for minutes before its first token.
- The key is not in the environment or any shell rc file; the CLI resolves
  it itself (`~/.gemini/settings.json` says `selectedType: gemini-api-key`).
  Both listener plists carry `/opt/homebrew/bin` on PATH, so `gemini`
  resolves under launchd. Whether the key resolves under launchd is the one
  thing not yet proven; step 7 proves it.
- `--allowed-tools` is deprecated in favour of the policy engine, and the
  claude_code grant spellings (`Bash(git:*)`) do not translate anyway.
  `--approval-mode` has `default`, `auto_edit`, `yolo`, `plan`.
  `--include-directories` is the `--add-dir` equivalent.

## Decisions

1. **Harness name `gemini_cli`, provider `google`.** Model IDs are
   `google/<native-name>`; the harness takes the native name on `-m`, so it
   joins `NATIVE_MODEL_HARNESSES`. Compatibility check mirrors claude_code's:
   `gemini_cli` serves `google` only.
2. **Approval mode is the whole permission story.** Non-interactive `default`
   mode has nobody to answer the prompt, so the harness never emits it:
   - `skip_permissions=True` → `--approval-mode yolo`;
   - otherwise, if `extra_args` already carries `--approval-mode`, it wins
     (the consumer's read-only roles pass `plan`, as they pass
     `--tools read-only` to agcode);
   - otherwise `yolo`. This is the same bypass claude_code already gets from
     `role_run.py`; the `allowed_tools` grant stays in `agents.toml` as the
     statement of what a role reaches for and is *not* passed to gemini.
   `--skip-trust` is always emitted.
3. **Failure comes from the result document.** `_extract_gemini` maps
   `status == "error"` (stream) or a missing/empty `response` with an
   `error` key (json) onto `is_error=True` and `subtype` = the error type, so
   run_harness's existing `elif meta.get("is_error")` branch names the
   failure. Exit code 0 is not trusted on its own.
4. **Usage is recorded, cost is not.** `meta["usage"]` gets
   `{"input_tokens", "output_tokens", "cached_tokens", "thoughts_tokens"}`
   read from `stats`; `cost_usd` is left absent. The mission-cost reader
   (`.local/agent/<role>/run-NNNN.json`) will show tokens only for gemini
   runs. `num_turns` comes from `stats.models.<m>.api.totalRequests`.
5. **Streaming is in scope but gated.** `build_argv(stream=True)` emits
   `-o stream-json`; the `stream = … and agent.harness in (…)` guard in
   run_harness admits `gemini_cli`. Events are forwarded verbatim — the
   consumer's progress display already tolerates unknown `type`s because
   agcode's events only *mostly* match claude_code's. No translation layer.
6. **No secret plumbing.** `_resolve_secret_environment` stays
   anthropic-only; the CLI owns its key. If a run under launchd cannot find
   the key (step 7), the fix is a `google_api_key_env` overlay secret mapped
   to `GEMINI_API_KEY`, added then, not speculatively now.
7. **Intrinsic capabilities** `{"agentic_tools", "workspace_fs"}`, same as the
   other two agentic harnesses.

## Steps

### Step 1 — pyagag `agent_config.py`

- Add `"gemini_cli"` to `CANONICAL_HARNESSES`, `INTRINSIC_CAPABILITIES`,
  `NATIVE_MODEL_HARNESSES`.
- `_validate_committed`: `gemini_cli` with a non-`google` provider is
  `E_INCOMPATIBLE`, spelled like the claude_code check.
- `_resolve_command`: default command `"gemini"`; `local.harness.gemini_cli`
  overlay (`command` / `command_glob`) already works through the generic path.
- Tests in `test_agent_config.py`: resolves to `gemini` on PATH, native model
  strips the provider, `google/x` under `claude_code` and `anthropic/x` under
  `gemini_cli` are both `E_INCOMPATIBLE`, `E_UNAVAILABLE` when the executable
  is missing.

### Step 2 — pyagag `harness.py`

- `build_argv` branch:
  `[command, "-p", "", "-o", "json"|"stream-json", "-m", native_model,
   "--skip-trust", "--approval-mode", <per decision 2>, "--include-directories", d…, *extra_args]`.
  A `--model`/`-m` in `extra_args` is still rejected; a `--approval-mode`
  in `extra_args` suppresses the harness's own.
- `_extract_gemini(raw)`: parse the single document, else `_result_line`.
  Output is `response` (json) — the stream result line has no `response`, so
  in stream mode the answer is the concatenated `content` of
  `{"type":"message","role":"assistant"}` lines; confirm the exact spelling
  from a successful stream run before writing the test fixture (step 2's first
  action is one more `-o stream-json` run that succeeds).
  Meta: `is_error`, `subtype`, `usage`, `num_turns`, and `duration_ms` from
  the wall clock as today.
- Dispatch in run_harness (`elif agent.harness == "gemini_cli"`), and the
  streaming guard.
- Tests in `test_harness.py`, using the `fake`-style pattern already there
  (a stub executable echoes a captured document): argv shape incl. approval
  mode precedence, json extraction, stream extraction, **error-with-exit-0 is
  `outcome: failed`**, model smuggling rejected.

### Step 3 — pyagag docs and README

- `docs/agent-config-v1.md`: add the row
  `gemini_cli | gemini -p "" -o json -m <native-name> --skip-trust --approval-mode …| google only | agentic_tools, workspace_fs`
  and a paragraph on the two things that differ from claude_code: exit code
  is not a failure signal, and permissions are an approval mode, not a grant.
  Extend the vocabulary-history paragraph with this third change.
- `README.md`: the harness list sentence.
- Commit and push pyagag; note the commit hash for the pin.

### Step 4 — pj-agdev `agents.toml` (agautolab and agfront)

Both files gain:

```toml
[models."google/gemini-2.5-flash"]

[profiles.gemini]
harness = "gemini_cli"
model = "google/gemini-2.5-flash"
```

Roles stay on `sonnet` in the committed files. Selection is:

- autolab: per project, `.local/projects/<p>/agents.toml` `[roles.<role>]
  profile = "gemini"` — the gateway's `GET /projects` already lists
  `profiles`, so `gemini` shows up as selectable without code.
- front: `agfront/.local/agents.toml` `[roles.front] profile = "gemini"` for
  the trial; flip the committed default only after step 8's verdict.

`gemini-2.5-flash` is the model that answered today; the stronger default
model can be declared alongside once it stops returning 503, and the choice
is one TOML line per project either way.

### Step 5 — `agautolab/src/agautolab/role_run.py`

- `gemini_args(role)` next to `agcode_args`: `["--approval-mode", "plan"]`
  for `READONLY_ROLES`, else `[]`.
- `skip_permissions=agent.harness in ("claude_code", "gemini_cli")`, and
  `extra_args` chosen per harness. Docstring: the bypass paragraph now names
  both harnesses.
- `tests/test_role_run.py`: the `gemini` profile passes yolo for `coding`
  and plan for `summarizer`.
- agfront's listener calls the skeleton `run_role` without
  `skip_permissions`; under decision 2 it still gets `yolo`, which is what
  its `Bash(agentchat:*)` grant needs. No agfront code change.

### Step 6 — pin and lock

`uv lock --upgrade-package pyagag` in `agautolab`, `agfront`, and `agforge`
(agforge shares the dependency and must not be left on a pyagag that rejects
a profile it never uses — it loads only its own `agents.toml`, so it is safe
either way, but a mixed pin is the kind of drift the contract doc warns
about). `uv run pytest` in each. Update `README.md` in agautolab (the
"three profiles" sentence).

### Step 7 — launchd proof

`launchctl kickstart -k gui/$(id -u)/com.agdev.agfront-zulip` and the same
for `com.agdev.agautolab-zulip`. Then, with `agfront/.local/agents.toml`
selecting `gemini`, one message in `#front`. The run record must show
`harness: gemini_cli`, `provider: google`, `usage`, and `outcome: done`. If
it shows `outcome: failed` with an auth error, apply decision 6 and repeat.
Revert the front overlay after the proof unless the answer quality says
otherwise.

### Step 8 — one autolab mission on `gemini`

Select `gemini` for `coding` (or `summarizer`, the cheapest) in one project's
overlay, drive one task through the usual acceptance route, read
`run-NNNN.json`. Report: did the run finish inside `WORK_TIMEOUT_SECONDS`
given the CLI's silent retries, what the token usage was, and whether the
answer stood up. This is the report the episode exists for.

## Acceptance

- `uv run pytest` green in pyagag, agautolab, agfront, agforge.
- `GET /projects` lists `gemini` among `profiles` with no `error` row.
- A front run and one autolab role run on `gemini` produce
  `ag.agent-run.v1` records with `harness: gemini_cli`, and a deliberately
  failing run (bad model name) produces `outcome: failed` despite exit 0.
- Every commit pushed (localrule).

## Risks and open questions

- **Retry latency vs. timeouts.** The CLI's own backoff can eat a large share
  of a 1200 s planning budget before the first token. If step 8 shows this,
  the answer is a `--max-retries`-style option if the CLI grows one, or a
  smaller `timeout` margin; not in this plan.
- **Model naming drift.** `-m gemini-2.5-flash` was reported as
  `gemini-3.5-flash`. The record keeps the canonical ID from the profile; the
  extractor must not key `stats.models` by the requested name — take the
  single entry present.
- **Stream answer text.** The stream-json answer spelling is unverified
  (every stream run today hit 503). Step 2 starts by getting one.
- **Trust flag.** `--skip-trust` trusts the run's cwd for that session. The
  roles are workspace-bound already, which is the same argument that
  justified claude_code's bypass.

## Out of scope

- Translating `allowed_tools` grants into Gemini policy-engine files.
- A cost estimate for gemini runs (no cost in the CLI's output; would need a
  price table).
- Gemini for agforge or arxivsage; they inherit the harness with the pin and
  can opt in per profile later.
