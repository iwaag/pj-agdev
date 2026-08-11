# Step 0 report — target identity and mapping

Status: **complete** on 2026-08-11.

## Result

The four identities now have an explicit, verified mapping:

| Layer | Identity | Evidence |
|---|---|---|
| agautolab project | `three-choice-quiz` | `/projects` returns one row with `coding=local` and `director=local`, both sourced from node defaults |
| main source | `autodev/three-choice-quiz` | public Gitea repo; intentionally empty before the implementation issue |
| direction source | `autodev/three-choice-quiz-direction` | public Gitea repo at commit `de8cddad1c951a57937bfbe202e760f8d1544fb2` |
| task manager | Plane project `Three Choice Quiz` (`PA`) | retained UUID `76f39ab2-b921-42da-bee2-0426a1162760`; its description records the autolab and repository mapping |

The node clones are under the normal ignored project workspace as `main/`
and `direction/`. The direction head contains exactly `.gitignore`,
`GUIDE.md`, and `concept.md`; the main clone has zero commits. The project
index contains exactly one `three-choice-quiz` line. No per-project
`agents.toml` was added, so the effective profiles intentionally inherit the
node defaults.

Plane had zero issues after the rename. The project UUID agrees across the
controller credential bundle, agdevworld assistant configuration, deployed
node configuration, and the Plane project read. `agautolab1` was reachable
and idle at the final preflight; the unavailable configured `agstudio` row was
preserved.

## Bootstrap timeline

1. Window run 7 failed before doing work because the front agent misspelled
   the checkout path and requested access outside its workspace.
2. Window run 8 spent its 300-second budget attempting read-only operations;
   the front role correctly had no Bash grant and made no project change.
3. Window run 10 emitted provisioning mission run 6, but both mediator
   sessions failed immediately: gateway children resolved system `python3`,
   which could not import the locked `agag` dependency.
4. The deployment role now prepends the checkout `.venv/bin` to the gateway
   service PATH. The Ansible role change is `a8e38b3`; the parent
   pj-clusterintent pointer update is `0a83032`. Syntax check passed, the
   managed deployment completed with 25 tasks OK and no failures, and both an
   `.venv` import probe and the active systemd environment confirmed the fix.
5. Window run 12 reissued the same bootstrap request without inspecting the
   workspace. Provisioning mission run 7 completed in mediator session 13:
   20 turns, 569 seconds, local profile, reported cost `$0.00`. It created the
   repo pair and clones, pushed the direction seed, registered the project,
   and successfully exercised the effective director profile with a `ping`.
6. The mediator then incorrectly reported both repos as public. An
   independent authenticated Gitea read found `private=true` for both.
   Correction mission run 8 ignored its mission in both sessions and ended
   with exit 10 without changing state. The Omni Agent changed only these two
   repository visibility fields and verified authenticated `private=false`
   plus unauthenticated repository reads — did repository visibility
   correction for the mediator, handoff candidate.
7. The existing Plane placeholder was renamed and described through its API;
   its UUID and `PA` identifier were retained.

No product feature, coding job, Plane issue, or deployment was created during
this step. `cagent-snake-e2e` was not modified or reused.

## Baseline and reproducible checks

Before bootstrap, `nctl status --json` returned `ok=true`, one running worker,
and zero pending jobs (operation `01KZRDPFB3NB4CHV8N7KWE2S16`).
`nctl drift --host agautolab1 --json` returned two converged targets and no
warnings or errors. After target provisioning, status operation
`01KZRFA6THNGWXYREGS3EDJFW7` again reported one worker, zero pending jobs, and
no errors; drift again reported two converged targets with zero warnings and
errors. The final target-provisioning checks were:

```sh
curl /api/autolab/agautolab1/projects
curl /api/plane/issues?per_page=100
curl /api/v1/repos/autodev/three-choice-quiz
curl /api/v1/repos/autodev/three-choice-quiz-direction
uv run --project nctl nctl status --json
uv run --project nctl nctl drift --host agautolab1 --json
```

The abbreviated paths assume the configured agdevworld, Gitea, and nctl
origins; no credential or secret-bearing URL is recorded here.
