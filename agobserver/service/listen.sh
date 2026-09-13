#!/bin/sh
# Run the agobserver Zulip listener (credentials: .local/zulip.env).
set -eu
cd "$(dirname "$0")/.."
mkdir -p .local/out
exec uv run python -m agobserver.listener
