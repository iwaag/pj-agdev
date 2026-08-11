# Scope 1 Plan — Local Music Generation Path

Goal: stand up a small music-generation service (ACE-Step 1.5) in the
`music-gen` workspace, serve it from `agpc`, and let the agforge request
agent use it. **Done when one song is generated end-to-end through an
agforge request** and a human confirms the audio is music.

Implementer: Omni Agent builds and deploys the service directly. Tool
Giving / Failure Farming apply only to the agforge agent's *use* of the
service, not to how the service is built.

## Known facts (from preresearch and local env)

- ACE-Step 1.5 already ran successfully on `agpc`: Quadro RTX 8000
  (48 GB VRAM, Turing), CUDA 13.1, Python 3.12, uv. One 10-second stereo
  48 kHz WAV in ~2.5 s with the Turbo DiT at 8 steps.
- FlashAttention is unavailable on Turing; ACE-Step falls back to the
  PyTorch CUDA backend automatically — expected, not an error.
- The preresearch install (repo clone + downloaded models) may still be
  on `agpc`; verify and reuse before re-downloading. Only the temporary
  loopback API process was stopped.
- ComfyUI and graphics processes coexist on the GPU (~1 GB baseline);
  plenty of headroom remains.
- `agpc` access: the managed Ansible channel from
  `pj-clusterintent/ansible_agdev`, or direct ssh with
  `~/.ssh/ansible_key` after confirming with the user. `agpc.local`
  resolves and answers from agstudio.
- `music-gen` workspace: `~/projects/music-gen`, a **public** GitHub repo
  (`iwaag/music-gen`), currently only LICENSE.
- agforge request service: `:8092` on agstudio
  (`agforge/service/serve.sh`), contract `POST /api/requests {"desire"}` →
  poll `GET /api/requests/{id}`. The agent re-reads `service/charter.md`
  per request — wording changes need no restart.
- agforge already delivers images as MinIO presigned URLs
  (`agstudio.local:9100`, bucket `agforge`); browsers on this LAN resolve
  them directly.

## Steps

1. **Service implementation (music-gen repo).** Small HTTP service
   wrapping ACE-Step 1.5. Keep it a dumb deterministic tool (this is the
   tool being *given*, not an agent): a generate endpoint taking at least
   prompt text, optional duration/seed/steps, returning the audio or a
   URL to it. Sync response is viable at ~2.5 s/song, but a simple job
   pattern is fine too — implementer's choice. uv project, config via
   env vars, README with run instructions.
2. **Delivery of audio.** Recommended: reuse the MinIO presign pattern
   from `agforge/src/agforge` (endpoint/bucket/keys via env). A plain
   file-serving endpoint on the service is an acceptable simpler
   alternative. Either way the caller must receive a URL reachable from
   the LAN, not an agpc-local path.
3. **Deploy on agpc.** Clone `music-gen` onto agpc, reuse the existing
   ACE-Step environment/models if present, start the service by hand
   (nohup/tmux; no systemd, no desired-state registration — explicitly
   out of scope). Bind a LAN-reachable port (agforge uses 8092 on
   agstudio; anything free on agpc works — record the choice in the
   report). Smoke-test with curl from agstudio.
4. **Tool Giving to agforge.** Give the request agent the information it
   actually needs to use the service — Tool Giving means no unnecessary
   rules or instructions, not missing usage information. Two acceptable
   shapes, implementer's choice:
   - Self-describing service (recommended): the service exposes its own
     help (e.g. a `GET /guide` like agforge's), and `charter.md`/
     `GUIDE.md` tells the agent the URL and how to fetch that help.
   - Direct explanation: `charter.md`/`GUIDE.md` documents the endpoint
     and its parameters properly.
   Either way, don't add wrapper scripts or usage prohibitions.
   Endpoint URLs are environment facts — put the actual URL in `.local`
   config, not in committed agforge files.
5. **End-to-end run.** POST a music desire to agforge `:8092`, poll,
   confirm the agent returns something containing a working audio URL.
   Keep the transcript and `.agent-run.json`. If the agent fails, the
   failure report is the asset: capture it in the report, fix the
   usage information (or the service's own help) as evidence demands,
   retry.
6. **Report.** `scope1/report.md`: what was built, agpc port/paths,
   how to restart the service by hand, the agforge run outcome
   (including failures verbatim), and the human-listening result.

## Prohibitions (minimum)

- Never commit endpoints, hostnames, credentials, tokens, or generated
  audio to the public `music-gen` repo (same rule agforge already has).
- Don't write to the `nctl-outbox` bucket (another project's).
- `agpc` changes go through the Ansible channel or confirmed
  `ansible_key` ssh only.
- No `--dangerously-skip-permissions` / `--auto` for agents running
  natively on agstudio (existing agforge rule; unchanged).

Everything else — framework, API shape, port, job model, audio format,
directory layout — is implementer's discretion. No backward
compatibility obligations anywhere in this scope.

## Hints

- ACE-Step 1.5 exposes a Python API and a gradio/API server of its own;
  wrapping the Python API in a thin FastAPI service gives the cleanest
  contract, but shelling out to its CLI is fine for scope 1.
- Model load is the slow part; keep the model resident in the service
  process rather than loading per request.
- The agforge agent answers callers with its own JSON, unvalidated — the
  music URL just needs to appear somewhere in its answer; agdevworld
  reads bodies with a model, not a schema.
- If the agent can't find the service, the cheapest evidence-driven fix
  is one more sentence in `charter.md`, not a wrapper tool.
