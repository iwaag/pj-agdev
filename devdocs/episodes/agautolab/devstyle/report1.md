# Step 1 report — development style specifications

## Result

Added the mediator-facing development-style documents in the `agautolab`
submodule:

- `styles/README.md` defines explicit-choice precedence, first-session
  selection and NOTES recording, later-session reuse, and cheap mid-mission
  switching without restarting jobs.
- `styles/instant-ramen/STYLE.md` defines the plan-skipping, smoke-gate flow
  while preserving durable NOTES/evidence and mediator/implementer separation.
- `styles/slow-brew/STYLE.md` points to the existing reviewed-plan flow and
  requires gate effort to remain proportionate to mission risk.

Both style specifications use the required five sections and remain short
enough to be read as single-page operating notes.

## Verification

- Confirmed the three expected files exist under `agautolab/styles/`.
- Confirmed both `STYLE.md` files contain exactly the five requested section
  headings.
- Confirmed the Instant Ramen contract uses the existing `job.yaml` `gates`
  mechanism and introduces no Python or schema change.
- Recorded the style documents in agautolab commit `8993193`.
