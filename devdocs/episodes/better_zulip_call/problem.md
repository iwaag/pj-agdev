# better_zulip_call — problem

Date: 2026-09-14. Written from an investigation of the agent room's
"could not be read" failures, read off the running relay, the Zulip
response headers and the relay's code. The 429 itself was not reproduced:
doing so means spending the Developer account's whole quota on purpose,
which stalls every other tool on that account.

## Symptom

Closing `#front` topics from the agent room (the completion panel,
`front_desk` p4) sometimes breaks the view mid-way. A reload then shows
the headline `11 channel(s) could not be read: …` and no topic list. A
second reload about 30 seconds later shows everything again.

The closes themselves are not failing: the relay's completion history has
no `failed` outcome, Zulip carries the ✔ on every topic that was closed,
and every plan the relay produces answers in well under a second.

## Cause

1. **One account, one quota.** Every Zulip call the relay makes on the
   agent-room path is made as the Developer account: the room sweep
   (`AGENTROOM_ZULIP_ENV`) and the completion's reads and writes
   (`AGENTROOM_CHAT_ZULIP_ENV`) both point at `developer.env`. Zulip
   answers that account with `x-ratelimit-limit: 200` — 200 calls a
   minute. Anything else run as the Developer (`agentchat` from a shell,
   a second Omni session) spends the same 200.

2. **One close is a burst.** A completion reads the conversation graph for
   the preview (15 calls for a four-target plan, more for a wide one such
   as `front-routine-mediagen` with 29 targets), reads it again on apply
   to re-derive the targets, writes the acceptance notes, the ✔ renames
   and the channel archives, then calls `room.forget()`
   (`agentroom/src/agentroom/server.py`, the `/complete` answer). The
   frontend hears `COMPLETED_EVENT` and reloads `/agents` and `/work` at
   once (`src/views.ts`), and a `/work` sweep is one call per watched
   channel — about 50. Two closes in a row, or a close beside an
   `agentchat` session, is enough to reach 200.

3. **A 429 is swallowed per channel.** `Room._read_work`
   (`agentroom/src/agentroom/room.py`) wraps each `channel_topics` call in
   a bare `except Exception`, appends `{channel, error}` to `errors` and
   moves on. That is the right shape for one genuinely unreadable channel;
   for a rate limit it means every channel after the quota ran out lands
   in `errors`. `agag.zulip` raises `RateLimited` with the server's
   `Retry-After` in it, and the room never looks at the type. Nothing is
   logged: the relay log has no trace of any of these episodes.

4. **The failed sweep is cached.** `Room._cached` stores whatever
   `_read_work` returned for `AGENTROOM_CACHE_SECONDS` (30 s), errors
   included. A reload inside that window is served the same failed
   payload, which is why the view stays broken for "about 30 seconds" and
   then recovers on its own: the next sweep after the TTL finds the quota
   back.

5. **The view reports the count, not the reason.** `views.ts` prints
   `N channel(s) could not be read: <names>` from `work.errors`. The error
   strings are there but are not shown, so a rate limit looks like eleven
   broken channels rather than one quota.

## What is not the cause

- The ops engine (`/ops`) uses its own bot (`opsroom.env`) and an event
  queue; it does not draw on the Developer quota and is not what breaks.
- The completion's 20 s / 60 s frontend timeouts are not being hit.
- Nothing in Zulip is left half-closed: the writes land, only the read-back
  after them fails.

## Proposals

Ordered by how little they change.

### A. Do not cache a failed sweep, and wait out a 429 (recommended first)

- In `Room._read_work`, catch `RateLimited` separately: sleep
  `retry_after` (bounded, the same `rate_limit_backoff` the ops engine
  uses) and retry that channel once before giving up on it.
- Let `_cached` skip storing a payload whose `errors` is non-empty, or
  store it under a much shorter TTL, so the next reload after the quota
  returns reads afresh instead of re-serving the failure.
- Log every channel-level error with its message. The absence of a log line
  is the reason this had to be reasoned out rather than read.

### B. Say what happened in the view

- Show the error text of the first failed channel next to the count, and
  when it is a rate limit, say so: `Zulip rate limit — reading again in
  Ns`. A viewer who reads "11 channels could not be read" reasonably
  concludes the realm is broken.
- Keep the last good `/work` payload in the frontend and draw it greyed
  under the headline while the fresh one fails, rather than an empty list.

### C. Spend fewer calls per close

- After a completion, reload only what the close touched: the room already
  knows the targets it wrote, so `forget()` could drop just those channels
  from the cached payload and patch their rows, instead of clearing the
  whole board and forcing a 50-call sweep.
- The apply step re-reads the graph the preview read seconds earlier. A
  short-lived graph cache keyed by the fingerprint would make the second
  walk free when nothing moved (the fingerprint is already what says
  whether it did).

### D. Separate the quotas

- Give the room sweep its own read-only bot, as the ops engine has, so a
  burst of writes from a close cannot starve the read that follows it, and
  a shell `agentchat` session cannot starve the GUI. Zulip has no read-only
  key, so the gain is isolation, not safety — but isolation is the whole
  problem here.

A and B together remove the symptom the Developer sees. C and D reduce
how often the quota is reached at all, and D is the one that also protects
the GUI from calls made outside it.
