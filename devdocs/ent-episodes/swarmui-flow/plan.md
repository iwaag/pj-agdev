# SwarmUI flow — plan

Follow-up to [problem.md](problem.md) and braindump.txt. First "Easier Next
Time" episode: turn the on-the-spot fixes into a reproducible flow.

## Goal (acceptance criteria)

1. From a clean checkout, with only `agforge/.local/.env` and the versioned
   defaults file present, `scripts/generate.sh "a prompt"` succeeds with no
   on-the-spot fixes.
2. An explicit per-request parameter override (e.g. width) demonstrably
   reaches SwarmUI (verify via output image size or SwarmUI's response
   metadata).
3. `model` is documented and enforced as the only required generation
   parameter; all others are optional.

## Premises (state them, so the report can confirm they held)

- SwarmUI is reachable at `AGFORGE_SWARMUI_URL` (already in `.local/.env`).
  Endpoint discovery via pj-clusterintent is out of scope this episode.
- S3/MinIO is assumed available (happy path). The only handling for the
  unavailable case is the agent instruction in Step 3 — no code fallback.
- Destructive phase: no backward compatibility needed. Env var names, script
  interface, and file layout may change freely.

## Constraints (minimum)

- Keep the two existing hard rules from `agforge/README_DEV.md`: never commit
  endpoints/credentials/generated images; never write to the `nctl-outbox`
  bucket.
- Everything else is implementer's discretion.

## Step 1 — Parameter layering in generate.py

Replace the "SwarmUI UI is pre-configured" premise with explicit parameters
on every request, merged from three layers (later wins):

1. versioned defaults file → 2. `.local/.env` → 3. per-request CLI flags.

- Add a versioned defaults file, suggested `agforge/params/defaults.toml`
  (Python 3.11 has built-in `tomllib`; JSON is equally fine — implementer's
  choice). It holds sample values for the optional params (width, height,
  steps, cfgscale, seed) and documents that `model` is required but
  environment-specific, so its real value lives in `.local/.env`, not here.
  Values can be rough; structure (required vs optional) must be explicit.
- Add CLI flags to `generate.py` for at least model/width/height/steps/
  cfgscale/seed. The existing `ENV_PARAMS` map (`generate.py:47`) is the
  natural merge point.
- Fail fast with a clear message when `model` is resolvable from no layer.
  Hint: this exact failure is problem.md #1 — SwarmUI 0.9.7.4 returns
  "No model input given" otherwise. Valid names come from
  `POST /API/ListModels`; mentioning that in the error message helps the
  next person.

## Step 2 — Update README_DEV.md

- Document the three-layer merge and the defaults file location.
- Keep the required/optional split already present in the `.env` keys
  section; adjust to whatever Step 1 changed.
- Fix the stale episode path in "Related docs" (currently points at
  `devdocs/episodes/agforge/begin/`; this episode lives under
  `devdocs/ent-episodes/swarmui-flow/`).

## Step 3 — Agent instruction: MinIO fallback

Add a short agent-facing instruction (suggested location: a section in
`agforge/README_DEV.md`, or `AGENTS.md` if preferred): when the
`AGFORGE_S3_*` variables are unset and the user's prompt names no
alternative storage, do not improvise — propose starting the pj-clusterintent
devenv MinIO and set it up with these reproducible steps (from problem.md #3):

1. Start MinIO from `pj-clusterintent/devenv/` (docker compose).
2. With root credentials from `pj-clusterintent/devenv/.env`
   (`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`): `mc mb <alias>/agforge`,
   create policy `agforge-rw` scoped to the `agforge` bucket, create user
   `agforge` with that policy.
3. Record endpoint/key/secret in `agforge/.local/.env`.

Note in the instruction that the nctl user's key cannot be reused (its
policy `nctl-outbox-rw` is scoped to `nctl-outbox` only) — that dead end
cost time once already.

## Step 4 — Record deferred work in devdocs/todo_done.md

Two lines, so the scope-outs don't evaporate:

- Resolve the SwarmUI access point from pj-clusterintent instead of a
  hand-set `.env` value (fits the `nctl relations` service-binding graph;
  would eliminate problem.md #2's manual port probing).
- Fold the agforge bucket/policy/user creation into the declarative
  `minio-init` in `pj-clusterintent/devenv/nautobot/docker-compose.yml`,
  replacing Step 3's manual `mc` steps.

## Step 5 — Verify and report

- Run the acceptance criteria from the Goal section (clean run, one explicit
  override run) and write `report.md` in this folder: what was done, whether
  each premise held, and anything unexpected — same format as a normal
  episode report.
