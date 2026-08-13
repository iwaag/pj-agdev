# Step 8 — Replace the Zulip listener workflow

Status: **done**

## Result

`handle_message()` now performs the four workflows in order for each accepted
`mission-*` topic message:

1. read up to 1,000 messages of topic history, format a speaker-labelled
   oldest-first transcript, and `topic_dump()` it in the fixed front cwd;
2. call the idempotent project initializer unconditionally;
3. call the local gateway `/window` with the dump notice plus the English
   instruction to inspect `uv run new_mission.py --help`, add a mission when
   appropriate, and report the result;
4. pass the front reply unchanged to `topic_write()` for the original topic.

The acceptance predicate is unchanged: it is based on a live `mission-*`
topic and is channel-independent. The handler validates the `pj-<project>`
channel before provisioning, so a matching topic in an unrelated subscribed
channel fails visibly rather than creating an invalid project.

## New-channel subscription

pyagag now exposes small wrappers for listing public channels, listing the
bot's subscriptions, and subscribing by channel name. The autolab listener:

- reconciles all visible `pj-*` channels before registering its event queue;
- repeats reconciliation every 60 seconds;
- uses a second `ZulipClient` for that background work so the polling client
  is never shared across threads.

This covers channels created manually after the listener starts. The passive
log-only mode still observes without running the four mutating workflows.

## Verification

- agautolab: `uv run pytest -q` — 28 passed.
- pyagag: `uv run pytest -q` — 42 passed.
- Tests pin acceptance, transcript formatting, exact four-stage order, window
  prompt content, unchanged reply forwarding, project-channel validation, and
  missing-only `pj-*` subscription.
- A live subscription reconciliation completed successfully; the bot was
  already subscribed to every currently visible `pj-*` channel.
- `python3 -m py_compile` and `git diff --check`: passed.

## Commits and publication

- pyagag: `a1f52cd` (`Add Zulip channel subscription helpers`), pushed to
  GitHub `main`.
- agautolab: `70de29f` (`Route mission topics through project setup and
  front`), with the lock pinned to pyagag `a1f52cd`.
