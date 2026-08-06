# agforge begin — step 2 report: storage bucket on existing MinIO

Status: done.

## What was done

Reused the MinIO already running for nctl (pj-clusterintent devenv,
`http://agstudio.local:9100`, health check returned 200 — no service start
needed).

- Plan allowed reusing the nctl access key, but that turned out impossible:
  the `nctl` user's policy (`nctl-outbox-rw`, see the devenv `minio-init`
  container) is scoped to the `nctl-outbox` bucket only, so `mc mb` returned
  Access Denied. Fell back to the "separate key is nicer" option.
- Using the devenv root credentials, created:
  - bucket `agforge`
  - policy `agforge-rw` — `ListBucket`/`Get`/`Put`/`DeleteObject` on the
    `agforge` bucket only (mirrors the nctl-outbox policy pattern)
  - user `agforge` with a freshly generated 40-hex-char secret
- Recorded credentials in git-ignored `agforge/.local/.env`
  (`AGFORGE_S3_ENDPOINT`, `AGFORGE_S3_BUCKET`, `AGFORGE_S3_ACCESS_KEY`,
  `AGFORGE_S3_SECRET_KEY`), mode 600. Updated `agforge/.local/devenv.md`.
- Registered local `mc` aliases `agforge-root` and `agforge-user`.

## Done criterion — verified

With the new `agforge` user: `mc cp` PUT of a test object succeeded,
`mc share download --expire 10m` produced a presigned URL whose host is
`agstudio.local:9100` (not localhost, per the plan's hint), and `curl` of
that URL returned the object content. Test object deleted afterwards.

## Notes for next steps

- The `agforge` user cannot create buckets or touch `nctl-outbox` —
  the plan's hard rule is now enforced at the policy level, not just by
  convention.
- No repo file changes in the agforge submodule this step (everything lives
  in `.local/`), so there is no agforge commit for step 2.
