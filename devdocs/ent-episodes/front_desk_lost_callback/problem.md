# A Front Desk ghtrends run reported failure after autolab had finished

2026-09-08, `#front` › `front-desk-20260908-161951`, mission G-15
(`pj-ghtrends` › `workplan-trend7`, `work-g-15`). The developer asked Front
to run the GitHub trend routine once more. autolab picked
heygen-com/hyperframes, wrote the summary, committed `cc0caa0` to
`autodev/ghtrends`, marked G-16 Done and resolved its run topic. Front then
told the developer the mission was "looping on the same bug" and stopped.

## What actually happened

1. autolab's first plan wrote `plan.md` and `start.flag` but no `task1.md`
   (the guide said task files were optional). The listener reported "wrote
   no task files; the mission has no sub-work" and, in the same reply,
   "mission G-15 is now In Progress; each task waits for a post in its own
   `workrun-…` topic". No topic existed to post in.
2. Front opened `work-g-15/workrun-task1-g-15` by hand. autolab answered
   that a hand-made topic is bound to nothing. Front asked for a re-plan;
   autolab wrote `task1.md`, and opened the same topic name, so the two
   merged. Front posted the start; autolab ran the task and reported.
3. The completion report (message 5244) and the ✔ resolve (5245) landed in
   the same second. Front's callback run was served after the rename.
   `rootchat_notes` drops resolved topics, so `remotes_for_home` returned no
   thread for `work-g-15`, and the run had only `workplan-trend7` beside its
   chatlog, ending in "opened work-g-15/workrun-task1-g-15; post there to
   start it". Front posted a second start (5248) into the bare name, which
   opened an empty twin topic. autolab answered the twin with "not bound",
   Front was called back again, and concluded the mission was looping.

## Fixes

- pyagag `9c9e5a9`: `remotes_for_home` keeps resolved remotes under their
  bare name; `write_threads` reads the ✔ name when the bare one is empty;
  `agentchat send` refuses the bare name of a resolved conversation.
- agautolab `4e87117`: the superdirector guide says a mission runs only
  through its task files and a single-task mission still gets `task1.md`;
  the listener's no-task-files line says nothing can run and asks for a
  re-plan.
- agfront `ecf27f9`: the character_talk guide says never to open a
  `workrun-` topic, to read a topic before posting, and that a ✔ topic is a
  result to report, not a place to post a second start.

## Close-out (Omni Agent, 2026-09-08)

did the close-out for agent autolab and agent Front — handoff candidate:
resolved `pj-ghtrends/workplan-trend7` and `front/front-desk-20260908-161951`,
folded the twin `work-g-15/workrun-task1-g-15` into its ✔ topic, and marked
G-15 Done with `python -m agautolab.mission_done G-15`. `work-g-15` is kept,
as every finished mission's channel is. No report was posted to the desk
conversation: a post there is a paid Front run, and the developer read the
outcome here instead.
