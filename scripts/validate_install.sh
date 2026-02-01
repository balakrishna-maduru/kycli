#!/bin/bash

# kycli Global Test Matrix Validator
# Tests ALL commands and ALL options (flags).

# Setup
export BASE_TEST_DIR="/tmp/kycli_matrix_final"
rm -rf "$BASE_TEST_DIR"
mkdir -p "$BASE_TEST_DIR"
export PYTHONPATH=.
export TERM=xterm-256color

# Colors
ESC=$(printf '\033')
GREEN="${ESC}[0;32m"
RED="${ESC}[0;31m"
NC="${ESC}[0m"

# Helper
PYTHON_CMD=${PYTHON_EXECUTABLE:-"$(pwd)/.venv/bin/python"}
KY_CLI="$PYTHON_CMD -m kycli.cli"

# Column Widths
W_ID=13
W_CMD=20
W_DESC=45
W_STAT=8

# Table Header
printf "|-%-${W_ID}s-|-%-${W_CMD}s-|-%-${W_DESC}s-|-%-${W_STAT}s-|\n" "$(printf '%0.s-' $(seq 1 $W_ID))" "$(printf '%0.s-' $(seq 1 $W_CMD))" "$(printf '%0.s-' $(seq 1 $W_DESC))" "$(printf '%0.s-' $(seq 1 $W_STAT))" | sed 's/ /-/g'
printf "| %-${W_ID}s | %-${W_CMD}s | %-${W_DESC}s | %-${W_STAT}s |\n" "Test Case #" "Command/Option" "Test Description" "Status"
printf "|-%-${W_ID}s-|-%-${W_CMD}s-|-%-${W_DESC}s-|-%-${W_STAT}s-|\n" "$(printf '%0.s-' $(seq 1 $W_ID))" "$(printf '%0.s-' $(seq 1 $W_CMD))" "$(printf '%0.s-' $(seq 1 $W_DESC))" "$(printf '%0.s-' $(seq 1 $W_STAT))" | sed 's/ /-/g'

count=1
total=0
passed=0
last_output=""
last_status=0

run_cmd() {
    local cmd="$1"
    last_output=$(eval "$cmd" 2>&1)
    last_status=$?
}

check_test() {
    local cmd_label=$1
    local description=$2
    local actual_exit=$3
    local match_pattern=$4
    local actual_output=$5
    local expected_exit=${6:-0}

    local status="FAIL"
    local pattern_ok=1
    if [[ -n "$match_pattern" ]]; then
        echo "$actual_output" | grep -Ei "$match_pattern" > /dev/null
        pattern_ok=$?
    fi

    if [[ "$actual_exit" -eq "$expected_exit" && "$pattern_ok" -eq 0 ]]; then
        status="PASS"
    elif [[ -z "$match_pattern" && "$actual_exit" -eq "$expected_exit" ]]; then
        status="PASS"
    fi

    ((total++))
    if [[ "$status" == "PASS" ]]; then
        ((passed++))
    fi

    local status_display="${RED}${status}${NC}"
    if [[ "$status" == "PASS" ]]; then
        status_display="${GREEN}${status}${NC}"
    fi

    # Width 19 = 8 (original width) + 11 (color codes)
    printf "| %-${W_ID}s | %-${W_CMD}s | %-${W_DESC}s | %-19s |\n" "$count" "$cmd_label" "$description" "$status_display"
    ((count++))
}

# --- SECTION 1: Standard Commands ---
export HOME="$BASE_TEST_DIR/standard"
mkdir -p "$HOME"

run_cmd "$KY_CLI kys k1 v1 --ttl 3600"
check_test "kys" "Save basic key" $last_status "Saved" "$last_output"

run_cmd "$KY_CLI kyg k1"
check_test "kyg" "Read basic key" $last_status "v1" "$last_output"

run_cmd "$KY_CLI kys k1 v2 --ttl 3600"
check_test "kys (Update)" "Overwrite key" $last_status "Updated|No Change" "$last_output"

run_cmd "$KY_CLI kyl"
check_test "kyl" "List all keys" $last_status "k1" "$last_output"

run_cmd "$KY_CLI kyg -s \"v2\""
check_test "kyg -s" "Full-text search" $last_status "k1" "$last_output"

run_cmd "$KY_CLI kyg -s \"v2\" --limit 1"
check_test "--limit" "Search with limit" $last_status "k1" "$last_output"

run_cmd "$KY_CLI kyg -s \"v2\" --keys-only"
check_test "--keys-only" "Search for keys only" $last_status "k1" "$last_output"

run_cmd "$KY_CLI kys j '{\"x\": 1}' --ttl 3600"
run_cmd "$KY_CLI kypatch j.x 5"
check_test "kypatch" "Patch JSON path" $last_status "Patched" "$last_output"

run_cmd "$KY_CLI kys l '[1]' --ttl 3600"
run_cmd "$KY_CLI kypush l 2"
check_test "kypush" "Append to list" $last_status "Updated|Result|overwritten" "$last_output"

run_cmd "$KY_CLI kyrem l 1"
check_test "kyrem" "Remove from list" $last_status "Updated|Result|overwritten" "$last_output"

# --- SECTION 2: Scenarios & Flags ---
run_cmd "$KY_CLI kys k_ttl v --ttl 10"
check_test "--ttl" "Save with expiration" $last_status "Expires" "$last_output"

# Encryption (Isolated HOME to avoid decryption fail on load)
export HOME="$BASE_TEST_DIR/enc"
mkdir -p "$HOME"
run_cmd "$KY_CLI kys s1 \"secret\" --key \"pass\" --ttl 3600"
check_test "--key (Save)" "Encrypted save" $last_status "Saved" "$last_output"

run_cmd "$KY_CLI kyg s1 --key \"pass\""
check_test "--key (Read)" "Encrypted read" $last_status "secret" "$last_output"

export KYCLI_MASTER_KEY="pass"
run_cmd "$KY_CLI kyg s1"
check_test "KYCLI_MASTER_KEY" "Read via environment variable" $last_status "secret" "$last_output"
unset KYCLI_MASTER_KEY

# Workspaces
export HOME="$BASE_TEST_DIR/standard"
$KY_CLI kyuse ws1 > /dev/null
$KY_CLI kys mk "v" --ttl 3600 > /dev/null
$KY_CLI kyuse default > /dev/null
run_cmd "echo \"y\" | $KY_CLI kydrop ws1"
check_test "kydrop" "Delete non-active workspace" $last_status "deleted" "$last_output"

# Drop active
$KY_CLI kyuse active_to_drop > /dev/null
$KY_CLI kys k "v" --ttl 3600 > /dev/null
run_cmd "echo \"y\" | $KY_CLI kydrop active_to_drop"
curr_ws=$($KY_CLI kyws --current 2>&1)
if [[ "$last_output" == *"deleted"* ]] && [[ "$last_output" == *"Switched to 'default'"* ]] && [[ "$curr_ws" == "default" ]]; then
    status_ws="PASS"
else
    status_ws="FAIL"
fi

((total++))
status_display_ws="${RED}${status_ws}${NC}"
if [[ "$status_ws" == "PASS" ]]; then
    ((passed++))
    status_display_ws="${GREEN}${status_ws}${NC}"
fi

printf "| %-${W_ID}s | %-${W_CMD}s | %-${W_DESC}s | %-19s |\n" "$count" "kydrop (Active)" "Delete active workspace & move to default" "$status_display_ws"
((count++))

run_cmd "$KY_CLI kyws --current"
check_test "kyws --current" "Verify current workspace" $last_status "default" "$last_output"

$KY_CLI kys move_me "val" --ttl 3600 > /dev/null
run_cmd "echo \"y\" | $KY_CLI kymv move_me ws_new --ttl 3600"
check_test "kymv" "Move key to new workspace" $last_status "Moved" "$last_output"

# Recovery
echo "k1" | $KY_CLI kyd k1 > /dev/null
run_cmd "$KY_CLI kyr k1"
check_test "kyr" "Restore deleted key" $last_status "Restored" "$last_output"

ts=$(date "+%Y-%m-%d %H:%M:%S")
sleep 1
$KY_CLI kys p1 "v" --ttl 3600 > /dev/null
run_cmd "$KY_CLI kyrt \"$ts\""
check_test "kyrt" "Recovery to timestamp" $last_status "restored" "$last_output"

# Meta
run_cmd "$KY_CLI kyh"
check_test "kyh" "Help command" $last_status "Available" "$last_output"

run_cmd "$KY_CLI init"
check_test "init" "Integration info" $last_status "Integration|Already" "$last_output"

run_cmd "$KY_CLI kyfo"
check_test "kyfo" "Index optimization" $last_status "optimized" "$last_output"

run_cmd "$KY_CLI kyco 0"
check_test "kyco" "Compaction" $last_status "complete" "$last_output"

# --- SECTION 4: Security & Migration ---
export HOME="$BASE_TEST_DIR/security_migration"
mkdir -p "$HOME"

# Rotation
run_cmd "$KY_CLI kys r1 v1 --key \"oldpass\" --ttl 3600"
run_cmd "$KY_CLI kyrotate --new-key \"newpass\" --old-key \"oldpass\" --backup"
check_test "kyrotate" "Rotate master key" $last_status "Rotation complete|Re-encrypted 1" "$last_output"

run_cmd "$KY_CLI kyg r1 --key \"newpass\""
check_test "kyrotate (Verify)" "Read with new key after rotation" $last_status "v1" "$last_output"

# Migration
LEGACY_DB="$HOME/.kycli/data/default.db"
mkdir -p "$(dirname "$LEGACY_DB")"
rm -f "$LEGACY_DB" # Ensure fresh file for SQLite
# Create legacy SQLite DB
python3 -c "import sqlite3; conn=sqlite3.connect('$LEGACY_DB'); conn.execute('CREATE TABLE kvstore (key TEXT PRIMARY KEY, value TEXT, expires_at DATETIME)'); conn.execute('INSERT INTO kvstore (key, value) VALUES (\"mig1\", \"val1\")'); conn.commit(); conn.close()"

run_cmd "$KY_CLI kyg mig1 --key \"migpass\""
check_test "migration" "Auto-migration from legacy SQLite" $last_status "val1" "$last_output"

# Verify rotation backup exists
if ls "$HOME/.kycli/data/default.db.bak"* 1> /dev/null 2>&1; then
    status_bak="PASS"
else
    status_bak="FAIL"
fi

((total++))
status_display_bak="${RED}${status_bak}${NC}"
if [[ "$status_bak" == "PASS" ]]; then
    ((passed++))
    status_display_bak="${GREEN}${status_bak}${NC}"
fi

printf "| %-${W_ID}s | %-${W_CMD}s | %-${W_DESC}s | %-19s |\n" "$count" "rotation backup" "Verify backup created during rotation" "$status_display_bak"
((count++))

# --- SECTION 5: Usage Errors & Corner Cases ---
export HOME="$BASE_TEST_DIR/standard"
run_cmd "$KY_CLI kyuse"
check_test "kyuse" "Usage with no args" $last_status "Usage: kyuse" "$last_output"

run_cmd "$KY_CLI kyuse bad/name"
check_test "kyuse" "Reject invalid workspace name" $last_status "Invalid workspace name|Invalid" "$last_output"

run_cmd "$KY_CLI kyws extra_arg"
check_test "kyws" "Extra args suggestion" $last_status "Did you mean|Workspaces" "$last_output"

run_cmd "$KY_CLI kyg"
check_test "kyg" "Usage with no args" $last_status "Usage" "$last_output"

run_cmd "$KY_CLI kypatch"
check_test "kypatch" "Usage with no args" $last_status "Usage" "$last_output"

run_cmd "$KY_CLI kypush"
check_test "kypush" "Usage with no args" $last_status "Usage" "$last_output"

run_cmd "$KY_CLI kyrem"
check_test "kyrem" "Usage with no args" $last_status "Usage" "$last_output"

# Missing key
run_cmd "$KY_CLI kyg missing_key"
check_test "kyg" "Missing key returns error" $last_status "not found|Key not found" "$last_output"

# Abort deletion
run_cmd "$KY_CLI kys delme v --ttl 3600"
run_cmd "echo \"n\" | $KY_CLI kyd delme"
check_test "kyd" "Delete abort" $last_status "Aborted|Cancelled" "$last_output"
run_cmd "$KY_CLI kyg delme"
check_test "kyd" "Abort keeps key" $last_status "delme|v" "$last_output"

# kymv error cases
run_cmd "$KY_CLI kymv missing_key ws_missing"
check_test "kymv" "Move missing key" $last_status "not found|Key not found" "$last_output"

run_cmd "$KY_CLI kymv delme default"
check_test "kymv" "Move to same workspace" $last_status "same" "$last_output"

# kypush unique
run_cmd "$KY_CLI kys uniq '[1]' --ttl 3600"
run_cmd "$KY_CLI kypush uniq 1 --unique"
check_test "kypush" "Unique append avoids duplicates" $last_status "overwritten|nochange|No Change|Updated|Result" "$last_output"

# kyrem non-list
run_cmd "$KY_CLI kys notlist v --ttl 3600"
run_cmd "$KY_CLI kyrem notlist 1"
check_test "kyrem" "Remove from non-list" $last_status "Unexpected Error|Not a list" "$last_output" 1

# Search invalid regex
run_cmd "$KY_CLI kyl '\\['"
check_test "kyl" "Invalid regex pattern" $last_status "No keys found" "$last_output"

run_cmd "$KY_CLI kyg -s \"no_such_value\""
check_test "kyg -s" "Search no results" $last_status "No matches found" "$last_output"

# Export / Import
export HOME="$BASE_TEST_DIR/io"
mkdir -p "$HOME"
run_cmd "$KY_CLI kys expk v --ttl 3600"
run_cmd "$KY_CLI kye $BASE_TEST_DIR/io/export.csv csv"
check_test "kye" "Export CSV" $last_status "Exported" "$last_output"

run_cmd "$KY_CLI kye $BASE_TEST_DIR/io/export.json json"
check_test "kye" "Export JSON" $last_status "Exported" "$last_output"

run_cmd "$KY_CLI kyi $BASE_TEST_DIR/io/export.csv"
check_test "kyi" "Import CSV" $last_status "Imported" "$last_output"

run_cmd "$KY_CLI kyi $BASE_TEST_DIR/io/missing.csv"
check_test "kyi" "Import missing file" $last_status "File not found" "$last_output"

# Execute
run_cmd "$KY_CLI kyc missing_cmd"
check_test "kyc" "Execute missing key" $last_status "not found" "$last_output"

# TTL expiry
run_cmd "$KY_CLI kys ttl_short v --ttl 1"
sleep 2
run_cmd "$KY_CLI kyg ttl_short"
check_test "--ttl" "Expired key not returned" $last_status "Key not found|not found" "$last_output"

# KYCLI_DB_PATH overrides
export HOME="$BASE_TEST_DIR/env_override"
mkdir -p "$HOME"
export KYCLI_DB_PATH="$BASE_TEST_DIR/env_override/"
run_cmd "$KY_CLI kys envkey v --ttl 3600"
check_test "KYCLI_DB_PATH" "Directory override" $last_status "Saved" "$last_output"
unset KYCLI_DB_PATH

export KYCLI_DB_PATH="$BASE_TEST_DIR/env_override/specific.db"
run_cmd "$KY_CLI kys envkey2 v --ttl 3600"
check_test "KYCLI_DB_PATH" "File override" $last_status "Saved" "$last_output"
unset KYCLI_DB_PATH

# --- SECTION 6: Queues and Stacks ---
export HOME="$BASE_TEST_DIR/queues"
mkdir -p "$HOME"

# 1. Queue (FIFO)
$KY_CLI kyws create q_fifo --type queue > /dev/null
$KY_CLI kyuse q_fifo > /dev/null
run_cmd "$KY_CLI kypush q_item1"
check_test "kypush" "Push to queue" $last_status "pushed" "$last_output"

$KY_CLI kypush q_item2 > /dev/null
run_cmd "$KY_CLI kypeek"
check_test "kypeek" "Peek head of queue" $last_status "q_item1" "$last_output"

run_cmd "$KY_CLI kypop"
check_test "kypop" "Pop head (FIFO)" $last_status "q_item1" "$last_output"

run_cmd "$KY_CLI kycount"
check_test "kycount" "Count remaining items" $last_status "1" "$last_output"

# 2. Stack (LIFO)
$KY_CLI kyws create s_lifo --type stack > /dev/null
$KY_CLI kyuse s_lifo > /dev/null
$KY_CLI kypush bottom > /dev/null
$KY_CLI kypush top > /dev/null

run_cmd "$KY_CLI kypop"
check_test "kypop (Stack)" "Pop top (LIFO)" $last_status "top" "$last_output"

# 3. Priority Queue
$KY_CLI kyws create pq_prio --type priority_queue > /dev/null
$KY_CLI kyuse pq_prio > /dev/null
$KY_CLI kypush low --priority 1 > /dev/null
$KY_CLI kypush high --priority 100 > /dev/null
$KY_CLI kypush med --priority 50 > /dev/null

run_cmd "$KY_CLI kypop"
check_test "kypop (Priority)" "Pop highest priority" $last_status "high" "$last_output"

# 4. Clear
run_cmd "echo \"y\" | $KY_CLI kyclear"
check_test "kyclear" "Clear workspace" $last_status "cleared" "$last_output"
run_cmd "$KY_CLI kycount"
check_test "kycount" "Verify empty after clear" $last_status "0" "$last_output"

# 5. Type Safety (Negative)
# Trying to use kykys on a queue
run_cmd "$KY_CLI kys key val"
check_test "kys (Negative)" "Block KV command on Queue" $last_status "not supported" "$last_output" 1

# Bottom Line
printf "|-%-${W_ID}s-|-%-${W_CMD}s-|-%-${W_DESC}s-|-%-${W_STAT}s-|\n" "$(printf '%0.s-' $(seq 1 $W_ID))" "$(printf '%0.s-' $(seq 1 $W_CMD))" "$(printf '%0.s-' $(seq 1 $W_DESC))" "$(printf '%0.s-' $(seq 1 $W_STAT))" | sed 's/ /-/g'

# Final Summary
failed=$((total - passed))
accuracy=0
if [ "$total" -gt 0 ]; then
    accuracy=$(( (passed * 100) / total ))
fi

printf "\n"
printf "${GREEN}Test Summary Matrix${NC}\n"
printf "|----------------------|------------|\n"
printf "| %-20s | %-10s |\n" "Total Tests" "$total"
printf "| ${GREEN}%-20s${NC} | ${GREEN}%-10s${NC} |\n" "Passed" "$passed"
printf "| ${RED}%-20s${NC} | ${RED}%-10s${NC} |\n" "Failed" "$failed"
printf "| %-20s | %-10s |\n" "Accuracy" "$accuracy%"
printf "|----------------------|------------|\n"

if [ "$failed" -eq 0 ]; then
    printf "\n✅ ${GREEN}OVERALL STATUS: SUCCESS${NC}\n"
    printf "Message: All system components are healthy and validated.\n"
else
    printf "\n❌ ${RED}OVERALL STATUS: FAILED${NC}\n"
    printf "Message: Some validation tests failed. Please check the table above.\n"
    exit_status=1
fi
printf "\n"

# Cleanup
rm -rf "$BASE_TEST_DIR"

exit ${exit_status:-0}
