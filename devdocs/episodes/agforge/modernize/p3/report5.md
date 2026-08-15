# p3 report 5 — specs, tests, deploy, and the live round

Step 5 of `p3/plan.md`. Two live rounds were run, not one: the first failed
in a way worth keeping, and its two causes were fixed before the second.

## Specs

- `README_DEV.md` Map: the `generate.sh` entry is now the `agforge` CLI with
  its three subcommands, followed by an `agent/toolsets/` entry describing
  the whole route — `toolsets.csv` → `generator/tools/` → the Work's
  `[TOOLS]` footer → `runcreate`'s `tools/` — and naming
  `src/agforge/toolsets.py` as its only reader. Tool grants now point at
  `role_run.py`, where they actually live. `AGFORGE_COMFYUI_URL` joined the
  `.local/.env` key list.
- The `create_topic` / `runcreate_topic` docstring diagrams show `tools/`;
  no `tools.md` remains anywhere in `src/`, `tests/`, `agent/` or the docs.

## Tests

`uv run pytest -q` → **159 passed**, from 116 passed / 8 failed at the start
of the phase. New in this step: `tests/test_toolsets.py` (the `--list`
contract, lenient resolution including that a name cannot escape the
library, placement) and `tests/test_comfy_video.py` (class_type injection
and reseeding, every clear-error branch, the GPU-free policy, and the
output-reference reader). Live ComfyUI stays a hand check, as the plan says.

## Deploy

Committed and pushed each step (localrule), then both launchd jobs:
`launchctl kickstart -k gui/$(id -u)/com.agdev.agforge-zulip` and
`… /com.agdev.agforge`. The listener came back with
`pull sweep, prefixes ('runcreate-', 'create-') + DM thread`.

## Round 1 — everything but the video

One FreeForge request through the assistant endpoint: *"a short video: a red
paper boat drifting down a rain puddle at dusk, gentle ripples"*.

What worked, all of it new in this phase:

- The **front ran `agforge toolsets --list`** and wrote a one-line
  `toolsets.csv`: `toolset-video, General video generation & editing tools`.
  The `Bash(agforge:*)` grant is the reason it did not hang on a permission
  prompt.
- `generator/tools/` held exactly `toolset-video.md`.
- The generator wrote a plan whose single step is
  `agforge video generate --prompt "…"`, quoting the tool's real
  constraints ("no other parameters can be specified").
- Plane Work **F2-8** carries `[TOOLS] toolset-video` as its description's
  last line.
- `runcreate` rebuilt the workspace from that footer: `tools/toolset-video.md`
  alone, and a `plan.md` with **no** `[TOOLS]` line in it.

Then the deliverable failed. The generator's first `agforge video generate`
hit ComfyUI's out-of-memory error; it retried, **backgrounded** the retry,
posted *"I'll wait for it to finish and then package the result"* — and
ended its turn. The harness recorded `outcome: done` after 6 min, `result/`
was empty, no `failure.flag`, so the Work was reported successful and closed
with nothing delivered. ComfyUI's history shows that abandoned retry
*succeeded* two minutes later; nobody was left to download it.

## The two fixes

**The GPU.** Both failures so far — my hand run in Step 2 and the agent's
here — are the identical error: `MiniMaxH3ImageToVideo` asking for 500 MiB
with 72 MiB free, 44.18 GiB already allocated of a 47.26 GiB device. This
workflow needs nearly the whole card, so the *previous* run's resident
models fail the next one. Second occurrence, mechanical, same signature:
`comfy_video.free_memory` now asks an idle ComfyUI to unload before
submitting, and **skips it when anything is queued or running** — the GPU is
shared, and unloading under someone else's job would only move the failure
to them. It is best effort; an unreachable server is reported by the submit
that follows.

**The waiting.** The agent had no way to know the command takes minutes, so
backgrounding it looked reasonable. That is missing usage information, not a
missing rule, and the braindump's one prohibition is against patching guides
around generation failures. So it went where usage information belongs: the
`--help` description, one stderr line at the start of the run (`generating;
this takes several minutes`), and two sentences in `toolset-video.md` — it
runs for several minutes, prints the URL last, wait for it in the foreground.
No guide text was touched.

## Round 2 — the whole loop

The same Work (F2-8, reopened to its unstarted state) re-triggered with a
`go` post:

```text
running "Plan: Red Paper Boat Video Clip"
result/ holds 1 file(s); zipped and uploaded
delivered to FreeForge/create-20260815-133601-214424
work F2-8: commented yes, Done yes
```

- The generator ran the command **in the foreground** this time and kept its
  output as `intermediate/video_generate.log` — which shows the new stderr
  line, the `prompt_id`, and the presigned URL.
- `result/red_paper_boat.mp4`, 501,820 bytes. Video 5.17 s, audio 5.20 s.
- The origin `create-` topic received the zip URL; downloading it gives
  `200 application/zip` containing exactly `red_paper_boat.mp4`.
- Plane F2-8: commented, and back in the completed state.
- 13 turns, 7.5 min, $0.24.

## Notes

- Paid runs this step: front, plan generator, and two runcreate generators —
  the second round was worth its cost, since it is what proves the fixes.
- Deus Ex Machina, unchanged from p2: the Omni Agent posted the request and
  both `runcreate-` triggers on the developer's behalf. Still a handoff
  candidate.
- Reopening F2-8 rather than requesting a second plan kept the retry to one
  paid run and tested exactly the path that had failed.
