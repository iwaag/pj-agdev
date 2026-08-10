# ex2 report — autolab creates a director-attached project, guidance-only

Episode executed by the Omni Agent on 2026-08-10. Both tests **passed on the
first attempt**; the guidance text alone (Step 2) carried the whole
braindump. Step reports: `report1.md`–`report6.md`.

## Outcomes

**Test 1 — create the project (`POST /mission`): success.**
The agent created gitea repos `autodev/yokai` and `autodev/yokai-direction`,
cloned them to `.local/projects/yokai/{main,direction}/`, planted
`GUIDE.md`, `concept.md` (Edo-era setting, yokai cast, ukiyo-e style) and
`.gitignore` itself, pushed the direction commit (91b1341), and updated
`.local/projects/projects.md` — which now lists `scifi` and `yokai`, as the
braindump expects. One session of the 12-session budget: session-0028,
52 turns, **$1.52**, 267 s. Records: gateway run 12
(`run-0012.log`/`.exit`), `.local/agent/done`, `session-0028.json`.

**Test 2 — consult the director (`POST /window`): success.**
The window identified the yokai project, launched a director session in
`.local/projects/yokai/direction/` (inner transcript
`2fdd0b53-...jsonl`, cwd verified), passed the request through as a
faithful reformulation, and relayed three protagonist proposals explicitly
attributed to the director. The proposals visibly reflect the planted
`concept.md` (ukiyo-e, hyakki-yagyō, tengu/rokurokubi). Record:
`window/run-0053.json` — **$0.18**, 68 s, 4 turns.

**Episode cost**: ~$1.70 across both tests, inside the $1–3 hint.

## Deviations

- Test 1 ran through `POST /mission`, not the braindump's `/window` — a
  developer decision made before the plan (missions are the sanctioned
  write path), not drift.
- Repo name: the agent chose `yokai` (name was left to its discretion; the
  pair and paths were what was judged).
- Preflight found the gateway token at 0644; tightened to 0600.
- No other deviations. No harness (gateway.py / session.sh) change was made
  at any point.

## How far guidance-only reached (the episode's product)

All the way. Zero evidence-driven corrections were needed — the Step 2
text (a "Projects" section in `AGENT_GUIDE.md`, a re-pointed "Project
directors" section in `agent/GUIDE.md`) was sufficient for both tests.
Notably, behaviors the guidance deliberately did NOT prescribe (Failure
Farming targets) emerged anyway:

- The agent updated `projects.md` unprompted — the text only states the
  index exists.
- It honored the role intent: did the repo/planting work itself, created no
  coding-agent job, and left `main/` as the auto-init README, reasoning
  that growing it is a later coding-agent job.
- It found `scifi` on its own as the reference implementation and rejected
  the older `gallery-*` layout as a template.
- It self-verified beyond the ask: ran the documented director-consultation
  flow before declaring done, and left a detailed handoff in
  `.local/agent/NOTES.md`.

Friction observed but not fatal: session 28 logged **11 permission
denials** (repo-inspection loops, the clone script, the commit+push
script, the nested `claude -p` probe). The agent re-shaped commands and
routed around every one — the known harness-instruction leak showed up as
turn inflation, not as the run-killing failure seen previously. Reported
per the plan rather than worked around in the harness.

## Next-element suggestions (from observed need only)

- **Denial friction**: the one real observed cost. If it recurs, the
  evidence points at session.sh allowlist review for the exact shapes that
  were denied (compound `TOKEN=$(cat ...)` pipelines, nested `claude -p`)
  — one widening per observed denial, per the Step 5 rule.
- **Inner director run cost is recorded nowhere** (ex1 lesson, confirmed
  again on run-0053): if spend accounting starts to matter, that is the
  next instrumentation gap.
- **`claude_bin` glob**: the mission agent noted `.local/agent/claude_bin`
  holds a literal glob it had to resolve by hand for its nested probe.
  session.sh resolves it correctly; only a note unless an in-agent consumer
  appears again.
- Nothing else — the untested prescriptions (order of operations, index
  update instruction, director-file wording) stayed unnecessary and should
  stay absent.

## Deus Ex Machina

Step 1 (scifi migration), Step 2 (guidance edits), and driving both tests
were Omni Agent work done for the autolab agent from outside. All three are
handoff candidates: the migration and guidance authorship could in
principle be mission work, and test-driving could move to a routine
entrance. Recorded as required; no action taken this episode.

## Scope

Committed on local agstudio only (agautolab `bdc7b42` + pj-agdev episode
files + submodule bump). Pushing to the agstudio gitea mirror and updating
agautolab1 via ansible are out of scope, as planned.
