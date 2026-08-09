# director_workspace — final report

## Outcome

The old director implementation was removed and replaced with a deliberately
minimal workspace-backed entrance. A new Gitea repository contains only
`.gitignore`, `GUIDE.md`, and `concept.md`; `POST /director` passes the user's
text to one Claude CLI process after the fixed instruction to read
`GUIDE.md`. The harness does not inject direction-file contents.

The experiment succeeded. Claude independently discovered the unmentioned
`concept.md` in all three real runs. It used that context to explain the
project, propose a futuristic image prompt, and approve the generated image
against the sci-fi direction. This supports the proposed starting point:
"read the guide, then let the agent inspect its own workspace" is sufficient
for this small direction repository.

## What was built

- Removed `pj-agdev/director/` and stopped its former port-8094 process.
- Created public Gitea repository `autodev/scifi-direction` and pushed its
  initial commit `1edb154`.
- Cloned it locally at the ignored
  `agautolab/.local/direction/scifi-direction/` path.
- Added `POST /director` to the autolab gateway in submodule commit
  `87a9acc`.
- Restricted the one-shot Claude process to `Read,Glob,Grep`, used the
  direction clone as `cwd`, serialized requests, and recorded every run under
  `.local/agent/director/`.
- Restarted the local gateway and exercised the new route end to end.

## Test inputs and outputs

1. `What is this project?`

   The director called it a minimal sci-fi game workspace, cited
   `concept.md`, and stated that all imagery must follow futuristic
   aesthetics. Because neither the request nor fixed prefix mentions that
   file or theme, this proves self-directed context discovery.

2. `Suggest prompt to generate background image of this game.`

   The director proposed a wide cinematic scene with futuristic
   megastructures, spacecraft, holographic elements, a nebula, cool blue/cyan
   lighting, and warm neon accents. That prompt was sent to agforge request
   `fe592977a3d0476bb4a6b91078225c9f`.

3. `review .local/image/background.png`

   The director opened the generated image and approved it. It explicitly
   used the sci-fi direction in `concept.md`, citing the hard-surface
   spacecraft, blue/orange lighting, nebula, scale, and composition. It also
   noted that the underside detail was somewhat busy and symmetrical.

The three Claude runs completed in 16 turns and 43.115 seconds of reported
backend time, costing USD 0.3001105. Detailed per-test evidence and timings
are in `report4.md`; raw HTTP responses and gateway records remain in ignored
local storage.

## Generated asset

Agforge generated a 1024×576 JPEG. It was converted to a real PNG and placed
at the requested workspace role as `.local/image/background.png`. SHA-256:
`556c1bd9ca80000026328e3e51ccea5b021a7a02f02e2d6513f5187623839962`.
The direction repository ignores `.local/`, so neither this generated asset
nor the test responses were pushed.

## Deviations from the braindump

- The repository is named `scifi-direction`. The braindump did not prescribe
  a name; the plan recommended a distinct name to avoid the historical
  `director` and `gallery-direction` repositories.
- The ready-made episode `GUIDE.md` was copied byte-for-byte as required by
  the plan. It says `the game director`, whereas the earlier braindump sentence
  said `a game director`; the user-provided file and execution plan were the
  authoritative source.
- The braindump called the generated image `background.md`. The implementation
  uses `background.png` because the artifact is an image, and converts the
  returned JPEG bytes so the extension is truthful.
- The route name is `/director`, selected under the plan's implementation
  discretion. Responses use the existing JSON record envelope rather than
  unframed text so cost and run identity remain observable.

## Elements the test operation suggests adding next

1. **Durable gateway supervision.** The first manual `nohup` restart passed a
   healthcheck but died when its launching shell ended. A launchd unit or an
   equivalent managed service should own startup, logs, restart behavior, and
   the exact deployed commit.
2. **Version evidence in health/status.** A healthcheck proves liveness but
   not that the listener contains `/director`. Reporting the gateway commit or
   build ID would make restarts deterministic to verify.
3. **Paid-entrance policy.** The in-process lock prevents concurrency, but the
   new unauthenticated route can spend money repeatedly. Before broader use,
   add an explicit authentication and/or budget policy without expanding the
   director prompt.
4. **Structured downstream handoff only when needed.** Test 2 required
   extracting a creative prompt from prose. If director-to-agforge automation
   becomes routine, a small typed artifact or explicit final marker would be
   useful; it is not needed for the current human/Omni-operated window.
5. **Asset provenance beside local assets.** A lightweight ignored sidecar
   could retain the source request ID, original media type, conversion, hash,
   and review run ID. The gateway and agforge already expose all the evidence;
   this would only join it for easier later inspection.
6. **Richer direction only in response to observed need.** The director
   correctly noticed that genre details, setting, UI constraints, and concrete
   usage were absent. Those should become new workspace documents only when a
   real task needs them, preserving the minimal starting point validated here.

## Deus Ex Machina record

Omni Agent did Gitea setup, autolab gateway implementation, agforge generation, and director evaluation for the autolab and director agents — handoff candidate.

## Commit trail

- `4ed5b42` — remove the legacy director and report Step 0
- `58cf5af` — report Gitea repository creation
- `04f6041` — report direction workspace initialization
- `824e2b5` — advance agautolab to `87a9acc` and report gateway installation
- `8d1d560` — report the end-to-end director experiment

The external workspace note `understand_agents.md` and ignored local
configuration/evidence were updated as required but are not part of the
`pj-agdev` tracked commit set.
