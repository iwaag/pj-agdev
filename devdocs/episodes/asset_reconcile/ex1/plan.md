# asset_reconcile ex1 — plan

Goal: re-verify the agforge ↔ autolab integration end to end through real
development, after the large autolab reworks. The product is deliberately
tiny: a browser gallery app that switches between 3 images with buttons.

**Premise: remote development on `agautolab1.local`**, as proven twice in
`devdocs/episodes/agautolab/remote_access/` (report.md, report_retest.md).
No SSH on the request path: missions go through the gateway
(`POST http://agautolab1.local:8791/mission`, bearer token at
`~/.local/state/autolab-gateway/agautolab1.token` on agstudio), Ansible is
the only channel that touches the node
(`ansible-playbook -i inventories/agautolab.yml
playbooks/agent/setup_autolab_node.yml`).

Inputs: `braindump.txt` (this folder), the parent episode's
`../plan.md` / `../report.md` / `../problem.md`, the remote_access reports,
`agautolab/AGENT_GUIDE.md`, `director/README.md`, `agforge/README_DEV.md`.

## Roles (decided)

- **Operator (agstudio side)**: writes the mission, POSTs it, polls
  `/status` and `/log`, verifies independently. Touches the node only via
  gateway + Ansible.
- **Autolab agent (node-side mediator)**: receives the mission, drives the
  autolab loop (plan → approval window → implement), talks to agforge,
  runs the director, places accepted bytes into `target/`. All external
  I/O on the node lives here.
- **Coding agent** (inside the autolab job on the node): plans,
  implements, proposes gates. During planning it authors the **asset
  manifest** — technical fields only (path under `target/`, format,
  dimensions, request ids). Never reads direction material.
- **Director** (runs node-side, next to the mediator; the node has a
  claude binary via `claude_bin`): reads only the direction workspace
  brief + one manifest entry; composes the creative desire per image and
  reviews candidates leniently. Never edits the manifest's technical
  fields.

## Key mechanics (decided)

- **Asset delivery happens at the `awaiting_approval` stop (exit 40),
  before the mediator approves the implement phase.** This all happens
  inside one mission — the mediator already runs plan → approve →
  implement itself; the mission text inserts the reconcile step before
  its approve. No autolab code change, and the implement loop never
  idles waiting for assets (which would trip no-progress → stuck).
- **Asset bytes never transit agstudio.** The node downloads directly
  from the agforge presigned MinIO URL. agforge service runs on agstudio
  (`:8092`, `agforge/service/serve.sh`); presigned URLs are signed
  against `agstudio.local:9100`.
- **Mechanical acceptance stays deterministic.** Format signature + exact
  dimensions + byte-identical copy, as in the parent episode. This check
  earned script status (it caught the JPEG-for-PNG failure); reuse
  `director/reconcile.py`'s check rather than re-judging by agent.
- **The mediator only places files; the coding agent commits them** in
  its first implement iteration, and gates verify them.
- **Bounded retry:** at most 2 agforge attempts per image. A third
  failure on any image = mission reports failure honestly; never
  transcode/resize/rename to force a pass.
- **Persist director evidence.** Every compose/review JSON envelope
  (verdict, desire, cost, timing) and agforge request id is saved — this
  was the parent episode's known gap. Push them with the direction repo
  (or job evidence) so the operator can read them without SSH.

No backward compatibility is owed to the parent episode's artifacts; adapt
or rewrite `director/` glue freely. Environment is experimental — prefer
generous tool allowances over micro-restricting agents (`skip_permissions`
is acceptable on the experimental node per existing policy, never on
agstudio). Secrets stay in `.local/`; delivered bytes are never converted
to mask an agforge failure. Everything else is implementer's discretion.

## Step 1 — Node refresh, repos, pre-flight

1. Push any needed `agautolab`/`director` changes to the agstudio gitea,
   then run the setup playbook once to fast-forward the node and restart
   the gateway. Confirm `/healthz` ok and `/status` shows
   `driver.running: false` (the zombie-reap defect is fixed but
   pre-flight `/status` is cheap — remote_access retest §1).
2. Create two repos on gitea (`autodev` org):
   - `gallery-direction` — concept repo: a one-or-two-line `brief.md`
     ("A medieval-fantasy themed image gallery. Warm, painterly, slightly
     archaic mood."), plus an ignored staging/review area.
   - `gallery-web` — source repo, starts empty; the coding agent owns it.
3. **Reachability probe** (cheap, do it before designing the mission):
   verify the node can reach `http://agstudio.local:8092/healthz` and a
   sample presigned `agstudio.local:9100` URL. `.local` mDNS resolution
   from the Linux VM is the single most likely environment blocker; if it
   fails, fall back to IP or /etc/hosts via the playbook. A trivial probe
   mission through the gateway is an acceptable way to test this without
   SSH. Start `agforge/service/serve.sh` on agstudio first (in-memory
   jobs vanish on its restart — just re-request).

Deliverable: refreshed node, both repos, proven node→agforge path,
`report1.md`.

## Step 2 — Mission design

Write the mission text (operator-side, reviewed before sending). It must
tell the mediator to:

1. Clone `gallery-direction` (direction workspace) and set up the job:
   goal nearly verbatim from the braindump ("browser gallery app, 3
   images switched by buttons, images arrive later via an asset manifest
   you define"), no `gates` (plan phase), `push: true` to `gallery-web`.
2. Run to exit 40 and check the plan: `PLAN.md`, `proposed_gates.yaml`,
   and a manifest with 3 image entries (path, PNG, dimensions,
   `status: requested`). Manifest missing or entangled with creative
   content → `reject --feedback` and re-plan (this round-trip is itself
   part of what ex1 verifies).
3. For each entry, before approving: director compose → agforge
   `POST /api/requests {"desire": ...}` → poll to `done|failed` →
   download → mechanical check → director review → copy exact bytes to
   the manifest path, flip that entry to `delivered`. Do not commit.
   Persist every envelope and request id.
4. `approve`, loop to terminal, expect the first iteration to commit the
   assets and the gates (tests + asset gate: PNG signature, exact
   dimensions, referenced by the app) to drive the rest.
5. Install the verified build into `.local/agent/serve/` and finish with
   the standard STATUS contract.

Hints: last time the manifest lived at `target/assets/manifest.json`;
1024×1024 PNG is the proven size. `director/reconcile.py` already does
step 3 for one entry — adapt it or call it three times, implementer's
choice. Budget expectation: prior single-game missions ran 519–774 s /
$0.68–0.78; this mission adds 3 generations (tens of seconds each) and
director calls, so allow a larger session budget or plan a second run.

Deliverable: mission text saved in this folder (`mission.md`),
`report2.md`.

## Step 3 — Fire and monitor

1. `POST /mission` with the text; expect `{"accepted": true}` (409 means
   a mission is still marked running — check `/status`).
2. Poll `GET /status` (~30 s interval) and `GET /log?tail=N` when
   curious. Do not intervene while STATUS progresses; if drive exits
   nonzero or stalls, read the log tail, fix the environment (playbook
   or agforge side), and re-request — jobs and missions are re-runnable.

Deliverable: completed mission (`STATUS: complete`, `game_served: true`),
`report3.md` with per-image attempts, costs, and timing from `/status`.

## Step 4 — Independent verification (operator-side)

1. `GET http://agautolab1.local:8791/game/` — all files HTTP 200, no
   external references; 3 images present and switched by buttons (check
   the served JS logic, and screenshot via headless Chromium against a
   byte-identical mirror if the sandbox can't reach the LAN — same
   technique as remote_access).
2. Record the served revision; never verify a different checkout than
   the one claimed deployed (parent `problem.md` §8).
3. Pull `gallery-web` and `gallery-direction` from gitea; confirm the
   delivered bytes match the manifest (signature/dimensions), the
   director envelopes are present, and the game repo contains no
   direction material (context isolation held).

Deliverable: `report4.md` with screenshot and served-revision evidence.

## Step 5 — Wrap-up

Write `report.md`: what ran, LLM costs (gateway `/status` session
summaries + director envelopes), agforge attempts per image, what broke
and how it was recovered, and two judgments for the future:

- should the awaiting-approval delivery window become the standard
  pattern, or does autolab need a real `awaiting_assets` state;
- is the one-mission-does-everything shape right, or should asset
  reconcile become a separate mission/service boundary.

Log recurring friction `problem.md`-style if anything from the parent
episode reappeared.
