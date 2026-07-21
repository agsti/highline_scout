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

test_validate_args_rejects_non_numeric_n
test_validate_args_rejects_zero
test_validate_args_rejects_missing_dir
test_validate_args_accepts_valid_input
test_check_hcloud_installed_fails_when_absent
test_generate_cloud_init_embeds_files_and_preserves_exec_bit
test_generate_cloud_init_empty_dir_has_empty_write_files
