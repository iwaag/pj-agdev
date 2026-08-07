# asset_reconcile — plan

Goal: prove the director-agent pattern end to end once. A coding agent makes
the othello game able to show a background image; a **director** agent decides
the creative spec, requests the asset from agforge, reviews it leniently, and
delivers it into the game repo. See `braindump.txt` for rationale.

This is an experimental environment in a breaking-change phase: no backward
compatibility, minimal ceremony. The implementer has wide latitude on code
shape; only the boundary rules below are fixed.

## Fixed decisions (from braindump + discussion)

- **director** is a small one-shot runner (clusterintent-executer style: a
  tiny script driving one headless `claude -p` call per question), backend
  `claude-sonnet-5`. Not a general-purpose agent.
- **Context isolation is by placement, not prose.** Direction material lives
  in a separate repo/folder *outside* the game target repo, so the coding
  agent physically cannot read it. Conversely the director's knowledge base
  is the direction folder only; from the game repo it may read exactly two
  things: the asset manifest (the contract) and the delivered asset files it
  is reviewing. The point is context hygiene, not security.
- **The contract is a file, not chat**: `assets/manifest.json` in the game
  repo. Technical fields (path, format, dimensions) are owned by the coding
  side; creative fields (theme, style) are owned by the director. Neither
  side edits the other's fields.
- Asset transport: agforge's existing presigned-URL flow. The director
  downloads the URL and copies the file into place; nothing new to build on
  the agforge side.
- **agforge is desire-only by design.** The service takes prompt text and
  nothing else; quantitative requirements (resolution etc.) are stated in
  the desire text, and it is agforge's internal job to figure out how to
  satisfy them — or refuse. Callers never pass individual generation
  parameters. If agforge keeps returning the wrong size, that is an agforge
  defect: **stop the episode there and report it as a blocking point that is
  out of scope to fix here.** Do not work around it by relaxing the check,
  resizing the image yourself, or modifying the agforge service.
- The work targets the **existing othello job workspace on agautolab1.local**
  (deployed in the autodev episode — see `devdocs/episodes/autodev/report.md`
  and `report6.md`): the autolab job dir with `target/` tracking
  `autodev/othello-web` on the agstudio gitea. Don't set up a fresh clone
  elsewhere.

### Contract: `target/assets/manifest.json`

```json
{
  "requests": [
    {
      "id": "background",
      "path": "assets/bg/background.png",
      "format": "png",
      "width": 512,
      "height": 512,
      "status": "requested"   // coding side sets "requested"; director sets "delivered"
    }
  ]
}
```

Exact schema is the implementer's call — keep it this small. `id`/`path`/
`status` are the load-bearing parts.

## Step 1 — coding side: background support + manifest

Run an autolab job in the existing othello job workspace on agautolab1.local
(the `claude_code` adapter with `skip_permissions` is already proven there;
push the result to the gitea `main` as in Step 6 of autodev):

- `index.html` renders `assets/bg/background.png` as the board page
  background **if the file exists**; game must remain fully playable and all
  10 existing acceptance tests must keep passing when it doesn't.
- Add `assets/manifest.json` with the `background` request (`requested`).
- Add a gate script (e.g. `test/background.test.mjs`) that passes only when
  every manifest entry with `status: "delivered"` exists on disk, is a
  decodable image of the declared dimensions, and is referenced from
  `index.html`. With no delivered entries it must pass trivially — that keeps
  the game repo green before and after delivery.

The coding agent decides resolution/format/path (technical fields). It never
sees the direction folder.

Done: fresh clone renders unchanged without the asset, tests pass, manifest
and gate committed.

## Step 2 — direction workspace + director runner

- Create the direction workspace as its own folder, outside the game repo
  (a gitea repo `autodev/othello-direction` is nice for symmetry but a plain
  local folder is acceptable for this first pass).
- Content is deliberately minimal: `brief.md` with one line, e.g.
  "A medieval, old-fashioned atmosphere Othello game." Plus an empty
  `reviews/` folder.
- Director runner: a small script (repo home: implementer's choice;
  `pj-agdev/` somewhere sensible) that, given the direction folder and a
  manifest, can answer one question at a time via `claude -p` — e.g.
  "compose the agforge desire text for this request" and later "does this
  image match the brief, yes/no + one sentence".

Done: runner produces a sensible desire string from brief + manifest entry
(e.g. "medieval town street, oil painting style, game background, 512x512").

## Step 3 — request, review, deliver

Director flow, driven by the runner (plain script glue around the LLM calls):

1. Read manifest entries with `status: "requested"`.
2. Compose desire text (LLM: brief + technical fields).
3. `POST /api/requests {"desire": ...}` to the agforge service, poll
   `GET /api/requests/{id}` until `done`/`failed`, download the presigned
   artifact URL.
4. Mechanical check (no LLM): file decodes as an image, dimensions match the
   manifest. A dimension mismatch is an agforge defect: re-request once,
   and if it still mismatches, **stop and report blocked** (see fixed
   decisions) — do not resize or relax. Subjective check (LLM, **lenient** —
   agforge is immature): one yes/no "roughly matches the brief?" with the
   image attached. Reject only on clear failure; on reject, re-request once,
   then stop and leave the verdict for the human.
5. On accept: copy into `assets/bg/background.png` in the game checkout, set
   `status: "delivered"` in the manifest, commit.
6. Write `reviews/background.md` in the direction folder: desire text used,
   agforge request id, mechanical results, subjective verdict
   (`accepted` / `provisional` — provisional means fine for now, queued for
   human final review).

Done: asset committed in the game repo, manifest `delivered`, review file
written.

## Step 4 — verify

- Run the game repo gates (`node --test`): the Step 1 background gate now
  exercises the delivered branch and must pass alongside the original 10.
- Human eyeball: open `index.html`, background visible, board readable.

Done: all gates pass; screenshot or one-line human confirmation noted.

## Step 5 — report

`report.md` in this folder: what ran, costs, whether the manifest contract
and the placement-based isolation actually held (did any agent try to read
across the boundary?), agforge quality impressions, and follow-ups (obvious
candidates: director as a persistent service, more asset kinds, wiring the
director call into the autolab loop itself).

## Hints and gotchas discovered while planning

- agforge service: `agforge/service/serve.sh`, port 8092. Jobs are
  **in-memory only** — a restarted service 404s old ids; just re-POST.
  Generation takes tens of seconds; poll every few seconds.
- `model` is the only required SwarmUI param and has **no default in
  `params/defaults.toml`** — confirm `AGFORGE_SWARMUI_MODEL` is set in
  `agforge/.local/.env` before blaming your code. Endpoints/quirks live in
  `agforge/.local/devenv.md`.
- Size goes in the desire text (e.g. "..., 512x512") — the service is
  desire-only by design and that stays. `generate.sh --width/--height`
  exists underneath, but whether agforge's internals honor a size stated in
  the desire is agforge's responsibility; if it doesn't, that's the blocking
  point defined above, not something to patch in this episode. Tip: pick
  dimensions SD-family models like (multiples of 64, e.g. 512x512) to give
  agforge a fair chance.
- Presigned URL host comes from `AGFORGE_S3_ENDPOINT` — must be reachable
  from wherever the director runs (never `localhost` if crossing machines).
- Delivery route to the VM workspace: the director runs on agstudio, so the
  clean path is commit+push the asset/manifest to the gitea `main` from a
  local clone, then pull inside the VM's job `target/` (which already tracks
  that remote). Direct `scp` from agstudio hit the permission classifier in
  autodev Step 6 — ssh-with-stdin or the git route avoids that friction.
- Never write to the `nctl-outbox` bucket; agforge has its own `agforge`
  bucket. Don't commit endpoints/credentials/generated images to agforge.
- Quick local image checks on macOS: `sips -g pixelWidth -g pixelHeight`, or
  Python/Pillow via `uv run`.
- Gate wisdom from autodev: bare `node --test` (a directory argument
  misbehaves on newer Node); validate the new gate fails/passes correctly
  against a throwaway fixture *before* letting an agent loop on it.
- `claude -p --output-format json` one-shot with prompt on stdin is the
  known-good headless pattern (see agautolab's `claude_code` adapter for
  flags and cost-field capture). Attaching an image to a one-shot review
  call: pass the file path in the prompt and allow the Read tool.
- Keep waits short per local policy: poll loops with a hard timeout
  (~3 min per generation), fail loudly rather than hang.

## Out of scope

Multiple asset kinds, music/video, director-in-the-autolab-loop automation,
prime-agent integration, human final-review tooling, agforge quality
improvements.
