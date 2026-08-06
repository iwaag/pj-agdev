# agforge begin — plan

Goal: from the `agforge` workspace, one command takes a prompt, generates one
image via SwarmUI, uploads it to S3-compatible storage, and prints a
time-limited download URL.

Experimental environment. No backward compatibility required. Implementer has
free rein on language/tooling — the few hard rules are marked **MUST**.

Hard rules (the only ones):
- **MUST NOT** commit endpoints, hostnames, credentials, or generated images.
  All of those live in `agforge/.local/` (git-ignored) or in storage.
- **MUST NOT** write into the `nctl-outbox` bucket — use a dedicated
  `agforge` bucket.

## Step 1 — Workspace scaffold

Make `agforge/` openable as an agent workspace:

- `agforge/README_DEV.md` — entry point an agent reads first: what agforge is
  (asset-generation workspace, "Easier Next Time"), how to run the pipeline,
  where local config lives.
- `agforge/.gitignore` — ignore `.local/` and any image output dir.
- `agforge/.local/devenv.md` — local-only notes (actual endpoints, quirks).
- `agforge/scripts/` — pipeline scripts land here in later steps.

Done: fresh agent opening `agforge/` can find everything from README_DEV.md.

## Step 2 — Storage: bucket on the existing MinIO

Reuse the MinIO already running for nctl (devenv service, see
`pj-clusterintent/nctl.toml` `[storage]`: endpoint `http://agstudio.local:9100`).

- Create bucket `agforge` (via `mc`, MinIO console on the server, or a tiny
  script). Reusing the nctl access key is acceptable here; a separate key is
  nicer but optional.
- Record endpoint/bucket/key location in `agforge/.local/` (e.g. `.local/.env`:
  `AGFORGE_S3_ENDPOINT`, `AGFORGE_S3_BUCKET`, `AGFORGE_S3_ACCESS_KEY`,
  `AGFORGE_S3_SECRET_KEY`).

Hints:
- **Presigned URLs embed the endpoint hostname used at signing time.** Sign
  against `agstudio.local:9100`, never `localhost`, or URLs won't open from
  other machines. This is exactly why nctl.toml carries that comment.
- If the MinIO service isn't running, it lives in the pj-clusterintent devenv;
  starting it is fine. Falling back to a fresh MinIO compose under
  `agforge/devenv/` is also fine if reuse turns out to be more friction than
  it's worth — just keep the bucket/endpoint contract the same.

Done: an object PUT + presigned GET (e.g. with `mc` or a 10-line boto3 call)
works from this Mac and the URL opens in a browser.

## Step 3 — SwarmUI: generate one image via API

Assumption: SwarmUI generation settings are already configured manually in its
UI; the script only needs prompt + session handling.

- Put `AGFORGE_SWARMUI_URL` in `agforge/.local/.env`.
- Script (suggest Python, since boto3 is needed in step 4 anyway;
  `uv run` with inline script metadata keeps it dependency-light):
  1. `POST {url}/API/GetNewSession` (empty JSON body) → `session_id`.
  2. `POST {url}/API/GenerateText2Image` with `session_id`, `prompt`,
     `images: 1`. Leave other params unset so SwarmUI's current UI defaults
     apply — that's the "already configured manually" premise.
  3. Response contains image path(s)/URL(s) relative to the SwarmUI server;
     download the file locally (e.g. to `agforge/.local/out/`).

Hints:
- If the generate call rejects missing params, the minimal known-good set is
  roughly `prompt`, `images`, `model`, `width`, `height`, `steps`, `cfgscale`,
  `seed: -1` — check what the running SwarmUI version actually requires and
  hardcode the minimum into `.local` config, not the repo.
- SwarmUI also has a websocket variant of the API; ignore it, plain HTTP
  polling is enough for one image.

Done: script prints a local file path to a freshly generated image.

## Step 4 — Upload + presigned URL

- Extend (or add alongside) the script: upload the image to the `agforge`
  bucket (key suggestion: `images/<date>/<uuid>.png`), then create a presigned
  GET URL with a TTL (default e.g. 1h, flag to override) and print it as the
  final line of output.
- boto3 works against MinIO with `endpoint_url` set; `mc share download` is a
  no-code alternative.

Done: URL printed by the script downloads the image from another device on the
LAN before TTL, and stops working after (spot-check is enough).

## Step 5 — One command + wrap-up

- Single entry point, e.g. `agforge/scripts/generate.sh "a prompt"` (or the
  Python script directly) → prints the download URL. This is the episode's
  real deliverable: next time is one command.
- Update `agforge/README_DEV.md` with the exact invocation and the
  `.local/.env` keys it expects.
- Write `devdocs/episodes/agforge/begin/report.md`: what works, actual
  commands, anything discovered (SwarmUI API quirks, MinIO friction) — the
  "Easier Next Time" payload.

Out of scope (explicitly deferred): cagent/clusterintent integration, request
queueing, multiple images, model/parameter management, auth on the pipeline.
