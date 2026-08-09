#!/bin/bash
# Quick profiling: compare F16 vs Q8_0 MatMul timing
# 1W+2M per config, 50 eval interval for profile dump
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CALIBRATOR="/workspace/llama.cpp-omni-f16-baseline/calibrate_per_chunk.py"
SERVER="$SCRIPT_DIR/build/bin/llama-omni-server"
F16_MODEL="/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
Q8_MODEL="/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q8_0.gguf"
RESULTS_DIR="$SCRIPT_DIR/profiling-results"
mkdir -p "$RESULTS_DIR"

run_config() {
    local label="$1"
    local model="$2"
    shift 2
    local extra_env=("$@")
    local server_log="$RESULTS_DIR/${label}_server.log"
    local client_log="$RESULTS_DIR/${label}_client.log"

    echo "============================================================"
    echo "RUN: $label"
    echo "Model: $model"
    echo "Extra env: ${extra_env[*]:-none}"
    echo "============================================================"

    # Kill any existing server
    pkill -9 -f llama-omni-server 2>/dev/null || true
    sleep 2

    # Start server
    env OMNI_T2W_DEVICE=cann-flow-only \
        OMNI_PER_CHUNK_DRAIN=0 \
        OMNI_PROFILE_MATMUL=1 \
        OMNI_PROFILE_MATMUL_INTERVAL=50 \
        "${extra_env[@]}" \
        "$SERVER" -m "$model" -t 4 --port 22500 --host 0.0.0.0 \
        > "$server_log" 2>&1 &
    local server_pid=$!
    echo "Server PID=$server_pid"

    # Wait for startup
    sleep 10
    if ! ps -p $server_pid > /dev/null 2>&1; then
        echo "ERROR: Server died on startup"
        tail -20 "$server_log"
        return 1
    fi

    # Run calibration
    echo "Running calibration 1W+2M..."
    if python "$CALIBRATOR" --warmup 1 --measured 2 > "$client_log" 2>&1; then
        echo "SUCCESS: $label"
    else
        echo "FAILED: $label (exit=$?)"
        tail -20 "$client_log"
    fi

    # Kill server and wait
    pkill -9 -f llama-omni-server 2>/dev/null || true
    sleep 2

    # Extract profiling summary
    echo ""
    echo "--- Profiling Summary for $label ---"
    grep "CANN_MATMUL_PROFILE\|\[bench\]" "$server_log" | tail -20
    echo ""
}

# Run all three configurations
run_config "A_F16_NZ_ON"  "$F16_MODEL"
run_config "B_Q8_0"       "$Q8_MODEL"
run_config "C_F16_NZ_OFF" "$F16_MODEL" GGML_CANN_WEIGHT_NZ=off

echo "All profiling runs complete. Results in $RESULTS_DIR/"
