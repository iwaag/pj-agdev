# Per-project agent settings — final report

## Built

agautolab projects can now carry a developer-owned, Git-ignored agent selection
at `.local/projects/<name>/agents.toml`:

```toml
[roles]
coding = "sonnet"
director = "local"
```

Jobs link to a project with `project:`. Coding iterations and director runs
both resolve through the shared agent contract without model or harness
fallback, and their existing normalized evidence records retain the project
name together with the resolved profile.

Coding precedence is explicit `job.yaml` `profile` > project `[roles].coding`
> shared coding-role default. Director precedence is explicit `--profile` >
project `[roles].director` > shared director-role default. A missing project
file uses defaults; malformed files, unknown roles, and unknown profiles fail
visibly.

Director runs infer the project from a `.local/projects/<name>/direction/`
working directory. An explicit `--project` option was also added for callers
whose cwd cannot express that relationship. This is the only small extension
beyond the plan's default shape.

## Verification

- Full suite: **89 passed**.
- Live local director: `yokai / local / opencode`, successful normalized run.
- Live coding resolution: `project-agent-setting-smoke / local / opencode`,
  identity recorded; target gate failed because of a pre-existing OpenCode cwd
  issue, with raw evidence retained.
- Live runtime reselection: the same project's coding profile changed to
  `stub`; the next fake-harness iteration recorded it and converged.
- Local cluster prerequisite: `nctl status --json` returned `ok: true` for
  Nautobot and its worker. The optional manually started gateway was stopped,
  so the documented common CLI supplied director evidence directly.

## Follow-up

The observed OpenCode cwd mismatch was subsequently traced to a stale inherited
`PWD`: `subprocess(cwd=...)` changed the real cwd without changing that
environment value. The follow-up deliberately applies two defenses and records
the reason in code and documentation: pyagag synchronizes `PWD` with cwd, while
the OpenCode adapter also passes its native `--dir`. Both have regression tests,
and a local/OpenCode job launched from the parent checkout subsequently
converged with all tool events confined to its `target/`.

did per-project coding/director agent-setting implementation and live smoke
evidence for the agautolab in-system agent — handoff candidate.
