# agforge begin — step 4 report: upload + presigned URL

Status: done.

## What was done

Extended `agforge/scripts/generate.py` (same script, per plan's "extend or
add alongside"):

- After generation, uploads the image to the `agforge` bucket via boto3 with
  `endpoint_url` set to `AGFORGE_S3_ENDPOINT`, key
  `images/<date>/<uuid><ext>` with a correct Content-Type.
- Creates a presigned GET URL, TTL default 60 minutes with a `--ttl MINUTES`
  flag to override, and prints it as the final line of stdout. The local
  file path now goes to stderr so stdout's last line is cleanly the URL for
  scripting.
- Guard rails: refuses to run if `AGFORGE_S3_BUCKET=nctl-outbox`, and fails
  fast on missing `.local/.env` keys.

## Done criterion — verified

- `uv run scripts/generate.py --ttl 5 "a red vintage bicycle leaning against
  a brick wall"` printed a URL on `http://agstudio.local:9100/agforge/...`.
- `curl` of that URL succeeded and the downloaded bytes are identical
  (`cmp`) to the local file.
- Expiry: a 1-second-TTL presigned URL for the same object returned HTTP 200
  when fresh and HTTP 403 three seconds later — MinIO enforces the TTL.
- "From another device" caveat: verified from this Mac only, but the URL is
  signed against `agstudio.local:9100` (the LAN-reachable mDNS name, exactly
  the hostname rule from step 2), not localhost, so any LAN device resolving
  mDNS reaches the same endpoint.

## Notes

- boto3 needs `region_name` set to something (`us-east-1`) for signing;
  otherwise nothing MinIO-specific came up. Presign uses SigV2-style query
  params on this MinIO version — works fine with plain curl.
