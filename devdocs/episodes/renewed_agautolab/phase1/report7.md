# Step 7 — Add `agent/front/new_mission.py`

Status: **done**

## Result

The front workspace now exposes exactly the promised command shape:

```text
uv run new_mission.py <mission_name> <mission_description>
```

Its `--help` tells the agent to use a short outcome-oriented title, provide a
complete quoted description, and call the tool once after reading the latest
dumped project chat.

The project is derived from the latest
`.local/topics/pj-*/.../chatlog.txt` in the fixed front cwd. This keeps the two
user-facing positional arguments limited to mission name and description as
planned. `AUTOLAB_PROJECT` is an explicit override for direct smoke tests.

The command finds the matching Plane project, reads that project's live state
vocabulary, creates one issue with escaped `description_html`, and prints
`success`. It never reuses ProjectA's committed/local state UUIDs.

## Live finding and fix

The initial implementation asked the new project for a state named `Ready`,
as expected from the existing ProjectA vocabulary. A live create proved that
Plane's newly created projects instead start with `Backlog`, `Todo`, `In
Progress`, `Done`, and `Cancelled`; no issue was created on that failed call.

The final implementation selects the live actionable start state in this
order: `Ready`, `Todo`, any `unstarted` group state, then `Backlog`. This keeps
the intended Ready behavior where available and correctly used `Todo` for the
new smoke project.

## Verification

- `uv run pytest -q` — 22 passed.
- Tests cover latest-chat project selection, explicit override, HTML escaping,
  state ID use, all starting-state fallbacks, and empty argument rejection.
- `cd agent/front && uv run new_mission.py --help`: passed with the concise
  two-argument interface.
- Live create returned `success`; Plane contains `Phase 1 mission smoke` in
  state `Todo` under `Phase1 Smoke 20260813`.
- `python3 -m py_compile` and `git diff --check`: passed.

Implementation commit: `b9a4040` (`Add the front mission registration tool`).
