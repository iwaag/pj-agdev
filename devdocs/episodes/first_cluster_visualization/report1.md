# Step 1 Report: Fetch script and snapshot

Implemented the read-only cluster snapshot workflow in the `agdevworld`
submodule.

## Result

- Added `scripts/fetch-cluster-state.mjs` and the `npm run cluster:fetch`
  command.
- The script submits one natural-language cagent request, polls every eight
  seconds with a six-minute deadline, extracts the first download URL, and
  downloads the artifact immediately.
- The artifact is parsed and validated as an `nctl.drift.v1` envelope before
  an atomic write to `public/cluster/state.json`.
- The bearer token is read from `CAGENT_TOKEN` or a gitignored token file.
  `CAGENT_URL` supplies the entrance address; neither value is committed.
- Added `public/cluster/` to `.gitignore`. The real snapshot and its temporary
  write path are both excluded from Git.
- Added a scrubbed `public/state.sample.json` with seven targets. It covers all
  four statuses, a missing actual node, a node awaiting manual initial access,
  and a non-node target for loader/filter acceptance tests.

## Live proof

The fetch used the human entrance at `https://agstudio:8789` with its static
bearer token. Request `req_8817095dc90f4a7ca42842a719af6f04` completed and
produced a valid snapshot with:

- schema: `nctl.drift.v1`
- `ok`: `true`
- 19 targets
- summary: 10 converged, 2 drifting, 7 unknown

The downloaded payload remains local and ignored. `git check-ignore` confirms
that `public/cluster/state.json` is excluded.

The exact cagent prompt was:

> Please run `nctl drift --json`, save the output as a file, upload it with
> `nctl upload`, and reply with only the download URL.

## Verification

- `node --check scripts/fetch-cluster-state.mjs`
- JSON parse and schema/target checks for `public/state.sample.json`
- Live `CAGENT_URL=https://localhost:8789 npm run cluster:fetch`
- JSON parse and envelope checks for the resulting local snapshot
- `git diff --check`

Submodule implementation commit: `5cfc372` (`Add cluster snapshot fetch
workflow`).
