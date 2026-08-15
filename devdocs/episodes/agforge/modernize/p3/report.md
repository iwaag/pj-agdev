# p3 report — agforge CLI, toolsets, `tools/` folders, `failure.flag`

Phase 3 of `agforge/modernize`, realizing `braindump.md` against the guides
committed in `19fa4ea`. Destructive phase: nothing was kept for backward
compatibility. Per-step detail is in `report1.md` … `report5.md`.

## What agforge looks like now

**One command.** `agforge`, reached by its bare name from any role's
workspace (`scripts/agforge`, and `role_run.tool_environment` already puts
`scripts/` on every role's PATH):

```text
agforge toolsets --list                 → toolset-image, General image generation …
agforge image generate "<prompt>"       → presigned URL on the last line
agforge video generate --prompt "…"     → the same, one 5-second clip with sound
```

`--help` on each is the usage information. `Bash(agforge:*)` is granted to
the front — which had no Bash grant at all and would have hung on a
permission prompt — and to the generator.

**One unit of tool vocabulary.** `agent/toolsets/toolset-*.md`, each opening
with `# Description`. It travels the whole flow:

```text
front:      agforge toolsets --list  →  toolsets.csv
create:     toolsets.csv             →  generator/tools/toolset-*.md
Plane:      the Work's description   →  … last line: [TOOLS] toolset-video
runcreate:  that footer              →  workspace tools/toolset-*.md
```

`src/agforge/toolsets.py` is the only reader of that directory. Name
resolution is deliberately lenient — extension, `--list` description tail,
case, quotes — because the names travel through an agent's copy-paste; an
unresolvable name is logged and skipped, never fatal. The single `tools.md`
is gone from every flow.

**One verdict channel added.** `runcreate` clears `failure.flag` before the
run and reads it after: present means `report_work(success=False)`, so the
Work stays unstarted and selectable, and both the topic summary and the
origin delivery say so while still handing over whatever was produced. The
exit code remains the first-class failure signal.

## What the live rounds proved, and what they cost

Round 1 delivered nothing, and was the most useful part of the phase. Every
new mechanism worked — the front ran the CLI, `toolsets.csv` became `tools/`,
the Work carried `[TOOLS] toolset-video`, `runcreate` rebuilt exactly that
`tools/` and a footer-free `plan.md` — and the video still failed, twice
over:

1. **A shared GPU with no room.** This workflow needs ~45 GiB of a 47 GiB
   device, so the previous run's resident models fail the next one. Seen
   once by hand in Step 2 and once by the agent in Step 5, byte-identical
   error both times. Fixed mechanically (`free_memory` before submit, skipped
   whenever something else is queued or running) — a second occurrence of the
   same signature is what earns code, not the first.
2. **A six-minute command with nothing saying so.** The agent backgrounded
   it, said it would wait, and ended its turn; the abandoned render finished
   two minutes later with nobody to download it. That is missing usage
   information, so it went into `--help`, one stderr line, and
   `toolset-video.md` — not into a guide. The braindump's one prohibition
   held: no guide text was added anywhere in this phase.

Round 2, on the same reopened Work, closed the loop: `result/` held
`red_paper_boat.mp4` (5.17 s video, 5.20 s audio), the zip reached the origin
topic as a presigned URL that downloads, and Plane F2-8 was commented and
completed.

## State

- Tests: **159 passed** (116 passed / 8 failed at the phase's start — those
  eight wanted the `tools.md` the guide commit had already deleted).
- Deployed: both launchd jobs reloaded; every step committed and pushed to
  GitHub as it was finished.
- `.local/.env` gained `AGFORGE_COMFYUI_URL=http://agpc.local:8188`
  (git-ignored, documented in `README_DEV.md`).

## Left for later

- The `[TOOLS]` footer is visible in the Plane UI. It reads as noise to a
  human; moving it to a comment needs a list API in `agag.plane`, which was
  the reason it went to the description in the first place.
- `toolset-speech.md` has a `# Description` and no content. It is listed, so
  a front can ask for it and a generator will receive an empty document.
- Both `runcreate-` triggers were still posted by the Omni Agent for the
  developer — the p2 handoff candidate, untouched.
