# Step 6 — Add idempotent `init_project.py`

Status: **done**

## Result

The new root-level `init_project.py <project>` command performs the requested
four-part initialization and prints `success` only after all parts complete:

1. find or create the Plane project;
2. find or create `<project>` and `<project>-direction` in Gitea's `autodev`
   organization;
3. clone them to `.local/projects/<project>/main` and `direction`;
4. safely return success on later invocations without duplicating resources.

The implementation uses the ignored shared Plane credentials file and the
ignored autolab Gitea token. Clone authentication uses the existing askpass
script and an environment-only token; repository URLs and process output do
not embed it.

Plane identifiers use deterministic word initials and numeric parts, limited
to 12 characters. Existing identifiers are collected before creation and
collisions receive numeric suffixes. A same-name project is recognized by a
case/separator-normalized comparison, so `whack-a-mole` reuses a Plane display
name such as `Whack A Mole`.

## Live finding and fix

The first live create attempt returned Plane HTTP 400 because this Plane
version rejects hyphens in a project display name. It failed at the first
step, before any Gitea repository or clone was created. The implementation now
converts a repository name such as `phase1-smoke-20260813` to the deterministic
Plane display name `Phase1 Smoke 20260813`, while preserving kebab-case for
Gitea and local paths.

## Verification

- `uv run pytest -q` — 13 passed at completion.
- `uv run init_project.py --help`: concise project-name contract displayed.
- Ran `uv run init_project.py phase1-smoke-20260813` twice; both returned
  `success`.
- Plane contains `Phase1 Smoke 20260813` with identifier `PS20260813`.
- Gitea contains both `autodev/phase1-smoke-20260813` and its `-direction`
  repository.
- Both ignored local destinations contain Git clones. Empty-repository clone
  warnings were expected because no seed files are added in Phase 1.
- `git check-ignore` confirmed the clone tree is excluded; `git diff --check`
  passed.

Implementation commit: `5a1a934` (`Add idempotent autolab project
initialization`).
