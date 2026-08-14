# Step 2 — the new create-topic workflow

## What was built

`agforge/src/agforge/create_topic.py`, and `zulip_listener.main` now points
the topic handler at it. `zulip_chat.react_topic` — one charter run per topic
— is out of the topic path. The DM path is untouched and still runs
`zulip_chat.react`.

The flow, as served:

```
ACK "Message received. Please wait for the reply."
N   = highest existing numeric directory under .local/topics/<ch>/<topic>/ + 1
<N>/front/       chatlog.md            → front run   → answer posted at once
<N>/generator/   required_items.md     → generator run
                 tools.md                plan.md → register_plan (step 3)
                                         idea.md → posted verbatim
                                                 → generator answer posted
```

Decisions inside the plan's latitude:

- **The front's answer is posted on its own, before the generator starts.**
  It is the conversational reply, and the generator run takes tens of seconds
  to minutes; the topic should not sit silent through it.
- **`N` is read off the directory, not a counter file.** A hand-made or
  hand-removed generation cannot desynchronize it. autolab's `generation()`
  counter file is the thing step 5 should reconcile, not this.
- **Acks are stripped from the chatlog**, reusing `zulip_chat.SWEEP_ACK` and
  `ACK_PREFIX` as the plan suggested. Leaving them in would teach the front
  that "please wait for the reply" is something it once said in answer to a
  request.
- **The "human posted during the run" re-check** is carried over from
  autolab's `handle_topic`. A re-serve cuts a new `N`, which is exactly the
  behavior the decisions section asks for.

`register_plan()` is a named seam in `create_topic.py` that currently reports
the plan and says registration lands in step 3. It is replaced by the
`plane.py` call there; the step-2 tests target the seam, so they survive it.

## Verification

### Fake-client tests over the three paths — `tests/test_create_topic.py`

```
88 passed in 4.02s
```

(a) no `required_items.md` → ack, one answer, no `generator/` directory at
all. (b) present → the generator workspace gets `required_items.md` +
`tools.md`, the run happens in it, and `plan.md` / `idea.md` / the answer are
reported in that order. (c) an exception anywhere after the ack → the topic
gets `failed during <step>: …`, with the step named (`front`, `generator`).
Plus: generations increment per serve and old ones survive intact, a mid-run
human post triggers a second serve as generation 2, and traversal in a
channel or topic name is refused.

### One real round trip in `#FreeForge`

Listener swapped with `launchctl kickstart -k gui/$(id -u)/com.agdev.agforge-zulip`
(this is step 4's first bullet, done early because a live check needs it).
Topic `create-20260814-modernize-p1-step2`, request: *"a small pixel-art icon
of a blue bird, 64x64, transparent background"*.

What the topic received, in order:

1. `Message received. Please wait for the reply.`
2. the front's answer — it had written `required_items.md`
3. `idea.md` verbatim, then the generator's answer

Workspace afterwards, exactly as designed:

```
1/front/chatlog.md
1/front/required_items.md
1/generator/required_items.md
1/generator/tools.md
1/generator/idea.md
```

Both runs recorded, both on sonnet, no cheap-model substitution:

| role | model | turns | duration | cost |
|---|---|---|---|---|
| front | anthropic/claude-sonnet-5 | 5 | 12.9 s | $0.122 |
| generator | anthropic/claude-sonnet-5 | 10 | 41.5 s | $0.219 |

So one topic costs about $0.34 at present prompt sizes.

## Failure Farming: the generator refused, and it was right to

The generator wrote `idea.md`, not `plan.md`. Its reasoning: `tools.md`
offers `generate.sh` plus file writing, `generate.sh` has no alpha/transparent
flag, and — quoting it — *"I have no image-editing tool (no ImageMagick, no
Python/PIL, nothing beyond raw file writes)"*. It proposed two concrete
enablements: a `--background transparent` flag on `generate.sh`, or a
chroma-key post-processing script.

That is the guide working as intended. It also surfaces a real **Tool Giving**
gap, and it is worth naming precisely: the generator's grant
(`role_run.ROLE_ALLOWED_TOOLS["generator"]`) *does* include
`Bash(magick:*)`, `Bash(sips:*)`, and `Bash(python3:*)`. The tools were
granted and never described. `tools.md` is the only place the agent looks, so
from where it stood the refusal was correct — an Unexplained Chainsaw in
reverse: a chainsaw it was handed but never told about, which is the same
failure as not handing it over at all.

Not fixed here — it is outside this step's scope and it is the agents'
document, not the transport's. **Handoff candidate**: `tools.md` should
describe the post-processing tools the grant already allows. Left as-is so
step 3's live check can also exercise the `plan.md` branch by asking for
something the current `tools.md` fully covers.

## Deviations from the plan

None. `register_plan` as a placeholder seam is the step boundary the plan
implies (Plane registration is step 3's deliverable), not a change of scope.
