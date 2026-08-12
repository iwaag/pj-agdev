# Report 7 — clean `.local/`

Plan step 7. All untracked, so nothing appears in a commit; this report is the
only record that it happened. Irreversible.

`agautolab/.local/`: **7.8M → 20K**.

## Deleted

| Path | Was | Why |
|---|---|---|
| `projects/` | 1.2M | `scifi`, `yokai`, `project-agent-setting-smoke`, `projects.md` — the auto-developed projects the braindump named |
| `jobs/` | 5.8M | 25 job directories with their per-iteration evidence |
| `agent/sessions/`, `window/`, `director/`, `gateway/`, `serve/` | 636K | run records and drive logs of the deleted loop |
| `agent/MISSION.md`, `NOTES.md`, `done` | 28K | the last mission's state |
| `agent/archive-agentify/`, `archive-smoke/` | 44K | archived mission state |
| `phase7/` | 16K | leftover run records from an episode phase |
| `tmp/` | 8K | scratch (two downloaded gitea pages) |

`phase7/` and `tmp/` were not in the plan — I found them in `.local` while
executing it and they are the same generation of leftovers.

## Confirmed before deleting

`.local/jobs/` was the one item the plan flagged as beyond the braindump's
literal words, since it held the only record of what the loop actually did,
failure runs `denial-in-1`…`denial-in-8` included. Asked, and the answer was
delete. Recorded here because the ENT reading — failure records are assets —
argued the other way, and a later reader should know the trade was made
deliberately rather than overlooked.

## Kept

`.env`, `agents.local.toml` (the node's real profile overlay, still read on
every request), `gitea/` (askpass, password, token), `zulip.env`.

## Verified after

Gateway restarted against the emptied tree:

- `GET /projects` → `profiles: [local, sonnet, stub]`, `projects: []`. The
  profile list still comes from `agents.toml`; the empty project list is now
  the truth on this machine.
- `POST /window` → 200, and `.local/agent/window/run-0001.json` was recreated
  from scratch. Window numbering restarts at 1, which is expected: the counter
  was always derived from the files on disk.
