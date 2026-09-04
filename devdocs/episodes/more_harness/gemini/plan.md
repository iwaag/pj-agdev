# Plan — `gemini_cli` as a fourth harness

Ask (2026-09-04): add Gemini CLI as a selectable profile for autolab and
front. This Mac has `gemini` 0.58.0 on PATH with its key configured.
AI-drafted from the Omni Agent's investigation. The environment is a private
experiment: no backward compatibility is owed, and the implementer decides
the details — everything below that is not marked *verified* is a hint.

## The shape of the work

A profile is `(harness, model)`, and the harness vocabulary is a closed set
in pyagag (`CANONICAL_HARNESSES` in `agag/agent_config.py`; argv and output
extraction branch on the name in `agag/harness.py`). So: one pyagag commit
adds `gemini_cli`, then pj-agdev moves its pin and adds a profile. Same shape
as when `agcode` was added and `opencode` removed — pin and profiles move
together, no shim.

A wrapper script behind the `fake` harness would also "work" but records
`harness = "fake"` with no capabilities; not worth it.

## Verified on agstudio (2026-09-04)

- **Headless invocation.** `echo "<prompt>" | gemini -p "" -o json
  --skip-trust -m gemini-2.5-flash` answers. `-p` is what leaves interactive
  mode; its argument is *appended* to stdin, so `-p ""` passes the stdin
  prompt through unchanged — the same stdin handoff run_harness already does.
- **`--skip-trust` is needed.** Without it an untrusted cwd exits 55 and the
  approval mode is forced back to `default`. (`GEMINI_CLI_TRUST_WORKSPACE=true`
  in the env does the same.)
- **`-o json` output:** one document `{"session_id", "response", "stats"}`.
  `response` is the answer. `stats.models.<name>.tokens` has `input`,
  `prompt`, `candidates`, `total`, `cached`, `thoughts`, `tool`;
  `stats.models.<name>.api.totalRequests` is a turn count of sorts;
  `stats.tools` has call counts. **No cost field.**
- **`-o stream-json` output:** JSONL. `{"type":"init","model"}`,
  `{"type":"message","role":"user","content"}`, …, and last
  `{"type":"result","status":"success"|"error","error"?:{"type","message"},
  "stats":{"total_tokens","input_tokens","output_tokens",…}}`. The result
  line is last, so pyagag's `_result_line` already finds it. The assistant
  text spelling in stream mode is **not** verified (every stream run hit 503).
- **A failed run exits 0.** The API-overload run printed
  `"status":"error"` and exited 0. Failure has to be read from the document.
- **Latency.** The default model returned 503 all session. `gemini-2.5-flash`
  answered after five automatic retries, ~90 s wall clock, and `stats` named
  it `gemini-3.5-flash`. Expect silent minutes before the first token, and do
  not key `stats.models` by the requested name — take the entry that is there.
- **Key and PATH.** The key is not in the environment or shell rc files;
  the CLI resolves it itself (`~/.gemini/settings.json`:
  `selectedType: gemini-api-key`). Both listener plists put
  `/opt/homebrew/bin` on PATH. Whether the key resolves under launchd is the
  one unproven thing; if not, `GEMINI_API_KEY` in the run environment is the
  fix (an overlay secret like the anthropic ones, or the plist).
- **Permissions.** `--approval-mode {default,auto_edit,yolo,plan}`.
  `--allowed-tools` is deprecated (policy engine replaces it) and claude
  grant spellings like `Bash(git:*)` do not translate anyway.
  `--include-directories` ≈ `--add-dir`. `-m` takes the native model name.

## Suggested design

- Harness `gemini_cli`, provider `google`, model IDs `google/<native>`;
  joins `NATIVE_MODEL_HARNESSES` and gets `{agentic_tools, workspace_fs}`.
  Default command `gemini`; the generic `local.harness.<name>` overlay
  already handles `command`/`command_glob`.
- argv: `gemini -p "" -o json|stream-json -m <native> --skip-trust
  --approval-mode <mode> [--include-directories d]… <extra_args>`.
  Headless `default` mode has nobody to answer the prompt, so pick the mode
  from what the caller already says: `skip_permissions` → `yolo`; read-only
  roles → `plan` (autolab can pass it through `extra_args`, as it passes
  `--tools read-only` to agcode); otherwise `yolo` is the sensible default.
  The `allowed_tools` grant in `agents.toml` stays as documentation of the
  role and is simply not passed.
- Extractor: `response` → output; `status`/`error` → `is_error`/`subtype`
  so run_harness's existing `is_error` branch names the failure; tokens →
  `usage`; leave `cost_usd` absent. The mission-cost reader will show
  tokens only for gemini runs — acceptable, note it in the README.
- Streaming: emit `-o stream-json` when asked and let the events through
  as they are; the autolab progress consumer already tolerates agcode's
  near-claude event shapes. Get one successful stream run first to see the
  assistant-text spelling.

## Steps

1. **pyagag** — `agent_config.py` (vocabulary, provider compatibility,
   default command), `harness.py` (argv branch, extractor, stream guard),
   tests in the style of the existing `fake`-executable fixtures. Worth a
   test: error document with exit 0 → `outcome: failed`.
   `docs/agent-config-v1.md` harness table gets a row; README gets a word.
   Push; note the hash.
2. **agents.toml** in agautolab and agfront:
   ```toml
   [models."google/gemini-2.5-flash"]
   [profiles.gemini]
   harness = "gemini_cli"
   model = "google/gemini-2.5-flash"
   ```
   Roles can stay on `sonnet`; autolab selects per project via
   `.local/projects/<p>/agents.toml`, front via `agfront/.local/agents.toml`.
   `GET /projects` lists profiles from the file, so `gemini` shows up with
   no gateway change. Declare the stronger model too once it stops 503-ing.
3. **agautolab `role_run.py`** — extend the bypass to `gemini_cli`, add
   `--approval-mode plan` for `READONLY_ROLES`; one test each. agfront's
   listener needs nothing if `yolo` is the default (its `front` role needs
   `agentchat` from Bash).
4. **Pin** — `uv lock --upgrade-package pyagag` in agautolab, agfront,
   agforge; `uv run pytest` in each; kickstart the two listeners
   (`launchctl kickstart -k gui/$(id -u)/com.agdev.<agent>-zulip`).
5. **Prove it** — front on `gemini` answering one `#front` message; one
   autolab role (`summarizer` is cheapest) on `gemini` through the normal
   acceptance route. Read the `run-NNNN.json`: `harness: gemini_cli`,
   `usage` present, `outcome: done`; and one deliberately bad model name →
   `outcome: failed`. The report says whether the CLI's retries fit inside
   the role timeouts and whether the answers held up.

## Out of scope

- Grant → Gemini policy-engine translation.
- Cost estimation for gemini runs.
- Opting agforge / arxivsage in; they inherit the harness with the pin.
