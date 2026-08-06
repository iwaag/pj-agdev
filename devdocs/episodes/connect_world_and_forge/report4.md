# Report — Step 4: end-to-end verification

## How it was verified

Playwright (ad-hoc, not a project dependency) drove a real Chromium against
the composed stack at `http://localhost:8090`, typing into the chat panel
exactly as a user would. Three scenarios:

1. **Success** — "draw a castle at sunset": the assistant replied with a
   confirming sentence, a "generating image…" bubble appeared, and ~30 s
   later a 512×512 image rendered in the panel (`img.naturalWidth > 0`
   checked, screenshot inspected). ✅
2. **Double quotes** — "draw a robot holding a sign that says \"HELLO
   WORLD\" please": action survived extraction (the model obeys the
   no-quotes-in-desire instruction) and the image rendered. ✅
3. **Forced failure** — SwarmUI URL temporarily pointed at a dead port
   (`.local/.env` edited and restored): the bubble turned into a readable
   error: "image generation failed — requests.exceptions.ConnectionError:
   HTTPConnectionPool(…): Max retries exceeded…". ✅

Non-blocking chat was proven directly: while the success image was
generating, the send button was enabled and a second chat round-trip
("hello, are you still there?" → reply) completed before the image arrived. ✅

## Presigned-URL host reality

The URL host is whatever `AGFORGE_S3_ENDPOINT` says. On this machine the
browser resolves it fine, so images load directly and no image-byte proxying
is needed. Recorded in `.local/devenv.md`, including the caveat for browsers
on machines that cannot resolve that hostname (the cheap fix remains
proxying through the Step-2 passthrough).

## Fix that came out of verification

The failure bubble initially showed the *middle* of a Python traceback
(first 200 chars of an 800-char stderr tail) — technically "the stderr
tail", practically unreadable. `service/request_service.py` now uses the
last non-empty stderr line as `detail` (the sys.exit message or final
exception line), which is what a UI actually wants. Re-verified in the
browser.

## What held / what surprised

- The whole chain — chat → action JSON → passthrough → request service →
  generate.sh → SwarmUI → MinIO → presigned URL → `<img>` — worked on the
  first full browser run; the per-step acceptance checks had already caught
  everything that mattered.
- glm-4.7-flash was more reliable at emitting clean action JSON than the
  plan feared; the latest-user-message fallback never triggered.
- Follow-ups recorded in `devdocs/todo_done.md`: agent access point behind
  the agforge seam, artifact persistence, voice-driven flow.
