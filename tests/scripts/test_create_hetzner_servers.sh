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

test_validate_args_rejects_non_numeric_n() {
    local out
    if out="$(validate_args "abc" "$REPO_ROOT" 2>&1)"; then
        echo "FAIL: expected validate_args to reject N=abc" >&2
        FAILURES=$((FAILURES + 1))
    else
        assert_contains "$out" "positive integer" "rejects non-numeric N"
    fi
}

test_validate_args_rejects_zero() {
    if validate_args "0" "$REPO_ROOT" 2>/dev/null; then
        echo "FAIL: expected validate_args to reject N=0" >&2
        FAILURES=$((FAILURES + 1))
    fi
}

test_validate_args_rejects_missing_dir() {
    if validate_args "3" "/no/such/dir/$$" 2>/dev/null; then
        echo "FAIL: expected validate_args to reject a missing bootstrap-dir" >&2
        FAILURES=$((FAILURES + 1))
    fi
}

test_validate_args_accepts_valid_input() {
    if ! validate_args "3" "$REPO_ROOT" 2>/dev/null; then
        echo "FAIL: expected validate_args to accept N=3 and an existing dir" >&2
        FAILURES=$((FAILURES + 1))
    fi
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

test_generate_cloud_init_embeds_files_and_preserves_exec_bit() {
    local dir; dir="$(mktemp -d)"
    echo "hello" > "$dir/plain.txt"
    printf '#!/bin/sh\necho hi\n' > "$dir/run.sh"
    chmod +x "$dir/run.sh"

    local out; out="$(generate_cloud_init "$dir")"

    assert_contains "$out" "path: /root/bootstrap/plain.txt" "embeds plain.txt"
    assert_contains "$out" "path: /root/bootstrap/run.sh" "embeds run.sh"
    assert_contains "$out" "npm install -g @earendil-works/pi-coding-agent" "installs pi in runcmd"
    assert_contains "$out" "curl -LsSf https://astral.sh/uv/install.sh | sh" "installs uv in runcmd"

    local plain_b64 run_b64
    plain_b64="$(base64 -w0 "$dir/plain.txt")"
    run_b64="$(base64 -w0 "$dir/run.sh")"
    assert_contains "$out" "content: ${plain_b64}" "plain.txt content matches its base64"
    assert_contains "$out" "content: ${run_b64}" "run.sh content matches its base64"

    local plain_perms run_perms
    plain_perms="$(echo "$out" | grep -A2 "plain.txt" | grep permissions)"
    run_perms="$(echo "$out" | grep -A2 "run.sh" | grep permissions)"
    assert_contains "$plain_perms" "0644" "non-executable file gets 0644"
    assert_contains "$run_perms" "0755" "executable file keeps 0755"

    rm -rf "$dir"
}

test_generate_cloud_init_empty_dir_has_empty_write_files() {
    local dir; dir="$(mktemp -d)"
    local out; out="$(generate_cloud_init "$dir")"
    assert_contains "$out" "write_files: []" "empty bootstrap dir produces empty write_files"
    rm -rf "$dir"
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
    local dir; dir="$(mktemp -d)"
    echo "x" > "$dir/f.txt"

    local out; out="$(main 3 "$dir" 2>&1)"

    assert_contains "$out" "cpx22-1  10.0.0.1" "reports server 1 with its IP"
    assert_contains "$out" "cpx22-2  10.0.0.2" "reports server 2 with its IP"
    assert_contains "$out" "cpx22-3  10.0.0.3" "reports server 3 with its IP"

    local calls; calls="$(cat "$STUB_LOG")"
    assert_contains "$calls" "--type cpx22" "passes --type cpx22"
    assert_contains "$calls" "--image ubuntu-24.04" "passes --image ubuntu-24.04"
    assert_contains "$calls" "--datacenter nbg1" "passes --datacenter nbg1"
    assert_contains "$calls" "--ssh-key hetzner" "passes --ssh-key hetzner"

    rm -rf "$dir" "$STUB_DIR"
}

test_main_continues_after_one_failure() {
    setup_stub_hcloud "cpx22-2"
    local dir; dir="$(mktemp -d)"
    echo "x" > "$dir/f.txt"

    local out exit_code
    out="$(main 3 "$dir" 2>&1)"
    exit_code=$?

    assert_contains "$out" "FAILED: cpx22-2" "reports the failed server"
    assert_contains "$out" "cpx22-1  10.0.0.1" "still creates server 1"
    assert_contains "$out" "cpx22-3  10.0.0.3" "still creates server 3"
    assert_eq "1" "$exit_code" "main exits non-zero when any server failed"

    rm -rf "$dir" "$STUB_DIR"
}

test_main_rejects_missing_hcloud() {
    local empty_path_dir dir out exit_code
    empty_path_dir="$(mktemp -d)"
    dir="$(mktemp -d)"
    echo "x" > "$dir/f.txt"

    local old_path="$PATH"
    PATH="$empty_path_dir"
    out="$(main 1 "$dir" 2>&1)"
    exit_code=$?
    PATH="$old_path"

    assert_contains "$out" "hcloud CLI not found" "reports missing hcloud"
    assert_eq "1" "$exit_code" "main exits non-zero when hcloud is missing"

    rm -rf "$dir" "$empty_path_dir"
}

test_validate_args_rejects_non_numeric_n
test_validate_args_rejects_zero
test_validate_args_rejects_missing_dir
test_validate_args_accepts_valid_input
test_check_hcloud_installed_fails_when_absent
test_generate_cloud_init_embeds_files_and_preserves_exec_bit
test_generate_cloud_init_empty_dir_has_empty_write_files
test_main_creates_n_servers_with_expected_flags
test_main_continues_after_one_failure
test_main_rejects_missing_hcloud

if [[ $FAILURES -gt 0 ]]; then
    echo "$FAILURES test(s) failed" >&2
    exit 1
fi
echo "All tests passed."
