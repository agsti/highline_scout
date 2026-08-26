#!/usr/bin/env bash
# Spawn a runner job on OVHcloud AI Training and return immediately.
#
# usage: ovh.sh <run-id> <image> <command> [artifact-path...]
#
# Prints the job id on stdout; progress notes go to stderr. The job outlives
# this process — nothing here waits for it. Check on it with ovh_jobs.sh.
#
# Re-running with the same <run-id> resumes: the runner restores whatever that
# run-id kept in the bucket before starting, and the ETLs skip work already on
# disk. Use a fresh run-id, or RESUME=0, for a clean run.
#
# Environment:
#   OVH_CPU      CPUs to request (default: 8, max 12; memory is 4 GiB per CPU)
#   OVH_BUCKET   Object Storage bucket attached at /artifacts
#   RESUME       0 to ignore what a previous job with this run-id kept and
#                start clean; 1 (default) restores it before running
#   OVH_REGION   Object Storage datastore alias; must match the job's region
#   OVH_TIMEOUT  kill the job after this long (default: 7d, which is also the
#                hard maximum — the API rejects anything over 604800s). Lower
#                it for anything that should not be able to bill a full week:
#                a wedged command runs out the whole timeout.
set -euo pipefail

OVH_CPU="${OVH_CPU:-8}"
OVH_BUCKET="${OVH_BUCKET:-highline-runs}"
OVH_REGION="${OVH_REGION:-GRA}"
OVH_TIMEOUT="${OVH_TIMEOUT:-7d}"

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
    --env "RESUME=${RESUME:-1}"
)
if [ -n "$ARTIFACTS" ]; then
    OVH_ENV_ARGS+=(--env "ARTIFACTS=$ARTIFACTS")
fi

JOB_ID="$(
    ovhai job run \
        --name "run-$RUN_ID" \
        --cpu "$OVH_CPU" \
        --timeout "$OVH_TIMEOUT" \
        --volume "$OVH_BUCKET@$OVH_REGION:/artifacts:rw" \
        "${OVH_ENV_ARGS[@]}" \
        --output json \
        "$IMAGE" -- /app/entrypoint.sh "$COMMAND" | jq -r '.id'
)"

if [ -z "$JOB_ID" ] || [ "$JOB_ID" = "null" ]; then
    echo "ovh.sh: job submission returned no id" >&2
    exit 1
fi

SCRIPT_DIR="$(dirname "$0")"
{
    echo "submitted job $JOB_ID for $RUN_ID (timeout $OVH_TIMEOUT, ${OVH_CPU} CPU)"
    echo "  status: ${SCRIPT_DIR}/ovh_jobs.sh $JOB_ID"
    echo "  wait:   ${SCRIPT_DIR}/ovh_jobs.sh --wait $JOB_ID"
    echo "  logs:   ovhai job logs $JOB_ID"
} >&2

printf '%s\n' "$JOB_ID"
