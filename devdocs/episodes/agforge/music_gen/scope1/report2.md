# Step 2 Report — Audio delivery

Completed 2026-08-11.

Chose the permitted simple delivery path instead of object storage. On a
successful ACE-Step task, `music-gen` downloads the WAV from ACE-Step into its
local ignored output directory and returns a URL served by its own
`GET /audio/{filename}` endpoint. This makes the result reachable from the
LAN without exposing an agpc-local filesystem path and does not touch the
`nctl-outbox` bucket.

The service guide documents that contract. Its URL is a deployment environment
fact and is not in the public repository.
