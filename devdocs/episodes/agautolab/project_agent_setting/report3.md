# Step 3 report — director resolution

The common `agautolab.role_run` path now discovers a director's project when
its working directory is `.local/projects/<name>/direction/` or below. It uses
the same project settings loader and applies this precedence:

1. explicit `--profile`;
2. project `[roles].director`;
3. the shared director-role default.

An optional `--project` argument supports callers that cannot express the
workspace through `--cwd`. Both the returned metadata and a `--record` JSON
file include the discovered project and resolved profile. The gateway's
director mechanism already invokes this common CLI, so it reaches the same
resolution path without a second implementation.

Fake-harness tests cover direction-workspace discovery, normalized record
content, and visible failure for an unknown director profile.
