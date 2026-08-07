# asset_reconcile — Step 3 report

Date: 2026-08-07. Outcome: **blocked at the mechanical artifact check after
the one permitted re-request**. No asset or manifest change was committed to
the game repository.

## Flow implemented

Added `director/reconcile.py` as bounded glue around the Step 2 runner and the
existing desire-only agforge API. It:

1. composes one desire from the direction brief and requested manifest entry;
2. POSTs the desire, polls every three seconds with a 180-second deadline, and
   downloads the single image artifact into the direction workspace;
3. mechanically validates PNG structure and CRCs, decompresses the IDAT pixel
   stream, and checks exact manifest dimensions without Pillow or an LLM;
4. sends a mechanically valid candidate to the lenient director review;
5. only on acceptance copies it to the manifest path, changes only that
   request to `delivered`, and writes the direction-side review.

The glue permits at most two generation attempts and deliberately contains no
resize or format-conversion workaround. Eight unit tests now pass across the
director and reconcile modules, including the live agforge response contract,
PNG decode/dimension mismatch, and selective manifest mutation.

The first live invocation exposed a glue-side schema mismatch (`id` versus
the documented `request_id`, plus `working`/`detail`). The POST had already
been safely accepted as an in-memory job. The decoder was corrected to the
published API contract and covered by a unit test before restarting the flow.

## Live preflight

- Local Nautobot remained healthy.
- `nctl drift --host agpc --json`: `agpc` converged; its `swarmui-agpc`
  placement was active in desired and production state.
- SwarmUI at `agpc.local:7801` was reachable.
- agforge `/healthz` returned `{"ok": true}` and PID 44496, started before
  this episode run, was confirmed as the process listening on TCP 8092.
- `AGFORGE_SWARMUI_MODEL` was present without exposing its value.

## Blocking result

The director composed this technically complete desire:

> A 1024x1024 PNG game background depicting a medieval, old-fashioned
> tavern-hall atmosphere for an Othello board, with aged wood, candlelight,
> and weathered parchment tones, no text or UI elements

agforge completed both bounded requests:

- `82ce1e9a62db4a5a8aea034f47f0be42`
- `9923477a53ae43439c8c5c24ee40735d`

Both artifacts were JPEG/JFIF files, despite the explicit PNG desire. The
second candidate independently measured 1024×1024 with both `file` and
`sips`, so the agentify dimension guarantee worked. It failed the manifest's
PNG contract before subjective review.

This is not safely deliverable: renaming JPEG bytes to `.png` would fail the
game gate, while local transcoding would hide an agforge contract mismatch and
would violate this episode's copy-only, desire-owned asset boundary. Per the
plan, the request was tried once more and then stopped rather than weakening
the check or changing agforge in this episode.

The game clone remains clean at `61c65d7`; `assets/manifest.json` remains
`requested`, and `assets/bg/background.png` does not exist. The direction
review records both request IDs and the mechanical failures for follow-up.

## Required follow-up

agforge must either honor a requested image format in the desire and return
PNG bytes, or explicitly refuse that format. Once fixed and redeployed, rerun
Step 3 from the still-requested manifest; no cleanup or rollback is needed.

