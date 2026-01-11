#!/bin/bash

# kycli Global Test Matrix Validator
# Tests ALL commands and ALL options (flags).

# Setup
export BASE_TEST_DIR="/tmp/kycli_matrix_final"
rm -rf "$BASE_TEST_DIR"
mkdir -p "$BASE_TEST_DIR"
export PYTHONPATH=.
export TERM=dumb

# Helper
KY_CLI="python3 -m kycli.cli"

# Column Widths
W_ID=13
W_CMD=20
W_DESC=45
W_STAT=8

# Table Header
printf "| %-${W_ID}s | %-${W_CMD}s | %-${W_DESC}s | %-${W_STAT}s |\n" "Test Case #" "Command/Option" "Test Description" "Status"
printf "|-%-${W_ID}s-|-%-${W_CMD}s-|-%-${W_DESC}s-|-%-${W_STAT}s-|\n" "$(printf '%0.s-' $(seq 1 $W_ID))" "$(printf '%0.s-' $(seq 1 $W_CMD))" "$(printf '%0.s-' $(seq 1 $W_DESC))" "$(printf '%0.s-' $(seq 1 $W_STAT))" | sed 's/ /-/g'

count=1

check_test() {
    local cmd_label=$1
    local description=$2
    local exit_condition=$3
    local match_pattern=$4
    local actual_output=$5

    local status="FAIL"
    if echo "$actual_output" | grep -Ei "$match_pattern" > /dev/null; then
        status="PASS"
    fi

    printf "| %-${W_ID}s | %-${W_CMD}s | %-${W_DESC}s | %-${W_STAT}s |\n" "$count" "$cmd_label" "$description" "$status"
    ((count++))
}

# --- SECTION 1: Standard Commands ---
export HOME="$BASE_TEST_DIR/standard"
mkdir -p "$HOME"

out=$($KY_CLI kys k1 v1 --ttl 3600 2>&1)
check_test "kys" "Save basic key" $? "Saved" "$out"

out=$($KY_CLI kyg k1 2>&1)
check_test "kyg" "Read basic key" $? "v1" "$out"

out=$($KY_CLI kys k1 v2 --ttl 3600 2>&1)
check_test "kys (Update)" "Overwrite key" $? "Updated|No Change" "$out"

out=$($KY_CLI kyl 2>&1)
check_test "kyl" "List all keys" $? "k1" "$out"

out=$($KY_CLI kyg -s "v2" 2>&1)
check_test "kyg -s" "Full-text search" $? "k1" "$out"

out=$($KY_CLI kyg -s "v2" --limit 1 2>&1)
check_test "--limit" "Search with limit" $? "k1" "$out"

out=$($KY_CLI kyg -s "v2" --keys-only 2>&1)
check_test "--keys-only" "Search for keys only" $? "k1" "$out"

out=$($KY_CLI kys j '{"x": 1}' --ttl 3600 2>&1)
out=$($KY_CLI kypatch j.x 5 2>&1)
check_test "kypatch" "Patch JSON path" $? "Patched" "$out"

out=$($KY_CLI kys l '[1]' --ttl 3600 2>&1)
out=$($KY_CLI kypush l 2 2>&1)
check_test "kypush" "Append to list" $? "Updated|Result|overwritten" "$out"

out=$($KY_CLI kyrem l 1 2>&1)
check_test "kyrem" "Remove from list" $? "Updated|Result|overwritten" "$out"

# --- SECTION 2: Scenarios & Flags ---
out=$($KY_CLI kys k_ttl v --ttl 10 2>&1)
check_test "--ttl" "Save with expiration" $? "Expires" "$out"

# Encryption (Isolated HOME to avoid decryption fail on load)
export HOME="$BASE_TEST_DIR/enc"
mkdir -p "$HOME"
out=$($KY_CLI kys s1 "secret" --key "pass" --ttl 3600 2>&1)
check_test "--key (Save)" "Encrypted save" $? "Saved" "$out"

out=$($KY_CLI kyg s1 --key "pass" 2>&1)
check_test "--key (Read)" "Encrypted read" $? "secret" "$out"

export KYCLI_MASTER_KEY="pass"
out=$($KY_CLI kyg s1 2>&1)
check_test "KYCLI_MASTER_KEY" "Read via environment variable" $? "secret" "$out"
unset KYCLI_MASTER_KEY

# Workspaces
export HOME="$BASE_TEST_DIR/standard"
$KY_CLI kyuse ws1 > /dev/null
$KY_CLI kys mk "v" --ttl 3600 > /dev/null
$KY_CLI kyuse default > /dev/null
out=$(echo "y" | $KY_CLI kydrop ws1 2>&1)
check_test "kydrop" "Delete non-active workspace" $? "deleted" "$out"

# Drop active
$KY_CLI kyuse active_to_drop > /dev/null
$KY_CLI kys k "v" --ttl 3600 > /dev/null
out=$(echo "y" | $KY_CLI kydrop active_to_drop 2>&1)
curr_ws=$($KY_CLI kyws --current 2>&1)
if [[ "$out" == *"deleted"* ]] && [[ "$out" == *"Switched to 'default'"* ]] && [[ "$curr_ws" == "default" ]]; then
    status_ws="PASS"
else
    status_ws="FAIL"
fi
printf "| %-${W_ID}s | %-${W_CMD}s | %-${W_DESC}s | %-${W_STAT}s |\n" "$count" "kydrop (Active)" "Delete active workspace & move to default" "$status_ws"
((count++))

out=$($KY_CLI kyws --current 2>&1)
check_test "kyws --current" "Verify current workspace" $? "default" "$out"

$KY_CLI kys move_me "val" --ttl 3600 > /dev/null
out=$(echo "y" | $KY_CLI kymv move_me ws_new --ttl 3600 2>&1)
check_test "kymv" "Move key to new workspace" $? "Moved" "$out"

# Recovery
echo "k1" | $KY_CLI kyd k1 > /dev/null
out=$($KY_CLI kyr k1 2>&1)
check_test "kyr" "Restore deleted key" $? "Restored" "$out"

ts=$(date "+%Y-%m-%d %H:%M:%S")
sleep 1
$KY_CLI kys p1 "v" --ttl 3600 > /dev/null
out=$($KY_CLI kyrt "$ts" 2>&1)
check_test "kyrt" "Recovery to timestamp" $? "restored" "$out"

# Meta
out=$($KY_CLI kyh 2>&1)
check_test "kyh" "Help command" $? "Available" "$out"

out=$($KY_CLI init 2>&1)
check_test "init" "Integration info" $? "Integration|Already" "$out"

out=$($KY_CLI kyfo 2>&1)
check_test "kyfo" "Index optimization" $? "optimized" "$out"

out=$($KY_CLI kyco 0 2>&1)
check_test "kyco" "Compaction" $? "complete" "$out"

# Cleanup
rm -rf "$BASE_TEST_DIR"
