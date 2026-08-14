# Step 3 — Plane Work registration

## What was built

`agforge/src/agforge/plane.py` — local to agforge, as the plan asks, so that
touching it costs no pyagag push → `uv lock` round trip. Ported from
`agautolab/src/agautolab/project_init.py` (`PlaneConfig`, `load_plane_config`,
`_request_json`, `_rows`, `_normalized_name`) and `mission.py`
(`split_document`, `description_html`, `find_issue_by_external`,
`ensure_issue`, `starting_state_id`, `issue_label`).

`create_topic.register_plan` now calls it. The wrapper stays, so step 5 moves
the client into `agag` by changing one import.

### What was deliberately dropped in the port

- **`labels` is gone from `ensure_issue`.** It was the one place autolab's
  `AUTO` label attached. An `AUTO`-labelled issue is one `next_work` executes.
- **`ensure_plane_project`'s `[AUTO]` description marker is gone.** A project
  carrying it is one `next_work` *scans*. agforge's created projects get
  `agforge request records: <name>` instead.
- **`parent` is gone from `ensure_issue`.** agforge creates no sub-issues, so
  none of Plane CE v1.4.1's parent/child quirks (ignored `?parent=`, 404ing
  `sub-issues`) apply here.

### Routing

`pj-<name>` → the Plane project of that name; anything else → `FreeForge`,
created on first use. A `pj-` channel with no matching project falls back to
`FreeForge` and says so in one line on the topic — a routing fact, not a
failure, so it is returned in the report line rather than raised.

External key: `external_source = "agforge"`, `external_id =
"<channel>/<topic>"`. autolab uses `agautolab`, so the key spaces do not
collide.

## Verification

### Tests — `tests/test_plane.py`, with `_request_json` as the seam

```
101 passed in 3.83s
```

The two that matter most assert absences: a registered Work's request body has
no `labels` key, and a created project's description contains no `[AUTO]`.
Plus routing (own project / fallback with the note / non-`pj-` channel /
`FreeForge` created on first use), the 404-not-empty-list lookup contract, the
duplicate guard, and `starting_state_id`'s ready → todo → unstarted → backlog
walk.

### Live: all three checks from the plan

Listener restarted; three real `create-` topics served, then one re-served.

| topic | channel | Plane project | result |
|---|---|---|---|
| `…-p1step3-freeforge` | `#FreeForge` | FreeForge (created, `F2`) | `created F2-1 "Plan"` |
| `…-p1step3-pjmatch` | `#pj-spike` | Spike (existing) | `created S-2 "Plan"` |
| `…-p1step3-pjfallback` | `#pj-members-20260813` | FreeForge (fallback) | note + `created F2-2 "Creation Plan"` |

The fallback topic received exactly what the plan specifies:

```
no Plane project named 'members-20260813'; registering in FreeForge instead
created F2-2 "Creation Plan" in FreeForge
```

**No duplicate on re-serve.** Posting *"make the dragon green instead of red"*
into the FreeForge topic cut generation `2` and produced:

```
updated F2-1 "Plan" in FreeForge
```

The FreeForge project still holds exactly 2 issues, both with `labels: []`,
and the topic keeps one Work while `N` climbed to 2.

**The prohibition holds where it is actually enforced.** Run against the live
Plane after all four registrations:

```
next_work -> None
```

agautolab's chooser sees nothing to execute. Both mechanisms are why: the
issues carry no `AUTO` label, and neither `FreeForge` nor `Spike` carries the
`[AUTO]` project marker `next_work` scans for.

### Incidental confirmation of step 1

One generator said so itself, unprompted, on `#pj-spike`:

> I confirmed `generate.sh` is actually available on PATH (its `--help`
> output resolved) even though it isn't in this directory

That is step 1's PATH handover verified from inside a topic workspace by the
agent that depends on it.

## Observation, not fixed here

Two of the three Works are titled `"Plan"`, because `split_document` takes the
first heading and the generator writes `# Plan`. The Plane board therefore
reads as a column of identical names. The fix belongs in
`create_generator/guide_plan.md` (ask for a heading that names the *work*),
not in this transport — the document is the agents', and rewriting the title
here would be exactly the shackle the style guide warns against.

**Handoff candidate**: `guide_plan.md` should ask the generator to title
`plan.md` after the deliverable.

## Deviations from the plan

None.
