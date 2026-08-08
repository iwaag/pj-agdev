# remote access — report — 2026-08-08

Goal (from [braindump.md](braindump.md)): call the autolab agent on
`agautolab1.local` without SSH — deployment/updates of autolab on the node
owned by `ansible_agdev`, mission requests over an HTTP endpoint — and prove
it end to end by having a browser game (a simple 3-choice quiz) built and
served from a single no-SSH request.

## What was built

**1. Mission gateway** (`agautolab` commit `3f90669`, fix `bc0e038`) —
`agent/gateway.py`, a stdlib-only HTTP server run as the `autolab-gateway`
systemd user unit on the node (`:8791`). Routes:

- `POST /mission` `{"mission": "...", "max_sessions": N}` — bearer-token
  auth; writes `.local/agent/MISSION.md` and launches the existing
  `agent/drive.sh` detached; `409` while a mission is running (one at a
  time)
- `GET /status` — driver liveness + exit code, `NOTES.md` STATUS line
  (with the stale-notes guard mirrored from drive.sh), per-session
  cost/turn summaries, whether a game build is installed
- `GET /log?tail=N` — drive log tail, for no-SSH debugging
- `GET /game/…` — unauthenticated static serving of `.local/agent/serve/`
  (path-traversal guarded); missions that ship a browser game install
  their verified build there
- `GET /healthz` — unauthenticated liveness probe

The gateway refuses to start without `.local/agent/gateway_token`. The
agent layer itself (CHARTER, drive.sh, session.sh) is untouched — the
gateway is a thin front door over the same disk contract.

**2. Ansible ownership** (`ansible_agdev` commit `5d124c2`) — new
`autolab_node` role + `playbooks/agent/setup_autolab_node.yml`:
updates the `~/agautolab` checkout from the agstudio gitea
(`autodev/agautolab`, the node's existing origin), writes
`claude_bin`, generates the gateway token when absent (and keeps a
controller-side copy under `~/.local/state/autolab-gateway/<host>.token`,
local-only), installs/enables/restarts the systemd user unit, and waits on
`/healthz`. Restart is handler-driven on checkout or unit change, so the
same playbook is both install and update path. agautolab1 is not in the
generated production inventory (its DesiredNode application state is
`waiting_for_manual_initial_access`), so runs use a local-only static
inventory `inventories/agautolab.yml` (that directory is gitignored;
keeping node addresses out of Git also matches policy):

```sh
ansible-playbook -i inventories/agautolab.yml playbooks/agent/setup_autolab_node.yml
```

The deploy also brought the node's checkout from `ab2f59a` (pre-mediator)
to current `main` — the gitea `main` was behind the local repo and was
fast-forwarded to the mediator revision (`a7b255b`) as part of this
episode, so the node now runs the proper-role-separation agent.

## End-to-end proof (no SSH on the request path)

From agstudio, with only the fetched bearer token:

1. `POST http://agautolab1.local:8791/mission` with the quiz mission
   (3 options per question, ≥5 questions, feedback + score + restart,
   static site, install verified build into `.local/agent/serve/`) →
   `202 {"accepted": true, "run": 1}`.
2. Polled `GET /status` every 30 s. One agent session (mediator charter:
   plan → approve → implement via `autolab`), **519 s, 39 turns, $0.68**,
   `is_error: false`; drive exited `0` with `STATUS: complete`,
   `game_served: true`.
3. Verified the served product independently of the agent's own gates:
   `GET /game/` returns the quiz (`index.html` + `style.css` + `app.js` +
   `quiz-data.js`, all HTTP 200, no external references), 6 questions ×
   exactly 3 options with `correctIndex`, per-answer feedback,
   score/restart logic present and sound on code review; page renders in
   headless Chromium (screenshot taken against a byte-identical local
   mirror — the sandboxed browser could not reach the LAN directly).
   Playable at `http://agautolab1.local:8791/game/`.

Auth behaves: requests without the token get `401`; `/game/` and
`/healthz` are deliberately open; `/game/../gateway_token` gets `403`.

## Defect found and fixed

After drive.sh finished, `/status` kept `driver.running: true` and a
follow-up `POST /mission` would have been refused: the gateway never
reaps its detached wrapper, and `os.kill(pid, 0)` succeeds on the zombie.
Fixed in `bc0e038` — the wrapper's exit file is now the authoritative
"finished" signal and `SIGCHLD` is ignored so wrappers auto-reap. The fix
is pushed to gitea; **rolling it onto the node is one more run of the
same playbook** (pending at the time of writing; the running gateway
still serves the game fine).

## Notes and residue

- The permission classifier blocked agent-side `ansible-playbook`
  execution; per project rule the run was handed to the user (one
  command). Everything before and after — code, role, verification —
  was agent-side. If this recurs, an allowlist entry for
  `ansible-playbook` from `ansible_agdev/` is the candidate ENT.
- One mission at a time is a deliberate gateway property (drive.sh holds
  the same disk state); queueing is future work if it ever hurts.
- agautolab1 still lives outside the generated inventory. When its
  DesiredNode graduates past `waiting_for_manual_initial_access`, the
  static `inventories/agautolab.yml` should give way to a generated
  `autolab_nodes` group.
- Commits are on local `main`s and the agstudio gitea; pushes to GitHub
  (`agautolab`, `ansible_agdev`) are left to the user, as usual.
- Total mission spend: $0.68 (one session, one coding iteration inside).
