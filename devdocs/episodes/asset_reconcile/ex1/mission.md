# Mission

Re-verify the agforge ↔ autolab integration end to end by building a very
small browser gallery app. You are the node-side mediator: set up and drive
one normal autolab job, reconcile its planned assets before approval, audit
the result, and install the verified app for the gateway to serve. Do not
implement the app or its tests yourself.

## Repositories and boundaries

- Gitea is `http://agstudio.local:3000`, organization `autodev`; the token is
  in `.local/gitea/autolab-agent.token`. Keep credentials only in `.local/`
  or git configuration, never in tracked content.
- Clone `autodev/gallery-direction` as a separate direction workspace. It
  contains `brief.md`, ignored candidate staging, tracked `reviews/`, and the
  tested tools `tools/director.py` and `tools/reconcile.py`.
- Use `autodev/gallery-web` as the coding job's `target/`. It starts empty.
  Set `push: true` and omit `gates` so the job starts in plan phase.
- The coding agent must never receive or read the direction repository or its
  brief. The director must receive only the direction brief, one technical
  manifest entry, and the candidate image it reviews. This is placement-based
  context hygiene.

Pass this client goal to the coding agent nearly verbatim:

> Build a self-contained browser gallery app that displays three images and
> switches between them with buttons. The images will arrive later through an
> asset manifest that you define during planning. The manifest must contain
> only technical and surface-level requirements such as paths under the target
> repository, PNG format, exact dimensions, stable request IDs, and delivery
> status. Plan and propose deterministic acceptance gates for the app and for
> the delivered assets. Do not assume creative subject matter. After assets
> are delivered, implement and verify the complete app with no external
> runtime references.

Use the `claude_code` adapter pointed at `.local/agent/claude_bin`, with a
generous explicit allowed-tools list suitable for a small static web app.
Never use `skip_permissions` or `--dangerously-skip-permissions`. Use a
session/iteration budget large enough for plan review, asset generation, and
implementation (for example 10 job iterations, 900-second iteration timeout,
and 300-second gate timeout).

## Plan review at exit 40

Run the job until it reaches `awaiting_approval` / exit 40. Before approving,
inspect `target/PLAN.md`, `target/proposed_gates.yaml`, and the manifest
(normally `target/assets/manifest.json`). Require all of the following:

1. Exactly three image entries, each with a stable ID, safe relative path
   under `target/`, `format: png`, positive exact width and height (1024×1024
   is the proven choice), and `status: requested`.
2. The manifest has technical fields only. Creative content, theme, scene,
   style, prompt, or direction text in it is a boundary violation.
3. The plan maps every client requirement to a non-trivial proposed gate.
   Gates must cover gallery switching behavior and the delivered asset branch:
   PNG signature/decodability, exact declared dimensions, file presence, and
   actual reference by the app. They must not pass an empty or stub project.

If anything is missing or the creative/technical boundary is entangled, use
`autolab reject --feedback ...` and let the coding agent re-plan. Record the
round trip in NOTES. Do not repair the plan, manifest, or gates yourself.

## Asset reconcile before approval

While the job remains `awaiting_approval`, reconcile each of the three
`requested` entries exactly once by invoking the direction repository's
`tools/reconcile.py` with:

- the direction workspace;
- the job target manifest;
- that entry's request ID;
- `http://agstudio.local:8092` as agforge URL;
- `DIRECTOR_CLAUDE_CMD` set to the path stored in
  `.local/agent/claude_bin`.

For each entry the tool must perform director compose → agforge POST/poll →
direct download from the presigned `agstudio.local:9100` URL → deterministic
PNG signature/decode/dimension check → lenient director review → exact-byte
copy to the declared target path → change only that entry's status to
`delivered`. It allows at most two agforge attempts per image and never
transcodes, resizes, or renames bytes to manufacture a pass. Do not call it a
second time after it exhausts those two attempts; that is a terminal asset
failure for this mission.

After every image (including a failed one), commit and push the tracked
director evidence in `gallery-direction`: full compose/review JSON envelopes,
verdict, desire, cost/timing metadata, and every agforge request ID. Candidate
bytes stay ignored. Do not commit the delivered files or manifest changes in
`gallery-web`; the coding agent owns those bytes and must commit them in its
first implement iteration.

If any entry exhausts two attempts, push its evidence, write an honest
`STATUS: blocked` with the exact failure, and stop. Otherwise confirm all
three entries are `delivered`, then approve the existing plan and loop the job
to a terminal state. Confirm from iteration evidence that the coding agent,
not the mediator, committed the assets and gates.

## Final node-side audit and install

On convergence, independently audit the exact committed `gallery-web`
revision rather than relying only on its self-authored gates:

- run the accepted tests/gates and record their outputs;
- verify all three committed files are valid PNGs of the manifest dimensions
  and byte-identical to the accepted candidate evidence where available;
- verify the app references exactly those local assets, has three controls
  whose logic switches the visible image, and has no external runtime URLs;
- identify the exact static build/source tree audited, install only that
  verified product into `.local/agent/serve/`, and probe it through
  `http://127.0.0.1:8791/game/` including every required file;
- record the served git revision and the direction evidence revision.

Finish `.local/agent/NOTES.md` with the standard first line `STATUS: complete`
only after the audit, install, and gateway probes pass. Include job state,
served revision, direction revision, per-image attempt/request IDs, session
cost/timing summaries available on disk, and exact evidence paths. Use
`STATUS: blocked` only for a genuine terminal failure with the recovery facts
needed by the operator.
