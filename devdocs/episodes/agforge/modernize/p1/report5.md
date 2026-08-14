# Step 5 — share the common code (converge with agautolab)

## What moved into `agag`

Two new modules in pyagag, each with its own tests (41 new, `92 passed`).

### `agag.topics` — the serving skeleton

`serve_topic(client, channel, topic, handler, *, ack_text, empty_reply)` owns
the discipline both agents had grown independently: ack first, read the
history, hand a `TopicContext` to the caller's handler, always post back —
naming the step the handler was on if it raised — resolve when asked, and
re-check for human posts that arrived during the run.

Alongside it: `topic_workspace`, `next_generation`, `generation_dir`,
`next_record_path`, `format_chatlog`, `guide` / `GuideError`,
`prompt_with_guide`, `chatlog_placement`.

Two design points worth stating, because they are where the two agents
differed and had to be reconciled:

- **`format_chatlog(..., drop=…)`** takes a predicate instead of hard-coding
  ack text. agforge strips its two acks; autolab strips nothing. The
  predicate is consulted only for *our own* messages — a human quoting an ack
  is conversation.
- **`empty_reply` is opt-in but not cosmetic.** `sweep_topics` skips a topic
  only when its *last* poster is this bot, so a topic with no messages at all
  matches every sweep forever (the step-4 defect). Both agents now pass one.

### `agag.plane` — the Plane client

Credentials, HTTP, projects, states, labels, issues keyed on
`(external_source, external_id)`, and the Markdown ↔ issue conversion.

**`external_source` is a required argument on every keyed call, never
defaulted.** It is the only thing keeping agforge's and agautolab's external
ids apart in one workspace, and a default would make a collision a typo away.

**`labels` and `parent` are opt-in.** Whether an issue is eligible for
automatic execution is the calling agent's policy, so autolab passes
`labels=[AUTO]` and agforge passes nothing. The old `ensure_issue` attached
`AUTO` unconditionally; that decision now has to be made out loud at each call
site.

## What deliberately stayed out

Autolab-only: the `AUTO` label and its cache, the `[AUTO]` project marker and
`project_slug`, Sub-Work generation keys, `eligible_works` / `next_work`,
`report_work`, `start.flag` / `cancel.flag`, project clones (`init_project`,
gitea). agforge-only: channel→project routing and the FreeForge fallback.

## Both agents moved onto it

- **agforge**: `create_topic.serve` is now ~15 lines — cut the generation,
  write the chatlog, run the front, post, run the generator. `plane.py` is
  routing policy and the two absences, nothing else.
- **agautolab**: `mission.py` keeps its policy and delegates the rest;
  `zulip_listener`'s topic path is `serve_topic` plus autolab's own steps
  (project setup, Plane read-back, front, response handling).

## The `(N)` generation directory reaches autolab

This is the braindump's own note — *"autolabの方にこの(N)のインクリメント
フォルダがないので継続チャットで問題が出るはず"* — and it was right.

Before: one stable `front/` per topic, reused forever, so a continued
conversation ran on top of the previous run's leftovers. Two consequences the
old code had to work around, both now gone:

| worked around by | replaced by |
|---|---|
| deleting `new_mission.md` / `start.flag` / `cancel.flag` after acting, so a leftover command would not replay | a fresh `<N>/front/`, which the next serving never looks into |
| deleting stale `task[N].md` before a re-split | a fresh `<N>/coding/` |
| a separate `generation` counter file, to keep Sub-Work keys clear of cancelled generations' | `N` itself is the Sub-Work generation key |

Nothing is deleted any more. The generation number is the guard, and the
leftovers stay as evidence of what that run was told —
`test_the_sub_work_key_follows_the_generation` pins the key, and
`test_each_serving_cuts_a_new_generation` pins the workspace.

## Verification

```
pyagag     92 passed
agforge    99 passed
agautolab  77 passed
```

**agforge live, on the shared base** — topic `create-20260814-p1step5-shared`,
a watercolour stone bridge:

```
[Forge] Message received. Please wait for the reply.
[Forge] Created `required_items.md` … a 512x512 watercolour-style image …
[Forge] created F2-4 "Plan" in FreeForge
```

Identical to the pre-refactor behavior, which is what "changes no behavior"
had to mean.

**agautolab wiring**, free (`AUTOLAB_ZULIP_LOG_ONLY=1`):

```
agautolab zulip listener starting (pull sweep, prefixes ('mission-', 'run-'))
sweeping as user_id=11 (autolab-agstudio-bot@agstudio.local)
observed sweep match 'general'/'mission-stray-in-general'
```

## Deployment

Push order was pyagag → both agents' `uv lock --upgrade-package pyagag` →
agents. Then, per `devenv.md`, **from GitHub**:

```
uv run --project ../nctl nctl render production --out inventories/generated
AUTOLAB_NODE_PLANE_CREDENTIALS_SOURCE=… ansible-playbook … \
  playbooks/agent/setup_autolab_node.yml --limit agautolab1
```

```
agautolab1 : ok=25  changed=3  unreachable=0  failed=0
```

What actually landed on the node:

```
9563f25
https://github.com/iwaag/agautolab.git
pyagag.git?branch=main#a4f529e48c6f3077062c48947e669517132b1743
node imports ok
```

The node's checkout is at this step's commit, its source is **GitHub**, its
pyagag pin is the new one, and it can import the refactored modules. The local
`agstudio` checkout was updated as the working tree and its launchd listener
restarted; `--limit agstudio` was **not** run — `devenv.md` asks for that to be
deliberate, not a reflex after a push, and this Mac's checkout is already the
live tree.

One thing worth flagging for whoever reads the playbook next: the task is
still named *"Update the agautolab checkout from the command-node Gitea"*,
which is a stale name — the `repo_url` it uses is the GitHub one, as the
verification above shows. The name is misleading given how much weight the
no-gitea rule carries. **Handoff candidate**: rename that task.

## Deviations from the plan

The plan allowed splitting autolab's `(N)` into its own episode. It was done
here instead, because the same refactor already rewrote both call sites and
doing it twice would have been the larger change.

`agag.plane` is a generalization of agforge's step-3 client rather than a
verbatim move, so that autolab's labelled, parented issues could use it too —
otherwise the shared client would have served one agent and the duplication
would have survived in the other.
