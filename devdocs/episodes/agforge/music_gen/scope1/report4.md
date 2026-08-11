# Step 4 Report — Tool Giving to agforge

Completed 2026-08-11.

The request agent now has the minimal operational information needed to use
music generation: a local-only config supplies `MUSIC_GEN_URL`, and the
charter tells it to source that file, fetch the music service's own `/guide`,
call its documented `POST /generate` operation, and return `audio_url`.

The committed agforge guide now advertises one music track as a supported
capability. No wrapper scripts or usage prohibitions were added. The endpoint
itself remains only in ignored local configuration.

Validation: `uv run pytest -q` in agforge passed (58 tests).

Commit in the agforge submodule: `cdbfac4 Give agforge access to local music
generation`.
