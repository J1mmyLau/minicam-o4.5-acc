#!/bin/bash
# Start llama-omni-server with F16 model for official SPEAK→WAV benchmark
# Usage: bash start_f16_server.sh
set -euo pipefail

MODEL="/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
SERVER_BIN="/workspace/llama.cpp-omni-session-fix/build/bin/llama-omni-server"
PID_FILE="/tmp/gfh-die0/llama-omni.pid"
SERVER_LOG="/tmp/gfh-die0/server.log"

# Kill any existing server via PID file
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Stopping existing server PID=$OLD_PID..."
        kill -TERM "$OLD_PID"
        for i in $(seq 1 30); do
            kill -0 "$OLD_PID" 2>/dev/null || break
            sleep 1
        done
        kill -KILL "$OLD_PID" 2>/dev/null || true
    fi
fi

# Verify model exists
if [ ! -f "$MODEL" ]; then
    echo "FATAL: F16 model not found: $MODEL"
    exit 1
fi

echo "Starting F16 server..."
echo "Model: $MODEL ($(du -h "$MODEL" | cut -f1))"
echo "Device: CANN0 (ASCEND_RT_VISIBLE_DEVICES=0)"
echo "Log: $SERVER_LOG"

mkdir -p "$(dirname "$PID_FILE")"

ASCEND_RT_VISIBLE_DEVICES=0 "$SERVER_BIN" \
    -m "$MODEL" \
    --host 127.0.0.1 \
    --port 22500 \
    -ngl 999 \
    --device CANN0 \
    --ctx-size 4096 \
    --batch-size 512 \
    --ubatch-size 512 \
    -t 4 \
    > "$SERVER_LOG" 2>&1 &

SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

# Wait for server to be ready
echo "Waiting for server to be ready..."
for i in $(seq 1 120); do
    if curl -s http://127.0.0.1:22500/health > /dev/null 2>&1; then
        echo "Server ready (PID=$SERVER_PID, waited ${i}s)"
        sha256sum "$SERVER_BIN"
        exit 0
    fi
    sleep 1
done

echo "FATAL: Server failed to start within 120s"
echo "Last 20 log lines:"
tail -20 "$SERVER_LOG"
exit 1
