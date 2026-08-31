#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$root/.local/out" "$root/.local/tickets/done"
exec uv run --project "$root" comfynotify daemon
