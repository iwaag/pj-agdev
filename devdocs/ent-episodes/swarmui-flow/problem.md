# SwarmUI flow — unexpected issues

## 1. SwarmUI rejected requests without a model

plan.md's premise was that SwarmUI's generation settings were already
configured manually in its UI, so the API only needed `prompt` and `images`.

Calling `POST /API/GenerateText2Image` with only `session_id`, `prompt`, and
`images: 1` returned:

```
SwarmUI error: No model input given. Did your UI load properly?
```

On-the-spot fix: called `POST /API/ListModels` to list available
checkpoints, picked `perfectdeliberate_XL.safetensors` as a general-purpose/
photorealistic option, added it to `agforge/.local/.env` as
`AGFORGE_SWARMUI_MODEL`, and updated the script to include it on every
request. width/height/steps/cfgscale/seed were left unset and generation
still succeeded, so those were left to server-side defaults.

## 2. SwarmUI's host was unknown

plan.md did not record the SwarmUI endpoint. Probing localhost:7801 and
similar on this Mac (agstudio) returned nothing (`000`).

On-the-spot fix: grepped `pj-clusterintent/.local/desired-state.yaml` for
`mdns_name:` entries to get the list of cluster hosts, then curled port 7801
against `agpc.local`, `agbach.local`, `aghub.local` in turn.
`agpc.local:7801` returned `302` (redirecting to `/Text2Image`), which
located it. No formal nctl CLI (`nctl status`, `nctl drift`) was used — just
manual host probing.

## 3. The nctl MinIO access key could not be reused

plan.md said the existing nctl access key could be reused, though a
separate key was noted as nicer but optional.

Attempting `mc mb agforge` (bucket creation) with the `nctl` user's
credentials was rejected:

```
mc: <ERROR> Unable to make bucket `agforge-minio/agforge`. Access Denied.
```

Checking `pj-clusterintent/devenv/nautobot/docker-compose.yml`'s
`minio-init` definition showed the `nctl` user's policy
(`nctl-outbox-rw`) is scoped to the `nctl-outbox` bucket only.

On-the-spot fix: used the MinIO devenv root credentials
(`devenv/.env`'s `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`) to create the
`agforge` bucket, then created a new policy `agforge-rw` scoped to the
`agforge` bucket only and a new user `agforge`. The generated secret was
recorded in `agforge/.local/.env`.
