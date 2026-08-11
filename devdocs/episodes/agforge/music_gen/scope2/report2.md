# Step 2 Report — ACE Studio CLI Exploration

Date: 2026-08-11 (Asia/Tokyo)

## Result

The exploration succeeded. A Claude Code agent, running in normal permission
mode, used ACE Studio's self-describing CLI to author a Japanese vocal phrase
from the empty project and obtained a listenable WAV without cloning or
uploading a voice.

The request was to sing `未来へ進もう`. The resulting ACE Studio project has
one `Sing` track using the stock Japanese singer `Amaboshi Cipher`, one clip,
and eight notes whose explicit Japanese lyrics are `み/ら/い/へ/す/す/も/う`.
Independent post-run CLI reads confirmed the track, singer recipe, lyric
sentence `みらいへすすもう`, and an idle synthesis engine.

## What the CLI reaches

The agent successfully used the public CLI for:

- stock voice discovery and loading;
- Sing-track and clip creation;
- piano-roll note and per-note lyric authoring;
- singer-recipe, note-content, and lyric inspection;
- synthesis-status polling and playback transport.

Sentence-mode lyric distribution was unreliable for this CJK input. It gave
some kanji Chinese readings and padded surplus notes with `la`. Replacing the
notes with per-note kana and explicit `language: JPN` produced the intended
eight Japanese syllables.

No account, login, quota, or version error occurred.

## Export finding and audio hand-off

The installed public CLI has no export, render, bounce, or save-audio command.
This was checked through the top-level help, focused `help --search` queries,
and the `error-codes` topic. The latter mentions internal export rendering and
`_internal/test.export.*`, but explicitly describes those commands as
test-mode-only and unavailable through the distribution CLI/MCP surface.

A static strings-only check of the sibling `ace_mcp_server` found the same
embedded command documentation and no additional public export capability. No
MCP server was registered or used.

Playback caused ACE Studio to write the synthesized segment under its macOS
temporary `ACE Studio/AudioCache` directory as a headerless `.pcm` file. The
filename encoded a 44.1 kHz sample rate. Content probing showed float32 planar
dual-mono data: two byte-identical 9-second channels, with vocal energy over
the authored phrase and silence in the remaining clip tail. Taking one plane
and quantizing it to signed 16-bit PCM produced:

```text
.local/out/scope2-exploration-1/mirai_e_susumou.wav
```

The WAV is intentionally ignored by Git. Independent verification reported:

- RIFF/WAVE, linear PCM;
- mono, 44,100 Hz, signed 16-bit;
- 396,900 frames / 9.0 seconds;
- 793,844 bytes;
- SHA-256 `a6613a5a2981bb75b7e21da30bd47cfe443d2ec57c31df63ed3e046b40d9c2d4`.

The exploration agent also played the converted file locally with `afplay` and
reported the sung phrase as audible. This hand-off is functional but relies on
an undocumented internal cache rather than a supported CLI export contract.

## Retained evidence

All paths below are inside the ignored `agforge/.local/out/` directory:

- `scope2-exploration-1.full-transcript.jsonl`: full 45-turn Claude Code
  session, including commands and tool results;
- `scope2-exploration-1.agent.jsonl`: harness final-result transcript;
- `scope2-exploration-1.agent-run.json`: model/run/cost record;
- `scope2-exploration-1/result.json`: structured exploration findings;
- `scope2-exploration-1/mirai_e_susumou.wav`: converted listening artifact;
- `scope2-exploration-1/raw_seg_51430458624_44100_planar_f32.pcm`: copied
  source cache artifact.

The run used `anthropic/claude-sonnet-5` through the `claude_code` harness,
completed in about 314 seconds over 45 turns, and did not use web search.

## Decision input

Audible audio was obtained through a CLI-driven authoring and playback flow,
with filesystem extraction of the resulting synthesis cache. Step 3 should
therefore select the integration branch.
