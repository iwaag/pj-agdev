# Step 5 Report — End-to-End agforge Run

Date: 2026-08-11 (Asia/Tokyo)

## Result

The end-to-end request succeeded. agforge request
`17fc86d5d0b04e09b8320845d79a8313` returned `status: done` with a working,
time-limited MinIO audio URL for a Japanese vocal jingle generated through
ACE Studio.

The desire requested the lyric `明日へ走ろう、光を信じて`, a stock voice, and
an actually downloadable result. The delivered metadata reported:

- singer: `Amaboshi Cipher`, a stock Japanese ACE Studio voice;
- duration: 7.0 seconds;
- format: mono, signed 16-bit WAV at 44.1 kHz;
- delivery host: `agstudio.local:9100`, bucket `agforge`;
- no voice cloning or voice upload.

The full expiring presigned URL remains only in the ignored result/transcript
artifacts; it is not committed here.

## Independent verification

The returned URL was fetched immediately and produced HTTP success. The
downloaded file was independently checked as:

- RIFF/WAVE linear PCM;
- one channel, 44,100 Hz, signed 16-bit;
- 308,700 frames / 7.0 seconds;
- 617,444 bytes;
- SHA-256 `3c16b3e479e3cf29be2af932a32a8820ee7abab76b2120a7310ca3634de9c4fa`;
- RMS amplitude `1986.17`, peak `9540`, 84.7% nonzero samples.

The file was therefore neither empty nor silent.

Post-run ACE Studio reads showed one `Sing` track with one clip, stock singer
`Amaboshi Cipher`, and lyric sentence `明日へ走ろう光を信じて`. The Japanese
comma is not retained as a sung symbol, but the requested phonetic content is
present. `status synthesis` was idle.

## Prepared-tool check

The complete session transcript proves that the request agent used the
prepared ACE Studio path. It:

1. discovered the CLI commands;
2. loaded stock singer ID `5080` onto a Sing track;
3. set nonzero track gain;
4. created a Sing clip and an eleven-note melody;
5. applied the requested lyric sentence with `language: JPN`;
6. polled synthesis and triggered playback;
7. selected the newest `AudioCache/seg_*_44100.pcm` artifact;
8. converted its first float32 planar channel to a mono 16-bit WAV;
9. uploaded the WAV through `uv run service/transform.py`;
10. fetched the presigned URL and verified the RIFF payload before writing the
    caller result.

This was not a fallback to the scope-1 ACE-Step instrumental service.

## Failure Farming and fixes

Three local-profile attempts preceded the successful run:

- `c9e65f5be66b4554aa2886de1803568b` ended after about 456 seconds and 13
  turns without a result. It repeatedly tried to `source` the local env file,
  then stopped after help searches.
- `593b04090e634a9c9fb2627442ada418` ended after about 119 seconds and four
  turns with `agent produced no output`. Its transcript showed quoted
  absolute-path permission mismatch.
- `b989f6dbf59b40f5a0f769b4e914f0cd` proved the fixed OpenCode grant: it used
  `acestudio-cli`, created a stock singer track, clip, and notes, but became
  stuck revising Japanese mora distribution and ended after about 571 seconds
  and 27 turns without writing a result.

Evidence from those runs caused three bounded changes: explicit cache hand-off
guidance, a command-grant correction, and selection of the existing `sonnet`
profile in the ignored local deployment overlay. The successful Sonnet run
took about 553 seconds over 92 turns and recorded USD 2.72524.

During that successful run, the service process still held the older Claude
grant and the agent used the already-allowed Python subprocess path to invoke
the CLI. A final tooling correction replaced the space-containing app path at
the agent boundary with an ignored `.local/bin/acestudio-cli` symlink and
prepended that directory to the harness PATH. Direct Bash smoke tests then
succeeded through both Claude Code and OpenCode. The final implementation is
agforge commit `adc9721`; the service was restarted with that code and its
health endpoint returned `{"ok": true}`.

## Retained evidence

All of these are ignored local artifacts under `agforge/.local/`:

- `jobs/17fc86d5d0b04e09b8320845d79a8313/result.json`;
- `out/17fc86d5d0b04e09b8320845d79a8313.agent-run.json`;
- `out/17fc86d5d0b04e09b8320845d79a8313.agent.jsonl`;
- `out/17fc86d5d0b04e09b8320845d79a8313.full-transcript.jsonl`;
- `out/17fc86d5d0b04e09b8320845d79a8313.download.wav`;
- `problems/17fc86d5d0b04e09b8320845d79a8313.md`;
- the three failed-run `.agent.jsonl` and `.agent-run.json` pairs named by
  their request IDs above;
- `out/scope2-sonnet-alias-grant-smoke.agent.jsonl` and
  `out/scope2-opencode-alias-grant-smoke.agent.jsonl`.

## Verification

The final deterministic suite completed with `61 passed`. No credentials,
generated audio, account details, or presigned query string were committed.
