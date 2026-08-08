# Episode report — human-in-loop ex1: autolab view in agdevworld

agdevworld has a third view. A user picks an autolab node, sees its jobs as
panels, clicks one to get its iteration timeline, and asks for an iteration
summary — which is written **on the node** by a one-shot Claude agent that
reads the evidence there. The prime agent presents that summary and answers
questions about it. Raw evidence never crosses into agdevworld.

All five steps are done and verified against real data, including one paid
mission driven end to end through the finished UI
([report1](report1.md) … [report5](report5.md)).

## What shipped

| step | where | what |
|---|---|---|
| 1 | `agautolab/agent/gateway.py` | `POST`/`GET /jobs/<job>/summarize/<iter>`, a detached one-shot `claude -p` over one evidence dir, cached as `summaries/<iter>.md` |
| 2 | `agdevworld/assistant/server.mjs` | `/api/autolab/nodes` + `/api/autolab/<node>/<rest>` passthrough; `/evidence/` refused with 403 |
| 3 | `agdevworld/src/{autolabState,views,scenes}` | the autolab view: node picker chips, job panels, mediator headline; three-view cycle; `switch_view` by chat |
| 4 | `agdevworld/src/detailPopup.ts` | iteration timeline, on-demand summaries with pending/error/409 states, "ask the agent about this iteration" |
| 5 | live | one real mission watched from job-appears to converged, summarized mid-run; docs |

The plan's four constraints all hold: no raw evidence reaches agdevworld (and
the refusal lives in exactly one place, the passthrough); the summarizer writes
only under `summaries/`; nothing under `.local/` and no real hostname is
committed (`AUTOLAB_NODES` defaults to the local node, real values in an
ignored `.env`); the scope-1 monitor page still works.

Total spend proving the scope: **≈ $1.29** — $0.40 mediator, $0.18 job,
$0.71 for five summaries.

## What the work taught

**The exit code is not the answer.** `claude -p` exits 0 on refusals and
max-turns stops, so the summarizer promotes its output only when the JSON says
`is_error: false` and the text is non-empty. The same instinct — the cheap
signal is not the real one — is why the gateway's `.md` file, not the process
exit, is the cache and the success flag.

**In-between states are the product.** A job with no `state.json` yet, a node
that answers `/healthz` but 401s everything else, a summarizer that is still
thinking, a second summarize request refused by the one-at-a-time guard: each
of those is rendered as itself. The live mission run needed no fixes
afterwards, which is the return on having built those paths deliberately
rather than discovering them in front of a user.

**Summarize at the source, present verbatim.** The boundary that started as a
privacy constraint turned out to be the feature: a capable agent with file
access writes prose once, cheaply, next to the data; the small local model
never sees JSON it would drown in, and the summary is shown and forwarded
unabridged so nothing re-summarizes it away.

## Follow-ups (recommended, out of scope here)

1. **Register autolab as a nintent service.** Today the node picker reads a
   config list because autolab is not modeled in the cluster's desired state
   and `agautolab1` has no placements. Registering it would make the picker
   derive from the cluster snapshot — the vision-consistent shape — and, more
   urgently, would give the node something that reconciles it: it currently
   sits at 192.168.0.220 while its desired endpoint says 192.168.0.130, and
   runs a checkout old enough to still demand a token on read routes. Nothing
   in the system notices either fact.
2. **A key or an ansible pass for `agautolab1`.** Its gateway cannot be
   updated from here (publickey-only SSH, no key for this account), so
   whether `claude` exists there is still unverified. The `autolab_node` role
   in clusterintent's `ansible_agdev` owns that machine.
3. **Auth, system-wide.** An unauthenticated POST that spends money is
   accepted for this experimental phase and bounded by the one-at-a-time guard
   and the per-iteration cache. It should not survive the phase.
4. **Narrow viewports.** At 390×844 the chat panel covers the canvas for every
   view; pre-existing, untouched here.

## devstyle report

- **Style chosen**: five-course — the episode arrived as a written plan with
  five steps, each with its own done-criterion and report, and the work
  spanned three components (gateway, assistant, frontend) with a boundary
  constraint that had to hold across all of them.
- **Why**: the expensive mistakes here were architectural (where evidence is
  allowed to travel, what counts as a successful paid run), not typing —
  exactly the case where per-step verification against real data beats speed.
- **Was it right in hindsight**: yes, and the step boundaries paid for
  themselves twice. Step 1's live run exposed the exit-code and narration
  problems while the blast radius was one file; step 3's failed-load work is
  what made step 5's live mission uneventful. The one thing worth doing
  differently: verify through the deployment shape earlier — the passthrough
  looked broken against `agautolab1` for a while purely because a native
  `node` process on macOS is denied LAN access while the container is not.
