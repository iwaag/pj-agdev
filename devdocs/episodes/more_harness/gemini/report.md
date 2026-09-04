# Report — `gemini_cli` harness (2026-09-04)

Plan: `plan.md`. Steps 1–4 are done and pushed; step 5 (the proof under
launchd) stopped on one missing input, described at the end.

## What landed

- **pyagag `051ec2b`** — `gemini_cli` harness: vocabulary, `google`-only
  compatibility, default command `gemini`, argv
  `gemini -p "" -o json|stream-json -m <native> --skip-trust
  --approval-mode <yolo|caller's>`, extractor for both output modes, stream
  guard, docs table row and paragraph, 6 tests.
- **pyagag `e72a9f9`** — `local.secrets.google_api_key_file` / `_env` hand
  the key to the run as `GEMINI_API_KEY` (same shape as the anthropic pair).
- **agautolab `2b5c4be`, agfront `06fffba`, agforge `d20c58b`,
  pj-agdev `44d80d9`** — `[profiles.gemini]` on `google/gemini-2.5-flash`
  in both `agents.toml`; autolab's `role_run` gives gemini the bypass and
  its read-only roles `--approval-mode plan`; pins at `e72a9f9`; all suites
  green (pyagag 429, agautolab 214, agfront 21, agforge 211).
- Listeners and gateway kickstarted on the new pin.

## What was proven

- **Extractor against real captures.** `-o json` and `-o stream-json` runs
  from this Mac both extract to `pong` with `usage`; the stream's assistant
  text arrives as `{"type":"message","role":"assistant","content","delta":true}`
  lines and its result line carries flat `input_tokens`/`output_tokens`.
- **autolab `summarizer` on `gemini`, run directly** (not under launchd):
  read a file in `plan` mode, answered correctly, exit 0, record
  `harness: gemini_cli, provider: google, num_turns: 2, usage: {…},
  outcome: done`, 83 s wall clock.
- **Failure reporting.** The first front run failed and was reported as
  `failed`, with the CLI's error document quoted into the topic — the
  failure path works end to end.

## What stopped step 5

Front on `gemini` (`#front > front-gemini-trial`) exited 41:
*"When using Gemini API, you must specify the GEMINI_API_KEY environment
variable."* The key is not in any shell file or the environment — an
`env -i HOME PATH gemini …` from an interactive shell still works — so the
CLI keeps it in its encrypted store (`~/.gemini/gemini-credentials.json` is
not plain JSON), which a launchd-started process cannot open. Hence
`e72a9f9`: both `.local/agents.local.toml` overlays now point
`google_api_key_file` at `pj-agdev/.local/gemini_api_key`, which does not
exist yet — the value is the developer's to write. Until it exists, selecting
`gemini` fails fast at resolution (`E_UNAVAILABLE`), and `sonnet` roles are
untouched; the front overlay's `[roles.front] profile = "gemini"` is left
commented out for the same reason.

## Remaining

1. Developer writes the bare key, one line, to `pj-agdev/.local/gemini_api_key`.
2. Uncomment `[roles.front] profile = "gemini"` in `agfront/.local/agents.local.toml`
   (config is read per run; no restart), post once into a `front-*` topic,
   read the record under `agfront/.local/topics/front/<topic>/<N>/front/`.
3. One autolab role on `gemini` through the acceptance route, to see whether
   the CLI's silent 503 retries fit the role timeouts. Today's runs: 20–90 s
   on flash after up to five retries; the default model never answered.

## Notes for whoever runs on gemini

- The record has tokens, no cost. `-m gemini-2.5-flash` is reported by the
  CLI as `gemini-3.5-flash`; the record keeps the canonical profile ID.
- A kickstart of `agfront-zulip` re-served one pending mention on restart
  (one paid sonnet run); expect that when restarting listeners.
