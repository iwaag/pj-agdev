# p3 report 3 — the create flow: `toolsets.csv` → `tools/`

Step 3 of `p3/plan.md`. The generator no longer receives one `tools.md`; it
receives a `tools/` directory holding exactly the toolsets the front asked
for.

## One module for the toolset library

Three places read `agent/toolsets/` — the CLI listing, the create flow, and
(next step) the runcreate flow — so the rules live once, in
`src/agforge/toolsets.py`:

- `describe(text)` / `listing()` — the `# Description` body, one line per
  toolset. Moved out of `cli.py`, which now calls it.
- `resolve(name)` — the lenient name lookup. It accepts `toolset-image`,
  `toolset-image.md`, a whole `--list` line with its description tail, any
  case, and quotes; it takes the first comma-separated field and matches on
  the stem. That leniency is the point: an agent copies these names by hand
  out of printed output.
- `parse_names(text)` — a `toolsets.csv` body to names, in order, without
  repeats; blanks and `#` comments dropped.
- `place(names, target)` — copy what resolves, `log` and skip what does not,
  return what actually landed. Agent-first: a run that can do most of the
  job beats a run that refuses over one bad word.

## The create flow

`create_topic.place_toolsets(front_dir, generator_dir)` reads
`front/toolsets.csv` — the front writes it in its own generation directory,
as its guide says — and builds `generator/tools/`. The `tools.md` copy and
its source path are gone.

`tools/` is created whether or not anything lands in it. No csv, or nothing
resolvable, means an empty `tools/`, which is a route `guide_plan.md`
already covers on its own (ask back, `idea.md`, or decline); an absent
directory would be a murkier signal for no gain. The new ask-back behavior
in that guide needed no code, as the plan predicted — the generator's answer
is already relayed verbatim and both `plan.md` and `idea.md` are already
optional.

Checked by hand against the real library:

```text
toolsets.csv: toolset-image, General image…  /  toolset-video.md  /
              "  TOOLSET-MUSIC  "  /  # a comment  /  toolset-nope  /
              toolset-image (again)
→ placed: toolset-image, toolset-video, toolset-music
→ log:    unknown toolset 'toolset-nope'; skipped
```

## Tests

`tests/test_create_topic.py` follows the change: the fixture no longer
writes a guide `tools.md`, the front can now write a `toolsets.csv`, and the
csv resolves against a **test-owned** toolset library (`monkeypatch` on
`toolsets.TOOLSETS_DIR`) so nothing depends on which toolsets the repository
happens to ship. Two new tests pin the lenient resolution with an unknown
name mixed in, and the empty-`tools/` route.

`uv run pytest -q` → 118 passed, 8 failed. The eight are the same
pre-existing `test_runcreate_topic.py` failures, still wanting the deleted
`tools.md`; Step 4 removes that copy from `runcreate_topic` and rewrites
them.
