# S5 Plan — Build, finish, then improve a three-choice quiz on agautolab1

Provenance: AI-generated from the user's request and the Step 5 failure report.

## Goal

Use the external-task-manager flow to create a real development project on
`agautolab1`, build and deploy a small three-choice browser quiz, let the user
try the completed first version, and then turn one concrete dissatisfaction
into a second task that improves the same project.

This pass is complete only when both distinct cycles have finished:

1. initial request -> Plane issue -> manual Execute -> autolab job -> deployed
   and usable version 1 -> Plane progress comments and Done; and
2. dissatisfaction after using version 1 -> new Plane issue -> manual Execute
   -> improvement job against the same repository -> updated deployment ->
   Plane progress comments and Done.

The human confirms in a browser that version 1 is a complete game before the
improvement complaint is filed, and confirms afterward that the complaint was
actually addressed.

## Why this replans the failed Step 5

The previous attempt stopped correctly because Plane's placeholder ProjectA
had no source repository or registered autolab project behind it. This plan
makes project identity and mapping a hard precondition rather than something
the implementation mission is expected to infer.

There are four related but different registrations, and the report must not
conflate them:

| Layer | Identity in this pass | Evidence |
|---|---|---|
| agautolab development project | `three-choice-quiz` | `GET /projects` row |
| source | Gitea `autodev/three-choice-quiz` plus `autodev/three-choice-quiz-direction` | repository API/read and commit IDs |
| runtime service | a new static-web placement on `agautolab1` | `nctl drift`/`relations` and working browser URL |
| task management | the existing Plane project renamed from placeholder ProjectA to a quiz-specific name, retaining its UUID | Plane project read plus the deployed project UUID |

Keeping the existing Plane UUID avoids silently breaking the project-scoped
assistant passthrough and the credentials already deployed to agautolab1. Do
not create a second Plane project unless renaming the placeholder is impossible;
if a replacement is necessary, update and verify both the assistant and node
configuration before accepting any issue.

## Starting evidence (checked 2026-08-11)

- `nctl status --json` is healthy: Nautobot is reachable and authenticated,
  one worker is running, and there are no pending jobs.
- `nctl drift --host agautolab1 --json` reports both the node and compute
  instance converged.
- agdevworld's autolab boundary reports `agautolab1` reachable and `agstudio`
  unreachable. Preserve both configured rows; an unavailable row is still
  meaningful state.
- `GET /api/autolab/agautolab1/projects` returns no projects. This is the
  missing condition exposed by `external_taskman/report5.md`.
- `cagent-snake-e2e` is already a separate static web placement on
  `agautolab1`. It is not the quiz project and must not be renamed, reused, or
  overwritten. Let cluster intent choose or validate a non-conflicting
  endpoint/port for the new service.
- The node observation currently resolves the operational connection address
  independently of the desired primary address. Use rendered production
  inventory and nctl-derived routes rather than embedding either IP in this
  episode or in project source.

## Step 0 — Establish the target and prove the mapping

Before filing the first implementation issue, use the agautolab1 conversational
window to bootstrap only the project identity, not the game implementation:

1. Create the two public repositories under the existing `autodev` Gitea org:
   `three-choice-quiz` and `three-choice-quiz-direction`. If either name already
   exists, inspect it and reuse it only when it is clearly this unfinished
   project; never overwrite an unrelated repository.
2. Clone them under `.local/projects/three-choice-quiz/` as `main/` and
   `direction/`; initialize the direction repository with its normal
   `GUIDE.md`, `concept.md`, and `.gitignore`; and list the project in
   `.local/projects/projects.md`.
3. Give the project an explicit `coding`/`director` profile selection only if
   the user or mediator has a reason to depart from node defaults. Missing
   settings may intentionally inherit the defaults, but `/projects` must show
   the effective values without an error.
4. Rename Plane's placeholder ProjectA to a quiz-specific display name while
   retaining its project UUID. Record the mapping from that UUID to
   `three-choice-quiz` in the Plane project description and in the local
   execution report; do not place local URLs or credentials in either repo.

Preflight acceptance:

- `/projects` contains one healthy `three-choice-quiz` row;
- both Gitea repositories exist and the local clones point to them;
- the Plane project read shows the quiz name and the same UUID already used by
  the assistant and `.local/plane.env`;
- the Plane issue list contains no stale issue that could be mistaken for
  either cycle below; and
- agautolab1 is reachable and idle.

If any item fails, stop before creating an implementation issue and report the
actual mismatch. This is the explicit guard missing from the old Step 5.

## Step 1 — File and dispatch the version-1 implementation

Enter the initial desire through the agdevworld prime-agent conversation. The
prime agent creates one Ready Plane issue for project `three-choice-quiz`.
Its description should identify that project by name and ask for an outcome,
not prescribe a framework.

The bounded version-1 product is:

- a browser game with a clear start, question, and result flow;
- at least five bundled questions, each with exactly three visible choices and
  one correct answer;
- one answer accepted per question, visible correct/incorrect feedback, score
  accumulation, progress through the set, and a restart action;
- usable with mouse/touch at a phone-sized viewport as well as desktop; and
- no backend, login, analytics, generated assets, or external content service.

Implementation details, visual style, framework, and test tooling remain the
coding agent's judgment. The mediator should create a job linked with
`project: three-choice-quiz`, work against the registered main repository,
and push converged commits to its existing origin. If it uses autolab's plan
phase, the mediator reviews the proposed acceptance gates and approves or
rejects them; the unattended human is not expected to answer mid-mission.

From the tasks view, the human manually selects `agautolab1` and presses
Execute. Verify the existing orchestration rather than bypassing it:

- Plane moves Ready -> In Progress;
- the mission contains the Plane issue ID, issue title/description, and the
  explicit autolab project name;
- the mediator comments when it creates the job, after completed iterations
  with gate results, and at terminal outcome; and
- convergence moves the issue to Done. A stuck/error run gets evidence and a
  justified Ready or Cancelled transition, never a manufactured Done.

## Step 2 — Deploy version 1 and obtain human acceptance

After the coding gates converge, the mediator asks the cluster agent through
`autolab-cagent` to register the finished quiz as its own static web service on
`agautolab1`. The cluster agent owns the desired-state write. Use `nctl` to
inspect the resulting relation, render/use the production route, reconcile as
needed, and verify the service without direct ad-hoc SSH.

Technical acceptance for version 1:

- repository tests and production build pass;
- the pushed Gitea commit is the commit deployed by the service placement;
- the service is HTTP-reachable from agstudio and through the intended LAN/VPN
  browser address;
- a browser smoke pass completes all questions, produces the expected score,
  and restarts cleanly at desktop and phone-sized viewports;
- `nctl drift --host agautolab1 --json` has no new error/warning attributable
  to the quiz deployment; and
- the version-1 Plane issue contains the job, gate, commit, deployment, and
  final-state evidence without secrets.

The user then plays the deployed game and explicitly confirms that it is a
completed, usable first version. Do not file the improvement issue before this
checkpoint; otherwise the experiment cannot distinguish initial completion
from continuous unfinished implementation.

## Step 3 — Capture a real dissatisfaction as a second issue

After the version-1 checkpoint, the user tells the prime agent one concrete
dissatisfaction observed while playing. The prime agent creates a new Plane
issue in the same mapped project, references the version-1 issue/commit, and
states an observable improvement outcome. This is a new desire through the
Single Entrance, not feedback injected directly into a running job and not a
reopening of the completed implementation issue.

Prefer the user's actual reaction. If a deterministic rehearsal is needed and
version 1 really lacks it, a suitable example is: "正解か不正解かだけで、なぜその答えなのか分からず物足りない。回答後に短い解説を読みたい。" The issue should then require an
explanation after each answer without prescribing its code structure. Do not
use that example if version 1 already provides explanations; record what the
user genuinely dislikes instead.

Before dispatch, verify that the issue is Ready, names
`three-choice-quiz`, and does not broaden into a new game or project.

## Step 4 — Improve the same project through the full flow

Manually Execute the dissatisfaction issue on `agautolab1`. The mediator must
resolve the existing project row and create a fresh improvement job against
the current main-repository head. It must not create another repository or a
parallel replacement service.

The improvement gates include both:

- regression evidence that the complete version-1 quiz flow still works; and
- an assertion or browser check that directly demonstrates the complaint's
  requested outcome.

Push the converged improvement commit, update the existing runtime placement,
and verify the served revision. Exercise the same Plane comment and state
flow as in Step 1. The user repeats the scenario that caused the complaint and
confirms that the new behavior resolves it. A technically green build without
that human check is not the final acceptance for this episode.

## Step 5 — Evidence and report

Write step reports as useful and finish with `s5/report.md`. Retain sensitive
or bulky raw artifacts only under ignored `.local/` paths. The tracked report
should include:

- the final identity mapping across Plane, `/projects`, both Gitea repos, and
  the runtime service;
- both Plane issue IDs and their state histories, with concise summaries of
  mediator comments and any reporting failures;
- both autolab job names, iteration/gate outcomes, costs, and final commit IDs;
- the version-1 browser acceptance and the exact later dissatisfaction;
- before/after evidence showing how the second commit addressed it;
- the final browser URL in an environment-appropriate local report only if it
  should not be committed, plus reproducible read-only checks in the tracked
  report;
- `nctl` status/drift evidence before and after deployment; and
- what the agents did well or badly with Plane, project selection, and cluster
  registration, so a later ENT episode can harden only evidenced weak points.

Keep the two cycles legible as separate timelines. A final working game alone
does not prove that complaint -> second issue -> same-project improvement was
exercised.

## Constraints and stop conditions

- Never commit Plane/Gitea tokens, `.local/plane.env`, credentials, generated
  transcripts, or secret-bearing URLs.
- Do not remove the configured but unreachable `agstudio` autolab node and do
  not modify or appropriate `cagent-snake-e2e`.
- All user desire enters through the prime-agent conversation. The Step 0
  bootstrap window call is an explicit target-provisioning precondition and
  must not implement product features.
- Manual Execute remains the dispatch boundary for both product tasks; do not
  post their missions directly to `/window` to make the demo pass.
- Use the cluster agent/nctl/managed Ansible paths for node and desired-state
  work. Do not assume a fixed IP or allocate a port by guesswork.
- No `--dangerously-skip-permissions` or equivalent bypass on agautolab1.
- Do not declare either cycle successful unless its actual Plane API calls,
  autolab evidence, pushed commit, deployed revision, and browser behavior all
  agree.

Everything else—including the game theme, source layout, framework, styling,
test library, and the exact improvement chosen after human use—is left to the
agents and user. This preserves Tool Giving and Failure Farming without again
starving the run of a real target.
