# autolab_fix — report — 2026-08-08

Both problems from [problem.md](problem.md) are fixed, tested, and deployed
to the node.

## 1. `/status` is now scoped to the current run

`agautolab` commit `46f2d9f` (gateway.py + new `tests/test_gateway_status.py`):

- `POST /mission` now records the run's start time (`started`) in
  `gateway/current`.
- `sessions` only lists `session-*.json` files written at/after the current
  run's start; a new `sessions_total_on_disk` field keeps the overall count
  so accumulation is still visible.
- The served build is reported as a structured `game` object —
  `installed`, `installed_mtime`, and `installed_this_run` (mtime of
  `serve/index.html` vs. run start) — so a controller can answer "is my
  deliverable ready" from `/status` alone instead of fetching and
  inspecting `/game/` content. `game_served` is kept with its old
  "some build is installed" meaning for compatibility.
- Chosen direction: run-start-time filtering, not per-run session
  directories and not clearing `serve/` at accept — the agent layer's disk
  contract (drive.sh, session.sh, sessions/) stays untouched, and the
  previous game remains playable while a new mission runs.

Backward compatibility: a `gateway/current` written before this change has
no `started`, so `/status` falls back to the old everything-on-disk view
and never claims `installed_this_run: true`. Verified live on the node in
exactly that state; full scoping activates from the next `POST /mission`.

Tests: 2 new unit tests for the scoping helpers; full suite 41 passed.

## 2. `ansible_env` removed from the `autolab_node` role

`ansible_agdev` commit `0fed8b9`: every `ansible_env.HOME` in
`roles/autolab_node/{defaults,tasks}/main.yml` (repo dest, claude_bin,
service PATH, systemd-unit dir/dest) replaced with
`ansible_facts['env']['HOME']`. The playbook already runs
`gather_facts: true`, so no other change was needed. The
`lookup('env', 'HOME')` for the controller-side token dir is unrelated to
`INJECT_FACTS_AS_VARS` and stays.

Verified: re-running the playbook emits **no** deprecation warnings — only
the pre-existing, unrelated interpreter-discovery warning remains.

## Rollout

- `agautolab` `main` pushed to the agstudio gitea (`autodev/agautolab`),
  the node's deploy source.
- One run of the standard playbook
  (`ansible-playbook -i inventories/agautolab.yml
  playbooks/agent/setup_autolab_node.yml`) updated the checkout and
  restart-handled the gateway: `ok=13 changed=2 failed=0`, `/healthz` ok.
  No permission-classifier block; the whole episode ran agent-side.
- Post-deploy `GET /status` shows the new fields
  (`sessions_total_on_disk`, `game.{installed,installed_mtime,installed_this_run}`)
  with the documented pre-scoping fallback behavior.

## Residue

- No end-to-end mission was submitted to exercise the scoped view live
  (would spend ~$0.7 and ~10 min of agent time for what the unit tests
  already cover). The next real mission doubles as that check: expect
  `sessions` to contain only its own session(s) and
  `game.installed_this_run` to flip to `true` once it installs its build.
- Pushes to GitHub (`agautolab`, `ansible_agdev`) are left to the user,
  as usual.
