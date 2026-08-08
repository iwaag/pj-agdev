# Step 3 report — foreground execution contract

## Result

Replaced the operator guide's recommendation to background a long-running
`loop` with a plain requirement that both `run-once` and `loop` stay in the
foreground of the live mediator session because headless-session background
processes die with that session.

This removes the contradiction with the guide's existing lesson and adds no
process manager, persistence mechanism, or other tooling.

## Verification

- Searched `AGENT_GUIDE.md` for every occurrence of `background`,
  `foreground`, `run-once`, and `loop` around execution guidance.
- Confirmed no passage recommends background execution.
- Confirmed the edit is one paragraph and touches documentation only.
- Recorded the guide change in agautolab commit `866dc25`.
