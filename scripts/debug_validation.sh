#!/bin/bash

export TEST_HOME="/tmp/kycli_debug_home"
rm -rf "$TEST_HOME"
mkdir -p "$TEST_HOME"
export HOME="$TEST_HOME"
export PYTHONPATH=.
export TERM=dumb

KY_CLI="python3 -m kycli.cli"

echo "--- DEBUG: Encryption Save ---"
$KY_CLI kys k_sec "secret_data" --key "mypass" --ttl 3600 2>&1

echo "--- DEBUG: kypush ---"
$KY_CLI kys j_key '{"tags": ["a"]}' --ttl 3600 > /dev/null
$KY_CLI kypush j_key.tags "b" 2>&1

echo "--- DEBUG: kydrop ---"
$KY_CLI kyuse w_drop > /dev/null
$KY_CLI kyuse default > /dev/null
echo "y" | $KY_CLI kydrop w_drop 2>&1

echo "--- DEBUG: kyr ---"
$KY_CLI kys k_del "val" --ttl 3600 > /dev/null
echo "k_del" | $KY_CLI kyd k_del > /dev/null
$KY_CLI kyr k_del 2>&1
