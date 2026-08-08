# asset_reconcile ex1 — Step 1 report

Date: 2026-08-08. Outcome: **complete**.

## Node and service pre-flight

- `nctl status --json` reported Nautobot reachable and authenticated with the
  intent catalog and GraphQL available. `nctl drift --host agautolab1 --json`
  reported both the `agautolab1` compute instance and node `converged` (the
  node remains intentionally excluded from production inventory by
  `waiting_for_manual_initial_access`).
- `ansible-playbook -i inventories/agautolab.yml
  playbooks/agent/setup_autolab_node.yml` completed `ok=12 changed=0
  unreachable=0 failed=0`. The node already had the current agautolab Gitea
  revision, `46f2d9f`, so no restart was required.
- `GET /healthz` returned HTTP 200 with `ok: true`. Authenticated `GET /status`
  showed the previous run complete, exit code 0, and `driver.running: false`.
- The agforge service was already running on agstudio and its `/healthz`
  returned HTTP 200.

## Repositories

The two private `autodev` repositories had already been provisioned as empty
repositories at the beginning of the step (both created at
`2026-08-08T03:12:49Z`), so they were reused instead of deleted/recreated:

- `gallery-direction`: seeded at `3ddb38e` with the one-line medieval-fantasy
  `brief.md`, ignored candidate/staging areas, and a tracked `reviews/`
  placeholder for durable director evidence.
- `gallery-web`: confirmed empty, with `main` as its default branch. It is
  intentionally left empty for the coding agent.

The local agautolab `main` and Gitea `autodev/agautolab` `main` both resolve to
`46f2d9f`; there were no pending agautolab changes to push.

## Node-to-agforge reachability

The reachability probe was executed through Ansible, preserving the rule that
Ansible is the only controller channel touching the node:

- node → `http://agstudio.local:8092/healthz`: HTTP 200;
- node → a freshly signed `http://agstudio.local:9100` MinIO object: HTTP 200.

The first probe invocation was launched outside the `ansible_agdev` working
directory, so Ansible did not load the repository configuration and attempted
the wrong SSH authentication. It failed before running a remote task. Repeating
the same ignored probe playbook from `ansible_agdev/` loaded the configured key
and passed all three tasks (`ok=3 changed=0`). No hostname or `/etc/hosts`
fallback was needed.
