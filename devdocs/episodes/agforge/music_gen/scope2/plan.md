# Scope 2 Plan — Online (Proprietary) Music Generation Path via ACE Studio CLI

Goal: find out whether ACE Studio's bundled CLI (`acestudio-cli`) can be
used by an agent to actually produce music, and if it can, wire it into
agforge the same way scope 1 did. Suno is out of scope (no API, no CLI —
already decided in the braindump). The MCP route was considered and
dropped in favor of the CLI (developer decision, 2026-08-11): same app
surface, but plain Bash — no MCP registration or tool-allowlist plumbing.

**Done when** either:

- (a) an agforge request produces a listenable audio result generated
  through ACE Studio (E2E, like scope 1), or
- (b) exploration shows agent-driven generation is not (yet) achievable
  through the CLI, and the failure/limitation report says exactly what
  was tried and where it stopped. Outcome (b) is a *successful* scope
  completion — the report is the asset (Failure Farming).

Decision rule between the two: if the exploration step (step 2) yields
audible audio by any CLI-driven method, proceed to agforge integration;
if not, write the report and stop.

## Known facts (preresearch, 2026-08-11)

- ACE Studio is installed on agstudio and the developer has a working,
  logged-in account. The CLI is already usable.
- The CLI ships inside the app:
  `/Applications/ACE Studio.app/Contents/Helpers/acestudio-cli`. It
  "controls a running ACE Studio" — **the desktop app must be running**;
  the CLI is a remote control, not a standalone engine.
- The CLI is **self-describing**: `acestudio-cli help <command|topic>`
  serves markdown docs, `help --search <regex>` greps across them, and
  `--json` gives structured output. This is ideal Tool Giving material —
  the agent can discover usage on its own; humans need to hand over
  little more than the binary path.
- Command families observed: `track` (CRUD), `clip` (authoring,
  `clip lyrics`), `editor` (piano-roll notes), `sound-source` (singer/
  instrument library incl. community catalog, load/unload, tags),
  `playback` (transport), `status synthesis` / `status project`, `tempo`,
  `timesig`, `marker`, `loop`, `arrangement`, `convert`, `metronome`,
  `device`, `mixer`.
- **No export/render/bounce command surfaced** in a preresearch
  `help --search 'export|render|bounce|wav'` sweep. Synthesis happens
  in-app (`status synthesis` reports progress; `playback start` plays
  synthesized audio). Getting a *file* out is the central open question
  of the exploration step — do not assume either way.
- ACE Studio itself: AI vocal-synthesis workstation, MIDI + lyrics →
  sung vocals (140+ royalty-free voices, 8 languages incl. Japanese);
  2.0 added instrument/song generation. The *app* can make music; the
  question is only how much of it the CLI reaches.
- A sibling binary `ace_mcp_server` exists in the same Helpers dir —
  out of scope now, but if the CLI hits a wall the MCP tool list might
  reach something the CLI doesn't (worth one sentence in the report if
  checked).
- agforge request agents run **natively on agstudio** (no
  skip-permissions) with Bash-style tool grants (`agent_run.py` /
  `opencode.json`), so they can run the CLI directly — no network or
  protocol work at all.
- Scope 1 delivery pattern to reuse if E2E happens: audio file → MinIO
  presign (bucket `agforge`, LAN-reachable URL) → URL somewhere in the
  agent's free-form JSON answer. agdevworld reads answers with a model,
  not a schema.
- `service/charter.md` is re-read per request — the cheapest tuning
  lever for Tool Giving fixes; no restart needed.

## Steps

1. **Precondition check.** ACE Studio app running on agstudio (human
   starts it if not — the only manual part left), then
   `acestudio-cli status project --json` answers. Record app version.

2. **Exploration test (agent #1).** Run an interactive agent session on
   agstudio (Claude Code is the obvious harness — the CLI is just Bash)
   with a concrete musical desire, e.g. "make a short sung phrase in
   Japanese and get me an audio file". Give it the desire, the CLI path,
   and the fact that `help` / `help --search` exist — not a
   tool-by-tool script. Questions the exploration must answer:
   - Can the agent get from empty project → track + notes + lyrics +
     singer → synthesized playback?
   - Can it get *a file out*? Known-unknowns to probe: any export
     command the preresearch sweep missed; saving the project and
     locating rendered/cached audio on disk (`~/Library`, app caches);
     capturing playback via an audio device (`device` command exists);
     or worst case, project-on-disk that a human opens and exports.
   - Anything account/quota/version-flakiness shaped worth knowing.
   Keep the transcript. Partial success (project authored, no audio
   out) counts as outcome (b) unless a workaround surfaces.

3. **Decision gate.** Audible audio obtained by any CLI-driven method →
   continue. Otherwise → step 6 (report) and stop.

4. **Tool Giving to agforge.** Extend `charter.md`/`GUIDE.md` with the
   *minimum* usage information: the tool exists, what it's for (sung
   vocals — the thing the scope-1 local path can't do), where the
   binary lives, and that it documents itself via `help`. Deliberately
   start lean (Failure Farming) and add sentences only as failures
   demand. The absolute binary path is an environment fact — per
   existing convention put it in `.local` config, not committed files.
   Check the agent's tool grants actually permit running it before
   blaming the agent.

5. **E2E run.** POST a music desire to agforge `:8092` that should
   steer the agent toward ACE Studio — vocals-with-lyrics is the
   discriminator (scope-1 ACE-Step does instrumentals, ACE Studio does
   singing), so a "short sung jingle with these lyrics" desire makes
   tool choice observable. Poll, confirm the answer contains a working
   audio URL (MinIO presign reuse recommended). Read the transcript to
   verify the agent used the prepared CLI — "did it use what we
   prepared" is an explicit check from the braindump. Failures: capture
   verbatim, adjust usage info, retry.

6. **Report.** `scope2/report.md` (step reports `reportN.md` as
   useful): app version, what the CLI turned out to reach, the audio
   hand-off method found (or the precise wall), transcript locations,
   quota/stability issues, and either the E2E outcome + how to
   reproduce it, or recommended next moves (e.g. "recheck the MCP tool
   list", "hybrid: CLI composes, human exports").

## Prohibitions (minimum — same spirit as scope 1)

- Never commit credentials, tokens, account details, or generated audio.
  ACE Studio login stays human-side.
- No `--dangerously-skip-permissions` / `--auto` for agents running
  natively on agstudio (existing rule).
- Generated vocals use ACE Studio's royalty-free voices as-is; don't
  clone or upload anyone's voice.

Everything else — exploration style, how audio gets from ACE Studio to
a URL, charter wording — is implementer's discretion. No backward
compatibility obligations; scope-1 pieces may be freely changed if
integration needs it.

## Hints

- Start every unknown with `acestudio-cli help --search <regex>` — the
  built-in docs are richer than the online ones and include topics
  (`streaming-results`, `error-codes`, `note-exclusivity`,
  `tick-coordinates`) beyond the command list.
- `--json` on every command; errors go to stderr as JSON too — easy for
  an agent to reason about.
- The CLI drives one shared GUI instance. One request at a time is the
  safe assumption; `status synthesis` tells you when the engine is busy.
- Synthesis is asynchronous: authoring returns before audio exists.
  Poll `status synthesis` before expecting playable output.
- The `streaming-results` help topic mentions generated results being
  "placed in the project already" — read it early; it likely describes
  how the app's generation features surface through the CLI.
- The presign helper in `agforge/src/agforge` already takes arbitrary
  files; a WAV/MP3 from ACE Studio needs no new delivery code.
- If the agforge agent ignores the new tool, the first fix is one more
  sentence in `charter.md` (it's re-read per request), not a wrapper —
  scope-1 lesson, still applies.
