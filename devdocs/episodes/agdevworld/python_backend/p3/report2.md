# Phase 3, step 2 — Zulip: freeforge and missions

Done. Both workflow pairs round-trip against the live Zulip realm from
`:8093`, `zulip.mjs`'s client duties now live in `agag.zulip.ZulipClient`,
and nginx still has not moved.

## What was built

`assistant/agdevworld_assistant/workflows.py` — freeforge requests/resolve
and autolab missions/resolve, delegating the client to
`agag.zulip.ZulipClient`. Only the three things agag does not give were
ported:

- **Topic names**: `stamped_topic_name(prefix)` →
  `{prefix}-{YYYYMMDD-HHMMSS}-{token_hex(3)}`; `create-*` for freeforge,
  `mission-*` for missions, channel `pj-<project>`.
- **The active-user filter**: `active_user_ids()` keeps
  `is_active is not False` (a member with no flag counts as active, like the
  JS). Used by step 3's channel creation.
- **The one-retry**: `RetryingZulipClient` retries `call()` exactly once when
  the `ZulipError` message carries no `HTTP \d` — socket-level failures only,
  never HTTP answers — preserving the learned-the-hard-way behavior from
  `zulip.mjs`.

Route mechanics kept: lazy client construction on first use (the server
boots and serves chat without the credentials mount; tests rely on it), 405
on non-POST (GET and PATCH both), the exact validations
(`Number.isInteger`-equivalent excludes bools; project must match
`^[a-z0-9][a-z0-9-]{1,38}$`), the response kinds `freeforge.request.v1`,
`freeforge.resolve.v1`, `autolab.mission.v1`, `autolab.mission-resolve.v1`,
and `ZulipError` → 502 `zulip_unavailable`. `ZULIP_ENV_PATH` defaults to
`/run/secrets/zulip.env`. Compose gained the two secret mounts on
`assistant-py` (the Gitea token is step 3's; one compose edit beats two).

## The one real finding: .local DNS inside the container

The first live freeforge call hung for ~120 s. Cause, measured in the
container: Docker's DNS answers `agstudio.local` with **every** host
interface address (loopback, every bridge network, link-locals), and
Python's `urllib` walks them serially with the full connect timeout each —
one Zulip call cost ~121 s (measured `whoami`). The JS service never showed
this because Node's happy-eyeballs connect races the addresses. Pointing
`ZULIP_URL` at `host.docker.internal` instead is not an option — Zulip
resolves the realm from the `Host` header and answers 400 for any other name.

Fix: compose maps `${ZULIP_LAN_HOST:-host.docker.internal}` to
`host-gateway` in the container's hosts file — one address, right `Host`
header. The actual hostname lives only in the git-ignored `.env`
(`ZULIP_LAN_HOST=agstudio.local`, documented in `.local/devenv.md`); the
committed compose carries no LAN name. After the fix: `whoami` in 0.0 s.

Fallout of the slow first attempt: the timed-out request had still completed
server-side, so today's realm carries two proof topics instead of one. Both
were answered by agforge and both were resolved (see below). Two paid
agforge runs happened where one was intended; both cheap, both delivered.

## Proof

`uv run pytest` — 96 passed (32 new in `tests_py/test_workflows.py`: topic
naming, the active filter, all validation rows, the retry/no-retry/second
-failure cases against a fake client, the error mapping — no network).

Live, on `:8093` against the real realm:

```
POST /api/freeforge/requests {"desire":"…teal pixel-art gem icon"}
  -> 201 freeforge.request.v1, topic create-20260813-095639-56b633, message 101
     (plus the timed-out first attempt's create-20260813-095001-d6891b, message 98)
  agforge (user 13) answered both topics with a presigned image URL.
POST /api/freeforge/resolve {"message_id":101,...} -> 200 freeforge.resolve.v1
POST /api/freeforge/resolve {"message_id":98,...}  -> 200 freeforge.resolve.v1
POST /api/autolab/missions {"project":"spike","briefing":"…"}
  -> 201 autolab.mission.v1, topic mission-20260813-095639-d56aa2 in #pj-spike, message 102
POST /api/autolab/missions/resolve {"message_id":102,...} -> 200 autolab.mission-resolve.v1
GET  /api/freeforge/requests  -> 405   GET /api/autolab/missions -> 405
POST /api/freeforge/requests {"desire":""} -> 400 bad_request
```

Four views and chat unchanged through `http://localhost:8090` (nginx and the
JS service untouched this step).
