# Step 5 — end-to-end (sonnet, FreeForge)

## Setup

Listener reloaded with
`launchctl kickstart -k gui/$(id -u)/com.agdev.agforge-zulip`; the startup
line confirmed the new wiring for free before any paid run:
`pull sweep, prefixes ('runcreate-', 'create-') + DM thread`.

## The loop, as the plan lists it

Everything sonnet, everything through `#FreeForge`:

1. **create- request → labelled Work.** Developer post in
   `create-20260815-p2step5-apple` asking for a 32x32 pixel-art red apple
   icon (PNG, transparent background). The front/generator pair produced
   `Plan: 32x32 pixel-art red apple icon (transparent background)` — Plane
   Work `F2-7`, `labels` containing exactly the `FORGEAUTO` label id from
   Step 1. Verified over the API rather than the Plane UI.
2. **runcreate- trigger → ack, execution, summary.** A `go` post in
   `runcreate-20260815` got the ack, then one summary post:
   `running "Plan: …"` / `result/ holds 1 file(s); zipped and uploaded` /
   `delivered to FreeForge/create-20260815-p2step5-apple` /
   `work F2-7: commented yes, Done yes`.
3. **Workspace.** `.local/agentws/e56cd5f3-…/generator/` holds `plan.md`,
   `tools.md`, `result/apple.png`, `result.zip` (workspace root, outside
   `result/`), and an `intermediate/` full of the generation's working files
   — the generator genuinely used the intermediate/result convention from
   `runcreate_generator/guide.md`.
4. **Origin delivery.** The origin `create-` topic received the presigned
   URL post (60-minute TTL, `files/…​.zip` key — the generalized upload).
   The URL downloaded; the zip opened; it contains exactly `apple.png`,
   which begins with the PNG magic and renders as a 32x32 transparent-
   background red apple.
5. **Plane write-back.** The Work carries one comment (the generator's
   verification-style answer) and sits in the `completed` state group.
6. **Re-trigger → "no work".** A second post in the `runcreate-` topic got
   the ack and `no work`; `next_work()` also returns `None` directly. The
   completed-state guard holds live.

## Notes

- Total paid runs for the loop: three sonnet executions (front, plan
  generator, runcreate generator) plus the re-trigger's free Plane scan.
- The origin topic was left unresolved; resolving `create-` topics stays the
  human/assistant workflow it was in p1.
- Deus Ex Machina note: the Omni Agent posted the `create-` request and the
  `runcreate-` triggers for the developer — handoff candidate.

## Step 6 decision — skipped, deliberately

The plan marks Step 6 (lifting `ensure_label`/`eligible_works`/`next_work`/
`report_work` into pyagag) optional and "skip freely if the round trip is not
worth it now". Skipped: the port is fresh, both copies are pinned by their
own test suites, and the pyagag round trip costs a GitHub push plus
`uv lock --upgrade-package pyagag` in both consumers. Worth doing the next
time pyagag is touched anyway; `_update_project` (Step 1) is queued for the
same lift.
