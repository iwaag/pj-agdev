# ex3 step 1 — the convert/resize tool is offered to the agent

Work item 1 of [plan.md](plan.md): the jpeg→png convert → verify →
re-upload sequence, observed as the same mechanical chain in every ex2
format run, is now a sanctioned one-line tool the agent can call. The
decision whether to post-process stays with the agent; only the
mechanics moved into code.

## What changed (agforge repo)

- **New `service/transform.py`** (replaces the parked
  `service/candidate_tools.py`, now deleted):

      uv run service/transform.py [--format png|jpeg] [--width W --height H] <file>

  Resizes and/or converts with Pillow (LANCZOS; single unset dimension
  derived from the actual aspect ratio; RGBA→RGB on jpeg), re-uploads
  via the existing `generate.upload_and_presign`, and prints the fresh
  presigned URL as the LAST line of stdout — same output shape as
  `generate.sh`, so the agent already knows how to read it. The
  produced local path goes to stderr as `local: <path>`.
- **Flag-less form = bare re-upload.** `uv run service/transform.py
  <file>` uploads as-is, keeping `upload_and_presign` reachable in one
  line for post-processing the agent invents itself (plan requirement:
  no hand-rolled S3).
- **Charter** (`service/charter.md`): new "The post-processing tool"
  section describing the command and explicitly stating the decision
  stays with the agent; the fragile inline `python -c` re-upload
  snippet is deleted; the data-shaping rule now says the delivered URL
  must be the fresh upload printed by the tool.
- **Permissions: no changes needed.** Both the committed
  `opencode.json` (`"uv run *": "allow"`) and the claude
  `--allowedTools` list (`Bash(uv run:*)`) already cover the new
  command — verified, not assumed.
- **README_DEV.md**: the "parked candidate tools" paragraph replaced
  with the offered-tool description.

## Tests

Kept the ex2 pattern — deterministic shell only, no live services:

- New `tests/test_transform.py` pins the local Pillow mechanics
  (passthrough, jpeg→png, resize+convert incl. the 300×300 case,
  aspect-ratio derivation, alpha-drop on jpeg). Upload/presign needs
  live MinIO and stays out of unit tests.
- Charter composition test now asserts `service/transform.py` is
  mentioned and `python -c` is gone.

`uv run pytest -q` → **19 passed** (was 14). CLI smoke: `--help` works;
a local 320×320 JPEG transforms to a 300×300 PNG via the module path.

## Notes for later steps

- Live behavior of the agent *with* the offered tool (used / ignored /
  misused) is deliberately not exercised here — that is step 4's live
  validation with the 300×300 paper-crane case.
