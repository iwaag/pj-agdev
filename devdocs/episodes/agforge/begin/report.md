# agforge begin — final report

Goal reached: from the `agforge` workspace, one command takes a prompt,
generates one image via SwarmUI, uploads it to MinIO, and prints a
time-limited download URL.

## What works (the one command)

```sh
cd agforge
scripts/generate.sh "a prompt"              # URL valid 60 min
scripts/generate.sh --ttl 240 "a prompt"    # override TTL in minutes
# stderr: local: .local/out/<date>-<id>.jpg
# stdout final line: presigned download URL on http://agstudio.local:9100
```

Implementation: one Python script (`scripts/generate.py`, `uv run` inline
metadata, requests + boto3) plus a sh wrapper. Config entirely in
git-ignored `agforge/.local/.env`; actual endpoints and quirks in
`agforge/.local/devenv.md`.

## The environment, as discovered

- SwarmUI 0.9.7.4 runs on the `agpc` GPU node, port 7801 (not on agstudio).
- MinIO is the pj-clusterintent devenv instance on `agstudio.local:9100`.
  agforge got its own bucket `agforge`, user `agforge`, and policy
  `agforge-rw` (bucket-scoped), created with devenv root creds.

## Easier-next-time payload (quirks that cost time)

1. **SwarmUI requires `model`.** `GenerateText2Image` with only
   prompt/images fails with "No model input given" even though the UI has
   settings — the "UI defaults apply" premise does not extend to the model.
   Model name comes from `/API/ListModels`; kept in `.local/.env`
   (`AGFORGE_SWARMUI_MODEL`, currently `perfectdeliberate_XL.safetensors`).
   Width/height/steps/cfgscale/seed genuinely do default server-side.
2. **The nctl MinIO key is bucket-scoped.** Its policy only covers
   `nctl-outbox`, so "reuse the nctl access key" was not possible — a
   dedicated user/policy was the fix and is anyway safer: the agforge key
   physically cannot touch `nctl-outbox`.
3. **Presigned URLs embed the signing hostname.** Signed against
   `agstudio.local:9100` (LAN-reachable mDNS name), never localhost —
   confirmed the URL host and verified download + 403 after expiry.
4. **SwarmUI returns JPEG** (server-relative ref `View/local/raw/...`,
   plain GET, no session) with current settings — don't assume `.png`.

## Out of scope (deferred, per plan)

cagent/clusterintent integration, request queueing, multiple images,
model/parameter management, auth on the pipeline.
