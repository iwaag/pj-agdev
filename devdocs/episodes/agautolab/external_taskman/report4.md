# Step 4 report — autolab progress reporting access

The autolab mediator now has both the knowledge and the node-local credentials
needed to report Plane-backed missions.

## Tool Giving

agautolab commit `a67eb6c` adds `.local/plane.env` to the mediator's charter and
documents the exact Plane v1.4.1 calls in its entrance guide. For a mission
carrying a Plane issue ID, the mediator is told to comment when it creates the
job, after each completed iteration with its gate result, and at the final
outcome. It moves converged work to Done; stuck/error work returns to Ready or
becomes Cancelled with an explanatory comment according to whether another
attempt is useful.

The guide includes concrete `X-API-Key` comment and state-PATCH examples, the
configuration path, all five state-variable names, and the rule that reported
success requires an HTTP success. It also keeps the secret out of job prompts,
transcripts, comments, and repositories.

## Deployment

The cluster Ansible role changed in `ansible_agdev` commit `1aaac7c` (recorded
by pj-clusterintent commit `105187e`). It reads a controller-only properties
file selected by `AUTOLAB_NODE_PLANE_CREDENTIALS_SOURCE`, extracts only the
agent URL/key, workspace/project values, and state IDs, and renders
`.local/plane.env` mode 0600. Admin and viewer credentials present in the
controller bundle are not copied.

The agautolab commit was pushed to the agstudio Gitea deployment remote before
running the role. The first playbook run used the old static inventory example
from the local memo and stopped at the existing required-Ollama-endpoint assert:
the static inventory resolves the node but does not carry placement variables.
It had already updated the checkout but had not reached the Plane task. The
tracked playbook example and local memo were corrected to use the rendered
production inventory. The second run completed with 24 tasks OK, 3 changed,
0 unreachable, and 0 failed, then restarted the gateway.

## Verification

- Ansible playbook syntax check passed
- Ansible boundary/conformance suite: 4 passed
- the node checkout reported agautolab `a67eb6c` and served the new guide
- node `.local/plane.env` was mode 0600 and contained exactly the nine selected
  Plane keys
- the node reached the LAN Plane states endpoint with its deployed key (200)
- from the node, a temporary issue received a progress comment (201) and a
  transition to Done (200)
- the controller observed one comment and the Done state, then deleted the
  temporary issue (204)
- the pre-deploy `nctl status --json` was healthy: Nautobot 3.1.3 authenticated,
  one worker running, and no pending intent jobs

The temporary probe behaved exactly like the documented API calls. No missed
or incorrect agent-driven transition has been observed yet; Step 5 exercises
those calls from the mediator rather than from an Ansible verification shell.
