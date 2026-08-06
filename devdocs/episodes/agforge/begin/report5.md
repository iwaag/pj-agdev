# agforge begin — step 5 report: one command + wrap-up

Status: done. Episode complete.

## What was done

- Added `agforge/scripts/generate.sh` — the single entry point: a thin
  `set -eu` wrapper that cds to the agforge root and execs
  `uv run scripts/generate.py "$@"`, so `--ttl` passes through.
- Updated `agforge/README_DEV.md` with the exact invocation, output contract
  (stderr: local path; stdout final line: URL), the full required/optional
  `.local/.env` key list — including `AGFORGE_SWARMUI_MODEL`, which step 3
  discovered is mandatory — and a pointer to `.local/devenv.md` for actual
  values.
- Wrote the episode final report
  `devdocs/episodes/agforge/begin/report.md` (the "Easier Next Time"
  payload).

## Done criterion — verified

```
agforge/scripts/generate.sh --ttl 5 "a cozy reading nook with warm lamplight, watercolor"
→ stderr: local: .../agforge/.local/out/2026-08-06-fe4a7242.jpg
→ stdout: http://agstudio.local:9100/agforge/images/2026-08-06/82d1...jpg?...
```

curl of the printed URL: HTTP 200, 169552 bytes. One command, prompt in,
working download URL out.
