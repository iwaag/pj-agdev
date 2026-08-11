# Step 1 report — project settings loader

Added `agautolab.project_settings`, which reads the ignored
`.local/projects/<name>/agents.toml` file and returns its `[roles]` mapping.

- A missing project file means that shared role defaults remain active.
- A present but unreadable or malformed TOML file fails with
  `ProjectSettingsError`.
- Only `coding` and `director` keys are accepted, and every selected profile
  must be a non-empty string.
- Profile existence remains the responsibility of the shared
  `resolve_project_role()` contract, preserving its `E_UNKNOWN_PROFILE` error.
- Project names cannot contain path components.

Focused loader and resolution tests use the `stub` profile / fake harness and
cover valid, missing, malformed, unknown-role, empty-value, and unknown-profile
cases.
