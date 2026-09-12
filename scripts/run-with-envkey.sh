#!/usr/bin/env bash
# Run Horizon with secrets injected from the macOS keychain via envkey.
#
# Usage:
#   ./scripts/run-with-envkey.sh                    # default: --hours 24
#   ./scripts/run-with-envkey.sh --hours 8 -l INFO  # any horizon CLI flags
#
# Requires the HORIZON_KEY secret to be present in envkey.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# cron provides a minimal PATH; make envkey and uv reachable.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

if ! command -v envkey >/dev/null 2>&1; then
    echo "error: envkey not found on PATH" >&2
    exit 1
fi

# envkey export prints shell assignments; eval them so HORIZON_KEY reaches the child.
if ! export_line="$(envkey export HORIZON_KEY)"; then
    echo "error: could not read HORIZON_KEY from envkey" >&2
    echo "hint: set it with: envkey set HORIZON_KEY --from-stdin" >&2
    exit 1
fi
eval "$export_line"

if [ -z "${HORIZON_KEY:-}" ]; then
    echo "error: HORIZON_KEY is empty" >&2
    exit 1
fi

if [ "$#" -eq 0 ]; then
    set -- --hours 24
fi

exec uv run horizon "$@"
