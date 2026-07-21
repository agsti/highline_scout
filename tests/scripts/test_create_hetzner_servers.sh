#!/usr/bin/env bash
# Tests for scripts/create_hetzner_servers.sh.
# Run directly: bash tests/scripts/test_create_hetzner_servers.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$REPO_ROOT/scripts/create_hetzner_servers.sh"

FAILURES=0

assert_eq() {
    local expected="$1" actual="$2" msg="$3"
    if [[ "$expected" != "$actual" ]]; then
        echo "FAIL: $msg" >&2
        echo "  expected: $expected" >&2
        echo "  actual:   $actual" >&2
        FAILURES=$((FAILURES + 1))
    fi
}

assert_contains() {
    local haystack="$1" needle="$2" msg="$3"
    if [[ "$haystack" != *"$needle"* ]]; then
        echo "FAIL: $msg" >&2
        echo "  expected to contain: $needle" >&2
        echo "  actual: $haystack" >&2
        FAILURES=$((FAILURES + 1))
    fi
}

make_pi_env_file() {
    local f; f="$(mktemp)"
    printf 'PI_API_KEY=abc123\n' > "$f"
    echo "$f"
}

make_aws_credentials_file() {
    local f; f="$(mktemp)"
    printf '[default]\naws_access_key_id=AKIA...\naws_secret_access_key=secret...\n' > "$f"
    echo "$f"
}

test_validate_args_rejects_non_numeric_n() {
    local pi_env aws_creds out
    pi_env="$(make_pi_env_file)"; aws_creds="$(make_aws_credentials_file)"
    if out="$(validate_args "abc" "$pi_env" "$aws_creds" 2>&1)"; then
        echo "FAIL: expected validate_args to reject N=abc" >&2
        FAILURES=$((FAILURES + 1))
    else
        assert_contains "$out" "positive integer" "rejects non-numeric N"
    fi
    rm -f "$pi_env" "$aws_creds"
}

test_validate_args_rejects_zero() {
    local pi_env aws_creds
    pi_env="$(make_pi_env_file)"; aws_creds="$(make_aws_credentials_file)"
    if validate_args "0" "$pi_env" "$aws_creds" 2>/dev/null; then
        echo "FAIL: expected validate_args to reject N=0" >&2
        FAILURES=$((FAILURES + 1))
    fi
    rm -f "$pi_env" "$aws_creds"
}

test_validate_args_rejects_missing_pi_env_file() {
    local aws_creds
    aws_creds="$(make_aws_credentials_file)"
    if validate_args "3" "/no/such/pi-env/$$" "$aws_creds" 2>/dev/null; then
        echo "FAIL: expected validate_args to reject a missing pi-env-file" >&2
        FAILURES=$((FAILURES + 1))
    fi
    rm -f "$aws_creds"
}

test_validate_args_rejects_missing_aws_credentials_file() {
    local pi_env
    pi_env="$(make_pi_env_file)"
    if validate_args "3" "$pi_env" "/no/such/aws-creds/$$" 2>/dev/null; then
        echo "FAIL: expected validate_args to reject a missing aws-credentials-file" >&2
        FAILURES=$((FAILURES + 1))
    fi
    rm -f "$pi_env"
}

test_validate_args_accepts_valid_input() {
    local pi_env aws_creds
    pi_env="$(make_pi_env_file)"; aws_creds="$(make_aws_credentials_file)"
    if ! validate_args "3" "$pi_env" "$aws_creds" 2>/dev/null; then
        echo "FAIL: expected validate_args to accept N=3 and existing files" >&2
        FAILURES=$((FAILURES + 1))
    fi
    rm -f "$pi_env" "$aws_creds"
}

test_check_hcloud_installed_fails_when_absent() {
    local empty_path_dir out exit_code
    empty_path_dir="$(mktemp -d)"
    local old_path="$PATH"
    PATH="$empty_path_dir"
    out="$(check_hcloud_installed 2>&1)"
    exit_code=$?
    PATH="$old_path"
    assert_contains "$out" "hcloud CLI not found" "reports missing hcloud"
    assert_eq "1" "$exit_code" "returns 1 when hcloud is missing"
    rm -rf "$empty_path_dir"
}

test_generate_cloud_init_embeds_pi_env_and_aws_credentials() {
    local pi_env aws_creds out
    pi_env="$(make_pi_env_file)"; aws_creds="$(make_aws_credentials_file)"

    out="$(generate_cloud_init "$pi_env" "$aws_creds")"

    assert_contains "$out" "path: /root/bootstrap/pi.env" "embeds pi.env"
    assert_contains "$out" "path: /root/.aws/credentials" "embeds aws credentials at /root/.aws/credentials"
    assert_contains "$out" "  - python3" "installs python3"
    assert_contains "$out" "  - awscli" "installs awscli"
    assert_contains "$out" "npm install -g @earendil-works/pi-coding-agent" "installs pi in runcmd"
    assert_contains "$out" "curl -LsSf https://astral.sh/uv/install.sh | sh" "installs uv in runcmd"
    assert_contains "$out" "just.systems/install.sh" "installs just in runcmd"
    assert_contains "$out" "/etc/profile.d/pi-env.sh" "exports pi env vars for login shells"

    local pi_env_b64 aws_creds_b64
    pi_env_b64="$(base64 -w0 "$pi_env")"
    aws_creds_b64="$(base64 -w0 "$aws_creds")"
    assert_contains "$out" "content: ${pi_env_b64}" "pi.env content matches its base64"
    assert_contains "$out" "content: ${aws_creds_b64}" "aws credentials content matches its base64"

    local pi_env_perms aws_creds_perms
    pi_env_perms="$(echo "$out" | grep -A2 "pi.env" | grep permissions)"
    aws_creds_perms="$(echo "$out" | grep -A2 "/root/.aws/credentials" | grep permissions)"
    assert_contains "$pi_env_perms" "0600" "pi.env is 0600"
    assert_contains "$aws_creds_perms" "0600" "aws credentials is 0600"

    rm -f "$pi_env" "$aws_creds"
}

setup_stub_hcloud() {
    # Args: space-separated server names whose `hcloud server create` call should fail.
    local fail_names="$1"
    STUB_DIR="$(mktemp -d)"
    STUB_LOG="$STUB_DIR/calls.log"
    cat > "$STUB_DIR/hcloud" <<STUB
#!/usr/bin/env bash
echo "\$*" >> "$STUB_LOG"
if [[ "\$1" == "server" && "\$2" == "create" ]]; then
    for fail in $fail_names; do
        for arg in "\$@"; do
            if [[ "\$arg" == "\$fail" ]]; then
                exit 1
            fi
        done
    done
    exit 0
elif [[ "\$1" == "server" && "\$2" == "ip" ]]; then
    echo "10.0.0.\${3##*-}"
    exit 0
fi
exit 1
STUB
    chmod +x "$STUB_DIR/hcloud"
    export PATH="$STUB_DIR:$PATH"
}

test_main_creates_n_servers_with_expected_flags() {
    setup_stub_hcloud ""
    local pi_env aws_creds
    pi_env="$(make_pi_env_file)"; aws_creds="$(make_aws_credentials_file)"

    local out; out="$(main 3 "$pi_env" "$aws_creds" 2>&1)"

    assert_contains "$out" "cpx22-1  10.0.0.1" "reports server 1 with its IP"
    assert_contains "$out" "cpx22-2  10.0.0.2" "reports server 2 with its IP"
    assert_contains "$out" "cpx22-3  10.0.0.3" "reports server 3 with its IP"

    local calls; calls="$(cat "$STUB_LOG")"
    assert_contains "$calls" "--type cpx22" "passes --type cpx22"
    assert_contains "$calls" "--image ubuntu-24.04" "passes --image ubuntu-24.04"
    assert_contains "$calls" "--datacenter nbg1" "passes --datacenter nbg1"
    assert_contains "$calls" "--ssh-key hetzner" "passes --ssh-key hetzner"

    rm -f "$pi_env" "$aws_creds"
    rm -rf "$STUB_DIR"
}

test_main_continues_after_one_failure() {
    setup_stub_hcloud "cpx22-2"
    local pi_env aws_creds
    pi_env="$(make_pi_env_file)"; aws_creds="$(make_aws_credentials_file)"

    local out exit_code
    out="$(main 3 "$pi_env" "$aws_creds" 2>&1)"
    exit_code=$?

    assert_contains "$out" "FAILED: cpx22-2" "reports the failed server"
    assert_contains "$out" "cpx22-1  10.0.0.1" "still creates server 1"
    assert_contains "$out" "cpx22-3  10.0.0.3" "still creates server 3"
    assert_eq "1" "$exit_code" "main exits non-zero when any server failed"

    rm -f "$pi_env" "$aws_creds"
    rm -rf "$STUB_DIR"
}

test_main_rejects_missing_hcloud() {
    local empty_path_dir pi_env aws_creds out exit_code
    empty_path_dir="$(mktemp -d)"
    pi_env="$(make_pi_env_file)"; aws_creds="$(make_aws_credentials_file)"

    local old_path="$PATH"
    PATH="$empty_path_dir"
    out="$(main 1 "$pi_env" "$aws_creds" 2>&1)"
    exit_code=$?
    PATH="$old_path"

    assert_contains "$out" "hcloud CLI not found" "reports missing hcloud"
    assert_eq "1" "$exit_code" "main exits non-zero when hcloud is missing"

    rm -f "$pi_env" "$aws_creds"
    rm -rf "$empty_path_dir"
}

test_validate_args_rejects_non_numeric_n
test_validate_args_rejects_zero
test_validate_args_rejects_missing_pi_env_file
test_validate_args_rejects_missing_aws_credentials_file
test_validate_args_accepts_valid_input
test_check_hcloud_installed_fails_when_absent
test_generate_cloud_init_embeds_pi_env_and_aws_credentials
test_main_creates_n_servers_with_expected_flags
test_main_continues_after_one_failure
test_main_rejects_missing_hcloud

if [[ $FAILURES -gt 0 ]]; then
    echo "$FAILURES test(s) failed" >&2
    exit 1
fi
echo "All tests passed."
