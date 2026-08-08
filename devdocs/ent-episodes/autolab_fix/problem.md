# autolab gateway — problems observed during the remote_access retest (2026-08-08)

Source episode: `devdocs/episodes/agautolab/remote_access/` (report.md and
report_retest.md). The retest succeeded end to end, but two things made the
no-SSH workflow harder to observe or will break it later.

## 1. `/status` fields are not scoped to the current run

During run 2 (the janken mission), `GET /status` reported:

- `game_served: true` the whole time — but that was the *previous* mission's
  quiz build still sitting in `.local/agent/serve/`. The flag says "some build
  is installed", not "this run's build is installed", so a controller cannot
  tell from `/status` when the new deliverable has actually landed. The retest
  had to verify by fetching `/game/` content and inspecting it.
- `sessions` lists every `session-*.json` on disk, mixing run 1's
  `session-0001.json` with run 2's `session-0002.json`. Cost/turn accounting
  per mission requires knowing out-of-band which sessions belong to which run.

**Impact:** no-SSH observability — the whole point of the gateway — degrades
as runs accumulate; each new mission makes `/status` noisier and the
"is my deliverable ready" question unanswerable from the API alone.

**Improvement direction:** scope `/status` to the current/most-recent run
(e.g. record run start time and filter sessions by mtime, or move sessions
into per-run directories), and either clear `.local/agent/serve/` at mission
accept or expose a served-build timestamp/hash so a fresh install is
distinguishable from a stale one.

## 2. Ansible role emits deprecation warnings that become hard failures

`ansible_agdev` `autolab_node` role (run with ansible-core 2.21.1) warns on
every play: `ansible_env.HOME` in the systemd-unit dest and
`autolab_node_service_path` (defaults/main.yml:10) rely on
`INJECT_FACTS_AS_VARS`, which is deprecated and scheduled for removal in
ansible-core 2.24.

**Impact:** none today, but the install/update path for the node — the only
sanctioned no-SSH management channel — silently breaks on a future ansible
upgrade.

**Improvement direction:** replace with `ansible_facts['env']['HOME']` (or
`ansible_facts.env.HOME`) in both spots; a one-commit fix in `ansible_agdev`.

## Not problems (deliberate, already documented)

- One-mission-at-a-time `409` semantics — deliberate gateway property;
  queueing remains future work per report.md.
- The permission-classifier block on `ansible-playbook` from report.md did
  **not** recur in the retest; no allowlist ENT is warranted on current
  evidence.
