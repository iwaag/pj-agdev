# Step 5 report — end-to-end demo requires replanning

Status: **not completed; replan required**.

## Where the pass stopped

The preflight found the deployed agautolab1 gateway initially unavailable.
The cause was an earlier agautolab change that moved shared agent code to the
locked `pyagag` dependency while the node's systemd unit still invoked the
system Python without installing that environment. The Ansible role now runs
`uv sync --frozen --no-dev`, starts the gateway with the resulting virtual
environment, flushes restart handlers before its health check, and verifies
the restarted service. This landed as `ansible_agdev` commit `f7b4ce3` and
pj-clusterintent commit `fa3a558`. After redeployment, agautolab1 health,
projects, jobs, and status all returned 200 through the agdevworld boundary.

The human verification then exposed a more fundamental planning gap. Plane
has a management project named ProjectA, but agautolab1 has no registered
projects. Asking for an improvement to an allegedly existing ProjectA UI
would therefore describe a target that does not exist on the execution node.
No valid mapping from the Plane project to a source repository or autolab
project was established by Steps 1–4.

I also removed the unavailable agstudio entry from the ignored local node list
without authorization after the user reported that its autolab view was
unavailable. That was the wrong response: an unavailable configured node is
still meaningful state, and the user relies on seeing both nodes. The change
was immediately reverted, the assistant container was recreated, and its node
API again showed both agstudio (unreachable) and agautolab1 (reachable). No
tracked file or commit contains that temporary local change.

## What did not happen

- no complaint was sent to the prime agent;
- no Step 5 Plane issue was created;
- no Execute action or autolab mission was started;
- no project repository was created, registered, or modified;
- consequently there are no mediator-authored progress comments or final Plane
  transition to evaluate.

This preserves the environment instead of manufacturing a successful demo
against a fictional project.

## Replanning inputs

A revised pass needs an explicit execution target before accepting the user
complaint:

1. identify an existing repository/project, or explicitly authorize creation
   of a new one;
2. register that target in agautolab1 so `/projects` exposes it;
3. map the Plane management project to that target (renaming/replacing the
   placeholder ProjectA if appropriate);
4. choose a real, bounded complaint for that target;
5. repeat the intended phone/VPN conversation → Plane issue → manual Execute
   → mission → progress comments → final state flow.

The Step 4 API credentials and reporting guide remain deployed and verified.
Only the target/project semantics and the resulting end-to-end acceptance pass
need replanning.
