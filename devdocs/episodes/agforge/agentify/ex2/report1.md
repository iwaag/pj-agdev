# ex2 step 1 report — charter + runner, standalone

Status: **done**. `service/agent_run.py` composes a charter from
`service/charter.md`, runs one headless agent with a scoped tool
allowlist, and leniently parses `RESULT_URL:` / `RESULT_FAILED:` out of
the agent's final output. All three step-1 acceptance cases passed
against live SwarmUI, on the default **ollama** backend.

## What was built

- `service/charter.md` — the charter template (the ENT-tunable artifact):
  desire verbatim + request id, what agforge is, how to use
  `scripts/generate.sh` (sizes 64–2048, multiples of 64, model is
  configuration-owned, generator tends to emit JPEG and fixing format is
  the agent's job), data-shaping rules (creative-only prompt, re-upload
  via `generate.py`'s `upload_and_presign`, never `nctl-outbox`), the
  finish contract (RESULT_URL / problem.md at the path rule +
  RESULT_FAILED), and the wall-clock budget. Placeholders are
  `{{DESIRE}}`, `{{REQUEST_ID}}`, `{{PROBLEM_PATH}}`, `{{BUDGET_SECONDS}}`.
- `service/agent_run.py` — backend selection via `AGFORGE_AGENT_BACKEND`
  (process env → `.local/.env`, default `ollama`):
  - `ollama`: opencode headless (`opencode run`, v1.18.10) over the ex1
    model `qwen3.6:35b-a3b-coding-nvfp4`. Verified opencode reads the
    charter on stdin. Binary/model are configuration
    (`AGFORGE_OPENCODE_CMD`, `AGFORGE_OPENCODE_MODEL` in `.local/.env`).
  - `claude`: scoped `claude -p --output-format json` pinned to
    `claude-sonnet-5` with an explicit `--allowedTools` list
    (generate.sh, `uv run`, sips, file/ls/mkdir/cat, Read, Write) and
    cost capture copied from agautolab's `claude_code` adapter pattern.
    No `--dangerously-skip-permissions` anywhere (agstudio policy).
  - Test hook `AGFORGE_AGENT_CMD` replaces the whole invocation (charter
    on stdin, agent-style output on stdout) — verified with stubs for
    URL / FAILED / no-marker outputs.
- `opencode.json` (committed, agforge root) — deny-by-default bash
  permission allowlist for the opencode harness: `scripts/generate.sh`,
  `uv run`, `sips`, `file`, `ls`, `pwd`, `cat`, `mkdir`; `webfetch`
  denied; edits allowed (problem.md).
- The pre-ex2 uncommitted state (format field + deterministic convert +
  templated problem reports) was committed first as a baseline
  (`e5b665b`) so this episode diffs cleanly.

## Live acceptance runs (ollama backend, agstudio → SwarmUI on agpc)

| case | outcome | wall clock |
|---|---|---|
| "a cozy watercolor cottage in a forest" (1st try) | `done`, but the URL 403'd — see finding below | 40 s |
| same, after charter fix | `done`, URL downloads HTTP 200 | 42 s |
| "a pixel art robot mascot, 320x320" | `done`, downloaded file measured 320×320 JPEG | 41 s |
| "a short lofi hip-hop music track" | `failed` + agent-authored problem.md + `RESULT_FAILED` | 20 s |

The music problem report (`.local/problems/20260807-163446Z-44cf85fd/`)
is in the agent's own words: it quotes the desire verbatim, names what
was attempted, and explains that agforge has no audio capability — the
load-bearing content the old code-templated report could not carry.

## Finding: presigned-URL transcription is fragile (kept as know-how)

On the first plain-desire run the agent generated and self-verified
correctly, but the `RESULT_URL:` line contained a **corrupted signature**
(30-char, non-multiple-of-4 base64 — characters dropped while the model
retyped the long high-entropy URL). The object existed and a fresh
presign of the same key downloaded fine, so the failure is purely
final-message transcription by the 35b model. Charter fix applied:
"reproduce the URL character-for-character, never retype or shorten it."
The next run's URL was byte-exact. This is a hardening candidate for the
step-4 list (e.g. runner-side URL verification or letting the agent
emit the URL via a file), not silently patched code.

## Notes

- opencode's default headless output contains only the agent's final
  message (plus minor ANSI noise, stripped by the runner) — good for
  lenient marker parsing, but tool-level transcripts are not captured.
  Observation therefore reads the final message + artifacts, which was
  sufficient for all three cases.
- Manual entry point, as planned: `uv run service/agent_run.py "<desire>"`.
