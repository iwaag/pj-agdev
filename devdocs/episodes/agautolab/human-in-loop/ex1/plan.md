# Plan: human-in-loop ex1 — scope 3, autolab view in agdevworld

Goal: agdevworld gains an autolab visualization view next to the existing
desired-node and workspace views. The user picks a node, sees its jobs, clicks
a job to see its iteration list, and can ask for an iteration summary — which
is produced **on the autolab node by a one-shot summarizer agent**; raw
evidence files never leave the node. The prime agent presents the summary.

Static display only (scope 2 was closed): fetch on view entry and on click,
no push transport. Intervention controls remain out of scope. Experimental
environment: thin auth on purpose (all new routes unauthenticated), no
backward compatibility required.

## Context and findings (read before implementing)

**Decided boundary.** Iteration evidence is summarized where it lives. The
gateway's raw-evidence passthrough stays for the scope-1 monitor page, but
agdevworld and its assistant must not fetch or forward raw evidence — the only
iteration content that crosses into agdevworld is the summary text.

**Cluster reality (checked via `nctl drift`/`relations`, 2026-08-08).**
- The second autolab node is **`agautolab1`** (`agautolab1.local`,
  192.168.0.130, VM 109 on aghub). The braindump's "agautolab.local" is a
  naming slip — use `agautolab1` everywhere.
- autolab is **not modeled as a nintent service**, and node `agautolab1` has
  no placements (production state `waiting_for_manual_initial_access`). So the
  node picker cannot derive from desired state today: use a small config list
  now. Registering autolab as a nintent service so the picker derives from the
  cluster snapshot is the vision-consistent follow-up — record it as such, out
  of scope here.

**agdevworld architecture (all paths under `agdevworld/`).**
- One scene class, config-driven: `src/scenes/PanelGridScene.ts`; views are
  configs in `src/views.ts`, registered in `src/main.ts`, switched by
  `src/viewSwitcher.ts` (`VIEW_KEYS`, currently a 2-view toggle — going to 3
  views forces a nav decision: cycle or menu, implementer's choice).
- The browser fetches **same-origin only**; the gateway sends no CORS headers
  (by design). External services are reached through the assistant
  passthrough: `assistant/server.mjs` `handleForge()` proxies
  `/api/forge/<rest>` → `AGFORGE_URL`. Copy that template.
- Envelope discipline: hand-written narrowing keyed on the schema/kind field
  (`parseDriftEnvelope` etc. in `src/clusterState.ts`). Gateway responses
  carry `"kind": "autolab.monitor.v1"` and deliberately contain more than the
  scope-1 monitor page renders — no information needs to be added, only
  rendered.
- DOM precedent: `src/chatPanel.ts` / `src/detailPopup.ts` are absolutely
  positioned siblings of the canvas with injected `<style>`. Job grid as
  Phaser panels, text-heavy iteration list as a DOM popup matches the house
  style. Job status vocabulary (pending/running/converged/stuck/error,
  awaiting_approval) maps onto the existing status-style pattern
  (`CLUSTER_STATUS_STYLE`).
- Async UX precedent: the forge image flow (POST → poll every 3 s → render)
  is exactly the summary flow's shape.
- The assistant LLM is a small local model (ollama, glm-4.7-flash) with no
  tools; context is pre-summarized text, raw JSON is banned from context
  (`clusterState.ts` policy). The summarizer design below is what makes this
  a feature, not a limitation: the prime agent only ever sees finished prose.

**Why summaries don't go through `POST /mission`:** single-mission 409 (can't
summarize while a dev mission runs — the most interesting moment), it
overwrites `MISSION.md`/mediator state, and a full CHARTER session is ~$0.6 —
overkill. Hence a dedicated lightweight path.

Constraints (the true minimum):
1. Raw evidence files are not fetched by, forwarded to, or embedded in
   context for agdevworld/assistant — summaries only.
2. The summarizer writes only under its own output dir (e.g.
   `.local/jobs/<job>/summaries/`); it never touches `state.json`, evidence,
   `MISSION.md`, `NOTES.md`, or the job `.lock`.
3. Nothing under `.local/` committed; no real hostnames/tokens committed
   (existing agdevworld rule — defaults + env).
4. Keep the scope-1 monitor page working.

Everything else is implementer's discretion.

## Step 1 — on-node summarizer endpoint (gateway)

Add to `agautolab/agent/gateway.py`, unauthenticated:

- `POST /jobs/<job>/summarize/<iter>` — if a cached summary exists, return it;
  otherwise spawn a **one-shot summarizer** (`claude -p`, its own short
  system prompt — not CHARTER, not drive.sh) that reads
  `.local/jobs/<job>/evidence/<iter>/` and writes
  `.local/jobs/<job>/summaries/<iter>.md`, then return `202 {pending}`.
- `GET /jobs/<job>/summarize/<iter>` — `{status: pending|done|error,
  summary?}`. Include the summary in the job detail or list response too if
  convenient.

Hints:
- Reuse the `POST /mission` subprocess pattern (detached `Popen`,
  `start_new_session`, log + exit file, pid liveness) for the summarizer;
  a per-iteration lock file or "one summarizer at a time" guard is enough.
- Prompt suggestions: identify what changed (`diff.patch`), what gates
  ran/failed (`gates.json`), cost/turns (`adapter_result.json`), errors
  (`error.txt`); 5–10 sentences, human-facing, no file dumps. The summarizer
  may read files directly since it runs in the repo — constrain it to the
  one evidence dir in the prompt.
- Cache = the `.md` file; one paid call per iteration ever. Summaries of
  in-flight iterations are allowed to be wrong — they are cheap to
  regenerate (optional `?force=1`).
- Verify `claude` CLI exists on agautolab1 as well as agstudio (the
  `autolab_node` ansible role owns that machine's setup); if it is missing
  there, note it in the report rather than blocking — agstudio alone proves
  the design.
- Unauthenticated POST that spends money: acknowledged and accepted for this
  phase. A trivial guard (e.g. refuse if another summarizer is running) is
  enough.

Done when: `curl -X POST` then `GET` returns a real summary for a historical
iteration of an existing job (e.g. snake-web-b). `report1.md`.

## Step 2 — node registry + assistant passthrough

- Assistant env, e.g.
  `AUTOLAB_NODES="agstudio=http://host.docker.internal:8791,agautolab1=http://agautolab1.local:8791"`
  (defaults in code, real values via compose/env, per house rule).
- `GET /api/autolab/nodes` → configured node names (+ reachability if cheap).
- `/api/autolab/<node>/<rest>` → that node's gateway, GET plus the summarize
  POST. Clone `handleForge()`. **Do not proxy `/evidence/` paths** — that is
  constraint 1 enforced in one place.

Done when: `curl` through the assistant reaches both listed nodes' `/jobs`
(agautolab1 may legitimately be down — a clean error counts) and a summary
round-trips. `report2.md`.

## Step 3 — autolab view in agdevworld

- Third `PanelGridScene` config: node picker (from `/api/autolab/nodes`),
  jobs of the selected node as panels (status emoji/color, iteration/max,
  gates n/m, cost), mediator headline (mission first line, driver state,
  cumulative cost) somewhere visible.
- `VIEW_KEYS` + navigation for 3 views; add `switch_view` support and update
  the assistant `ROLE_PROMPT` so "show me autolab" works by voice/chat.
- `parseAutolabEnvelope` narrowing on `kind === "autolab.monitor.v1"`, same
  style as the drift/workspace parsers. Fetch on view entry + a manual
  refresh affordance; no polling loop needed for the grid.

Done when: the view renders real jobs from agstudio in the browser, view
switching works from UI and from a chat instruction. `report3.md`.

## Step 4 — iteration drill-down + summary presentation

- Click job → DOM popup (detailPopup pattern) listing `evidence/iter-NNNN`
  entries from `/jobs/<job>` with per-iteration cost/gates/exit already in
  the envelope.
- Select iteration → POST summarize, poll (forge pattern, ~3 s), render the
  summary in the popup and/or hand it to the prime agent: put the summary
  text into the selected-context digest (`getContext()` path) so the user
  can discuss it in chat, or have the agent present it as a chat bubble —
  implementer's choice on presentation, but the summary text itself must be
  shown unabridged (glm re-summarizing Claude's summary loses information).
- Show pending/error states honestly (scope-1 lesson: the in-between states
  are where real systems get rendered wrong).

Done when: from the browser — pick node, pick job, pick iteration, read its
summary, ask the prime agent a follow-up question about it. `report4.md`.

## Step 5 — live verification and wrap-up

Scope-1's strongest lesson: curl-green proves nothing about readability, and
stubs never exercise the in-between states. So: run one real (cost-approved)
mission while the autolab view is open — watch a job appear, iterate and
converge; summarize a freshly finished iteration; exercise the
mission-running + summarizer-running overlap; try agautolab1 if reachable.
Fix what falls out. Update `agautolab/AGENT_GUIDE.md`, `agautolab/README.md`,
and agdevworld docs with the new routes/view. `report5.md` plus a final
`report.md` for the episode, including the nintent-service follow-up
recommendation and a devstyle 3-line report.
