# Plan: External task manager (Plane) for agautolab

Braindump: [braindump.md](braindump.md)
Provenance: AI-generated, reviewed with the user.

## Goal

Self-host Plane CE as the practical task board for agautolab. The prime agent
(agdevworld assistant) files tasks from user complaints; the user dispatches
them manually from an agdevworld task list; autolab agents report progress back
to Plane. The user views Plane read-only. agdevworld stays the immersive view,
Plane the management board.

## Design decisions (from the braindump discussion)

1. **Manual push first.** Dispatch is a human click in agdevworld. Pull-based or
   scheduled auto-start is a future episode; the manual phase exists to farm
   evidence about when dispatch decisions are actually right.
2. **The dispatch button is not an entrance.** It only dispatches an existing
   Plane issue — no free-text input. New desire still enters through the prime
   agent conversation (Single Entrance holds).
3. **Cancel means pre-execution only.** Cancelling a not-yet-dispatched task
   (Ready → Cancelled) is in scope. Stopping a running mission is out of scope;
   the gateway has no stop route and we won't add one now.
4. **State vocabulary is fixed now, trigger mechanism is not.**
   Backlog → Ready → In Progress → Done / Cancelled (Plane's built-in state
   groups map 1:1). The manual button moves Ready → In Progress and posts the
   mission; a future pull worker would just watch Ready instead. Failed runs go
   back to Ready or to Cancelled with a comment — agent's judgement.
5. **Agent-first on the autolab side.** The mediator updates Plane through API
   knowledge in its charter/guide (Tool Giving), not through a deterministic
   sync process. Mirror `state.json` → Plane mechanically only if agent-driven
   updates demonstrably keep failing.
6. **Experimental environment.** No production traffic. Keep prohibitions
   minimal; implementer discretion is preferred over rules. No backward
   compatibility required — breaking changes to assistant, UI, and gateway are
   fine.

## Constraints (the minimal set)

- Plane tokens live in git-ignored files (`.local/` or `.env`), never in
  tracked files or agent-visible guides.
- The user's Plane account is viewer/read-only; only agents hold write tokens.
- Do not run skip-permissions agent jobs on agstudio itself.

## Steps

### Step 1 — Deploy Plane CE on agstudio (scratch)

Run Plane CE via its docker compose bundle on the agstudio Mac. Create one
workspace, one project per managed project (start with ProjectA), an agent API
token, and a read-only user account. Verify the board loads from a phone over
VPN.

Hints:
- Plane CE ships its own postgres/redis/minio in its compose stack. agstudio
  already uses host ports 3000 (gitea), 5432 (postgres), 6379 (redis),
  8090/8091/8092, 9100 (MinIO). Keep Plane's stack self-contained on
  non-conflicting ports rather than reusing existing containers.
- Plane's API auth is the `X-API-Key: <token>` header against
  `/api/v1/workspaces/<slug>/projects/<project_id>/...`. Confirm the exact
  paths against the running instance's API docs — the API surface has shifted
  between versions; trust the instance, not memory.
- Record the chosen URL/ports and token location in `pj-agdev/.local/devenv.md`.
- Later cluster placement (LXC on aghub via Nautobot/nctl) is intentionally
  deferred; don't design for it now.

### Step 2 — Plane passthrough + guide in the assistant

Add a same-origin passthrough `/api/plane/...` to
`agdevworld/assistant/server.mjs`, mirroring the existing autolab passthrough:
inject the token server-side from env (`PLANE_URL`, `PLANE_API_KEY`,
workspace/project mapping), agents and browser never see the key. Update the
assistant `GUIDE.md` with concrete usage: how to create an issue from a
complaint (title, description, initial state Backlog or Ready), how to list
issues and states, with curl-shaped examples. That guide text is the Tool
Giving — make it good enough that no dispatch rules are needed.

Hints:
- State transitions in Plane are `PATCH` of the issue's `state` to a state ID;
  fetch the project's state list once and put the ID mapping in the guide or
  make the passthrough resolve names.
- Whether the prime agent files new complaints as Backlog (needs triage) or
  Ready (dispatchable) is implementer/agent discretion; just make the choice
  visible in the guide.

### Step 3 — Task list + dispatch UI in agdevworld

Add a task board view to the agdevworld frontend: list Ready (and Backlog)
issues via the passthrough. Each Ready issue gets two buttons:
- **Execute**: move issue to In Progress, then POST a mission to the chosen
  node's `/api/autolab/<node>/window` containing the issue title, description,
  and the Plane issue ID (the ID is how autolab reports back).
- **Cancel**: move issue to Cancelled. No dispatch.

Hints:
- The gateway allows one mission at a time (409 while `drive.sh` lives). Use
  the existing `/api/autolab/nodes` health/busy probe to disable Execute while
  a node is busy — or just surface the 409; either is acceptable.
- Node choice can be a simple dropdown fed by `AUTOLAB_NODES`; don't build
  placement logic.
- UI polish is not the point; a plain list in the existing app shell is enough.

### Step 4 — Autolab reports progress to Plane

Give the autolab mediator Plane access and knowledge:
- Deliver `PLANE_URL` + token to the node as a `.local` config file via the
  `autolab_node` Ansible role (deploy path: push agautolab to agstudio gitea,
  then run the playbook — see `pj-agdev/.local/devenv.md`).
- Extend `agent/CHARTER.md` / `GUIDE.md` with both the *when* and the *how*.
  When: a mission carrying a Plane issue ID gets progress comments (job
  created, iterations, gate results) and a final state — Done on converged,
  back to Ready or Cancelled with an explanatory comment on stuck/error.
  How: the same concrete usage the assistant guide gets — token file path,
  `X-API-Key` header, workspace slug, project ID, the state-name → state-ID
  mapping, and one example call each for commenting and for changing state.
  The mediator cannot discover any of these identifiers on its own; omitting
  them is not Tool Giving, it's starvation. Alternatively make the delivered
  `.local` config file self-describing (IDs + examples inside it) and have the
  guide just point there.

Hints:
- agautolab1 must reach Plane over the LAN (`agstudio.local:<port>` or the IP);
  verify with curl from the node before blaming the agent.
- Expect imperfect updates at first. Missed or wrong state transitions are ENT
  assets: record them in the episode report instead of adding rules
  preemptively.
- Known trap: harness project instructions can leak into in-system agent runs
  on autolab nodes and kill sessions on permission denials — if mediator
  sessions die oddly, check that first.

### Step 5 — End-to-end demo + report

One full pass: complaint to the prime agent (phone/VPN) → issue appears in
Plane → Execute in agdevworld → mission runs on a node → progress comments →
final state in Plane, user watching read-only. Write `report.md` (and
per-step reports as work lands), including what the agents did well or badly
with the Plane API — that record decides whether Step 4 later hardens into a
deterministic mirror.
