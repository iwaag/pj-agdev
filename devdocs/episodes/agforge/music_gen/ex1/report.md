# ex1 Report — Are ACE Studio's Generative Kits (Inspire Me / Song Generator) Reachable from CLI or MCP?

Date: 2026-08-11 (Asia/Tokyo)

## Question

The braindump asks whether ACE Studio's near-complete text-to-music features
(`Inspire Me` and friends) can be driven from the CLI or MCP, and asks for the
answer to come from the shipped CLI/MCP surface itself rather than from
marketing documentation.

## Answer

**No. Not in the installed version.** ACE Studio 2.1.5 (build `2.1.5.25080`)
exposes exactly one automation contract — *surface 1.0* — over both the CLI and
the MCP server, and that contract contains no generative-kit command. Scope 2's
"author notes and lyrics, then extract the synthesis cache" path remains the
only machine-drivable music route through ACE Studio.

The features are real and present in the application; they are simply behind a
different, not-yet-public control surface (see "What exists but is not exposed").

## Environment tested

- ACE Studio running and logged in during the whole investigation.
- Application version `2.1.5`, bundle version `2.1.5.25080`.
- `acestudio-cli 0.1.0 (surface 1.0)`, connected and reporting
  `ACE Studio 2.1.5, surface 1.0`.
- MCP frontend `ace_mcp_server` ("ACE Studio MCP" `0.1.0`), STDIO transport,
  authenticated through the per-user bridge credentials file that ACE Studio
  writes while its MCP server is enabled.

Both binaries ship inside the ACE Studio application bundle under
`Contents/Helpers/`.

## Evidence

### 1. The CLI command tree has no generative command

`acestudio-cli --print-paths` returns 76 command paths across 15 groups:
`arrangement`, `clip`, `convert`, `device`, `editor`, `loop`, `marker`,
`metronome`, `mixer`, `playback`, `sound-source`, `special-tracks`, `status`,
`tempo`, `timesig`, `track`. There is no `generative`, `song`, `job`, `export`,
or `import` group.

Focused doc searches (`help --search`) for `inspire`, `text-to-music`,
`ai-song`, `lyric-to`, and `melody-gen` all returned `No matches`.

### 2. The MCP server is a mirror of the same surface, not a superset

A direct `tools/list` handshake against `ace_mcp_server` returned 30 tools:
each of the 15 CLI groups split into `<group>_read` / `<group>_edit`, plus
`get_docs`. No generative tool exists, and the per-tool `subcommand` argument is
a closed `enum` — there is no free-form command path a caller could smuggle a
generative command through.

This settles the open item left by Scope 2, which had only inspected the MCP
binary statically.

### 3. The application itself rejects the command paths

`get_docs` is answered by the running application over the bridge, not by the
client, so it is an authoritative probe of the app-side command registry:

```text
generative song -> unknown command path: generative song
song generate   -> unknown command path: song generate
job list        -> unknown command path: job list
export audio    -> unknown command path: export audio
```

The commands are absent from the registry, not merely hidden from help.

### 4. The contract says so explicitly

The `changelog` topic declares one versioned contract — "the command tree, every
command's input and output schema, and the error-code registry" — currently at
surface major 1 with an empty breaking-change list. The bridge handshake stamps
the same `surfaceVersion`. So the 76 paths above are the whole public contract,
and any future generative command arrives as an additive minor bump that a
consumer can detect from `--version` or the handshake.

## What exists but is not exposed

The application binary carries a `CapabilityRegistry` — a consent-token list for
a *different* consumer surface than the CLI/MCP one. It declares roughly 70
tokens, including a full generative family:

| Token | Display name / description |
|---|---|
| `generative.song` | Song Generator — "Run the Song Generator (Inspire Me) on your behalf." |
| `generative.enhance` | Music Enhancer |
| `generative.add-layer` | Add a Layer (accompaniment layers) |
| `generative.text2sample` | Text2Sample — generate samples from text |
| `generative.sound-effects` | Generate sound effects |
| `generative.seed-audio` | SeedAudio |
| `generative.stem-split` | Stem Splitter |
| `generative.vocal2midi` | Vocal-to-MIDI |
| `generative.voice-change` | Voice Changer |
| `generative.retake` | Regenerate vocal synthesis takes |

Alongside them sit `export.invoke` ("Export audio, MIDI, video, and other
material … to files"), `import.invoke`, `job.read` / `job.control`,
`credit.balance` / `credit.topup`, `project.lifecycle`, `recording.control`,
`lyric.write`, `vocalparam.write`, `media.*`, and `workflow.ui` /
`workflow.dev`.

The consuming subsystem is a **workflow-extension host** (`WorkflowExtensionHost`,
`WorkflowExtensionSession`, `WorkflowExtensionInstallStore`) that launches an
extension process and presents an embedded surface inside Studio. Grants are
computed once per session at handshake and are immutable. The CLI's own
`error-codes` topic describes the two grant policies, and confirms where today's
CLI/MCP sits:

> Under the StrictSubset policy (extensions at install consent) this is a hard
> handshake error; **today no public surface triggers it (CLI/MCP grants are
> FullSurface and ignore requested names)**.

In other words: CLI and MCP receive the full grant *of their own surface
profile*, and that profile is surface 1.0 — the 76 non-generative paths. The
generative tokens belong to the extension profile, and no extension install
store exists on this machine yet.

Two further signs that the generative surface is staged for release rather than
merely absent:

- The shipped `streaming-results` topic already documents the job ledger, the
  `streaming` result state, `staged` vs `direct` delivery, and
  `JOB_NOT_CANCELLABLE` — and names "the server-side generative kits: Song
  Generator and Music Enhancer" as the streaming-capable classes. The contract
  language exists; the commands do not.
- `credit.balance` / `credit.topup` tokens confirm the kits are credit-metered
  cloud calls, so a future automation path will consume account credits.

One naming trap worth recording: the `IMRunner` helper is **not** "Inspire Me".
Its symbols are `V2TIMSDKListener` — it is the Tencent instant-messaging SDK
used for the community features.

## Practical consequences for agforge

1. **No integration work is available today.** There is nothing to give the
   request agent; the desired capability is not addressable.
2. **Scope 2's path stands unchanged**, including its undocumented AudioCache
   hand-off and its one-request-at-a-time operating rule.
3. **A cheap upgrade detector exists.** `acestudio-cli --version` prints both
   the app version and the surface version in one line. When the surface minor
   moves past `1.0`, re-run `--print-paths` and the MCP `tools/list`. That is a
   two-command recheck, far cheaper than the strings-level investigation this
   report required, and it also covers Scope 2's other open wish — a supported
   `export` command to replace cache extraction, whose capability token
   (`export.invoke`) is waiting in the same registry.
4. **Expect a consent gate, not just new commands.** When the generative family
   lands it will likely arrive through the extension/consent model with
   per-capability grants and credit consumption, so integration will involve an
   install-time consent decision, not only a new CLI verb.
5. **If near-complete-song generation is wanted before then**, the realistic
   options are outside ACE Studio's public automation: the scope-1 LAN
   ACE-Step service for instrumental generation, or GUI automation of the Song
   Generator panel. GUI automation is not recommended — it would be a second
   undocumented contract on top of the AudioCache one.

## Method note

The public surface was probed live: CLI help and `--print-paths`, an MCP
`initialize` + `tools/list` + `get_docs` session over STDIO, and app-side
unknown-path probes. The unexposed capability inventory came from a read-only
strings inspection of the application binary, since there is no live interface
that enumerates it. Nothing was invoked that could modify the user's project,
start a job, or spend credits.
