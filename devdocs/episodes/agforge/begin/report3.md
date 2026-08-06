# agforge begin — step 3 report: one image via SwarmUI API

Status: done.

## What was done

- Located SwarmUI: not on this Mac — it runs on the `agpc` GPU node,
  `http://agpc.local:7801`, version 0.9.7.4 (found by probing cluster hosts
  from the desired-state on port 7801). Recorded as `AGFORGE_SWARMUI_URL` in
  `agforge/.local/.env`.
- Wrote `agforge/scripts/generate.py` (Python, `uv run` inline script
  metadata with `requests` + `boto3` — boto3 already declared for step 4).
  Flow: `POST /API/GetNewSession` → `POST /API/GenerateText2Image` with
  `session_id`, `prompt`, `images: 1` → download the returned image ref to
  `agforge/.local/out/<date>-<shortid>.<ext>`, print the local path.

## Done criterion — verified

```
uv run scripts/generate.py "a serene mountain lake at sunrise, photorealistic"
→ agforge/.local/out/2026-08-06-faf4625e.jpg
```

The file is a real 512x512 JPEG and visually matches the prompt (mountain,
lake, sunrise). Not committed, per the hard rule.

## Discoveries (the plan's hint was right)

- The bare-minimum call fails: SwarmUI 0.9.7.4 returns "No model input
  given" when `model` is omitted, even though generation settings exist in
  its UI. Per the plan's guidance the minimum extra param went into `.local`
  config, not the repo: `AGFORGE_SWARMUI_MODEL=perfectdeliberate_XL.safetensors`
  (picked from `/API/ListModels` as the general-purpose SDXL option).
  Width/height/steps/cfgscale/seed do fall back to server defaults; the
  script supports optional `AGFORGE_SWARMUI_*` overrides for them.
- The response's image ref is a server-relative path (`View/local/raw/...`);
  plain GET on `{base}/{ref}` downloads it, no session required.
- Server-side output format is currently JPEG, not PNG — the script keeps
  the server's extension rather than assuming `.png`.
