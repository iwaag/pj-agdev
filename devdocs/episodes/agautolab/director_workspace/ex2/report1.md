# ex2 Step 1 report — placement rule and scifi migration

Executed by the Omni Agent on 2026-08-10.

## What was done

Applied the redesigned placement rule (one project = one folder; main and
direction are siblings) to the existing SF project, now named `scifi`.
Everything lives under git-ignored `.local/`, so this was a plain `mv` with
no git surgery:

- `mkdir -p .local/projects/scifi`, then
  `mv .local/direction/scifi-direction .local/projects/scifi/direction`.
- Moved `projects.md` to `.local/projects/projects.md` and reworded its line
  to name the project `scifi` (same one-line summary; header now points at
  `.local/projects/` instead of `.local/direction/`).
- Removed the now-empty `.local/direction/`.

## Verification

- `.local/projects/scifi/direction/` contains `GUIDE.md`, `concept.md`,
  `.gitignore`, `.local`, and an intact `.git`.
- The moved clone is healthy: `git status` is clean, HEAD at `1edb154`
  ("Initialize minimal science-fiction direction workspace").
- The gitea remote is untouched:
  `http://agstudio.local:3000/autodev/scifi-direction.git` — already matches
  the `<name>-direction` convention.

## Deliberately not done (per plan)

- `autodev/scifi` (a main repo) was not created; scifi predates the rule.
- No `.local/projects/scifi/main/` clone exists for the same reason.
