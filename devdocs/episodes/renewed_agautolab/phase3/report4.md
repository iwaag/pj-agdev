# Phase 3 Step 4 Report — agforge adopts the pull loop

Done. agforge commit `6d935e3` (GitHub `main`), pyagag bumped
`4088bd2e → 1147476` (the sweep_serve revision).

## Shape chosen

The plan left DM handling to implementer's choice (thin event branch vs
`serve()` alongside); I chose **`serve()` alongside**: `main()` starts a
daemon thread running the unchanged `serve(dm_client, react,
accept=is_dm_for_us)` with its own client/event queue, while the main thread
runs `sweep_serve(client, react_topic, topic_filter="create-")`. Two queues,
each loop unchanged from its `agag.zulip` implementation. A DM narrow cannot
be swept, and a DM lost to downtime can simply be resent — the pull-mode
durability win applies to topics, and topics now have it.

## Per-match behavior

`react_topic(client, channel, topic)` in `zulip_chat.py`:

1. Posts the **common ack** ("Message received. Please wait for the
   reply.") *synchronously* — this is what makes the bot the topic's last
   poster, so the sweep stops re-matching while the run is in flight (same
   self-stabilization as agautolab's listener).
2. Then spawns the existing chat pipeline (`run_and_reply`) in a thread,
   exactly as before, except its own "On it — working on this now." ack is
   suppressed (`ack=False`) — one ack per match, not two. DMs keep the old
   "on it" ack.
3. `format_transcript` now also filters the common ack out of transcripts,
   like it already did the "on it" acks.

The `accept()` predicate is gone: DM acceptance is `is_dm_for_us` on the
serve thread, and topic acceptance (prefix, unresolved, last-poster) is the
sweep's own rule in pyagag, tested there.

## Tests

`tests/test_zulip.py`: the `accept` test is replaced by
`test_react_topic_acks_synchronously_before_the_run` (ack first and
synchronous, run spawned with `ack=False`), and the transcript test now
also feeds a common-ack line and expects it dropped.

`uv run pytest -q` in agforge: **71 passed**.

## Not deployed yet

The launchd service `com.agdev.agforge-zulip` on agstudio still runs the old
code; restart happens in step 5 alongside the agautolab deploy.
