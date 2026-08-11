# Scope 2 Final Report — ACE Studio CLI Music Generation

Completed: 2026-08-11 (Asia/Tokyo)

## Outcome

Scope 2 completed through outcome (a): an agforge request produced a working,
time-limited URL for a listenable vocal WAV authored and synthesized through
ACE Studio.

The successful E2E request was `17fc86d5d0b04e09b8320845d79a8313`.
It requested a short Japanese jingle with the lyric
`明日へ走ろう、光を信じて`, used the stock singer `Amaboshi Cipher`, and
returned a seven-second mono 16-bit/44.1 kHz WAV through agforge's existing
MinIO delivery path. Fetching the response URL succeeded and returned 617,444
bytes of non-silent RIFF/WAVE audio.

## Tested version

- ACE Studio: `2.1.5`
- application build: `2.1.5.25080`
- CLI: the `acestudio-cli` helper bundled with that application build

The logged-in account worked throughout voice discovery, synthesis, and
playback. No quota, login, account, or version-mismatch error appeared.

## What the CLI can do

The public CLI is sufficient for end-to-end vocal authoring inside the running
desktop application:

- inspect the current project and tracks;
- discover and load stock singers;
- create Sing tracks and clips;
- create, select, inspect, and replace piano-roll notes;
- assign sentence or per-note lyrics and language;
- inspect the active singer recipe and lyric content;
- control gain, marker position, synthesis polling, and playback.

The exploration authored `未来へ進もう` with eight explicit Japanese kana
notes. The E2E request authored `明日へ走ろう、光を信じて` on an eleven-note
melody. In both cases the CLI drove the shared GUI application rather than a
standalone engine.

One authoring caveat matters: sentence-mode G2P was unreliable during the
exploration when kanji and the note count did not align. It assigned some
characters an unintended language and filled surplus notes with `la`.
Per-note kana with explicit `language: JPN` is the reliable recovery path.

## Precise export limitation

ACE Studio 2.1.5 exposes no public CLI command for export, render, bounce, or
save-audio. Focused built-in help searches, the `error-codes` topic, and a
strings-only inspection of the sibling MCP server all agreed on this boundary.
Internal `_internal/test.export.*` names are test-mode-only and unavailable in
the distribution surface. The MCP server did not advertise an extra public
export capability, so no MCP setup was pursued.

The working hand-off is therefore:

```text
CLI authoring → synthesis/playback → newest AudioCache PCM
              → float32 planar channel → PCM16 mono WAV
              → agforge transform/upload → MinIO presigned URL
```

ACE Studio writes a synthesized segment into its macOS temporary
`ACE Studio/AudioCache` directory. For the tested clips, the file was
headerless float32 planar dual-mono, with the sample rate encoded in the
filename. The two channel planes were byte-identical. Taking one plane and
quantizing it to PCM16 produced a standard WAV.

This works, but it is an undocumented cache contract. A future ACE Studio
release may change its directory, filename, sample layout, channel count, or
lifetime. One ACE Studio request at a time remains the safe operating model;
the newest-cache-file heuristic would otherwise be ambiguous.

## agforge integration

The agforge charter and guide now distinguish two music paths:

- the scope-1 LAN service for instrumental generation;
- ACE Studio for sung vocals and lyrics.

The request agent receives only the minimum useful knowledge plus the
failure-derived cache hand-off facts. The host-specific application path stays
in ignored local configuration. An ignored local symlink exposes the stable
command name `acestudio-cli`; the runner prepends its directory to PATH, and
both OpenCode and Claude Code grant that exact command. Direct Bash smoke tests
succeeded through both harnesses without unsafe permission flags.

The final agforge implementation commit is `adc9721`. Its deterministic suite
completed with 61 passing tests. The request service was restarted with that
code and returned a healthy response.

## E2E evidence

The successful response URL was downloaded and checked independently:

- duration: 7.0 seconds;
- frames: 308,700;
- channels: 1;
- sample rate: 44,100 Hz;
- source depth: signed 16-bit;
- size: 617,444 bytes;
- SHA-256: `3c16b3e479e3cf29be2af932a32a8820ee7abab76b2120a7310ca3634de9c4fa`;
- RMS: `1986.17`;
- peak: `9540`;
- nonzero samples: 84.7%.

ACE Studio retained one stock-singer Sing track and the lyric sentence
`明日へ走ろう光を信じて`; punctuation is not represented as a sung symbol.
The synthesis engine was idle after completion.

The complete transcript shows the prepared CLI being used for singer loading,
track gain, clip/notes/lyrics, synthesis, playback, cache discovery, WAV
conversion, upload, and URL verification. It did not use the instrumental
fallback.

## Run stability and cost

The local OpenCode/Ollama profile was able to execute the CLI and author a
partial project, but it did not finish this multi-stage request. Three observed
failures were preserved:

- one run spent its budget on denied `source` attempts and help exploration;
- one run ended with no output after an absolute-path permission mismatch;
- one run reached singer/clip/note authoring but looped over Japanese mora
  distribution and ended without the caller result.

The existing `sonnet` profile completed the E2E request in about 553 seconds
over 92 turns. Its recorded cost was USD 2.72524. The ignored local deployment
overlay therefore remains on `sonnet`; the committed agent identity/config
contract is unchanged. This is a runtime model choice, not a new agent.

## Retained artifacts

Generated audio, presigned URLs, transcripts, result files, and account-side
details remain under ignored `agforge/.local/` paths. Important names are:

- exploration: `scope2-exploration-1.full-transcript.jsonl`, its run record,
  structured result, source PCM, and listening WAV;
- E2E: request `17fc86d5d0b04e09b8320845d79a8313` under `jobs/`, `out/`, and
  `problems/`;
- failed E2E attempts: `c9e65f5be66b4554aa2886de1803568b`,
  `593b04090e634a9c9fb2627442ada418`, and
  `b989f6dbf59b40f5a0f769b4e914f0cd` transcripts/run records;
- final direct-grant smokes: `scope2-sonnet-alias-grant-smoke.agent.jsonl`
  and `scope2-opencode-alias-grant-smoke.agent.jsonl`.

No generated audio, credential, account detail, or expiring presigned query
string was committed.

## Reproduction conditions

1. Start ACE Studio and keep the human account logged in.
2. Ensure the ignored ACE Studio env file points to the bundled CLI and the
   ignored local `acestudio-cli` symlink targets it.
3. Start the agforge request service and confirm `/healthz`.
4. Submit a desire that clearly requests sung vocals and lyrics.
5. Poll the returned request ID until the agent writes its answer.
6. Fetch the returned audio URL before expiry and verify it as nonempty audio.

The CLI controls one shared project. Use one vocal request at a time and begin
from a project whose existing content may safely be edited or cleared.

## Recommended next moves

- Recheck the public CLI/MCP command list after ACE Studio upgrades; a
  supported export command should replace cache extraction immediately.
- If this path is used regularly, make cache identification and PCM decoding a
  small tested local helper. It is now proven recurring mechanical work rather
  than an unknown worth rediscovering each request.
- Add provenance checks before selecting the newest cache file if concurrent
  ACE Studio work is ever allowed.
- Prefer explicit per-note kana for production Japanese lyrics until
  sentence-mode G2P behavior is shown reliable for the intended text.
- Keep the local profile failure transcripts as evaluation cases before moving
  this workflow back from Sonnet to a local model.

## Step reports

- `report1.md`: application/CLI/Nautobot preconditions;
- `report2.md`: autonomous CLI exploration and audio extraction;
- `report3.md`: integration decision gate;
- `report4.md`: initial Tool Giving and grants;
- `report5.md`: E2E attempts, fixes, success, and verification;
- `report6.md`: final reporting completion.
