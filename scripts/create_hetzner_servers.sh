#!/usr/bin/env bash
# Create N disposable Hetzner Cloud CPX22 servers, bootstrapped via cloud-init
# with git/uv/pi/awscli plus every file in a given directory.
#
# Usage: scripts/create_hetzner_servers.sh <N> <bootstrap-dir>
#
# Prerequisites: the `hcloud` CLI must be installed and authenticated
# (existing context or HCLOUD_TOKEN), and an SSH key named "hetzner" must
# already exist in the Hetzner project.
set -uo pipefail

SERVER_TYPE="cpx22"
SERVER_IMAGE="ubuntu-24.04"
SERVER_DATACENTER="nbg1"
SERVER_SSH_KEY="hetzner"

check_hcloud_installed() {
    if ! command -v hcloud >/dev/null 2>&1; then
        echo "error: hcloud CLI not found on PATH." >&2
        echo "Install it: https://github.com/hetznercloud/cli#installation" >&2
        return 1
    fi
}

validate_args() {
    local n="$1" bootstrap_dir="$2"
    if ! [[ "$n" =~ ^[1-9][0-9]*$ ]]; then
        echo "error: N must be a positive integer, got '$n'" >&2
        return 1
    fi
    if [[ ! -d "$bootstrap_dir" ]]; then
        echo "error: bootstrap-dir '$bootstrap_dir' is not a directory" >&2
        return 1
    fi
}

generate_cloud_init() {
    local bootstrap_dir="$1"
    cat <<'HEADER'
#cloud-config
package_update: true
packages:
  - git
  - curl
  - nodejs
  - npm
  - awscli
HEADER

    local files=()
    while IFS= read -r -d '' f; do
        files+=("$f")
    done < <(find "$bootstrap_dir" -maxdepth 1 -type f -print0 | sort -z)

    if [[ ${#files[@]} -eq 0 ]]; then
        echo "write_files: []"
    else
        echo "write_files:"
        local f base perms content
        for f in "${files[@]}"; do
            base="$(basename "$f")"
            if [[ -x "$f" ]]; then perms="0755"; else perms="0644"; fi
            content="$(base64 -w0 "$f")"
            cat <<ENTRY
  - path: /root/bootstrap/${base}
    encoding: b64
    permissions: '${perms}'
    content: ${content}
ENTRY
        done
    fi

    cat <<'RUNCMD'
runcmd:
  - curl -LsSf https://astral.sh/uv/install.sh | sh
  - npm install -g @earendil-works/pi-coding-agent
RUNCMD
}
