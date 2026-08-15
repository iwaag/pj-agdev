# p3 report 2 — `agforge video generate`

Step 2 of `p3/plan.md`. `agforge video generate --prompt "…"` produces one
5-second video with sound on the agpc ComfyUI and answers with a presigned
URL on its last line — the same contract as the image subcommand.

## What was built

`src/agforge/comfy_video.py`, plus the `video generate` subparser in
`cli.py`, `.mp4`/`.webm` in `generate.CONTENT_TYPES`, and
`AGFORGE_COMFYUI_URL=http://agpc.local:8188` in the git-ignored
`.local/.env`.

The flow is four small functions, each of which can be exercised on its own:

- `load_workflow(prompt)` reads the API-format export at
  `.local/resources/comfywf/video/minimax_h3_t2v_turbo.json`, writes the
  prompt into the `MiniMaxH3ImageToVideo` node's `inputs.prompt`, and
  replaces the `RandomNoise` node's `noise_seed` with a fresh one. Both are
  matched by `class_type` — node ids change on re-export. The exported file
  carries a fixed seed, so without the reseed every run returns the same
  video.
- `submit(base, workflow)` → `POST /prompt`, answers `prompt_id`.
- `wait_for_outputs(base, prompt_id)` polls `GET /history/<prompt_id>` every
  5 s for up to 600 s. It reads `status.status_str == "error"` as a failure
  and prints ComfyUI's own exception text; a completed run with no output
  files is also a failure, not an empty success.
- `output_references(entry)` collects every `{filename, subfolder, type}`
  dict under any `outputs` node, whatever key the node reports it under —
  `SaveVideo` has changed that key before, and the shape is the stable part.

Download is `GET /view?filename=…&subfolder=…&type=output`, saved to
`.local/out/<date>-<prompt id prefix>.mp4` and handed to the existing
`upload_and_presign`.

## Live verification (2026-08-15, ComfyUI 0.33.1 on agpc.local:8188)

Prompt: *"A red paper boat drifting down a rain puddle at dusk, cinematic
close-up, gentle ripples"*.

- Wall clock 6 min 36 s, comfortably inside the 600 s poll budget but not by
  much — the budget is right, and it is what the runcreate generator's
  1200 s run budget has to absorb.
- Output `2026-08-15-145ae229.mp4`, 444 KB. Two tracks: video 5.17 s, audio
  5.20 s. The plan's hint held — `VAEDecodeAudio` is in the workflow and the
  MP4 does arrive with sound.
- The presigned URL answers `200 video/mp4`, so the new `CONTENT_TYPES`
  entries reach the object as intended (a video lands under the `files/`
  prefix, not `images/`).

Error paths checked by hand: a missing workflow file, a missing
`AGFORGE_COMFYUI_URL`, and an empty prompt each exit with one clear line.

## The trap worth knowing: GPU memory

The **first** live run failed, and it failed usefully:

```text
ComfyUI run failed: {"status_str": "error", … "exception_message":
"Allocation on device 0 would exceed allowed memory. (out of memory)
Currently allocated: 44.18 GiB  Requested: 500.00 MiB
Device limit: 47.26 GiB  Free (according to CUDA): 72.38 MiB" …}
```

The queue was empty; the memory was held by models another workflow had left
resident on the Quadro RTX 8000. `POST /free {"unload_models": true,
"free_memory": true}` released 24 GB and the identical prompt then succeeded.

No code was added for this. The failure already surfaces ComfyUI's own
message, which names the cause precisely, and pre-emptively unloading other
people's models from a shared GPU is a worse default than reporting the
condition. If it recurs often enough to be mechanical, a `/free` before
submit is the obvious next step — that is the standing ENT order, not
something to guess at now.

## Test state

Unchanged from Step 1: 116 passed, the same 8 pre-existing
`test_runcreate_topic.py` failures that Steps 3–5 clear. Video unit tests
(the clear-error branches) come in Step 5; the live path is checked by hand,
as the plan says.
