# Step 1 report — Plane CE on agstudio

Plane CE `v1.4.1` is running on agstudio as a self-contained Docker Compose
stack. The browser URL is `http://agstudio.local:8290`; its unused HTTPS
listener is mapped to `8490`. Plane's PostgreSQL, Valkey, RabbitMQ, and MinIO
ports are internal to its Compose network and do not reuse the existing
agstudio services.

## Provisioned objects

- Workspace: `agautolab`
- Project: `ProjectA` (`PA`)
- States: Backlog, Ready, In Progress, Done, Cancelled
- One agent-owned API token using the instance's `X-API-Key` authentication
- One generated local administrator account
- One generated viewer account with Plane CE's Guest role

All credentials and live UUIDs are stored only in the git-ignored
`.local/plane-credentials.env` with mode `0600`. The Compose `plane.env`, which
also contains generated secrets, is git-ignored and mode `0600`. Instance
telemetry is disabled.

Plane CE has no stricter viewer role than Guest. The viewer cannot create or
transition issues (a real session-backed create attempt returned HTTP 403),
but CE permits some collaboration surfaces such as comments. This satisfies
board-read-only use, but it is not a strict HTTP read-only principal.

## Verification

- All Plane containers are running; the API and three frontend containers
  passed their health checks.
- `http://localhost:8290/` and `http://agstudio.local:8290/` returned HTTP 200.
- The running instance accepted the API token on the concrete v1 projects,
  states, and issues routes (HTTP 200 for all three).
- The viewer session listed ProjectA successfully and was denied issue
  creation with HTTP 403.
- The user confirmed that Plane and ProjectA load from a phone over VPN on
  2026-08-11.

## Deployment findings

The host shell exports `DEBUG=release`, while Plane expects a numeric `DEBUG`.
Plane management commands therefore use `env -u DEBUG ./setup.sh ...`; this is
recorded in `.local/devenv.md`.

The official generated env also leaves `DATABASE_URL` and `AMQP_URL` empty,
whose Compose fallbacks contain default passwords. After randomizing the
service passwords, both URLs had to be populated with the matching generated
values. The first empty deployment volumes were recreated before any user data
existed, and the corrected migration then completed successfully.

During header inspection, a transient admin session cookie was accidentally
shown in local tool output because the case-sensitive filter missed
`Set-Cookie`. It was not written to tracked files or sent externally. The
session was immediately signed out and its cookie/response files removed.

Provisioned Plane for the prime and autolab agents — handoff candidate.
