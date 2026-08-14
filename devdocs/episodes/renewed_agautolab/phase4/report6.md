# Phase 4 Step 6 Report — deploy

Everything in this phase is deployed. `agautolab1` runs `64284e6`, the same
commit as local `main`.

## What was pushed

| repo | commit | remote |
|---|---|---|
| pyagag | `2bb458f` | GitHub `main` |
| agautolab | `64284e6` | GitHub `main`, and the agstudio gitea mirror |
| pj-agdev | `963258d` | GitHub `main` |

## Correction: `agautolab1` deploys from GitHub, not from gitea

`.local/devenv.md` and phase 3's report5 both said the node deploys from the
agstudio gitea. **That is wrong**, verified live here by re-rendering the
production inventory from Nautobot (`nctl render production`, 27 placements
applied, read-only) and reading the result:

- `agautolab1` → `autolab_node_repo_url: https://github.com/iwaag/agautolab.git`
- `agstudio` → `http://agstudio.local:3000/autodev/agautolab.git`

The gitea URL belongs to the **agstudio** placement — this Mac's own checkout —
not to the node. The `autolab_node` role default
(`roles/autolab_node/defaults/main.yml:7`) is GitHub as well. So no repoint was
needed, and the phase 3 "blocked deploy" note is resolved by the facts rather
than by an action: the placement it wanted to change does not exist that way.

The gitea push was still made (mirror `main`: `f777634` → `64284e6`), per the
localrule "push every commit, then reflect it onto the consumers". Its only
consumer was the agstudio placement.

**Follow-up, same day:** the developer then corrected the `agstudio`
placement's `repo_url` in the Nautobot desired state as well. Re-rendered and
confirmed: both `agautolab1` and `agstudio` now carry
`https://github.com/iwaag/agautolab.git`. **The agautolab gitea mirror is
therefore dead — nothing deploys from it, and nothing may be pointed back at
it.** It was created to work around the GitHub-deploy rule, it went silently
stale, and a node deploying from a stale mirror runs superseded code while
accepting missions. `localrule.md` forbids this ("ローカルgitea参照に変えると
か…絶対にするな") and `.local/devenv.md` now says so at the point of use. The
gitea instance itself stays — it hosts the generated project repositories
(`<project>`, `-direction`, `-devlog`), which are workspaces, not a deployment
source.

`.local/devenv.md` has been corrected in place, with the verification command
(`ansible … -a "git -C /home/eiji/agautolab rev-parse --short HEAD"`) added so
the next reader checks instead of trusting the prose.

## Playbook run

```sh
cd pj-clusterintent/ansible_agdev
uv run --project ../nctl nctl render production --out inventories/generated
AUTOLAB_NODE_PLANE_CREDENTIALS_SOURCE=$PWD/../../pj-agdev/.local/plane-credentials.env \
  ansible-playbook -i inventories/generated/production.yml \
  playbooks/agent/setup_autolab_node.yml --limit agautolab1
```

`ok=25 changed=3 unreachable=0 failed=0` — the changes were the checkout
update, a gateway unit refresh, and the gateway restart; the health probe
passed afterwards. Deployed HEAD confirmed as `64284e6`.

As expected from earlier phases, this run also carried phases 1–3 to the node
in one go.

## agstudio

`launchctl kickstart -k gui/$(id -u)/com.agdev.agautolab-zulip` — the listener
came back up and immediately demonstrated the new dispatch on the leftover E2E
topic:

```
sweep matched 'general'/'mission-stray-in-general'
ignoring 'mission-stray-in-general': 'general' is not a project channel
```

`.local/agents.local.toml` is back to `profile = "local"` for both `front` and
`coding` (the E2E ran on `sonnet`; see report5).
