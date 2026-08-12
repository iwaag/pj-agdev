# Report 8 — verify, and where the stub is not yet

Plan step 8. The code work is done; the deployment question is open.

## The finished tree

21 tracked files, down from 55. 985 lines of Python/Markdown/TOML/shell, down
from about 5,800.

```
README.md                          agents.toml
agent/GUIDE.md                     opencode.json
agent/gateway.py                   pyproject.toml   uv.lock
agent/opencode-{front,coding,mediator,readonly}.json
agent/zulip_listen.sh
src/agautolab/{__init__,agent_settings,project_settings,role_run,zulip_listener}.py
devenv/gitea/{SETUP.md,compose.yaml}
.gitignore  LICENSE
```

## Checks

- All 6 Python files parse.
- The legacy-name grep — the check the deleted `test_legacy_removed.py` used
  to perform, widened to the names this episode retired (`run_once`,
  `adapters`, `drive.sh`, `session.sh`, `autolab loop`, `mission_witness`,
  `AGENT_GUIDE`, `CHARTER`, `from .state`, `from .job`, `from .gates`) —
  returns no hits across every tracked `.py`, `.md`, `.sh` and `.toml`.
- Every module imports under the relocked environment.
- Every route answered correctly against an emptied `.local` (report 3 and
  report 7).

## Not verified, and why

The plan asked for one more check: that `agdevworld/assistant` still reads a
valid document through its `/api/autolab/agstudio/…` passthrough. It cannot be
run yet.

`:8791` on this Mac is serving **the pre-stub implementation** from a process
started by hand before this work (pid 38673); its `/status` carries no
`"stub": true`. The assistant currently reports both nodes reachable and
answering 200 — against old code on both. The passthrough check needs the
local gateway restarted on the new code first, which is a decision, not a
verification step.

## Where the stub is not

Two places still run the implementation this episode deleted:

1. **This Mac, `:8791`** — the hand-started gateway process. A restart is all
   it takes; the working tree under it is already the stub.
2. **`agautolab1`** — deploys from the agstudio Gitea mirror
   (`autodev/agautolab.git`) via
   `ansible_agdev/playbooks/agent/setup_autolab_node.yml`. Until a push and a
   playbook run, that node keeps running the loop for real: it can still
   accept a mission, start coding-agent iterations, and spend money. The two
   nodes disagree about what agautolab is.

No Ansible change is needed to deploy the stub: `autolab-gateway.service.j2`
starts `agent/gateway.py`, which survives, and `agents.local.toml.j2` still
generates the overlay the stub reads. `plane.env.j2` installs credentials
nothing reads any more — harmless, and out of scope here.

## Left alone, as planned

`agdevworld/assistant` still documents autolab behaviour in its own GUIDE
(missions that run, iteration summaries that cost $0.13–0.21, per-job
`cost_usd` on agstudio) that this node will no longer produce. That is a
separate episode, not a silent fix inside this one.

`pj-clusterintent`, the `autolab_node` role, the `autodev` Gitea
repositories, the Plane workspace and the `#pj-*` Zulip channels are
untouched.

## Commits

`agautolab`: 6 commits, `16814b9`…`05c1289`.
`pj-agdev`: the plan and reports 1–8.
