#!/usr/bin/env bash
# Download what a run kept in Object Storage.
#
# usage:
#   ovh_fetch.sh <run-id> [dest]   fetch one run's artifacts (default dest: .)
#   ovh_fetch.sh --only data/ <run-id> [dest]
#                                  fetch only paths under that subdirectory
#   ovh_fetch.sh --list            run-ids present in the bucket
#   ovh_fetch.sh --list <run-id>   what that run kept, with sizes
#
# A run usually keeps cache/<country>/ as well as data/<country>/, and the
# cache is the bulk of the bytes (tens of GB of DTM tiles) while being
# re-downloadable. Use --only data/ when you just want the output.
#
# Paths land at their repo-relative position under <dest>: a run that kept
# data/japan/ writes <dest>/data/japan/, so fetching into a checkout drops the
# output where the app expects it. run.log comes along with it.
#
# Environment:
#   OVH_BUCKET  Object Storage bucket (default: highline-runs)
#   OVH_REGION  Object Storage datastore alias (default: GRA)
set -euo pipefail

OVH_BUCKET="${OVH_BUCKET:-highline-runs}"
OVH_REGION="${OVH_REGION:-GRA}"
STORE="$OVH_BUCKET@$OVH_REGION"

list_runs() {
    ovhai bucket object list "$STORE" 2>/dev/null \
        | awk '$4 ~ /^runs\// {split($4, p, "/"); print p[2]}' \
        | sort -u
}

list_one() {
    ovhai bucket object list "$STORE" 2>/dev/null \
        | awk -v run="runs/$1/" '$4 ~ run {print $2, $3, $4}'
}

ONLY=""
if [ "${1:-}" = "--only" ]; then
    if [ "$#" -lt 3 ]; then
        echo "usage: ovh_fetch.sh --only <subpath> <run-id> [dest]" >&2
        exit 2
    fi
    ONLY="${2#/}"
    shift 2
fi

case "${1:-}" in
-h | --help)
    sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
--list)
    if [ "$#" -ge 2 ]; then
        list_one "$2"
    else
        list_runs
    fi
    exit 0
    ;;
"")
    echo "usage: ovh_fetch.sh <run-id> [dest]" >&2
    exit 2
    ;;
esac

RUN_ID="$1"
DEST="${2:-.}"

if ! list_runs | grep -qx "$RUN_ID"; then
    echo "ovh_fetch.sh: no run '$RUN_ID' in $STORE" >&2
    echo "known runs:" >&2
    list_runs | sed 's/^/  /' >&2
    exit 1
fi

mkdir -p "$DEST"
# -r strips the runs/<id>/ prefix so paths land where the repo expects them;
# -o must end in a slash or the CLI rejects it.
ovhai bucket object download "$STORE" \
    --prefix "runs/$RUN_ID/${ONLY}" \
    --remove-prefix "runs/$RUN_ID/" \
    --output "${DEST%/}/"

echo "fetched ${ONLY:-everything} from $RUN_ID into ${DEST%/}/" >&2
