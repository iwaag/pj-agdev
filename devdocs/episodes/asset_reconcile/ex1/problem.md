# asset_reconcile ex1 — problem log

Date: 2026-08-08. None of these issues blocked completion.

## 1. Mediator NOTES lagged durable job state across sessions

- **Symptom:** Sessions 3–7 made plan, approval, reconcile, and git progress,
  but several ended before refreshing `.local/agent/NOTES.md`. Later sessions
  initially saw narration that was multiple steps behind the job.
- **Impact:** Session 8 spent time independently reconstructing state from
  `autolab status`, git history, the manifest, and evidence before continuing.
  It did not repeat requests or make an incorrect mutation.
- **Recovery:** Treat durable job state, git, and per-iteration evidence as
  authoritative; use NOTES as a narrative cache that may lag. Session 8 did
  exactly this and completed safely.
- **Future:** The driver should consider recording a tiny machine-generated
  checkpoint after each session/major mediator action, separate from the
  agent-authored NOTES narrative. A first-class asset operation state would
  also make the three request transitions visible without reconstruction.

## 2. Permission-command friction recurred

- **Symptom:** The three coding-agent iterations recorded 13 permission
  denials. Most were compound shell probes or commands outside the explicit
  allowlist (`file`, broad environment/tool discovery, and chained gate
  invocations). The mediator separately found `rm`, some multi-line inline
  scripts, and a few compound git forms blocked.
- **Relation to prior episode:** This is the same class of friction as the
  parent episode's permission-classifier problem, although it no longer
  prevented workspace mutation or required user action.
- **Impact:** Extra turns and workaround code increased cost and duration. No
  gate, asset, commit, or deploy result was invalidated.
- **Recovery:** Agents split commands, used the allowed `node`/`python3`
  paths, used `git -C`, and wrote a temporary script instead of relying on a
  denied destructive/compound command. All iterations ended successfully.
- **Future:** Add proven mechanical commands (`file` and narrowly scoped
  serve-directory replacement) to the node's explicit allowlist, and continue
  teaching agents to prefer simple single-purpose commands. Do not switch to
  unrestricted permission skipping.

## 3. Operator-side Ansible and zsh invocation mistakes

- The first reachability playbook was launched from the agforge directory, so
  Ansible did not load `ansible_agdev/ansible.cfg` and tried the wrong SSH
  authentication. Re-running from `ansible_agdev/` passed immediately.
- The first served-file checksum loop put a whitespace-separated scalar in a
  zsh loop; zsh treated it as one path and curl rejected the combined URL.
  Re-running with an explicit array verified all eight paths.

Both mistakes failed before changing target product state. They should remain
documented because the successful commands are cheap to copy next time.
