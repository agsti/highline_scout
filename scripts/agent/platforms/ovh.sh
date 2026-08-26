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
#   OVH_REGION   Object Storage datastore alias; must match the job's region
#   RESUME       0 to ignore what a previous job with this run-id kept and
#                start clean; 1 (default) restores it before running
#   OVH_ENV      space-separated names of environment variables to forward into
#                the job, e.g. OVH_ENV="HIGHLINER_NLS_API_KEY". Values are read
#                from this shell. Note they are stored in the job spec and are
#                readable afterwards via `ovhai job get`, so treat them as
#                exposed to anyone with access to the project.
#   OVH_WAIT_CAPACITY
#                seconds to wait for quota room before submitting (default: 0,
#                submit immediately and let an over-quota attempt fail). The
#                quota is CPU summed across live jobs and going over it fails
#                outright rather than queueing, so a batch driver should set
#                this rather than retry by hand.
#   OVH_TIMEOUT  kill the job after this long (default: 7d, which is also the
#                hard maximum — the API rejects anything over 604800s). Lower
#                it for anything that should not be able to bill a full week:
#                a wedged command runs out the whole timeout.
set -euo pipefail

OVH_CPU="${OVH_CPU:-8}"
OVH_BUCKET="${OVH_BUCKET:-highline-runs}"
OVH_REGION="${OVH_REGION:-GRA}"
OVH_TIMEOUT="${OVH_TIMEOUT:-7d}"
OVH_WAIT_CAPACITY="${OVH_WAIT_CAPACITY:-0}"
CAPACITY_POLL_SECONDS="${CAPACITY_POLL_SECONDS:-30}"

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

# Forward named secrets (API keys some countries' DTM sources require). Passing
# the name rather than the value keeps it off this script's command line.
for name in ${OVH_ENV:-}; do
    if [ -z "${!name:-}" ]; then
        echo "ovh.sh: \$$name is named in OVH_ENV but unset or empty" >&2
        exit 2
    fi
    OVH_ENV_ARGS+=(--env "$name=${!name}")
done

SCRIPT_DIR="$(dirname "$0")"

# Wait for quota room rather than bouncing off a 402. Deadline-bounded so a
# batch cannot wedge forever behind someone else's long job.
if [ "$OVH_WAIT_CAPACITY" -gt 0 ]; then
    DEADLINE=$(( $(date +%s) + OVH_WAIT_CAPACITY ))
    while [ "$("$SCRIPT_DIR/ovh_jobs.sh" --free-cpu)" -lt "$OVH_CPU" ]; do
        if [ "$(date +%s)" -ge "$DEADLINE" ]; then
            echo "ovh.sh: no room for ${OVH_CPU} CPU after ${OVH_WAIT_CAPACITY}s" >&2
            exit 1
        fi
        echo "ovh.sh: waiting for ${OVH_CPU} CPU of quota to free up" >&2
        sleep "$CAPACITY_POLL_SECONDS"
    done
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

{
    echo "submitted job $JOB_ID for $RUN_ID (timeout $OVH_TIMEOUT, ${OVH_CPU} CPU)"
    echo "  status: ${SCRIPT_DIR}/ovh_jobs.sh $JOB_ID"
    echo "  wait:   ${SCRIPT_DIR}/ovh_jobs.sh --wait $JOB_ID"
    echo "  logs:   ovhai job logs $JOB_ID"
} >&2

printf '%s\n' "$JOB_ID"
