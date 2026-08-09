# director — entrance guide

The capability card the director answers "what can you do / what does it
cost" from. Plain text, re-read from disk per request: edit it and the next
answer changes, no restart. Served raw at `GET /guide`.

## What this is

The creative-direction agent. It holds one project's taste — who the
characters are, how the world sounds, what is too much — and it will talk
about that with you. It is a colleague you ask, not a function you call.

Its persona is not in its code: it is the markdown in the direction
workspace (`brief.md`, `persona.md`, anything else `*.md`), read fresh on
every request. A human edits those files to change who the director is.

## What it can do today

- **Answer creative questions** — in character, with a position and a
  reason. "Would John say it this way?", "is this twist too heavy for this
  game?", "does this background fit the brief?"
- **Judge things for other agents** — pass/fail on a generated line, an
  image, a piece of copy. Ask for a judgment and the last line of the reply
  is `VERDICT: pass — reason` or `VERDICT: fail — reason`.
- **Compose generation requests** — turn the brief plus a manifest entry
  into a desire for agforge, in its own words.
- **Drive a delivery** — `reconcile.py` runs compose → agforge → look →
  decide, and the *director* decides after each attempt whether to deliver,
  try again, or stop. Nothing in the harness overrules it.
- **Read its workspace** — the direction files, the game repo, and the
  delivered assets. On the `claude` backend it has Read/Glob/Grep and can go
  look for itself.

## What it cannot do today

It cannot generate anything (that is agforge), run code, write files other
than its own run records, or deploy. It has no memory between requests
beyond what is written in the workspace files. It knows only the project
whose direction workspace it was pointed at.

## What it costs

Measured on agstudio, 2026-08-09, over the runs in
`<direction>/records/run-*.json`:

- **Default backend (`claude` / claude-sonnet-5): 0.085–0.26 USD and
  4–11 seconds** per answer through the window — the low end for a judgment
  on text you hand it, the high end when it goes reading workspace files for
  itself. Talking to the director is never free.
- **Looking at an image costs more: 0.13–0.18 USD and 10–30 seconds** per
  review.
- **A full `reconcile` delivery is 0.35–1.6 USD**, measured over three real
  runs of 3–10 director calls each, plus agforge's generation time (roughly
  40–60 s per attempt). How many attempts it takes is the director's
  decision, so the total is not knowable in advance; `--attempt-budget`
  bounds it.
- **Local backend (`DIRECTOR_BACKEND=ollama`): 0.00 USD, about 4 seconds** —
  it runs on a local model, which reports tokens and no price, so records
  carry a null cost rather than an invented zero. It is noticeably blunter,
  it has no tools and sees only the context blob, and it tends to stamp a
  VERDICT line on answers that were not judgments.
- **Image generation itself is agforge's cost, not the director's** — free
  on local SwarmUI today; see agforge's own guide.
- Hard wall-clock ceiling per answer: 240 s.

## How to talk to it

`POST /window {"text": "<whatever you want to say>"}` → the run record,
with the reply in it. `GET /guide` serves this file raw, `GET /healthz` is
the liveness probe. The CLI (`director.py "<text>" --direction …`) and
`reconcile.py` reach the same entrance in-process — three transports, one
place to express a desire. `direction` / `manifest` in the body name which
project you mean; they are addressing, not desire.

## Backend (Agent ≠ Model)

`DIRECTOR_BACKEND` = `claude` (default) | `ollama`, resolved from the
process environment first and then `pj-agdev/.local/.env`. Model within a
backend: `DIRECTOR_MODEL`. Also `DIRECTOR_OLLAMA_URL`, `DIRECTOR_CLAUDE_CMD`
(a glob is accepted, and resolves to the newest match). The strong backend
is the default here because creative judgment is the hard end of the task
spectrum. Every run records which backend served it.
