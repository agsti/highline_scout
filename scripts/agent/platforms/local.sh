#!/usr/bin/env bash
# Schedule a runner job on this machine via docker.
#
# usage: local.sh <run-id> <image> <command> [artifact-path...]
#
# Environment:
#   ARTIFACT_ROOT  host directory that receives runs/ (default: $PWD/.runs)
#   RESUME         0 to ignore what a previous run with this run-id kept and
#                  start clean; 1 (default) restores it before running
set -euo pipefail

ARTIFACT_ROOT="${ARTIFACT_ROOT:-$PWD/.runs}"

if [ "$#" -lt 3 ]; then
    echo "usage: local.sh <run-id> <image> <command> [artifact-path...]" >&2
    exit 2
fi

RUN_ID="$1"
IMAGE="$2"
COMMAND="$3"
shift 3

ARTIFACTS=""
if [ "$#" -gt 0 ]; then
    ARTIFACTS="$(printf '%s\n' "$@")"
fi

mkdir -p "$ARTIFACT_ROOT"

exec docker run --rm \
    -e "RUN_ID=$RUN_ID" \
    -e "ARTIFACTS=$ARTIFACTS" \
    -e "ARTIFACT_DIR=/artifacts" \
    -e "RESUME=${RESUME:-1}" \
    -v "$ARTIFACT_ROOT:/artifacts" \
    "$IMAGE" "$COMMAND"
