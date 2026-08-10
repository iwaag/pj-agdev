# ex2 — autolab creates a director-attached project, guidance-only

Plan for `braindump.txt` in this directory. Decisions already made with the
developer:

- Test 1 (project creation) runs through **`POST /mission`**, not `/window` —
  the window's read-mostly toolset was a deliberate restriction; missions are
  the sanctioned write path. Record this as a deviation from the braindump
  (which says `/window`) — a developer decision, not drift.
- Test 2 (consult the new director) stays on **`POST /window`**, as written.
- **Role intent** (goes into the guidance as fact): the autolab agent itself
  creates the repo pair and plants/maintains the direction files
  (`concept.md` etc.); coding agents grow the main repository's contents.
  Creating the project is autolab's own work, not a coding-agent job.
- The old pre-reset placement rule did not survive the director reset; the
  rule below is its redesign.

This environment is experimental, not production: security and
non-destruction rules are relaxed, backward compatibility is not required.
Steps 1–3 and driving the tests are Omni Agent work; the experiment itself is
whatever the mission/window agents do with the guidance text alone.

## Constraints (the minimum)

1. No `--dangerously-skip-permissions` anywhere (CHARTER safety device — the
   one rule that stays even here).
2. Secrets stay under `.local/`; never in tracked files or pushed content.
3. **No gateway.py or session.sh changes in the base plan.** The experiment
   is "guidance text only"; harness edits are allowed solely as
   evidence-driven fixes after an observed failure (Step 5), one at a time.

Everything else — wording tweaks, command shapes, retry strategy, commit
granularity — is implementer's discretion.

## Step 1 — placement rule and scifi migration

The rule (one project = one folder; main and direction are siblings):

```
gitea:  autodev/<name>            … main repository (coding agents grow it)
        autodev/<name>-direction  … director workspace (autolab plants files)
local:  .local/projects/<name>/main/       … clone of the main repo
        .local/projects/<name>/direction/  … clone of the direction repo
        .local/projects/projects.md        … index, one line per project
```

Migrate the existing SF project to project name `scifi` (everything is under
git-ignored `.local/`, so this is plain `mv`, no git surgery):

- `mv agautolab/.local/direction/scifi-direction agautolab/.local/projects/scifi/direction`
  (create the parent first). The gitea remote `autodev/scifi-direction`
  already matches the `<name>-direction` convention — leave it untouched.
- Move `projects.md` to `.local/projects/projects.md`; reword its line to
  name the project `scifi` with the same one-line summary.
- `autodev/scifi` (a main repo for scifi) does not exist and is NOT created
  here — scifi predates the rule; only the Edo project must satisfy it fully.
- Remove the now-empty `.local/direction/`.

## Step 2 — guidance text (the experiment's only real change)

No restarts needed: `agent/GUIDE.md` is re-read per window request, and
`AGENT_GUIDE.md` is read from disk by each mission session.

**(a) `agautolab/AGENT_GUIDE.md`** — append:

```markdown
## Projects

A project is a pair of git repositories under the `autodev` org on this
node's gitea (`http://agstudio.local:3000`; API token in
`.local/gitea/autolab-agent.token`; `POST /api/v1/orgs/autodev/repos`
creates a repo):

- `<name>` — the main repository. Coding agents grow its contents.
- `<name>-direction` — the director's workspace. The autolab agent creates
  the pair and plants and maintains the direction files itself: a `GUIDE.md`
  telling the director its role, a `concept.md` stating the project's theme,
  and a `.gitignore` containing `.local`.

Locally both are cloned under `.local/projects/<name>/`, as `main/` and
`direction/`. `.local/projects/projects.md` lists every project, one line
each.
```

**(b) `agautolab/agent/GUIDE.md`** — replace the "Project directors" section
(its paths are now stale) with:

```markdown
## Project directors

Project workspaces live under `.local/projects/<name>/direction/`;
`.local/projects/projects.md` lists every project, one line each. To consult
a project's director, run `claude -p --allowedTools Read,Glob,Grep` with the
request on stdin and that project's `direction/` directory as the working
directory.
```

Deliberately absent (Failure Farming — add only on observed need): the order
of operations, any "append to projects.md when you create a project"
instruction (the index's existence is stated as fact; whether the agent
updates it is an observation target), the main repo's initial contents, and
how to phrase the director files' text.

Verify the window card deployed: `curl -s localhost:8791/guide | tail`.

## Step 3 — preflight

- Gateway alive: `curl -s localhost:8791/healthz` (started by hand on
  agstudio; if dead, `cd agautolab && nohup python3 agent/gateway.py > .local/agent/gateway/serve.log 2>&1 &`).
- gitea alive: `curl -s http://agstudio.local:3000/api/v1/orgs/autodev/repos -H "Authorization: token $(cat agautolab/.local/gitea/autolab-agent.token)"`
  — also the baseline repo list for judging Test 1.
- No mission running: `/mission` returns 409 while drive.sh lives; check
  `.local/agent/gateway/current`.
- Token file present: `.local/agent/gateway_token` (0600).

## Step 4 — Test 1: create the project via /mission

```sh
curl -s -X POST localhost:8791/mission \
  -H "Authorization: Bearer $(cat agautolab/.local/agent/gateway_token)" \
  -H 'Content-Type: application/json' \
  -d '{"mission":"ディレクター付きで江戸の妖怪をテーマにしたアドベンチャーゲームのプロジェクトを作って"}'
```

Watch `/monitor/` and `.local/agent/gateway/run-NNNN.log`; the mission is
over when `.local/agent/done` exists (drive.sh budget: 12 sessions default).

Judgment, from the braindump:

- **Success**: two NEW repos in `autodev` (`<name>` and `<name>-direction`,
  name at the agent's discretion — judge the pair and the paths, not the
  name), cloned at `.local/projects/<name>/main/` and `direction/`.
- **Failure**: only one repo created.
- Additional check: `.local/projects/projects.md` now carries two lines —
  scifi and the Edo project (the braindump expects both present).

Also observe and record (not pass/fail): did the agent do the repo work
itself and plant `concept.md` itself (the role intent), or delegate to a
coding-agent job? Did it update projects.md unprompted? Evidence:
`.local/agent/sessions/session-NNNN.json` (cost/turns), the run log, gitea's
repo list, and any job directories it created.

## Step 5 — failure handling

On failure, diagnose from the session JSON and run log, then apply the
smallest evidence-driven correction — first candidate is one added line in
`AGENT_GUIDE.md`; an allowlist widening in session.sh only if a tool denial
is actually observed (unlikely: git/curl/mkdir/Write are already allowed).
One correction per retry. `POST /mission` clears the previous `done` file
itself. Repeated identical failures are an ENT result — report them rather
than piling on instructions.

## Step 6 — Test 2: consult the director via /window

```sh
curl -s -X POST localhost:8791/window -H 'Content-Type: application/json' \
  -d '{"text":"江戸の妖怪をテーマにしたゲームのディレクターへ、ゲームの主人公とその目的を提案して"}'
```

Judgment, same as ex1 (braindump 3-1/3-2):

- **Failure**: the window answers the proposal itself.
- **Success**: it identifies the Edo project from the index, launches a
  director session in that `direction/` workspace, passes the request
  through, and relays the director's answer; a thin frame is acceptable.

Observation point: does the answer reflect the planted `concept.md`'s
Edo-yokai theme? Evidence: `.local/agent/window/run-NNNN.json` plus the
inner session transcript if verbatim-relay needs checking (ex1 lesson: the
relay tends to be a faithful digest, and the inner run's cost is recorded
nowhere — note it, don't fight it here).

## Step 7 — report and commit

`ex2/report.md`, minimum contents:

- Both tests' outcomes with evidence, costs, and run/session record ids.
- Deviations: the `/mission` entrance for Test 1 (developer decision), the
  agent's chosen repo name, anything else.
- How far guidance-only reached, what needed evidence-driven correction —
  this is the episode's actual product.
- Next-element suggestions, only from observed need.
- Deus Ex Machina line: Step 1 migration, Step 2 guidance edits, and driving
  the tests were Omni Agent work for the autolab agent — handoff candidate.

Commit pj-agdev (agautolab submodule bump + episode files). Local agstudio
only; pushing to the agstudio gitea mirror / updating agautolab1 via ansible
is out of scope.

## Hints for the implementer (not binding)

- Costs (ex1 + AGENT_GUIDE figures): a window answer $0.1–0.5; a mission is
  the sum of its sessions (small jobs ran $0.09–0.21/iteration); expect $1–3
  for the whole episode.
- Known caveat: harness project instructions (CLAUDE.md-like material) leak
  into in-system agents' sessions and have killed runs on permission denials
  before. If a mission session dies that way, that is itself a reportable
  observation, not something to silently work around.
- The claude binary must be resolved via PATH or the `.local/agent/claude_bin`
  glob — absolute version-numbered paths die on every update (4 prior
  incidents). session.sh already does this; don't hand it absolute paths.
- If a gateway restart is ever needed, kill by PID from
  `lsof -nP -iTCP:8791 -sTCP:LISTEN`, and confirm the new code is serving by
  behavior (e.g. `/guide` content), not by `/healthz` — two prior
  stale-process incidents.
- Window timeout is 300 s and was enough for ex1's nested director run; no
  change expected for Test 2.
