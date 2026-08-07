# asset_reconcile — Step 2 report

Date: 2026-08-07. Outcome: **direction workspace and one-question director
runner are operational**.

## Direction workspace

Created an ignored local workspace outside the game checkout with exactly:

```text
othello-direction/
  brief.md       # A medieval, old-fashioned atmosphere Othello game.
  reviews/       # initially empty
```

It lives under the pj-agdev local-only area, while the game is a separate
Gitea clone. The coding VM has neither this folder nor its contents.

## Director runner

Added `director/director.py`, a standard-library one-shot runner pinned to
`claude-sonnet-5`. It supports two independent questions:

- `compose`: reads `brief.md` and one explicitly selected manifest entry,
  then returns a validated desire string that must retain the exact format
  and dimensions;
- `review`: derives the exact delivered asset path from the manifest, permits
  only Claude Code's Read tool, and returns a structured boolean verdict plus
  one-sentence reason.

Claude's working directory is always the direction workspace. Game context is
passed only from the explicit manifest entry; only the manifest-declared asset
path is exposed for image review. This is the intended placement-based context
hygiene rather than a claimed security sandbox.

`director/README.md` documents invocation. Four unit tests cover technical
field retention, malformed desire rejection, manifest-bound review paths, and
the direction-workspace working directory.

## Live compose acceptance

The real one-shot returned:

> Generate a 1024x1024 PNG background image for an Othello board game,
> evoking a medieval, old-fashioned tavern-hall atmosphere with aged wood,
> stone, and candlelit warmth.

This preserves the coding-owned 1024×1024 PNG contract and makes a sensible
creative interpretation of the one-line brief.

- Duration: 3.045 seconds
- Turns: 1
- Reported cost: USD 0.0619052
- Unit tests: 4 passed

