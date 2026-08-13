# Phase 3 Step 1 Report — pyagag sweep primitives and `sweep_serve()`

Done. pyagag now carries the pull loop; agautolab consumes the new revision.

## What was added (`pyagag/src/agag/zulip.py`)

- `ZulipClient.stream_id(name)` — `GET get_stream_id` wrapper. Kept even though
  the sweep itself does not need it (see below), as the general name→id lookup.
- `ZulipClient.channel_topics(stream_id)` — `GET users/me/<id>/topics`,
  returning topic names newest-first, resolved ones included.
- `sweep_topics(client, self_id, topic_filter)` — the awaiting-reply scan:
  every subscribed channel's topics, filtered to (a) prefix match, (b) not
  starting with `RESOLVED_TOPIC_PREFIX`, (c) last poster (via
  `topic_history(num_before=1)`) is not this bot.
- `sweep_serve(client, handler, *, topic_filter, log)` — the new loop beside
  `serve()`. Message events only set a `dirty` flag; the payload is never
  processed. When dirty, it clears the flag and calls `handler(channel, topic)`
  per match. A sweep also runs on every queue (re-)registration — startup and
  `QueueExpired` recovery — which is what makes downtime lossless. The loop is
  single-threaded and serial like `serve()`; handler exceptions are logged and
  the sweep continues; Zulip errors reset the queue (and thereby re-arm a
  sweep) exactly as `serve()` does.

Design note: the plan suggested a stream-name→id lookup for topic enumeration,
but `GET users/me/subscriptions` already carries `stream_id` per subscribed
channel, so `sweep_topics` iterates that directly — one call instead of one
per channel.

## Tests

Seven new tests in `pyagag/tests/test_zulip.py` (a `SweepClient` fake extends
the existing `FakeClient`): wrapper wiring, the three sweep rules plus the
"no history at all still matches" and "one message per last-poster check"
details, startup sweep, dirty-flag re-sweep on a message event, non-message
events ignored, re-sweep after queue expiry, handler-exception survival.

`uv run pytest -q` in pyagag: **50 passed** (43 before).

## Ship

- pyagag commit `1147476` pushed to GitHub `main`
  (github.com/iwaag/pyagag).
- agautolab `uv.lock` bumped `7cf02a4 → 1147476`, committed as `d3cd6a9`,
  pushed to GitHub `main`.

## State handed to Step 2

`uv run pytest -q` in agautolab: **39 passed, 4 failed**. The four failures
are the known pre-existing breakage the plan records ("the listener is
currently broken"): `zulip_listener.guide()` still resolves `guides/front/` /
`guides/coding/`, renamed on disk to `mission_front/` / `mission_coding/`.
Step 2's prompt rework subsumes the fix; those tests encode the old contract
and will be rewritten, not preserved.
