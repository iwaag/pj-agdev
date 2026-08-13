# Warnings

Things a later reader should not mistake for design.

## The absolute chat-log path handed to `/window` is a workaround

`zulip_listener.absolute_dump_notice()` rewrites `topic_dump()`'s
front-relative chat-log path into an absolute one immediately before the
sentence is passed to the gateway `/window`.

**This is an ad-hoc measure against a local-model defect, not a design
decision.** The design intent is the opposite: the front agent's working
directory is fixed to `agent/front/`, everything it needs lives beneath that
directory, and paths are expressed relative to it. An absolute path pointing
into an ignored `.local/` tree is exactly what that intent is meant to avoid.

### What forced it

Measured on 2026-08-13 with the front `local` profile
(opencode + `ollama/qwen3.6:35b-a3b-coding-nvfp4`). The relative path was
delivered correctly and the working directory was correct — verified by the
model itself reporting `agent/front`, by `pwd` inside its own bash tool, and by
`agag.harness.run_harness()` setting both `subprocess(cwd=…)` and `PWD`. The
model still rewrote the string it was given before using it:

- prefixed the repository root: `agautolab/.local/topics/…`
- prefixed the home directory: `/Users/…/.local/topics/…`
- dropped path segments: `.pj-e2e-recheck-20260813/…`

Six runs with the relative form succeeded twice. The same prompt on the
`sonnet` profile (claude_code + `anthropic/claude-sonnet-5`) succeeded 2/2 in
two turns, using the relative path verbatim. With the absolute form the local
profile succeeded 2/2 in two turns and 2/2 through the real listener prompt in
four turns, opening the file on its first tool call.

So the relative form is correct and a capable model handles it. Only the local
model cannot.

### Why it is still ad-hoc

- It hides a model capability problem inside the transport, where the problem
  is not. Nothing in the listener is wrong.
- It bends a workspace-scoped interface to one model's failure mode. A reader
  of `window_prompt()` cannot tell that the design meant the opposite.
- It is not the only such patch: the prompt already carries a
  "do not ask for path clarification unless you first run `pwd`" clause
  (commit `785a0dd`) added for the same underlying reason, and `echo*` was
  added to the front permission list because the model kept writing
  `… || echo "not found"` while flailing for the file.

### What would make it unnecessary

Any of these; none was chosen here.

- Move the front role to a model that follows a given path (`sonnet` does).
- Give the front a tool that returns the chat log content, so no path is
  exchanged at all.
- Accept the relative form and let the front fail visibly, treating the
  failures as evidence rather than patching around them.

Remove `absolute_dump_notice()` when the front no longer runs on a model that
corrupts the path. It has no other reason to exist.

## Sample sizes here are small

Every ratio above comes from single-digit run counts against a
non-deterministic local model. They are enough to show the failure is real and
reproducible, not enough to quote as rates.
