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

## agautolab1 — updated and verified

Initially this node answered `/healthz` but returned `401 missing or wrong
bearer token` on every useful route: it ran a checkout from before the read
side was made unauthenticated. The fix is not SSH (publickey-only, no key for
this account) but the existing deploy path, which was pointed out after the
first pass:

```sh
# push to the node's deploy source (the agstudio gitea), then:
cd pj-clusterintent/ansible_agdev
ansible-playbook -i inventories/agautolab.yml playbooks/agent/setup_autolab_node.yml
```

`autodev/agautolab` on the gitea was at `46f2d9f` — behind even GitHub — so
the node had been pinned there by its deploy source, not by anything on the
node. Fast-forwarding gitea to `8d36d57` and running the playbook gave
`ok=13 changed=2 failed=0` with the gateway restart handler firing.

Verified afterwards:

- `GET /jobs` on agautolab1 is now unauthenticated and returns its four jobs
  (`gallery-direction` not started, `gallery-web`, `janken-game`, `quiz-game`).
- **`claude` is present on that node** (`~/.local/bin/claude` → 2.1.224),
  answering the plan's open question.
- The summarizer runs there for real: `quiz-game/iter-0002` summarized through
  the assistant passthrough in ~18 s for **$0.165**, correctly reporting the
  four files implemented, all four gates passing, the ~12 Bash permission
  denials the agent worked around, 31 turns and ~$0.63.
- In the browser, picking `agautolab1` renders its jobs including the 🌱
  NOT STARTED case, with its own mediator headline and cumulative cost
  ($8.79).

So the multi-node design is proven on two nodes, not one. The address drift
remains: mDNS resolves `agautolab1.local` to 192.168.0.220 while Nautobot's
desired endpoint says 192.168.0.130 — untouched here, and still the strongest
argument for follow-up 1.

## Cost of the whole episode

| what | USD |
|---|---|
| mediator session (run 2) | 0.397 |
| `binary-cli` job iteration | 0.182 |
| 5 iteration summaries on agstudio (~$0.11–0.19 each) | 0.713 |
| 1 iteration summary on agautolab1 | 0.165 |
| **total spent proving this scope** | **≈ 1.46** |

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
