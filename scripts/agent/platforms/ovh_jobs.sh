#!/usr/bin/env bash
# Check on runner jobs spawned by ovh.sh.
#
# usage:
#   ovh_jobs.sh                 table of every job, newest first
#   ovh_jobs.sh --active        only jobs that have not reached a terminal state
#   ovh_jobs.sh <job-id>        detail for one job, with its log and fetch commands
#   ovh_jobs.sh --wait <job-id> block until the job is terminal, exit with its status
#   ovh_jobs.sh --capacity      CPU quota, how much is in use, how much is free
#   ovh_jobs.sh --free-cpu      just the free CPU count, for scripts
#
# Exit status is 0 for --wait on a job that finished cleanly, 1 otherwise.
# Listing modes always exit 0 if the query itself worked.
#
# Environment:
#   OVH_BUCKET   Object Storage bucket holding the artifacts (default: highline-runs)
#   OVH_REGION   Object Storage datastore alias (default: GRA)
#   POLL_SECONDS seconds between --wait status checks (default: 30)
set -euo pipefail

OVH_BUCKET="${OVH_BUCKET:-highline-runs}"
OVH_REGION="${OVH_REGION:-GRA}"
POLL_SECONDS="${POLL_SECONDS:-30}"

# Terminal states per the CLI; everything else means the job is still alive.
TERMINAL_RE='^(DONE|FAILED|ERROR|TIMEOUT|INTERRUPTED|SYNC_FAILED)$'

# jq helpers shared by the modes below. OVH only fills in .status.duration
# some of the time, so elapsed falls back to the timestamps — which also gives
# a running job its time-so-far rather than a blank.
JQ_DURATION='
def fmt: if . == null then "-" else . as $s
    | if $s >= 3600 then "\($s / 3600 | floor)h\(($s % 3600) / 60 | floor)m"
      elif $s >= 60 then "\($s / 60 | floor)m\($s % 60)s"
      else "\($s)s" end end;
def secs: if . == null or . == "" then null else (tonumber | floor) end;
def stamp: if . == null or . == "" then null
    else (.[0:19] + "Z" | fromdateiso8601) end;
def elapsed: (.status.duration | secs) as $d
    | if $d != null then $d
      else (.status.startedAt | stamp) as $a
        | ((.status.finalizedAt | stamp) // (now | floor)) as $b
        | if $a == null then null else ($b - $a) end
      end;
'

# The quota is a sum of the CPUs requested by live jobs, not a limit on how
# many jobs there are. Submitting past it fails outright (HTTP 402) rather
# than queueing, so callers have to look before they leap.
free_cpu() {
    local quota used
    quota="$(ovhai me --output json | jq -r '.quotas.resources.CPU')"
    used="$(ovhai job list --all --output json \
        | jq "[.[] | select(.status.state | test(\"$TERMINAL_RE\") | not)
               | .spec.resources.cpu] | add // 0")"
    echo $((quota - used))
}

show_capacity() {
    local quota used live
    quota="$(ovhai me --output json | jq -r '.quotas.resources.CPU')"
    live="$(ovhai job list --all --output json \
        | jq "[.[] | select(.status.state | test(\"$TERMINAL_RE\") | not)]")"
    used="$(printf '%s' "$live" | jq '[.[] | .spec.resources.cpu] | add // 0')"
    printf 'quota: %s CPU\n' "$quota"
    printf 'used:  %s CPU across %s job(s)\n' "$used" "$(printf '%s' "$live" | jq 'length')"
    printf 'free:  %s CPU\n\n' "$((quota - used))"
    # A table rather than one line for $OVH_CPU: the caller is usually deciding
    # what to set OVH_CPU to, so reporting only the current value answers the
    # wrong question.
    printf 'room for, at OVH_CPU =\n'
    local cpu
    for cpu in 12 8 5 4 2; do
        printf '  %-3s %s more job(s)\n' "$cpu" "$(( (quota - used) / cpu ))"
    done
}

list_jobs() {
    local only_active="$1" jobs
    jobs="$(ovhai job list --all --output json)"

    printf '%s' "$jobs" | jq -r --arg active "$only_active" "
        $JQ_DURATION
        def runid: (.spec.envVars // [] | map(select(.name == \"RUN_ID\")) | .[0].value // \"-\");
        map(select(\$active != \"1\" or (.status.state | test(\"$TERMINAL_RE\") | not)))
        | sort_by(.status.queuedAt) | reverse
        | .[]
        | [ .id[0:8], (.spec.name // \"-\"), .status.state,
            (.spec.resources.cpu // \"-\" | tostring),
            (. | elapsed | fmt),
            (.status.exitCode // \"-\" | tostring),
            (.status.queuedAt // \"-\" | .[0:16]),
            runid ]
        | @tsv" \
    | { printf 'JOB\tNAME\tSTATE\tCPU\tDURATION\tEXIT\tQUEUED\tRUN_ID\n'; cat; } \
    | column -t -s "$(printf '\t')"

    local alive
    alive="$(printf '%s' "$jobs" | jq "[.[] | select(.status.state | test(\"$TERMINAL_RE\") | not)] | length")"
    echo
    if [ "$alive" -gt 0 ]; then
        echo "$alive job(s) still running — these are billing right now."
    else
        echo "No jobs running; nothing is billing."
    fi
}

show_job() {
    local job_id="$1" job state run_id
    job="$(ovhai job get "$job_id" --output json)"
    state="$(printf '%s' "$job" | jq -r '.status.state')"
    run_id="$(printf '%s' "$job" | jq -r '.spec.envVars // [] | map(select(.name == "RUN_ID")) | .[0].value // "-"')"

    printf '%s' "$job" | jq -r "
        $JQ_DURATION
        \"job:       \(.id)
name:      \(.spec.name // \"-\")
state:     \(.status.state)\(if .status.exitCode != null then \" (exit \(.status.exitCode))\" else \"\" end)
message:   \(.status.info.message // \"-\")
image:     \(.spec.image)
resources: \(.spec.resources.cpu) CPU, \(.spec.resources.memory // 0 | tonumber / 1073741824 | floor) GiB RAM, \(.spec.resources.ephemeralStorage // 0 | tonumber / 1073741824 | floor) GiB disk
timeout:   \(.spec.timeout | secs | fmt)
queued:    \(.status.queuedAt // \"-\")
started:   \(.status.startedAt // \"-\")
finished:  \(.status.finalizedAt // \"-\")
duration:  \(elapsed | fmt)\""

    echo "declared artifacts:"
    printf '%s' "$job" | jq -r '.spec.envVars // [] | map(select(.name == "ARTIFACTS")) | .[0].value // "(none)"' \
        | sed 's/^/  /'

    echo
    echo "logs:  ovhai job logs $job_id"
    if [ "$run_id" != "-" ]; then
        echo "kept:  ovhai bucket object list $OVH_BUCKET@$OVH_REGION | grep runs/$run_id"
        echo "fetch: ovhai bucket object download $OVH_BUCKET@$OVH_REGION \\"
        echo "           -p runs/$run_id/ -r runs/$run_id/ -o ./"
    fi

    if printf '%s' "$state" | grep -qE "$TERMINAL_RE"; then
        [ "$state" = "DONE" ] && return 0 || return 1
    fi
    return 0
}

wait_job() {
    local job_id="$1" state
    while true; do
        state="$(ovhai job get "$job_id" --output json | jq -r '.status.state')"
        if printf '%s' "$state" | grep -qE "$TERMINAL_RE"; then
            echo "job $job_id finished: $state" >&2
            show_job "$job_id"
            return
        fi
        echo "job $job_id: $state" >&2
        sleep "$POLL_SECONDS"
    done
}

case "${1:-}" in
"") list_jobs 0 ;;
--active) list_jobs 1 ;;
--capacity) show_capacity ;;
--free-cpu) free_cpu ;;
--wait)
    if [ "$#" -lt 2 ]; then
        echo "usage: ovh_jobs.sh --wait <job-id>" >&2
        exit 2
    fi
    wait_job "$2"
    ;;
-h | --help)
    sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'
    ;;
-*)
    echo "ovh_jobs.sh: unknown option '$1'" >&2
    exit 2
    ;;
*) show_job "$1" ;;
esac
