#!/usr/bin/env bash
# Schedule a runner job on OVHcloud AI Training and wait for it to finish.
#
# usage: ovh.sh <run-id> <image> <command> [artifact-path...]
#
# Environment:
#   OVH_CPU      CPUs to request (default: 8, max 12)
#   OVH_BUCKET   Object Storage bucket attached at /artifacts
#   OVH_REGION   Object Storage datastore alias; must match the job's region
#   POLL_SECONDS seconds between status checks (default: 30)
set -euo pipefail

OVH_CPU="${OVH_CPU:-8}"
OVH_BUCKET="${OVH_BUCKET:-highline-runs}"
OVH_REGION="${OVH_REGION:-GRA}"
POLL_SECONDS="${POLL_SECONDS:-30}"

if [ "$#" -lt 3 ]; then
    echo "usage: ovh.sh <run-id> <image> <command> [artifact-path...]" >&2
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

OVH_ENV_ARGS=(
    --env "RUN_ID=$RUN_ID"
    --env "ARTIFACT_DIR=/artifacts"
)
if [ -n "$ARTIFACTS" ]; then
    OVH_ENV_ARGS+=(--env "ARTIFACTS=$ARTIFACTS")
fi

JOB_ID="$(
    ovhai job run \
        --name "run-$RUN_ID" \
        --cpu "$OVH_CPU" \
        --volume "$OVH_BUCKET@$OVH_REGION:/artifacts:rw" \
        "${OVH_ENV_ARGS[@]}" \
        --output json \
        "$IMAGE" -- /app/entrypoint.sh "$COMMAND" | jq -r '.id'
)"
echo "submitted job $JOB_ID for $RUN_ID" >&2

while true; do
    STATE="$(ovhai job get "$JOB_ID" --output json | jq -r '.status.state')"
    case "$STATE" in
    DONE)
        echo "job $JOB_ID finished: $STATE" >&2
        exit 0
        ;;
    FAILED | ERROR | TIMEOUT | INTERRUPTED | SYNC_FAILED)
        echo "job $JOB_ID finished: $STATE" >&2
        echo "logs: ovhai job logs $JOB_ID" >&2
        exit 1
        ;;
    esac
    sleep "$POLL_SECONDS"
done
