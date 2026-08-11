# Step 1 Report — Precondition Check

Date: 2026-08-11 (Asia/Tokyo)

## Result

The precondition passed. ACE Studio was running on `agstudio`, its bundled CLI
was executable, and the project-status request returned successfully.

## Evidence

Command:

```sh
ACE_STUDIO_CLI="/Applications/ACE Studio.app/Contents/Helpers/acestudio-cli"
"$ACE_STUDIO_CLI" status project --json
```

Response:

```json
{
  "duration": 57600,
  "isNewProject": true,
  "isTempProject": true,
  "projectName": ""
}
```

The open project was therefore a new, temporary, unnamed project suitable for
the exploration run.

Installed application version, read from the application bundle:

- `CFBundleShortVersionString`: `2.1.5`
- `CFBundleVersion`: `2.1.5.25080`

The local cluster support services were also checked with
`uv run nctl status --json` from `pj-clusterintent/nctl`. The status envelope
reported `ok: true`: Nautobot `3.1.3` was reachable and authenticated, the
intent catalog and GraphQL endpoint were available, one Celery worker was
running, and there were no pending jobs. Some node observation dumps were old,
but that does not affect this host-local ACE Studio exploration.

## Decision

Proceed to Step 2.
