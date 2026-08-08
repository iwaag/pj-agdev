# devstyle — selectable development styles for autolab

Plan for the desire in [braindump.txt](braindump.txt), informed by the
asset_reconcile ex1 analysis
(`devdocs/episodes/asset_reconcile/ex1/problem2.md`). AI-generated, reviewed
with the user.

## Goal

Give the autolab mediator two named development styles and let it choose one
per mission:

- **Instant Ramen Style** — no plan phase, minimal gates, small goals set on
  the fly, sprint to the mission. Some gaps/bugs surviving to the final human
  check are acceptable.
- **Slow Brew Style** — the current formal flow: plan → review →
  approve/reject → implement, coding-agent-authored gates, independent audit.

Explicit style instructions in the mission always win. Otherwise the mediator
chooses by its own judgment (Tool Giving: give options and hints, not a
decision procedure; a wrong choice is an ENT asset, not a failure to prevent).

## Design decisions (from the braindump discussion)

1. Selection is the agent's call. Do NOT hard-code default-style rules or
   escalation criteria. Provide hints (blast radius, reversibility, whether
   shared contracts/infra are touched) inside the style specs and let the
   mediator weigh them.
2. Style specs are one page each, max. Five sections: *when it fits / what to
   skip / what never to skip / gate scale / reporting*. If a spec grows past a
   page, it is over-engineering the anti-over-engineering fix.
3. Style-specific text lives in per-style folders read only after selection;
   the common contract (charter, AGENT_GUIDE) stays style-neutral and small.
4. Every mission records which style was chosen, why, and — at report time —
   whether it was the right call. This is the ENT feedback loop that will let
   us make selection more deterministic later *if evidence demands it*.
5. Even Instant Ramen keeps durable traces: NOTES.md discipline and evidence
   dirs stay mandatory. What it skips is the plan/review round trip and heavy
   gates, never the on-disk record.
6. Background execution of `run-once`/`loop` from headless mediator sessions
   is simply banned (braindump decision; problem2.md root causes 1–2). This is
   style-independent and fixed in the same episode because the guide currently
   contradicts itself.

## Steps

### 1. Write the two style specs

New files in the `agautolab` submodule:

```
agautolab/styles/README.md            # how selection works (~10 lines)
agautolab/styles/instant-ramen/STYLE.md
agautolab/styles/slow-brew/STYLE.md
```

`styles/README.md`: mission text may name a style; otherwise pick one after
reading the mission, write `STYLE: <name> — <one-line reason>` into
`.local/agent/NOTES.md` in the first session, then read only that style's
folder. Switching mid-mission is allowed and cheap: record the switch and the
reason in NOTES and continue the same job(s) — never restart the mission just
to change style.

`instant-ramen/STYLE.md` — key content beyond the five sections:
- Skip the plan phase mechanically: write `gates` directly in `job.yaml`
  (the existing contract — gates present ⇒ implement phase immediately,
  see `AGENT_GUIDE.md` and `run_once.py`). No autolab code change needed.
- Gate scale: a handful of smoke checks (build succeeds, endpoint answers,
  file exists), not a test framework. Reuse existing commands; never author a
  custom test harness.
- The charter rule "the mediator writes neither implementation nor tests" is
  relaxed for gates only: the mediator may write minimal smoke-gate commands
  itself, since there is no plan round trip to source them from. It still
  never writes implementation.
- Reporting: small goal declared per iteration in NOTES, short final report.

`slow-brew/STYLE.md` — mostly a pointer to the current flow (plan review
craft section of AGENT_GUIDE), plus the one lesson from ex1 worth keeping at
this layer: scale gates to risk; reject acceptance frameworks materially
larger than the product unless the mission itself demands them.

### 2. Wire selection into the mediator contract

Edit `agautolab/agent/CHARTER.md`:
- Add one step to the session-start list: after reading MISSION.md, resolve
  the style (from mission text, or NOTES if already chosen, or choose now)
  and read `styles/<chosen>/STYLE.md`.
- Move style-dependent phrasing (the plan-review flow description) out of the
  hard-rules section or mark it Slow-Brew-specific, so the charter stays
  style-neutral. Keep hard rules minimal: secrets under `.local/`, no
  `--dangerously-skip-permissions`, no background `run-once`/`loop`. Nothing
  else is added — this is an experimental environment; give the mediator and
  coding agents maximum discretion.

### 3. Kill the background contradiction

Edit `agautolab/AGENT_GUIDE.md`: delete/replace the passage recommending
launching `loop` in the background; state plainly that `run-once`/`loop` run
in the foreground of the live session and die with it. One paragraph, no new
tooling.

### 4. ENT recording

- Style spec "reporting" sections require the final mission report (and the
  episode's own report.md) to answer three lines: style chosen, why, was it
  right in hindsight.
- Nothing machine-enforced for now; if reports keep omitting it, that is the
  next ENT episode.

### 5. Acceptance

- Dry read-through: a fresh mediator session against a toy mission with no
  style named picks a style, logs `STYLE:` with a reason, and reads only that
  folder (verifiable from the session transcript).
- Real run: re-run a small mission of the ex1 class (three-image gallery
  scale) and compare sessions/cost against problem2.md's baseline
  (6 sessions / $9.81). Expect Instant Ramen to land in 1–2 sessions. A wrong
  style choice does not fail acceptance — an unrecorded one does.
- `uv run pytest -q` in agautolab still passes (steps 1–3 should touch no
  Python; if the implementer does touch code, tests gate it).

## Hints for the implementer

- Backward compatibility is explicitly NOT required (pre-production,
  destructive phase). Rewrite charter/guide text freely.
- The plan-skip mechanism already exists: `job.yaml` with `gates` ⇒ implement
  phase directly; `state.phase` is sticky after the first iteration
  (`run_once.py:455-460`). Prefer using this over adding any style flag to
  autolab code. A `style:` key in job.yaml is *not* needed — style is a
  mediator-layer concept, invisible to the loop.
- Styles do not fix problem2.md causes 1/2/6 (session lifetime, guide
  contradiction, stale NOTES). Step 3 handles 1–2; machine-generated
  checkpoints (corrective direction #3 in problem2.md) are out of scope here
  — a separate episode.
- Keep everything in English per devpolicy.
- Total expected diff: ~4 new markdown files, edits to 2 existing markdown
  files, zero Python.
