# Report — Step 2: update README_DEV.md

Status: done.

## What changed

- `agforge/README_DEV.md`
  - Pipeline section: added a `--width`/`--height` override example.
  - New "Generation parameters" section documenting the three-layer merge
    (`params/defaults.toml` → `.local/.env` → CLI flags, later wins),
    that `model` is the only required param and why it's deliberately
    absent from `defaults.toml`, and the fail-fast behavior.
  - `.local/.env` keys section: split into three tiers now — strictly
    required (URL/S3 keys), effectively required (`AGFORGE_SWARMUI_MODEL`,
    settable via `.env` or `--model`), and optional (width/height/steps/
    cfgscale/seed, sample values now in `params/defaults.toml`).
  - "Related docs": fixed the stale path
    `devdocs/episodes/agforge/begin/` → `devdocs/ent-episodes/swarmui-flow/`.

## Verification

- Read through the full updated file; cross-checked every documented flag
  and env key name against `agforge/scripts/generate.py` from Step 1 — all
  match (`ENV_KEYS`, `PARAM_NAMES`, the CLI flag names in `main()`).
- Confirmed `devdocs/ent-episodes/swarmui-flow/` is this episode's actual
  path (matches plan.md's own location).

## Notes for next steps

- Step 3 will add the MinIO-fallback agent instruction to this same file
  (or `AGENTS.md`), per plan.md's suggestion.
