#!/bin/bash
set -euo pipefail

LOG_DIR="/logs/verifier"
LOG_FILE="$LOG_DIR/log.txt"
REWARD_FILE="$LOG_DIR/reward.txt"

mkdir -p "$LOG_DIR"

status=0

current_user="$(whoami)"
if [ "$current_user" != "verifier" ]; then
    echo "FAIL: test.sh is running as '$current_user', expected 'verifier'" | tee -a "$LOG_FILE"
    status=1
else
    echo "PASS: running as 'verifier'" | tee -a "$LOG_FILE"
fi

if [ ! -f /home/agent/workspace/foo.txt ]; then
    echo "FAIL: /home/agent/workspace/foo.txt does not exist" | tee -a "$LOG_FILE"
    status=1
elif [ "$(cat /home/agent/workspace/foo.txt)" != "bar" ]; then
    echo "FAIL: /home/agent/workspace/foo.txt does not contain 'bar'" | tee -a "$LOG_FILE"
    status=1
else
    echo "PASS: /home/agent/workspace/foo.txt exists with correct contents" | tee -a "$LOG_FILE"
fi

if [ -f /home/agent/workspace/foo.txt ]; then
    owner="$(stat -c '%U' /home/agent/workspace/foo.txt 2>/dev/null || stat -f '%Su' /home/agent/workspace/foo.txt)"
    if [ "$owner" != "agent" ]; then
        echo "FAIL: /home/agent/workspace/foo.txt is owned by '$owner', expected 'agent'" | tee -a "$LOG_FILE"
        status=1
    else
        echo "PASS: /home/agent/workspace/foo.txt is owned by 'agent'" | tee -a "$LOG_FILE"
    fi
fi

if [ "$status" -eq 0 ]; then
    echo "1" > "$REWARD_FILE"
else
    echo "0" > "$REWARD_FILE"
fi

exit "$status"
