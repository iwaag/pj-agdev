# Step 2 report — conversational project-profile editing

## Outcome

The front role now receives `Write` and `Edit` capabilities in both supported
permission surfaces: the shared Claude Code allowed-tools list and
`agent/opencode-front.json`. Its capability card explains the project settings
location, the selectable `coding` and `director` roles, the root source of valid
profile names, and that a settings request should be handled directly rather
than converted into a mission.

The card also advertises the new read-only `GET /projects` route.

## Verification

- `uv run pytest -q`: 97 passed after adding capability-contract coverage.
- A live `POST /window` asked the default local/Ollama front agent to set
  project `yokai`'s `coding` profile to `sonnet`.
- The front agent completed the edit itself in five turns, reported zero USD,
  and did not start a mission.
- The ignored project file changed from `coding = "local"` to
  `coding = "sonnet"` while leaving `director = "local"` unchanged.
- A fresh `GET /projects` returned the new `sonnet` value with source
  `project`; `GET /status` confirmed no mission driver was running.

No project settings file was edited by the Omni Agent, so no Deus Ex Machina
handoff note is required.
