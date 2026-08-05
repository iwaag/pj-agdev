# Plan: first_cluster_visualization

Goal (from braindump): make the first working example of cluster visualization in
agdevworld. Download cluster info via pj-clusterintent's cluster-agent (cagent),
save it locally, and render each desired node that exists as actual state as an
emoji + node-name panel that gently floats so it doesn't look like a static GUI.
Engine: Phaser (already in place — agdevworld uses Phaser 4.2.1 + TypeScript + Vite).

## Scope decisions (already made — don't re-litigate)

- The official data path is **asking cagent in natural language** and receiving a
  time-limited presigned download URL in its reply. No new HTTP endpoint on the
  clusterintent side. Real-time updates are out of scope; a manually refreshed
  snapshot is fine.
- Experimental environment: no security hardening required. Backward
  compatibility not required — rewrite `MainScene` freely.

## Architecture

Two decoupled halves, joined by one file:

```
[fetch script] --ask cagent--> presigned URL --download--> agdevworld/public/cluster/state.json
[Phaser scene] --fetch('/cluster/state.json')--> filter nodes --> floating panels
```

The browser never talks to cagent. This sidesteps CORS, self-signed TLS, and the
multi-minute async turnaround entirely, and matches the braindump's
"download → save locally → represent" wording.

## The only hard rules

1. Do not commit the downloaded cluster payload or any cagent token to git.
   Add `public/cluster/` to `.gitignore`; ship a `state.sample.json` instead so
   the scene works without a live cluster. (Rationale: pj-clusterintent policy —
   "Git holds framework and policy, never the private cluster payload".)
2. Read-only toward the cluster. cagent won't mutate on your behalf anyway;
   don't work around that.

Everything else — file layout, panel visuals, animation parameters, script
language (shell vs node), grid vs random placement — is implementer's choice.

## Steps

### Step 1 — Fetch script + snapshot

A small script in `agdevworld/scripts/` (e.g. `fetch-cluster-state.mjs` or `.sh`)
that: submits a request to cagent, polls until `completed`, extracts the
download URL from the reply text, downloads it to `public/cluster/state.json`.

Hints:

- cagent API (see `pj-clusterintent/cagent/src/cagent_api/static/llms.txt` and
  `devdocs/vision/cluster_agent/{p1,p2,p4}/contract.md` for the full contract):
  - `POST /requests` with `{"message": "..."}` → `202 {"request_id", "session_id", "state": "queued"}`
  - `GET /requests/{request_id}` → poll; `response` is null until `state: "completed"`.
  - A real answer can take **up to ~4 minutes**. Poll every 5–10 s with a
    generous overall deadline (~6 min); never block with a short HTTP timeout.
- Two entrances; use whichever is already reachable from your machine:
  - Human entrance `:8789` — static bearer token over self-signed TLS
    (`curl -k -H "Authorization: Bearer $CAGENT_TOKEN"`). Simplest for a dev-machine script.
  - Node entrance `:8788` — mTLS; if this machine is enrolled
    (`~/.cagent/{ca_cert.pem,node_cert.pem,node_key.pem}` exist) the `cagent ask` /
    `cagent status` wrapper CLI is even easier than raw curl.
  - Keep host/token in env vars or `.local/` — not in the script.
- Prompt suggestion: ask for exactly one artifact, e.g.
  *"Please run `nctl drift --json`, save the output as a file, upload it with
  `nctl upload`, and reply with only the download URL."* Constraining the reply
  shape makes URL extraction trivial; a fallback regex like
  `https?://\S+` over the reply text is fine (the URL is MinIO-presigned and
  time-limited — download immediately).
- Acceptance: `public/cluster/state.json` exists and is a valid `nctl.drift.v1`
  envelope (`{schema: "nctl.drift.v1", ok, data: {targets, summary, ...}}`).
  Commit a scrubbed/minimal copy as `state.sample.json`.

### Step 2 — Load + filter in the scene

Load the snapshot (Phaser `this.load.json('drift', 'cluster/state.json')` in
`preload()`, or plain `fetch` — either is fine; fall back to `state.sample.json`
on 404). Derive the node list.

Data contract (`nctl.drift.v1`; producer:
`pj-clusterintent/nctl/src/nctl_core/drift_render.py`, node rules:
`nctl/src/nctl_core/drift/node_evaluation.py`):

- `data.targets[]` = `{target: {kind, slug, name, id}, status, diffs: [{code, severity, message, ...}]}`
- Every desired node appears as a target — absence never means "unchecked".
- **"Exists as actual" rule**: `target.kind === "node"` AND no diff whose `code`
  is one of `missing_actual_node`, `realized_device_missing`, `no_realized_object`.
- Caveat: nodes in `awaiting_manual_initial_access` are skipped by the
  comparators and get an informational diff — treat them as "not confirmed",
  not as existing.
- `status` (`converged | converging | drifting | unknown`) comes for free —
  carry it into the panel model for Step 3.

Acceptance: with the sample file, the filtered list matches a hand count.

### Step 3 — Floating panels

Replace the hello-world `MainScene` content with one panel per node.

Hints:

- Panel = `this.add.container(x, y, [bg, text])`; text via `this.add.text` with
  `backgroundColor` + `padding` alone is already enough for an MVP (the current
  `MainScene` "Push" button shows the exact pattern), or a
  `this.add.graphics()` rounded rect behind the text for nicer chrome.
- Emoji render as system-font glyphs in Phaser text — color emoji work as-is on
  macOS/Chromium. Don't switch to bitmap fonts (they lose color emoji).
  Suggested mapping: ✅ converged, 🔄 converging, ⚠️ drifting, ❓ unknown —
  e.g. `✅ node-alpha`.
- Float: one looping tween per panel, phase-shifted so they don't move in sync:

  ```ts
  this.tweens.add({
    targets: panel,
    y: panel.y + 8,
    duration: 1800 + i * 120,   // vary per node instead of Math.random if you
    delay: i * 250,             // want deterministic motion
    yoyo: true,
    repeat: -1,
    ease: 'Sine.easeInOut',
  })
  ```

  A second subtle tween on `angle` (±1.5°) sells the "not a GUI" feel cheaply.
- Layout: a simple grid/flow centered via the existing `layout(width, height)` +
  `this.scale.on('resize', ...)` pattern already in `MainScene`. Note the tween
  animates `y`, so on resize either kill+recreate tweens or put the float on an
  inner container and move the outer one.
- Dev loop: `docker compose up dev` (Vite HMR on :5173) or `npm run dev`;
  production check via the `web` service on :8090.

Acceptance: all filtered nodes visible, each gently floating out of phase,
window resize keeps them on screen.

### Step 4 — Report

`report.md` in this episode folder (policy: reports strongly recommended), with
a screenshot like the `initiate_agdevworld` episode's reports. State which
entrance the fetch script used and paste the cagent prompt that worked — that
prompt is the de-facto API contract for the next episode.

## Known follow-ups (explicitly not now)

- Automating/scheduling the fetch, or any live refresh.
- Richer data (services/relations via `nctl relations --json`, the
  `nctl.bundle.v1` state bundle) — the loader's filter function is the seam to
  extend.
- Interaction (click a node for details).
