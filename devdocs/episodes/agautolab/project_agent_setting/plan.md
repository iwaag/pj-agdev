# Per-project agent settings

## Desire (from braindump.txt)

Each agautolab development project carries its own agent selection, chosen by
the developer, not enforced by the project repository. Director-attached
projects select both `director` and `coding` profiles; others select `coding`
only. Iterations read the selection at run time, so a continuing project keeps
its previous agents by default and can change them at any moment.

## Context and useful facts

- Projects live in `.local/projects/<name>/` (listed in
  `.local/projects/projects.md`). `direction/` existing there is what makes a
  project director-attached. `yokai` has a director and a `main/` repo;
  `scifi` has a director only.
- Jobs live in `.local/jobs/<job>/` and currently carry **no project link**.
- Profile resolution already exists: `agents.toml` (roles → profiles) +
  `.local/agents.local.toml` (node overlay), resolved through
  `agag.agent_config.load_config` / `resolve_role`, wrapped by
  `src/agautolab/agent_settings.py:resolve_project_role()`. It already takes a
  `profile_override` argument — the new layer is just another source for that
  argument.
- Coding profile today: `job.yaml` `profile:` field (`src/agautolab/job.py`),
  consumed in `src/agautolab/run_once.py` around line 410.
- Director launches: `python -m agautolab.role_run director --cwd
  .local/projects/<name>/direction ...` (see `agent/GUIDE.md` "Project
  directors"); the gateway window may launch this too.
- Available profiles for testing: `stub` (harness `fake`, zero cost) is ideal
  for unit tests; `local` (opencode/ollama) and `sonnet` (claude_code) for
  live evidence.
- This is a destructive phase on an experimental, non-production environment.
  Backward compatibility is **not required**: legacy behavior, old fields, and
  old precedence rules may be rewritten or deleted rather than preserved.

## Target design (default shape — implementer may deviate with reason)

`.local/projects/<name>/agents.toml`:

```toml
[roles]
coding = "sonnet"
director = "local"   # only on director-attached projects
```

- Values are profile names defined by `agents.toml` (+ node overlay). An
  unknown profile or unreadable file fails loudly; never fall back silently.
- Living under `.local/` keeps it out of version control by construction,
  matching "developer preference, not project mandate".
- Suggested precedence for coding: explicit `job.yaml` `profile` (one-shot
  override) > project file > `agents.toml` role default. Since compatibility
  is not required, the implementer may instead simplify — e.g. drop the
  job-level override entirely — if the result is cleaner.

## Steps

### Step 1 — project settings loader

Add a small loader (e.g. `src/agautolab/project_settings.py`): given a project
name, read `.local/projects/<name>/agents.toml` and return a role → profile
mapping. Decide and document the failure behavior: missing file (probably
fine, means "use defaults"), malformed TOML, unknown role key, unknown
profile name (fail at resolution time via `resolve_project_role`, which
already validates). Unit-test with `stub`.

### Step 2 — link jobs to projects and resolve coding profile

Add `project:` to `job.yaml` parsing in `job.py`. In `run_once.py`, feed the
project file's `coding` entry into `resolve_project_role("coding",
profile_override=...)` per the chosen precedence. Record the project name and
the resolved profile in the iteration evidence / run record so "which agent
worked on this last time" is answerable later.

Hint: `run_once` already writes normalized run metadata; extending that record
is cheaper than inventing a new artifact.

### Step 3 — director resolution from the project file

Make director runs resolve their profile through the same project file.
Simplest route: `role_run.py` discovers `agents.toml` from `--cwd` (the
direction workspace's parent) or accepts an explicit `--project` argument —
implementer's choice. Verify the gateway-launched director path goes through
the same code. Director run records gain the project name too.

### Step 4 — documentation for the agents that will use this

Update `agent/GUIDE.md` and `agent/README.md` (and `README.md` if it mentions
profile selection): one short paragraph each describing the file, its
location, and its meaning. Tool Giving, not shackling — describe what exists;
do not add mandatory procedures or prompts telling agents when they must
consult it.

### Step 5 — tests and live evidence

- Unit tests with the `fake` harness: precedence order, missing file,
  unknown profile failure, director resolution from a direction workspace.
- Live evidence, one iteration each: a director-attached project (`yokai`)
  and a non-director job, showing project name + resolved profile in the
  records. A director smoke run through `role_run` counts for the director
  half; a full mission is not required.
- Write `report.md` in this episode folder: what was built, precedence
  actually chosen, deviations from this plan, and anything learned worth an
  ENT follow-up.

## Constraints (minimum)

- No credentials or private payloads in tracked files.
- No silent harness/model/profile fallback — unavailable or unknown
  selections fail visibly.
- Keep enough raw output to diagnose a failed run.

Everything else — module boundaries, exact file name (`agents.toml` vs
`project-agents.toml`), whether job-level override survives, error message
wording, test structure — is the implementing agent's judgment.

## Out of scope

- Promoting this to `devpolicy/contracts/agent/` (revisit only when agforge
  or agdevworld want the same layer).
- Deploying project files to agautolab1 (`.local/` is not shipped by
  Ansible; node-side files are written by hand for now).
