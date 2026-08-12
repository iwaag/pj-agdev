# Report 9 — deploy the stub

Beyond the plan's eight steps: the developer pushed the stub and asked for it
to be rolled out, **from GitHub rather than from the agstudio Gitea**.

## The deployment source changed

`agautolab`'s `origin` is `https://github.com/iwaag/agautolab.git`, and it
carries the stub at `05c1289`. The Gitea mirror
(`http://agstudio.local:3000/autodev/agautolab.git`) is stale at `f777634` —
two commits before this episode even began — which is the same staleness that
cost a day in the 2026-08-08 note in `.local/devenv.md`.

The `autolab_node` role still defaults `autolab_node_repo_url` to that Gitea
URL. I did **not** change the role: this episode declared `pj-clusterintent`
out of scope, and rewriting another project's role default is a decision about
every future deployment, not part of rolling out one stub. The playbook ran
with a one-run override instead:

```sh
cd pj-clusterintent/ansible_agdev
uv run --project ../nctl nctl render production --out inventories/generated
ansible-playbook -i inventories/generated/production.yml \
  playbooks/agent/setup_autolab_node.yml --limit agautolab1 \
  -e autolab_node_repo_url=https://github.com/iwaag/agautolab.git
```

**This leaves a footgun.** The next person who runs that playbook without
`-e` deploys the stale Gitea `f777634` — the full old implementation — over
the stub, and the node silently becomes able to run missions and spend money
again. Either the role default moves to GitHub or the Gitea mirror gets the
push; doing neither means the node's contents depend on how the last command
was typed.

## Checked before deploying

- GitHub `origin/main` is at `05c1289`, the stub.
- `https://github.com/iwaag/agautolab.git` answers an unauthenticated
  `info/refs` with 200, so the node needs no credentials for the new source.
- `agautolab1`'s `/status` showed `driver.running: false` — no live mission
  was killed by the redeploy. Its last mission (run 12, a Whack-a-Mole game)
  had already finished.
- The role's tasks reference none of the deleted files: no `drive.sh`,
  `session.sh`, `monitor/`, `autolab@.service` or CLI invocation. Only
  `autolab-gateway.service.j2`, which starts `agent/gateway.py`, and that
  survives.

## agstudio (this Mac)

The hand-started gateway on `:8791` (pids 38670/38673) was killed and
restarted on the new code from the working tree. Verified:

- `GET /status` now carries `"stub": true`.
- The assistant passthrough works end to end:
  `GET localhost:8091/api/autolab/agstudio/status` → the stub document,
  `/jobs` → `{"jobs": []}`, `/api/autolab/nodes` → both nodes reachable, 200.

That is the check report 8 could not run. The response shapes held through the
proxy: the assistant reads an empty node, not a broken one.

## agautolab1

`PLAY RECAP: ok=24 changed=3 failed=0`. The three changes were the checkout
moving to the GitHub source, the regenerated overlay, and the gateway restart
handler; the health probe passed.

Verified against the node afterwards:

- `GET /status` → `"stub": true`.
- `GET /jobs` → `{"jobs": []}`.
- `GET /monitor/` → 404.
- `POST /window` → 200, canned reply, and a record resolving `front` to
  `sonnet / claude_code / anthropic / anthropic/claude-sonnet-5` — the node's
  own overlay, different from this Mac's `local / opencode / ollama`, and
  still read for real. `cost_usd: 0.0`.
- Through the assistant: `/api/autolab/nodes` reports both nodes reachable and
  200, and `/api/autolab/agautolab1/jobs` returns the stub document.

Both nodes are stubs now. Nothing in the cluster can start a coding-agent
iteration.

## Two things left open

1. **The role default still points at the stale Gitea mirror.** Described
   above; a plain `ansible-playbook … setup_autolab_node.yml` reinstalls the
   deleted implementation on the node.
2. **`agautolab1` keeps its own `.local/`.** Its `GET /projects` still lists
   node-side auto-development projects (`three-choice-quiz` and others), and
   its job directories are presumably still there too. Step 7 emptied
   `.local/` on this Mac only. Deleting state on a remote node was never in
   the plan and is irreversible, so it was not done here — but if the
   braindump's "delete the auto-development projects" is meant cluster-wide,
   the node is where the rest of them are.
