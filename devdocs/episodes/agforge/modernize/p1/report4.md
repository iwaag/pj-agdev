# Step 4 — end-to-end and wiring

## The swap

`launchctl kickstart -k gui/$(id -u)/com.agdev.agforge-zulip`, log at
`agforge/.local/out/zulip-listener.log`. Done repeatedly through steps 2–4;
the service is running the committed code and `launchctl print` reports
`state = running`.

The listener starts clean on the new module:

```
agforge zulip listener starting (pull sweep prefix 'create-' + DM thread)
sweeping as user_id=13 (forge-bot@agstudio.local)
```

## `AGFORGE_ZULIP_LOG_ONLY=1` — the free observer

Verified as a real free-of-charge wiring check. The launchd job was booted
out, one request posted, and the observer run by hand:

```
sweep matched 'FreeForge'/'create-20260814-p1step4-observer'
observed sweep match 'FreeForge'/'create-20260814-p1step4-observer'
```

Matched, logged, no run, no spend.

## Resolving a topic takes it out of the sweep

Same topic, resolved to `✔ create-20260814-p1step4-observer`, observer
re-run:

```
registered event queue …
(no match)
```

Confirmed.

## End to end, under launchd, on the committed code

Topic `create-20260814-p1step4-e2e`, request: a 768x512 oil-painting
lighthouse at dusk.

```
[Developer] Please make one 768x512 image of a lighthouse at dusk, oil-painting style.
[Forge]     Message received. Please wait for the reply.
[Forge]     Created `required_items.md` — …a single 768x512 oil-painting-style image…
[Forge]     created F2-3 "Creation Plan" in FreeForge
            I created `plan.md` — all required attributes map directly to
            `generate.sh` parameters…
```

Ack → front answer → Plane Work → generator answer, end to end, with no
manual step in between.

## Defect found and fixed: an empty topic matched the sweep forever

Resolving the finished test topics while the listener was live produced a
**phantom topic**. The sequence, from the log and both topic histories:

1. Zulip resolves a topic by *renaming* it, and Notification Bot posts
   "@_**Developer** has marked this topic as resolved" into it.
2. A sweep pass ran inside that rename window (12:53:05) and still saw the
   old name, `create-20260814-p1step3-freeforge`, with a non-bot last poster.
3. By the time the handler read it, every message had moved to the `✔` name.
   The chatlog was **empty** — and the front was run on it anyway, at full
   price, and answered *"The chatlog is empty, so there's nothing for me to
   interpret as a request."*
4. Those two posts **recreated** the unresolved `create-…` topic. The channel
   then held both `create-20260814-p1step3-freeforge` and
   `✔ create-20260814-p1step3-freeforge`.

The deeper fact, which is what makes this worth fixing rather than shrugging
at: `agag.zulip.sweep_topics` skips a topic only when its **last poster is
this bot**. A topic with *no messages at all* has no last poster, so it does
not qualify for the skip — **an empty topic matches every sweep, forever**. In
this incident the loop only stopped because the front's answer happened to
make the bot the last poster. A silent early return would have turned it into
a hot loop instead.

**Fix** (`create_topic.handle_topic`): when the history holds no message from
anyone but this bot, post one line — *"There is nothing in this topic to
answer yet."* — and return before any agent run. One Zulip post instead of a
$0.12 front run, and the post is what silences the topic. Pinned by two tests:
`test_an_empty_topic_is_answered_in_one_line_and_costs_no_agent_run` and
`test_a_topic_holding_only_our_own_posts_is_also_empty`.

Cost of the incident: one wasted front run. No generator run (no
`required_items.md` was written), no Plane write, no duplicate Work.

The race itself lives in shared code (`sweep_topics`) and is not fixed here —
agforge's handler is now robust to it, which is the right layer for this step.
**Step 5 candidate**: `sweep_topics` should skip a topic with no messages,
which removes the class rather than the symptom.

## Final state

```
103 passed in 4.06s
```

Every topic created during this phase is resolved. The only unresolved
`create-` topic in `#FreeForge` is `create-20260814-phase3-pullcheck`, which
predates this episode and is dormant (bot is its last poster). The sweep has
been quiet since the cleanup.

Plane holds four agforge Works — `F2-1`, `F2-2`, `F2-3` in FreeForge and `S-2`
in Spike — all unlabelled, and `next_work` returns `None`.

## Deviations from the plan

None. The empty-topic guard is an addition, driven by an observed failure
rather than by anticipation.
