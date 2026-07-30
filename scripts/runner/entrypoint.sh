#!/usr/bin/env bash
# Runner image entrypoint: run one command, keep the declared artifacts.
#
# usage: entrypoint.sh <command>
#
# Environment:
#   RUN_ID        opaque label for this run (default: UTC timestamp)
#   ARTIFACTS     newline-separated repo-relative paths to keep
#   ARTIFACT_DIR  where to keep them (default: /artifacts)
set -uo pipefail

ARTIFACT_DIR="${ARTIFACT_DIR:-/artifacts}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%d-%H%M%S)}"
ARTIFACTS="${ARTIFACTS:-}"
DEST="$ARTIFACT_DIR/runs/$RUN_ID"

collect_artifacts() {
    local path parent
    while IFS= read -r path; do
        [ -z "$path" ] && continue
        if [ ! -e "$path" ]; then
            echo "runner: declared artifact '$path' does not exist, skipping" >&2
            continue
        fi
        parent="$(dirname "$path")"
        mkdir -p "$DEST/$parent"
        cp -r "$path" "$DEST/$parent/"
    done <<< "$ARTIFACTS"
    return 0
}

if [ "$#" -lt 1 ]; then
    echo "usage: entrypoint.sh <command>" >&2
    exit 2
fi

mkdir -p "$DEST"
trap collect_artifacts EXIT

bash -lc "$*" 2>&1 | tee "$DEST/run.log"
exit "${PIPESTATUS[0]}"
