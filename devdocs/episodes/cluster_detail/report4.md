# Report — Step 4: ingest `nctl actual --detail` (facts_raw)

Status: done.

## What changed

- `scripts/fetch-cluster-state.mjs` — third `ARTIFACTS` entry: command
  `nctl actual --json --detail`, schema `nctl.actual.v2`, env override
  `CLUSTER_ACTUAL_OUTPUT`, output `public/cluster/actual.json`, plus
  `validateActualEnvelope` in the style of the existing validators.
- `public/actual.sample.json` — minimal sample fallback (2 devices matching
  `state.sample.json` node slugs, with representative `facts_raw`: cpu,
  memory, gpu, docker containers).
- `src/clusterState.ts`
  - `ActualDeviceModel` / `ActualEnvelope` types, `parseActualEnvelope`,
    `loadActualDevices()` with the usual live→sample fallback.
  - `matchDeviceForTarget` — devices carry Nautobot names that may be fully
    qualified (`agbach.local`, `agstudio.home.arpa`) while drift targets use
    bare slugs, so matching tries the exact name first, then its first DNS
    label.
  - `deviceHardwareFacts` — the curated fact set: machine
    (manufacturer+model), cpu (Linux `cpu.model`, mac `hardware.chip`),
    memory total, GPUs with VRAM, Docker container count and first 8
    name/state pairs. Everything else stays behind the raw view.
  - `summarizeNode(target, device?)` — appends "Hardware: CPU …, memory …,
    GPU …" and a Docker line to the agent digest. Selected fields only,
    never the whole dict (per the small-model rule).
- `src/detailPopup.ts` — HARDWARE section (key/value) for nodes with a
  matched device, and a second collapsible "RAW FACTS (actual --detail)"
  section holding the full device record.
- `src/main.ts` — loads devices at startup (warn-only if the snapshot is
  missing) and enriches node selections opportunistically; the ask handler
  passes the device into `summarizeNode`.
- `README_DEV.md` — snapshot section now lists all three files, same
  do-not-commit rule (`public/cluster/` was already git-ignored).

## Verification

- `CAGENT_URL=https://localhost:8789 npm run cluster:fetch` fetched and
  validated all three snapshots; live `actual.json` is 124 KB (5 devices,
  `detail_level: raw`) — full-cluster `--detail` is small enough, so the
  host-scoped per-node fallback contemplated by the plan was not needed.
- Headless-browser sweep against the rebuilt `:8090` container: all 5 node
  popups show a HARDWARE section with real facts (e.g. agpc: ASRock X870E,
  Ryzen 9 9950X, 123.41 GB, Quadro RTX 8000 48 GB, 7 containers; agstudio:
  Apple M3 Ultra, 512 GB, 26 containers listed by name/state) and the RAW
  FACTS section. FQDN-named devices matched their slugs correctly.
- "Ask agent" e2e: the assistant's reply now references the node's hardware
  ("…it has the necessary hardware and IP address assigned…") alongside the
  drift explanation.
- `npm run build` passes; web container rebuilt
  (`docker compose up --build -d web`), HTTP 200.

## Episode wrap-up

All four plan steps are complete (report1–4). Final state: clicking any
node/workspace panel opens a DOM detail popup (intent, hardware, diffs with
desired/actual, raw JSON), and the "Ask agent" button gets a plain-language
explanation from the assistant grounded in a compact digest including
hardware facts. Hard rules held: no snapshots or credentials committed;
cagent access stayed read-only.
