# Report — Step 1: parameter layering in generate.py

Status: done.

## What changed

- `agforge/params/defaults.toml` (new) — versioned sample defaults for the
  optional params only (`width`, `height`, `steps`, `cfgscale`, `seed`).
  Comment explains `model` is deliberately absent: it's environment-specific
  and required, so it lives in `.local/.env` or a `--model` flag instead.
- `agforge/scripts/generate.py`
  - Replaced the old `ENV_PARAMS` env-only merge with `resolve_params()`,
    merging three layers (later wins): `load_defaults()` (reads
    `params/defaults.toml` via `tomllib`) → `.local/.env` (`ENV_KEYS`,
    same env var names as before) → CLI flags.
  - Added `--model`, `--width`, `--height`, `--steps`, `--cfgscale`,
    `--seed` flags to `argparse`, all optional (default `None`, so absence
    doesn't override a lower layer).
  - `resolve_params()` fails fast with `sys.exit` if `model` is unresolved
    from any layer, naming all three places it could have come from and
    pointing at `POST /API/ListModels` for valid values (per problem.md #1
    / plan.md's hint).
  - `generate_image()` now takes the merged `params` dict directly and
    merges it into the request payload (`payload.update(params)`) instead
    of reading `env` itself.

## Verification

- `python3 -m ast` parse check passed (syntax only, no network).
- Fail-fast path: with `.local/.env` stripped of `AGFORGE_SWARMUI_MODEL`
  and `params/defaults.toml` temporarily removed, `generate.sh` exited
  with the intended message: *"model is required but not set anywhere:
  not in params/defaults.toml, not as AGFORGE_SWARMUI_MODEL in
  .local/.env, and no --model flag. List valid names with POST
  /API/ListModels against your SwarmUI instance."*
- Clean run (defaults.toml present, `.env` has `AGFORGE_SWARMUI_MODEL` but
  no width/height, no CLI flags): succeeded, produced a 512×512 JPEG
  (confirmed via `sips`) — matches `defaults.toml`'s `width = 512` /
  `height = 512`.
- Override run (`--width 256 --height 256`, everything else unchanged):
  succeeded, produced a 256×256 JPEG — confirms the CLI layer reaches
  SwarmUI and wins over the defaults file.
- Test output images were local-only (`.local/out/`, git-ignored) and have
  been deleted after verification; no generated images or credentials are
  part of this commit.

## Notes for next steps

- Step 2 (README_DEV.md) needs to document the three-layer merge, the
  `params/defaults.toml` location, and adjust the required/optional key
  split (`AGFORGE_SWARMUI_MODEL` is still effectively required, but now
  resolvable from `--model` too, not just `.env`).
- Full acceptance-criteria verification (Goal #1/#2 in plan.md, from a
  fully clean checkout) is deferred to Step 5 per the plan; the checks
  above were scoped to confirming Step 1's own change works.
