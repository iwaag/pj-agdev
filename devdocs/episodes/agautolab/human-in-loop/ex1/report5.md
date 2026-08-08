# Step 5 report — live verification and wrap-up

Scope 1's lesson was that curl-green proves nothing and stubs never exercise
the in-between states, so this step drove a real, paid mission through the
finished view.

## The live run

`POST /mission` (run 2, `max_sessions: 2`): *"a tiny command-line tool that
converts a decimal integer into its binary representation… keep the job's
max_iterations at 2 or less"*. One mediator session, one job, one iteration,
exit 0.

What the autolab view showed while it happened, without a reload beyond the
refresh chip:

1. The headline switched to the new mission text with `driver running` as soon
   as `MISSION.md` was written.
2. `binary-cli` appeared as a sixth panel **before it had a `state.json`** —
   the 🌱 not-started case the gateway reports as `not_started`, which exists
   precisely because the mediator writes `job.yaml` first.
3. It became 🔄 `RUNNING · iter 1/2`, then ✅ `CONVERGED · iter 1/2 ·
   gates 7/7 · $0.18`.

**The overlap the plan asked for**: with `driver.running` still true, the
freshly finished `iter-0001` was summarized from the browser. It worked — the
summarizer and the mediator do not contend, because the summarizer writes only
under `summaries/` and takes no `.lock`. The summary is accurate down to the
details a human would check: seven gates all passing (including the
"no traceback on `-1`" gate), `binary.py` as a single new 26-line file, 7
turns, ~20 s, ~$0.182 "almost entirely from Sonnet 5 usage".

Nothing had to be fixed after this run. The states that usually break —
job-with-no-state, running, just-converged, summarize-while-driving — had all
been built for deliberately, and the earlier steps' honest-error work
(step 3's failed-load path, step 4's pending/409 rendering) is what made the
live run boring.

## agautolab1

Reachable at `agautolab1.local` and answering `/healthz`, but every useful
route returns `401 missing or wrong bearer token`: that node runs a checkout
from before the read side was made unauthenticated, and mDNS resolves it to
192.168.0.220 while Nautobot's desired endpoint is 192.168.0.130. Neither the
checkout nor the address can be fixed from here — SSH to it is publickey-only
and this account has no key — so it stays as the plan allowed: agstudio proves
the design, and the view renders agautolab1's failure honestly instead of
hiding it. Whether `claude` exists on that node is therefore still unverified.

## Cost of the whole episode

| what | USD |
|---|---|
| mediator session (run 2) | 0.397 |
| `binary-cli` job iteration | 0.182 |
| 5 iteration summaries (~$0.11–0.19 each) | 0.713 |
| **total spent proving this scope** | **≈ 1.29** |

The summarizer averages **$0.14 per iteration, 6 turns, ~13 s** — cheap enough
that the per-iteration cache is comfort rather than necessity, and far below
the ~$0.6 a CHARTER session would have cost through `POST /mission`.

## Documentation updated

- `agautolab/agent/README.md` — the two summarize routes, the `summaries/`
  layout, and the fact that the summarizer writes nowhere else (step 1).
- `agautolab/AGENT_GUIDE.md` — the operating agent is now told that a separate
  one-shot summarizer may read its evidence while it drives, that this is
  someone else's session, and that what it leaves in an evidence dir is what a
  human will later be told about.
- `agautolab/README.md` — monitoring section points at the agdevworld view and
  the summarize boundary.
- `agdevworld/README_DEV.md` — the autolab view and the passthrough, including
  the `AUTOLAB_NODES` convention and the `/evidence/` refusal.
