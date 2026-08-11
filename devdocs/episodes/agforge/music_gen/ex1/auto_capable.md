# ACE Studio — Automation-Capable Features (No Human Manual Operation)

Date: 2026-08-11. Based on ACE Studio 2.1.5 (surface 1.0), verified live in
the ex1 investigation (`report.md`). "Automation-capable" means reachable by
an agent through `acestudio-cli` or the MCP server against a running,
logged-in ACE Studio, plus the proven scope-2 cache hand-off. The MCP surface
is an exact mirror of the CLI (each group as `<group>_read`/`<group>_edit`
plus `get_docs`), so everything below applies to both transports.

## Standing preconditions

- ACE Studio must be running with the human account logged in. (App launch
  itself is scriptable via `open -a "ACE Studio"`, but first-time login and
  consent dialogs are manual.)
- One shared project, one automation client at a time is the safe model.
- All mutations below participate in the app's undo stack.

## 1. Self-description and docs

- `--print-paths`, `--json` on every command, `--version` (reports app +
  surface version — the cheap upgrade detector).
- `help <command|topic>` / `help --search <regex>` / MCP `get_docs`: full
  markdown docs, input/output schemas, error-code registry, changelog with
  machine-readable breaking-change blocks. The surface is fully
  self-describing; an agent can learn it without external docs.

## 2. Project and synthesis status

- `status project` — project name, temp/new flags, duration.
- `status synthesis` — poll whether background vocal synthesis is running
  (the readiness gate before playback/cache capture).

## 3. Tracks (CRUD-ish)

- `track count / list / get` — enumerate tracks, types, settings.
- `track singer-recipe` — inspect which singer/recipe a Sing track uses.
- `track rename`, `track delete`, `track set-record`.
- `track set` — color, pan, gain, mute, solo (partial update, undoable).
- `track get-selection / set-selection`.
- Note: there is no `track create`; new tracks appear by placing a clip into
  an empty track slot (`clip add` auto-converts the slot) or by loading a
  sound source onto it.

## 4. Clips

- `clip list / get` — positions, durations, types, colors, names.
- `clip add` — create empty Sing / Instrument / GenericMidi clips at a tick
  position (this is the track-creation path too).
- `clip move-edges` — resize/trim.
- `clip note-content` — read notes inside a clip.
- `clip lyrics` — read sentence-level lyrics of a Sing clip.
- `clip audio-content` — read an Audio clip's file name and loading state
  (read-only; audio clips cannot be created via this surface).

## 5. Piano-roll editor (note authoring)

- `editor open / status / tick-range / current-clip` — window control and
  scope inspection. Which clip is edited follows the marker-line position.
- `editor get-content` — read notes in ranges (`all`, `clip_region`,
  `viewport`, or custom tick ranges).
- `editor add-notes` — bulk, atomic note insertion with two lyric modes:
  - per-note `lyric` + `language` (reliable for Japanese kana; the proven
    path from scope 2);
  - sentence mode (`--lyric-sentence`) with G2P syllable distribution —
    convenient but unreliable for kanji/mora mismatches (pads with `la`).
- `editor get-selection / set-selection / select-notes / delete-selection` —
  select and delete notes; replace = delete + add.
- Monophonic note exclusivity in Sing clips is enforced atomically per batch.

## 6. Voices / sound sources

- `sound-source list` — installed singers, choirs, instruments, ensembles,
  filterable by type/tags/keyword/language/category; `sound-source tags` for
  the tag vocabulary.
- `sound-source load / unload` — put a singer (or instrument/choir/ensemble)
  on a track; undoable.
- Community catalog, fully headless: `community-pages` (page count),
  `community-list` (browse/search cloud voices, 30 per page),
  `community-collect` (add a community voice to the library so it becomes
  loadable). This is a real cloud-side action an agent can take.

## 7. Timing, tempo, structure

- `tempo get / set` — read and replace the whole tempo automation table
  (points with BPM and curve bend).
- `timesig get / set` — time-signature table.
- `convert *` — tick↔time↔measure conversions and editor↔global coordinate
  mapping via the project tempo map (six converters).
- `arrangement get/set/clear/move-selection` — timeline selection control.
- `loop get / set`, `marker get / set / seek / get-focus` — loop region and
  marker-line (playhead) control, in seconds or ticks.

## 8. Transport and monitoring

- `playback start / stop / toggle / status`.
- `metronome on / off / get`.
- `mixer show / hide / get`, `special-tracks show / hide / get` — panel
  visibility (UI state only).
- `device audio-current / audio-list / midi-list` — audio/MIDI device
  interrogation (read-only).

## 9. Audio retrieval (undocumented but proven)

The surface has **no export command**. The proven hand-off (scope 2):
synthesize + play, then read the newest file under the macOS temp
`ACE Studio/AudioCache` directory — headerless float32 planar dual-mono PCM
with the sample rate in the filename — take one plane, quantize to PCM16,
wrap as WAV. Constraints: undocumented cache contract, may break on any
release; one request at a time so "newest file" stays unambiguous.

## 10. Existing end-to-end automation (agforge)

The whole chain is already wired agent-side: agforge request →
CLI authoring → synthesis poll → playback → cache capture → WAV →
MinIO presigned URL (verified E2E, scope 2).

## Explicitly NOT automatable today (for contrast)

Generative kits (Inspire Me / Song Generator, Music Enhancer, Text2Sample,
sound effects, stem split, vocal2midi, voice changer, SeedAudio), audio/MIDI
**export and import**, project lifecycle (new/open/save), FX chains, vocal
parameter curves and breath marks, recording, chord-clip editing, per-note
phoneme editing, job ledger access, credit operations. These exist in the
app's capability registry for a future extension surface but are absent from
surface 1.0 (see `report.md`).
