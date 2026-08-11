# Turn 1 report — autolab project profile selection from agdevworld

## Result

Turn 1 is complete. A user can now see every agstudio autolab project's
effective coding/director profiles in agdevworld and change either selection
by asking the prime agent. The write stays inside the node's conversational
window; the deterministic route is read-only and confirms the result.

The delivered path is:

1. agautolab `GET /projects` returns `autolab.projects.v1`, with available
   profiles, effective role selections, value sources, and per-project errors.
2. Gateway job rows/details retain the optional `project` field.
3. The front role has general Edit/Write capability and a capability card that
   describes project profile settings.
4. agdevworld fetches projects through the existing bounded passthrough and
   renders read-only project cards ahead of jobs.
5. The prime agent knows to read the project, ask the node window to change it,
   and confirm with another read. No direct write endpoint or UI selector was
   introduced.

The passthrough's evidence-path 403 and the node scope of agstudio only remain
unchanged.

## End-to-end evidence

The final pass used the production-style web and assistant containers and the
live agstudio gateway:

- Prime chat changed `yokai` coding `local → sonnet`.
- The prime agent's confirmation, `GET /projects`, the ignored project file,
  and a refreshed 1280x800 Playwright view all showed `sonnet`.
- Prime chat changed coding `sonnet → local` and the same evidence surfaces
  showed `local`.
- That return edit unexpectedly removed the explicit director setting, making
  director inherit the `sonnet` default. A follow-up prime chat restored
  director to `local` while preserving coding `local`; the route and file then
  agreed on both explicit values.
- No mission was started during profile changes.

Final `yokai` state: coding `local` from project settings, director `local`
from project settings.

## Verification summary

- agautolab: 97 pytest tests passed.
- agdevworld: 28 Node tests passed; TypeScript and Vite build passed.
- agforge: 58 pytest tests passed after its dependency-source update.
- Live web, assistant, gateway, and assistant passthrough health checks passed.
- `nctl status --json` reported the local Nautobot/intent-catalog environment
  healthy before service work.

Vite continues to emit its existing non-failing Phaser bundle-size advisory.

## Additional dependency correction

The gateway restart exposed that the sibling editable `../../pyagag` source
made standalone installs depend on a particular workspace layout. With human
authorization, agautolab and agforge now declare the GitHub `pyagag` main
branch as their uv source; each lockfile pins the resolved commit. The pyagag
repository itself was already clean and synchronized, so it required neither a
change nor a push.

## Workflow observation

The front agent successfully chose how to edit TOML without an implanted
script, proving the intended Tool Giving path. The director-setting loss on one
rewrite is useful failure evidence: capability alone works, but preserving
unrequested keys should be strengthened through evidence-driven guidance or a
focused regression exercise in a later turn.

No project settings file was edited directly by the Omni Agent.
