# asset_reconcile — problem log

Date: 2026-08-07. This log consolidates every problem observed from the first
attempt through the current Step 3 stop. It includes recovered operational
friction and implementation mistakes, not only the final blocker.

## 1. Claude Code could not mutate the autolab VM workspace

- **Where:** First attempt, before Step 1 (`failure1.md`).
- **Symptom:** The Claude Code auto-mode permission classifier denied the SSH
  and SCP operations needed to reset `state.json` and archive `NOTES.md`.
  `autolab run-once` therefore continued to see the old terminal `converged`
  state and could not start the new job.
- **Cause:** The previously recommended project-scoped SSH/SCP allowlist had
  not been installed. Editing Claude's own permission settings would have
  been an improper self-grant, so that route was correctly abandoned.
- **Impact:** The first attempt stopped before Step 1 and produced no game
  commit.
- **Status:** Resolved for the restarted episode by running under Codex with
  the user's explicit instruction to execute the VM-based plan. The uploaded
  `job.yaml` was reused intact.

## 2. Interactive SSH did not inherit the systemd Node.js PATH

- **Where:** Step 1 independent verification.
- **Symptom:** `node --test` returned `node: command not found`, including
  through a login-shell attempt, even though the autolab gate had passed.
- **Cause:** The installed systemd user unit explicitly adds
  `$HOME/.local/node/bin`; the SSH command environment did not.
- **Impact:** Only the redundant manual verification command failed. The
  autolab run and its recorded gate were unaffected.
- **Status:** Resolved by inspecting the installed unit and invoking the
  independent test with that user-local Node directory explicitly in PATH.

## 3. A fresh local clone could not authenticate to private Gitea

- **Where:** Step 1 fresh-clone acceptance.
- **Symptom:** Clone attempts through both `localhost:3000` and
  `agstudio.local:3000` failed with `could not read Username` in the
  non-interactive environment.
- **Cause:** The private `autodev` organization requires the agent credential;
  the macOS Git credential helper had no applicable stored credential for
  these URLs.
- **Impact:** Delayed the independent clean-checkout verification; the VM
  push had already succeeded.
- **Status:** Resolved by reading the ignored agent token file without
  printing it and supplying a one-command HTTP authorization header. The
  resulting clone retains a clean, credential-free origin URL.

## 4. Step 2 review interface had the wrong pre-delivery ordering

- **Where:** Initial Step 2 director runner (`a6ef91e`).
- **Symptom:** `review` derived and required the final game asset path from
  the manifest. Step 3, however, must review a candidate before copying it
  into the game repository and changing the manifest to `delivered`.
- **Cause:** The Step 2 interface modeled post-delivery review while the plan
  specifies review-before-delivery.
- **Impact:** The initial interface could not drive Step 3 without either
  prematurely placing an unaccepted asset in the game checkout or being
  changed.
- **Status:** Resolved in `c48ac35`. `review` now accepts an explicit staged
  candidate path, and `reconcile.py` stages candidates under the direction
  workspace. Its default remains the manifest-declared final path for later
  re-review. The LLM still receives only the brief, manifest entry, and one
  explicit image.

## 5. Step 2 accidentally included Python bytecode in its first commit

- **Where:** Step 2 commit preparation.
- **Symptom:** Running unit tests and `py_compile` created `director/__pycache__`,
  and the first form of the Step 2 commit included two `.pyc` files.
- **Cause:** The new directory did not yet have a Python cache ignore rule,
  and the directory-wide `git add director` staged generated files.
- **Impact:** No pushed history or runtime behavior was affected, but the
  initial local commit was polluted by generated artifacts.
- **Status:** Resolved immediately: the exact bytecode files were removed,
  `director/.gitignore` was added for `__pycache__/` and `*.py[cod]`, and the
  Step 2 commit was amended before subsequent work. Current commit `a6ef91e`
  contains no bytecode.

## 6. Step 3 glue initially decoded the wrong agforge response schema

- **Where:** First live Step 3 invocation.
- **Symptom:** The POST succeeded, but the client reported
  `agforge create response has no request id` and exited immediately.
- **Cause:** The new glue expected generic fields `id`, `queued`/`running`,
  and `error`; the documented existing API uses `request_id`, `working`, and
  `detail`.
- **Impact:** One in-memory generation job was accepted without its ID being
  retained by the caller. It made no game or manifest mutation and required
  no durable cleanup, but consumed an unnecessary generation.
- **Status:** Resolved in `c48ac35` by matching the published API contract and
  adding a unit test that covers create, working, and done responses.

## 7. agforge returned JPEG for an explicit PNG desire twice

- **Where:** Step 3 mechanical delivery check.
- **Symptom:** The director's desire explicitly requested a 1024×1024 PNG.
  Both bounded agforge requests completed, but both downloaded artifacts were
  JPEG/JFIF. The retained second candidate measured exactly 1024×1024, so
  dimension handling worked while format handling did not.
- **Request IDs:** `82ce1e9a62db4a5a8aea034f47f0be42` and
  `9923477a53ae43439c8c5c24ee40735d`.
- **Cause:** agforge's current interpreter/generator path does not turn the
  desire's output-format requirement into enforced output bytes; the current
  SwarmUI configuration emits JPEG.
- **Impact:** This is the active blocker. Renaming the bytes would fail the
  game repository's PNG signature/IHDR gate. Local transcoding would hide the
  producer contract failure and violate the episode's copy-only boundary.
  Subjective director review, delivery, Steps 4–5, and their reports therefore
  have not run.
- **Status:** Resolved on 2026-08-08. After the agforge fix, request
  `16c1cd905a8a4ace9a7349ffecaa5a15` returned a valid 1024×1024 PNG on the
  first attempt. The unchanged mechanical check accepted it, the director
  provisionally approved it, and game commit `6ff9d87` delivered the exact
  bytes without conversion.

## 8. Visual verification used the wrong serving location

- **Where:** Initial Step 4 verification and final report.
- **Symptom:** The report said the delivered background had been verified in
  a browser, but `http://agautolab1.local:8080` still showed no background.
- **Cause:** The screenshot was taken from a temporary server in the agstudio
  delivery clone. The asset commit had been pushed to Gitea, but the existing
  `agautolab1` job target serving port 8080 had not pulled it and remained at
  `61c65d7`.
- **Impact:** The image and game gate were valid, but the claimed end-to-end
  live deployment verification was false until the target was updated.
- **Status:** Resolved on 2026-08-08. After explicit SSH authorization, the
  clean VM target was fast-forwarded to `6ff9d87`. VM tests passed 12/12, the
  background returned HTTP 200 with the committed SHA-256, the manifest
  returned `delivered`, and a new browser screenshot through an SSH local
  forward verified the actual port 8080. Reports 3–5 and the final report were
  corrected. Future visual acceptance must probe the named deployment URL and
  record its served revision/artifact before claiming completion.
