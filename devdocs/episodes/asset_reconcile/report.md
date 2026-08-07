# asset_reconcile — final report

Date: 2026-08-08. Outcome: **completed end to end**.

A coding agent declared and implemented the technical background contract. A
separately placed one-shot director composed the creative desire, requested an
asset from agforge, reviewed it leniently, and delivered it without conversion
into the game repository. The delivered game passed all gates and rendered the
background readably.

## What ran

1. The existing `agautolab1` Othello job added optional background loading,
   the 1024×1024 PNG manifest request, and the delivered-asset gate. Its
   result was pushed as game commit `61c65d7`.
2. pj-agdev gained the small `claude-sonnet-5` one-question director and an
   ignored direction workspace containing only the one-line brief and review
   area.
3. The bounded reconcile glue composed a desire, used the existing agforge
   presigned-URL API, mechanically checked the candidate, obtained a
   provisional creative acceptance, copied the exact bytes, and changed only
   the request status to `delivered`.
4. The delivered game commit `6ff9d87` was pushed to Gitea `main` and pulled
   into the existing `agautolab1` job target. Bare `node --test` passed 12/12
   on the VM, including the delivered branch. A browser screenshot from the
   VM's actual port 8080 confirmed a visible background and readable board.

The first Step 3 attempt on 2026-08-07 correctly stopped when two requests
returned JPEG despite the explicit PNG desire. After agforge was fixed, the
same unchanged contract succeeded on the first new request,
`16c1cd905a8a4ace9a7349ffecaa5a15`. No resize, transcode, extension rename,
or relaxed check was used.

## Cost and timing

- Step 1 coding agent: USD 0.4811157, 17 turns, 105.565 seconds.
- Step 2 live director compose: USD 0.0619052, 1 turn, 3.045 seconds.
- Recorded known LLM total: USD 0.5430209.
- The successful Step 3 compose/review envelope was not persisted, so its
  exact LLM cost and timing are excluded rather than estimated.
- agforge generation cost was not exposed by its API and is therefore not
  reported.

## Contract and context isolation

The manifest boundary worked as intended. The coding side chose the path,
format, dimensions, and initial status. The director preserved those fields,
supplied the creative desire, and changed only `status` after acceptance. The
game gate independently enforced that delivered meant present, referenced,
decodable, and exactly 1024×1024 PNG.

Placement-based isolation also held:

- the coding agent ran only inside the game checkout and had no direction
  workspace;
- the director ran with the direction workspace as its working directory;
- compose received only the selected manifest entry and brief;
- review received only the brief, selected entry, and staged candidate;
- the delivered game commit contains no brief, candidate staging, or review
  material.

There is no evidence that either agent attempted to read across the boundary.
This remains context hygiene, not a hostile security sandbox.

## Asset quality

The accepted asset is a coherent, warm candlelit medieval stone room with
wooden furniture and a central gaming table. It matches the deliberately
minimal brief well enough for provisional use. Behind the translucent UI
panel it adds atmosphere without compromising the board, score, move hints,
or New game control.

The original JPEG-for-PNG failure was a useful producer-contract finding. The
fixed agforge path now returns valid 1024×1024 PNG bytes for the same style of
desire, and the delivery flow proved that rather than masking it downstream.

The first visual-verification report exposed a separate deployment mistake:
the screenshot had been taken from a temporary agstudio server while the VM
still served the pre-delivery commit. HTTP probing found the live background
404, the clean VM target was fast-forwarded, and verification was repeated
against its actual port 8080. Future acceptance checks must name and probe the
intended deployment endpoint rather than treating an equivalent local checkout
as live evidence.

## Follow-ups

- Persist the director's structured compose/review result so every successful
  run has complete cost, timing, desire, and verdict evidence.
- Evolve the one-shot runner into a small persistent director service only
  when repeated use justifies the additional lifecycle and authorization
  surface.
- Add further manifest asset kinds one at a time, retaining producer-side
  format/dimension responsibility and mechanical consumer gates.
- Wire director reconciliation into the autolab loop after the manual
  contract boundary has proved stable across more than one asset kind.
- Add explicit human final-review tooling for provisional assets; the current
  screenshot check is sufficient for this experiment but is not a durable
  approval workflow.

Step evidence is in `report1.md` through `report5.md`; operational friction and
recovered failures remain consolidated in `problem.md`.
