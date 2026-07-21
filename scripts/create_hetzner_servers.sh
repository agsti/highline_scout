#!/usr/bin/env bash
# Create N disposable Hetzner Cloud CPX22 servers, bootstrapped via cloud-init
# with git, python3, uv, just, awscli, and the pi coding agent.
#
# Usage: scripts/create_hetzner_servers.sh <N> <pi-env-file> <aws-credentials-file>
#
# pi-env-file: KEY=VALUE lines (one per line), exported for every login shell
# on the new server (e.g. the pi coding agent's API key).
# aws-credentials-file: copied verbatim to /root/.aws/credentials.
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
    local n="$1" pi_env_file="$2" aws_credentials_file="$3"
    if ! [[ "$n" =~ ^[1-9][0-9]*$ ]]; then
        echo "error: N must be a positive integer, got '$n'" >&2
        return 1
    fi
    if [[ ! -f "$pi_env_file" ]]; then
        echo "error: pi-env-file '$pi_env_file' is not a file" >&2
        return 1
    fi
    if [[ ! -f "$aws_credentials_file" ]]; then
        echo "error: aws-credentials-file '$aws_credentials_file' is not a file" >&2
        return 1
    fi
}

generate_cloud_init() {
    local pi_env_file="$1" aws_credentials_file="$2"
    local pi_env_b64 aws_credentials_b64
    pi_env_b64="$(base64 -w0 "$pi_env_file")"
    aws_credentials_b64="$(base64 -w0 "$aws_credentials_file")"

    cat <<HEADER
#cloud-config
package_update: true
packages:
  - git
  - curl
  - nodejs
  - npm
  - python3
  - awscli
write_files:
  - path: /root/bootstrap/pi.env
    encoding: b64
    permissions: '0600'
    content: ${pi_env_b64}
  - path: /root/.aws/credentials
    encoding: b64
    permissions: '0600'
    content: ${aws_credentials_b64}
runcmd:
  - curl -LsSf https://astral.sh/uv/install.sh | sh
  - npm install -g @earendil-works/pi-coding-agent
  - curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin
  - bash -c 'while IFS= read -r line; do [ -n "\$line" ] && echo "export \$line" >> /etc/profile.d/pi-env.sh; done < /root/bootstrap/pi.env'
HEADER
}

create_server() {
    local name="$1" cloud_init_file="$2"
    if ! hcloud server create \
        --type "$SERVER_TYPE" \
        --image "$SERVER_IMAGE" \
        --datacenter "$SERVER_DATACENTER" \
        --ssh-key "$SERVER_SSH_KEY" \
        --name "$name" \
        --user-data-from-file "$cloud_init_file" >/dev/null; then
        echo "FAILED: $name" >&2
        return 1
    fi
    local ip
    ip="$(hcloud server ip "$name")"
    echo "$name  $ip"
}

main() {
    if [[ $# -ne 3 ]]; then
        echo "usage: $0 <N> <pi-env-file> <aws-credentials-file>" >&2
        return 1
    fi
    local n="$1" pi_env_file="$2" aws_credentials_file="$3"

    check_hcloud_installed || return 1
    validate_args "$n" "$pi_env_file" "$aws_credentials_file" || return 1

    local cloud_init_file
    cloud_init_file="$(mktemp)"
    generate_cloud_init "$pi_env_file" "$aws_credentials_file" > "$cloud_init_file"

    local i failures=0
    for ((i = 1; i <= n; i++)); do
        create_server "cpx22-${i}" "$cloud_init_file" || failures=$((failures + 1))
    done

    rm -f "$cloud_init_file"

    if [[ $failures -gt 0 ]]; then
        echo "warning: ${failures} of ${n} server(s) failed to create" >&2
        return 1
    fi
    return 0
}

if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
    main "$@"
fi
