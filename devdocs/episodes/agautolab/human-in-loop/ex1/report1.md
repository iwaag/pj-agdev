# Step 1 report — on-node summarizer endpoint

Iteration evidence is now summarized where it lives. Two routes were added to
`agautolab/agent/gateway.py`:

- `POST /jobs/<job>/summarize/<iter>` `?force=1` — returns the cached summary
  when one exists, otherwise spawns a one-shot summarizer and answers
  `202 {"status": "pending"}`.
- `GET /jobs/<job>/summarize/<iter>` — `{"status": absent|pending|done|error,
  "summary"?, "summarizer"?}`.

`GET /jobs/<job>` now also carries a per-iteration `summary` status in its
evidence timeline, so a UI knows which iterations are already paid for without
a probe request per row.

## How it works

The summarizer is `claude -p` with its own short prompt (`SUMMARY_PROMPT`), not
CHARTER and not `drive.sh`. It is given `Read,Glob,Grep` and one directory to
look at — `.local/jobs/<job>/evidence/<iter>/` named explicitly in the prompt —
and asked for 5–10 sentences of prose covering what was asked, what changed,
which gates ran and failed, and what it cost. Spawning reuses the `POST
/mission` shape: detached `Popen` with `start_new_session`, a log file, an exit
file, and the pid recorded for liveness.

Everything it writes stays under `.local/jobs/<job>/summaries/`:
`iter-NNNN.md` (the summary and the cache), `.raw.json` (claude's own JSON),
`.cost.json`, `.prompt.txt`, `.log`, `.run.json`, `.exit`. It never touches
`state.json`, evidence, `MISSION.md`, `NOTES.md` or the job's `.lock`, so it is
safe against a live iteration — constraint 2 holds by construction.

Cache and guards: the `.md` file is the cache, so one paid call per iteration
ever unless `?force=1`. One summarizer runs at a time across all jobs (`409`
otherwise) — that is the whole protection an unauthenticated money-spending
POST gets in this phase, as the plan accepted. The claude binary is resolved
exactly like `session.sh` does (`AUTOLAB_CLAUDE_BIN` → `.local/agent/claude_bin`
→ PATH); the model is `AUTOLAB_SUMMARY_MODEL`, default `claude-sonnet-5`.

## Two things the first live run changed

**The shell's exit code is not a success signal.** `claude` exits 0 on a
refusal, a max-turns stop, or an empty answer. Promotion therefore runs through
a small extractor: claude writes JSON, the extractor promotes it to `.md` only
when `is_error` is false and the text is non-empty, and it records the
summarizer's own cost/turns/duration on the way. A failed summarizer leaves no
`.md`, so it reads as `error` and can never be served as a cached summary.
Recording the cost was not in the plan, but an unauthenticated route that
spends money should say how much: the one run made after this change cost
**$0.185** for 6 turns in 15 s, summarizing an iteration that had itself cost
$0.55. (The first run predates the change, so it has no cost file — the earlier
`iter-0001.cost.json` is simply absent and reads as a `done` without a
`summarizer` block, which the GET route handles.)

**The model narrates.** The first real summary opened with "Now I have enough
to write the summary." The plan requires the summary text be shown unabridged
downstream, so that line would have reached the user. The prompt was hardened
and a `tidy_summary()` drop of a leading one-line narration paragraph was added
before the text is cached — conservative: only a standalone short first line
starting with a known throat-clearing opener, so a real sentence beginning with
"Here" survives.

## Verification

`curl -X POST` then `GET` against the live gateway on agstudio for
`snake-web-b`:

- `iter-0001` — pending → done, a correct 6-sentence summary naming `PLAN.md`,
  `proposed_gates.yaml`, the empty `gates.json`, 31 turns, ~$0.80.
- `iter-0002` — pending → done through the hardened pipeline, correctly
  reporting all four gates passing, the 8 `node --test` cases, the denied
  `python3 -m http.server` attempts, 19 turns, ~$0.55. No narration preamble;
  `summarizer.cost_usd` present.

Both summaries were checked against the evidence files and are accurate,
including the awkward parts (the permission denials, the empty gate list).

Also exercised: the one-at-a-time guard (`409` naming the running job/iter), a
cached POST returning `done` without spending, and `POST .../iter-9999` →
`404`.

`tests/test_gateway_summary.py` covers the state machine with a fake claude
binary — absent/pending/done/error, exit-0-without-output, exit-0-with-
`is_error`, a dead pid, the cross-job running guard, tidying, and cost
recording. Full suite: **61 passed**. A latent bug surfaced while writing it:
`pid_alive()` answered "alive" for pid 0 and -1 (those address process groups),
now rejected.

## Notes for later steps

- **agautolab1 is up, but its gateway is old.** `agautolab1.local` pings and
  `/healthz` returns `{"ok": true}`, yet `GET /jobs` answers
  `{"error": "missing or wrong bearer token"}` — that node runs a checkout from
  before the read side was made unauthenticated. Step 2's passthrough will see
  a 401, not a connection error, from a node that looks healthy. Whether
  `claude` exists there could not be verified: SSH from agstudio is refused
  (publickey only, no key for this account), so it needs the `autolab_node`
  ansible role or a manual check. agstudio alone proves the design, as the plan
  allowed.
- The raw `claude -p` JSON is kept per summary under `.local/` for audit. It
  never leaves the node, and `.local/` is git-ignored.
