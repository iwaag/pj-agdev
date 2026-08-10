# ex2 Step 2 report — guidance text

Executed by the Omni Agent on 2026-08-10. This is the experiment's only real
change: guidance text, no harness edits.

## What was done

- **`agautolab/AGENT_GUIDE.md`** — appended the "## Projects" section exactly
  as written in the plan: a project is a repo pair (`<name>` /
  `<name>-direction`) under the `autodev` gitea org, the autolab agent
  creates the pair and plants the direction files itself, local clones live
  under `.local/projects/<name>/` as `main/` and `direction/`, and
  `.local/projects/projects.md` lists every project.
- **`agautolab/agent/GUIDE.md`** — replaced the "Project directors" section
  (its paths pointed at the retired `.local/direction/` layout) with the
  plan's text pointing at `.local/projects/<name>/direction/`.

Per the plan's Failure Farming stance, nothing was added about the order of
operations, updating `projects.md` on creation, the main repo's initial
contents, or the wording of the director files.

## Verification

- `curl -s localhost:8791/guide | tail` serves the new "Project directors"
  section — the window card deployed with no restart, as expected (GUIDE.md
  is re-read per request; AGENT_GUIDE.md is read from disk per mission
  session).

## Commit

agautolab `bdc7b42` — "Guidance for director-attached projects; repoint
director paths to .local/projects/". The submodule bump in pj-agdev happens
in Step 7.
