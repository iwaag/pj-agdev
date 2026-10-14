# The recovery recipient's initial content (observer p3)

The `agops` project (a managed project of the agdev area, its own Gitea
repository) holds the `recover` workflow and the recovery agent's guide.
These files are what it was created with; the project's repository is
authoritative afterwards. Observer requests a recovery run by posting a
`request-<incident>` topic in `wf-agops.recover`; WFE's intake accepts it from
the agent requester named in `zulip.json` (`intake.agents`).

- `devdocs/workflows/recover.yaml` — one `do` node, manual documentation
  policy, agent `recovery-agent`, profile `sonnet`, Zulip requests.
- `agent/guide.md` — the recovery agent's contract.
