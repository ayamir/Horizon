#!/usr/bin/env bash
# Horizon launchd entrypoint.
#
# Runs the daily Horizon job with secrets injected from the macOS keychain via
# envkey. Designed for an unattended launchd LaunchAgent in the GUI domain,
# where keychain access is available.
#
# Usage: ./scripts/launchd-run.sh
# Logs:  logs/horizon.log (stdout+stderr merged by the plist)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

# launchd provides a minimal PATH; make uv, envkey and git reachable.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

cd "$PROJECT_DIR" || { echo "$LOG_PREFIX FATAL: cannot cd to $PROJECT_DIR" >&2; exit 1; }

echo "$LOG_PREFIX === Horizon launchd run starting ==="

# 1. Update to the latest upstream main. A dirty worktree or offline remote must
#    not abort the run, so failures here are logged and skipped.
if git fetch --quiet upstream main 2>&1; then
    if git merge --ff-only upstream/main 2>&1; then
        echo "$LOG_PREFIX main updated"
    else
        echo "$LOG_PREFIX WARN: cannot fast-forward main; running current checkout" >&2
    fi
else
    echo "$LOG_PREFIX WARN: git fetch failed; running current checkout" >&2
fi

# 2. Install/update dependencies. Keep the optional extras that enabled
#    sources depend on: Twitter is configured with mode=playwright, so a plain
#    `uv sync` would uninstall Playwright and silently disable the source.
if ! uv sync --quiet --extra twitter 2>&1; then
    echo "$LOG_PREFIX FATAL: uv sync failed" >&2
    exit 1
fi

# 3. Run Horizon with the keychain-backed API key.
if ! "$SCRIPT_DIR/run-with-envkey.sh" --hours 24; then
    echo "$LOG_PREFIX FATAL: Horizon run failed" >&2
    exit 1
fi

# 4. Mirror today's digest into the Tolaria vault as a single `news` note.
#    Auxiliary: a missing or unmounted vault must not fail the run.
VAULT="${TOLARIA_VAULT:-$HOME/Documents/Tolaria}"
if [ -d "$VAULT" ]; then
    if uv run python "$SCRIPT_DIR/sync_to_tolaria.py" --latest --vault "$VAULT" 2>&1; then
        echo "$LOG_PREFIX Tolaria sync complete"
    else
        echo "$LOG_PREFIX WARN: Tolaria sync failed" >&2
    fi
else
    echo "$LOG_PREFIX WARN: vault not found at $VAULT; skipping Tolaria sync" >&2
fi

echo "$LOG_PREFIX === Horizon launchd run finished ==="
