# Report 10 — GitHub is the deployment source; agautolab1's clone is gone

Two instructions after report 9.

## 1. The role default now points at GitHub

`ansible_agdev` (a submodule of `pj-clusterintent`, its own repository):

```yaml
# roles/autolab_node/defaults/main.yml
autolab_node_repo_url: https://github.com/iwaag/agautolab.git   # was the gitea mirror
```

Committed as `38a6f3d` and pushed. The comment above the value says why, so
the next reader does not have to find this report: the Gitea mirror goes stale
silently — it sat two commits behind through this whole episode — and
deploying from it reinstalls the implementation the episode deleted, putting a
node back in a state where it accepts missions and spends money.

**This default is not to be moved back to Gitea.** Report 9 chose a one-run
`-e` override instead of changing it; that was the wrong call, and the
standing instruction is now explicit.

Checked: no other file in `pj-clusterintent` names the Gitea agautolab URL.

## 2. `~/agautolab` on agautolab1 is deleted

30M, including the node's own `.local/` — the job directories and the
auto-development projects (`three-choice-quiz` and the rest) that report 9
flagged as still present. Gone with the checkout. Irreversible; nothing was
copied off the node first.

Sequence, each step verified before the next:

1. `systemctl --user stop/disable autolab-gateway.service` → `inactive`,
   `disabled`.
2. `file: path=/home/eiji/agautolab state=absent` → `changed`.
3. `ls ~` → empty. `ss -ltn | grep 8791` → not listening.

The systemd user unit file itself remains at
`~/.config/systemd/user/autolab-gateway.service`, disabled and pointing at a
`WorkingDirectory` that no longer exists. A playbook run reinstalls the unit
and re-clones the checkout, now from GitHub.

## Where the cluster stands

- **agstudio** — serving the stub on `:8791`.
- **agautolab1** — no checkout, no gateway. The assistant reports it
  `reachable: false, ECONNREFUSED`, which is now the truth about that node
  rather than a fault.

Nothing was redeployed to agautolab1: the instruction was to delete the
folder, and re-creating it in the same breath would have undone that. Say the
word and one playbook run brings it back as a clean GitHub-sourced stub.

## Pushed

Per `localrule.md`, every commit in this episode is now on GitHub:
`agautolab` (`05c1289`), `ansible_agdev` (`38a6f3d`), and `pj-agdev` with the
plan and reports 1–10.
