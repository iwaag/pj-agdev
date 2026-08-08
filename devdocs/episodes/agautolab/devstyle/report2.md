# Step 2 report — mediator contract wiring

## Result

Updated `agautolab/agent/CHARTER.md` so every mediator session resolves its
development style after reading the mission and prior NOTES, records a new
choice or switch, and reads only the selected style folder before operating
autolab.

The charter introduction is now style-neutral. The Slow Brew plan/review
workflow and role details no longer appear as universal hard rules; they live
in the selected style specification. The common hard-rule list contains only
the three requested safety boundaries: no dangerous permission bypass,
secrets under `.local/`, and no background `run-once`/`loop` execution.

## Verification

- Read the revised start sequence top to bottom and confirmed first-session,
  resumed-session, explicit-choice, and style-switch paths are all stated.
- Confirmed the charter has no universal `PLAN.md`, `approve`, or `reject`
  requirement.
- Confirmed the common hard-rule list has exactly three entries.
- Recorded the charter change in agautolab commit `5e6159b`.
