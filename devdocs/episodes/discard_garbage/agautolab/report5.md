# Report 5 — trim the surviving docs

Plan step 5 (the "Order" list; the plan's body headings are numbered one
lower — these reports follow the Order list, where step 1 is the deletion).

`AGENT_GUIDE.md`, `agent/README.md`, `agent/CHARTER.md` and `styles/README.md`
went in step 1. This step rewrites the two documents that survive.

## `agent/GUIDE.md`

Kept because it is live surface, not prose: the gateway re-reads it per
request and serves it at `GET /guide`. 131 lines → 47.

It now opens by saying the node is a stub and what an autolab node used to be,
lists the routes with a plain statement of which two are real, and answers the
cost question with "nothing — no harness is launched from this node, by any
route". The agent section survives in full, since the roles and profiles are
the configuration the episode keeps.

Removed: the cost table (six figures, each now false), the Plane reporting
section with its `curl` recipes, and the project-director section — all three
described machinery that no longer exists. Removing them also clears the
dangling pointers into the deleted `CHARTER.md` and `styles/`.

## `README.md`

99 lines → 30: what agautolab was, what was deleted, the three things kept,
and the two commands that still start something. It points at this episode for
the why.

## Checked

A grep across every surviving `.md`, `.py`, `.sh`, `.toml` and `.json` for
names of deleted things (`AGENT_GUIDE`, `CHARTER`, `styles/`, `drive.sh`,
`session.sh`, `run_once`, `adapters`, `mission_witness`, `autolab loop`,
`autolab@.service`, `MISSION.md`, `NOTES.md`) returns only:

- `agent/gateway.py` and `agent/GUIDE.md` naming the `/monitor/` **route**,
  which still exists and answers 404 — correct, not a dangling reference;
- one line inside `WINDOW_PROMPT`, the preserved window prompt template, that
  still describes writing `MISSION.md` and spawning the drive loop. The
  template is kept deliberately as part of the entrance's design and is never
  sent anywhere: `run_role` ignores the prompt. The comment directly above it
  says so, so a reader meets that fact before the stale sentence.

This grep is the removal check the deleted `test_legacy_removed.py` used to
perform, and step 8 runs it again over the finished tree.
