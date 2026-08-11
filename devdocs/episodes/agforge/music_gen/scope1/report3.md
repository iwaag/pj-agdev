# Step 3 Report — agpc deployment

Completed 2026-08-11 through the managed Ansible channel.

`agpc` already had `/home/eiji/ACE-Step-1.5`, uv, its model cache, and a
Quadro RTX 8000 (48 GB). Reused that installation. The public `music-gen`
checkout was cloned under the user's projects directory and synchronized with
its locked dependencies.

Started manually with `nohup`:

- ACE-Step REST API: loopback `127.0.0.1:8001`.
- `music-gen`: LAN listener `0.0.0.0:8093`.

The wrapper is configured locally with its public base URL and an ignored
output directory. From agstudio, `GET http://agpc.local:8093/healthz` returned
`{"status":"ok"}` and `/guide` returned the service usage card. ACE-Step and
the wrapper were both listening on their expected ports.

Manual restart: from the ACE-Step checkout run `uv run acestep-api --host
127.0.0.1 --port 8001`; from the music-gen checkout run `uv run music-gen`
with `ACE_STEP_URL`, `MUSIC_GEN_PUBLIC_BASE_URL`, and
`MUSIC_GEN_OUTPUT_DIR` set as used at deployment. Logs are kept under the
checkout's ignored `.local/log/` directory.
