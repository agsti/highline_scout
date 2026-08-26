#!/usr/bin/env bash
# Runner image entrypoint: restore a previous run's outputs, run one command,
# keep the declared artifacts.
#
# usage: entrypoint.sh <command>
#
# The declared artifacts are copied back out of $ARTIFACT_DIR before the
# command runs, so a job that reuses a RUN_ID picks up where the last one
# stopped. The ETLs skip work whose output is already on disk, so this turns a
# killed or timed-out run into a resumable one. Set RESUME=0 for a clean run.
#
# Environment:
#   RUN_ID        opaque label for this run (default: UTC timestamp)
#   ARTIFACTS     newline-separated repo-relative paths to keep
#   ARTIFACT_DIR  where to keep them (default: /artifacts)
#   RESUME        restore those paths before running (default: 1)
set -uo pipefail

ARTIFACT_DIR="${ARTIFACT_DIR:-/artifacts}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%d-%H%M%S)}"
ARTIFACTS="${ARTIFACTS:-}"
RESUME="${RESUME:-1}"
DEST="$ARTIFACT_DIR/runs/$RUN_ID"

# Restore is the mirror of collect: collect copies <path> to $DEST/<parent>/,
# so the kept copy is at $DEST/<path> and lands back under <parent>/.
restore_artifacts() {
    local path parent restored=0
    while IFS= read -r path; do
        [ -z "$path" ] && continue
        if [ ! -e "$DEST/$path" ]; then
            continue
        fi
        parent="$(dirname "$path")"
        mkdir -p "$parent"
        if cp -r "$DEST/$path" "$parent/"; then
            echo "runner: restored '$path' from a previous run of $RUN_ID"
            restored=$((restored + 1))
        else
            echo "runner: failed to restore '$path', continuing without it" >&2
        fi
    done <<< "$ARTIFACTS"
    if [ "$restored" -eq 0 ]; then
        echo "runner: nothing to restore for $RUN_ID, starting clean"
    fi
    return 0
}

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

if [ -n "$ARTIFACTS" ] && [ "$RESUME" != "0" ]; then
    restore_artifacts
fi

trap collect_artifacts EXIT

# Append rather than truncate: a resumed run must not erase the log of the
# attempt it is continuing.
{
    echo "=== run $RUN_ID started $(date -u +%Y-%m-%dT%H:%M:%SZ) (resume=$RESUME) ==="
    echo "=== command: $* ==="
} >> "$DEST/run.log"

bash -lc "$*" 2>&1 | tee -a "$DEST/run.log"
exit "${PIPESTATUS[0]}"
