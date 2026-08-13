# Step 9 — Local end-to-end verification

Status: **done**

## End-to-end result

Created `#pj-phase1-e2e-20260813` without subscribing the autolab bot. On
listener startup, project-channel discovery found and subscribed to it before
registering the event queue. A `mission-*` request then exercised the complete
local path:

```text
Zulip topic
  → numbered front chat dump
  → idempotent Plane/Gitea project initialization and two clones
  → local gateway /window
  → OpenCode + Ollama front
  → uv run new_mission.py
  → Plane issue in Todo
  → unchanged front reply in the original Zulip topic
```

The clean final acceptance topic was `mission-document-setup`. Its one request
produced:

- Plane project `Phase1 E2e 20260813`, identifier `PE20260813`;
- Gitea repositories `phase1-e2e-20260813` and
  `phase1-e2e-20260813-direction`;
- both ignored local clones;
- chat dump version `1` in the front workspace;
- Plane issue `Document local setup`, state `Todo`;
- an Autolab Agstudio reply in the same Zulip topic confirming creation.

## Failure farming and fixes

The first live topic reached the front but the local model asked for path
clarification despite both files existing. A direct diagnostic run proved its
actual cwd was `agent/front` and both relative paths were present. The listener
prompt was therefore grounded with those facts and now requires `pwd`/path
inspection evidence before requesting clarification. The retry registered
`Add service health check` and replied successfully.

That retry exposed a separate environment issue: launchd started the gateway
through the absolute uv path but did not put `/opt/homebrew/bin` in child
`PATH`, so the agent fell back to `python3 new_mission.py`. The committed
gateway launchd template and installed local plist now set the same explicit
PATH as the listener template. After reload, a real front run successfully
executed `uv run new_mission.py --help`; the clean acceptance topic then used
the intended interface.

The prompt hardening is agautolab commit `785a0dd` (`Ground the front mission
prompt in its workspace`).

## Periodic subscription proof

While the listener was already running, created
`#pj-phase1-subscribe-20260813` with the autolab bot initially unsubscribed.
The background reconciliation subscribed it within 25 seconds, proving the
periodic path rather than only startup discovery.

## Services after verification

- `com.agdev.agautolab-gateway`: installed/running under launchd with explicit
  PATH; `/healthz`, `/status`, `/jobs`, and `/projects` return 200 and the
  removed `/guide` returns 404.
- `com.agdev.agautolab-zulip`: installed/running under launchd from the
  existing committed template; its independent polling and subscription
  clients are registered.
- Plane instance endpoint: 200.
- authenticated Gitea user-repositories endpoint: 200.
- `nctl status --json`: `ok: true`; Nautobot reachable/authenticated and one
  worker running.

## Final verification

- agautolab: `uv run pytest -q` — 28 passed.
- pyagag: `uv run pytest -q` — 42 passed.
- `git diff --check`: passed in both implementation repositories.
- No agautolab1 deployment or cluster SSH/Ansible operation was performed.
