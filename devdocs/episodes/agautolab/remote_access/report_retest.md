# remote access — retest — 2026-08-08

Follow-up to [report.md](report.md): repeat the no-SSH flow end to end with a
different deliverable — a janken (rock-paper-scissors) browser game. No direct
SSH was used at any point; Ansible was the only channel that touched the node.

## What happened

1. **Pre-flight** — `GET /status` reproduced the known zombie-reap defect
   exactly as documented: the run-1 driver had finished (`exit_code: 0`,
   `STATUS: complete`) but `driver.running` was still `true`, which would have
   made a new `POST /mission` return `409`.
2. **Fix rollout** — one run of the same playbook
   (`ansible-playbook -i inventories/agautolab.yml
   playbooks/agent/setup_autolab_node.yml`) updated the checkout and
   restart-handled the gateway. `ok=13 changed=2 failed=0`. After restart
   `driver.running` correctly read `false`. Notably, the permission classifier
   did **not** block `ansible-playbook` this time, so the whole retest ran
   agent-side with zero user-executed commands.
3. **Mission** — `POST /mission` with the janken spec (3 choices vs. random
   CPU, per-round result feedback, win/loss/draw tally, reset, static site, no
   external references, install into `.local/agent/serve/`) → `202`-style
   `{"accepted": true, "run": 2}`.
4. **Run** — one agent session, **774 s, 35 turns, $0.78**, `is_error: false`;
   drive exited `0` with `STATUS: complete`, `game_served: true`.

## Independent verification (agent-side, not the mission's own gates)

- `GET /game/` serves `index.html` + `style.css` + `logic.js` + `app.js`, all
  HTTP 200, zero external URL references.
- Executed the served `logic.js` under Node: all 9 choice combinations map to
  the correct win/lose/draw result, and the tally accumulator is correct.
- Page renders in headless Chromium (screenshot against a byte-identical local
  mirror): three choice buttons with JP/EN labels, choice/result display,
  score row, reset button.
- Playable at `http://agautolab1.local:8791/game/` (replaces the quiz build,
  as the mission allowed).

## Notes

- The `bc0e038` reap fix works in practice: run 2 was accepted immediately
  after the restart, and `driver.running` flipped to `false` on completion
  without manual intervention.
- Run 2 took ~50% longer than run 1 (774 s vs 519 s) but still completed in a
  single session (`session-0002.json`).
- Total spend this retest: $0.78.
