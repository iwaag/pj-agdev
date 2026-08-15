# p3 report 4 — the `[TOOLS]` footer, runcreate's `tools/`, and `failure.flag`

Step 4 of `p3/plan.md`. The toolsets a Work was planned with now survive the
trip through Plane, and the generator's own verdict on its run is heard.

## The footer

`plane.py` gained a third marker beside `[AUTO]` and `FORGEAUTO`:

- `with_tools_footer(description, names)` appends one last line,
  `[TOOLS] toolset-image, toolset-video`. No toolsets, no line.
- `split_tools_footer(description)` → `(description without it, names)`.

`register_plan(channel, topic, plan, tools=())` composes it;
`create_topic.handle_generator` passes exactly what `place_toolsets`
reported as landed in `tools/`, so the footer describes what the plan was
actually written against, not what the front asked for.

The distinction that carries the whole fallback: `split_tools_footer`
answers `None` for "no footer at all", never `[]`. `None` means hand-made or
pre-phase, and is answered with the entire toolset library; a Work planned
with no toolsets carries no footer and is answered the same way, which is
the plan's stated behavior. A pinned test says so, because `[]` and `None`
being the same value would be an invisible regression.

The line is plain text, so it round-trips through
`description_html` → Plane → `html_to_text` untouched; that round trip is
its own test rather than an assumption.

## runcreate's workspace

`prepare_workspace` now:

- splits the footer off, writes `plan.md` **without** it (that line is
  addressed to this function, not to the agent),
- rebuilds `tools/` — `shutil.rmtree` first, then `toolsets.place`, so a
  toolset dropped from the footer cannot linger from the previous trigger.
  `tools/` is derived from the Work, exactly like `plan.md`; `result/` and
  `intermediate/` remain the persistent ones,
- removes any leftover `failure.flag`, so what is found after the run is
  this run's verdict and not the last one's.

`TOOLS_FILE` and the `tools.md` copy are gone.

## `failure.flag`

`runcreate_generator/guide.md` tells the generator to create an empty
`failure.flag` when it fails. After the run:

- `success=False` goes to `report_work`, which then does **not** move the
  Work to `completed` — it stays unstarted, hence selectable, hence
  re-runnable on the next trigger.
- the topic summary says `failure.flag is present: the generator reports
  failure`.
- the origin delivery is prefixed with *"the run reported failure; what it
  produced follows"* — and still carries the result or answer. A failed run
  that produced three of five files should hand over the three.

The exit code remains the first-class failure signal: a non-zero exit still
raises before any of this is reached. The flag is the agent's own verdict on
a run the harness saw nothing wrong with.

## Tests

`uv run pytest -q` → **135 passed, 0 failed**. The eight failures carried
since Step 1 are gone with the `tools.md` they were waiting for.

New: the footer on a registered Work and its absence when there were none,
the Plane round trip, `None` vs `[]`; and on the runcreate side — a
footerless Work getting the whole library, an unknown footer name being
skipped rather than fatal, a re-trigger rebuilding `tools/` from the current
footer, `failure.flag` → `success=False` plus both messages, and a leftover
flag not condemning the next run. Both test modules now resolve toolsets
against a test-owned library, so none of this depends on which toolsets the
repository ships.
