# Phase 4 Step 5 Report — E2E verification

All four planned scenarios ran live against the agstudio Zulip/Plane/Gitea
stack, through the launchd listener (`com.agdev.agautolab-zulip`) running this
phase's code. Suites at the end: pyagag **51 passed**, agautolab **77 passed**.

Profiles: the E2E ran with `front` *and* `coding` on `sonnet` (see the profile
note below); `.local/agents.local.toml` is restored to `local` for both.

## 1. Regular flow — `#pj-phase4e2e` / `mission-hello-readme`

Posted as the Developer: "Create a README.md that greets the reader and a
LICENSE file (MIT)", then "Yes, please create that mission and split it into
two tasks… Start it."

Confirmed:

- Three Gitea repos and three clones: `main`, `direction`, `devlog`.
- `.gitignore` containing `.local/` in all three, each as a single
  `Ignore .local/` commit that also established `main` in the empty repos.
- Plane project description exactly
  `[AUTO] autolab project: phase4e2e` (display name `Phase4e2e`).
- Project label list: `{'auto': …}` — created lazily on the first issue write.
- `AUTO` label id present on the Work `P6-1` and on both Sub-Works
  `P6-2`/`P6-3`, whose external ids are
  `pj-phase4e2e/mission-hello-readme@1#1` and `…#2`.
- Sub-Works in state group `unstarted` (`Todo`), Work `started` via
  `start.flag`.

So the live write shapes left open at planning time are confirmed: `labels`
as a list of label ids on the issue POST, and `comment_html` on the comment
POST (below).

## 2. Run trigger — `#general` / `run-1`

`run` posted as the Developer, three times:

1. `running "Create a greeting README.md" in phase4e2e` → agent output →
   `work P6-2: commented yes, Done yes`. `README.md` appeared in
   `.local/projects/phase4e2e/main/`, the report landed as a Plane comment on
   `P6-2`, the issue moved to group `completed`, `.local/work/` was gone
   (`.local/` left empty) and `.local/agent/run/run-0001.json` was written
   (`ag.agent-run.v1`, role `coding`, profile `sonnet`, harness `claude_code`,
   model `anthropic/claude-sonnet-5`, cost recorded).
2. Second `run` picked `P6-3` — the next Sub-Work by creation order —
   producing `LICENSE`, `commented yes, Done yes`.
3. Third `run` → `no work` (both Sub-Works completed; the parent Work is
   excluded both as `started` and as a parent).

## 3. Edge cases

- **Dirty workspace**: a hand-seeded
  `.local/projects/phase4e2e/main/.local/work/work.md` produced
  `work dirty: phase4e2e/main has a leftover .local/work/; remove it by hand
  and trigger again`, no run started, and the leftover file was still there
  afterwards — the dirty check never deletes.
- **Failing work**: an issue created via the API with the `AUTO` label,
  `unstarted`, whose description tells the agent to report a blocker and *not*
  create `success.flag` (`P6-4`). Outcome: `work P6-4: commented yes, Done no`,
  the comment on the issue, and the issue still `unstarted` afterwards.
- **Re-selection**: as the plan predicted, the next trigger (`run-2`) selected
  `P6-4` again. Accepted — triggers are manual. `P6-4` was cancelled by hand
  after the test so the scratch project does not keep offering it.
- **`no report`**: covered by unit tests only; every live `sonnet` run wrote
  the report its guide asks for, so the path was not reachable without faking
  it.

## 4. Isolation

`mission-stray-in-general` posted in `#general`:

```
sweep matched 'general'/'mission-stray-in-general'
ignoring 'mission-stray-in-general': 'general' is not a project channel
```

No reply was posted to that topic (its history still holds only the human
message), and `run-2` in the same sweep was served normally. `#general` was
reconciled by the subscription pass at startup (`subscribed 6 user(s) to
general`), which is what made any of this visible.

## Profile note — the front on `local` failed the same way phase 3 warned

The first attempt ran `front` on the `local` profile
(opencode + ollama). It reported creating `new_mission.md`, but wrote it to
the topic root instead of its `front/` working directory, so
`handle_front_response` found nothing and no Work was created. That is the
`warning.md` failure mode (the local model rewriting the paths it is given),
not a phase-4 regression: the same round on `sonnet` wrote the file in the
right place and the whole chain ran. The stray file was removed and the topic
re-armed with one more Developer post.

## Deploy state at the end of this step

agstudio's listener is running this phase's code. `agautolab1` is step 6.
