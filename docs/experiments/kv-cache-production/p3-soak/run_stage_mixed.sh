#!/bin/bash
# P3 Stage M1/M6/C/D/E: Mixed-Workload KV Cache stability soak
# 7-mode cycle: H(HIT) → M(MISS rebuild) → H(HIT) → F(Force OFF) → R(Re-ON) → P(Prefix) → C(Corruption)
#
# Per-iteration telemetry:
#   - wall clock (for adaptive timeout)
#   - RSS (VmRSS from child proc)
#   - FD count, thread count
#   - cgroup memory, HBM usage (global snapshot)
#   - metadata written to iter_NNN.meta
#
# Adaptive timeout:
#   - Initial: 180s floor
#   - After warm-up: p95 of all wall times × 1.5, clamped to [180, 600]
#   - Recalculated every 5 iterations
#
# NOTE: Do NOT use 'set -euo pipefail' — pipefail kills script when
# 'ls glob_that_matches_nothing | wc -l' returns non-zero.
# Instead handle errors explicitly with || true and || { ... } blocks.
set -u

BINARY=/workspace/llama.cpp-omni-kvcache-prod/build/bin/llama-omni-cli
MODEL=/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf
TEST_PREFIX=/workspace/llama.cpp-omni-kvcache-prod/tools/omni/assets/test_case/omni_test_case/omni_test_case_
OUTDIR=/workspace/llama.cpp-omni-kvcache-prod/docs/experiments/kv-cache-production/p3-soak
CACHE_DIR=/tmp/omni-kvcache
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUNDIR="${OUTDIR}/stage_mixed_${TIMESTAMP}"
# Default 1h for M1; override via env for longer stages
DURATION_SEC=${OMNI_MIXED_DURATION:-3600}
STAGE_LABEL="${OMNI_MIXED_STAGE:-M1}"

mkdir -p "$RUNDIR"

export OMNI_T2W_DEVICE=cann-flow-only
export OMP_NUM_THREADS=8
export OMNI_T2W_DRAIN_TIMEOUT_MS=10000
export OMNI_KV_CACHE_PATH=$CACHE_DIR

# ─── Adaptive Timeout State ──────────────────────────────────────────
ADAPTIVE_TIMEOUT=180        # initial floor
TIMEOUT_FLOOR=180           # absolute minimum
TIMEOUT_CEILING=600         # absolute maximum
WALL_TIMES_FILE="${RUNDIR}/.wall_times"
WARMUP_ITERS=5              # use fixed 180s timeout for first N iters
ADAPT_INTERVAL=5            # recalculate timeout every N iters
: > "$WALL_TIMES_FILE"      # create/truncate

recalc_timeout() {
    local count
    count=$(wc -l < "$WALL_TIMES_FILE" 2>/dev/null) || count=0
    if [ "$count" -lt "$WARMUP_ITERS" ]; then
        ADAPTIVE_TIMEOUT=$TIMEOUT_FLOOR
        return
    fi
    # Compute p95 from all wall times, use python3
    local p95
    p95=$(python3 -c "
import sys
times = sorted(float(line.strip()) for line in open('$WALL_TIMES_FILE') if line.strip())
n = len(times)
idx = int(n * 0.95)
if idx >= n:
    idx = n - 1
p95 = times[idx]
timeout = max($TIMEOUT_FLOOR, min($TIMEOUT_CEILING, int(p95 * 1.5 + 15)))
print(timeout)
" 2>/dev/null) || p95=$TIMEOUT_FLOOR
    # Clamp
    if [ "$p95" -lt "$TIMEOUT_FLOOR" ] 2>/dev/null; then
        ADAPTIVE_TIMEOUT=$TIMEOUT_FLOOR
    elif [ "$p95" -gt "$TIMEOUT_CEILING" ] 2>/dev/null; then
        ADAPTIVE_TIMEOUT=$TIMEOUT_CEILING
    else
        ADAPTIVE_TIMEOUT=$p95
    fi
}

# ─── Resource Sampling ──────────────────────────────────────────────
# Sample child process resource usage during execution.
# Runs in background, writes peak values to a temp file.
# $1 = timeout wrapper PID; the actual binary PID is found via pgrep -P.
sample_child_resources() {
    local timeout_pid="$1"
    local outfile="$2"
    local peak_rss=0 peak_fd=0 peak_threads=0 hbm_pct=0
    local rss fd threads pid

    # Wait briefly for timeout to spawn the actual binary, then find it
    sleep 2
    pid=$(pgrep -P "$timeout_pid" 2>/dev/null | head -1) || pid=""
    if [ -z "$pid" ]; then
        pid="$timeout_pid"  # fallback to timeout wrapper
    fi

    while kill -0 "$timeout_pid" 2>/dev/null; do
        if [ -f "/proc/$pid/status" ]; then
            rss=$(awk '/^VmRSS:/ {print $2}' "/proc/$pid/status" 2>/dev/null) || rss=0
            [ "$rss" -gt "$peak_rss" ] 2>/dev/null && peak_rss=$rss
            threads=$(awk '/^Threads:/ {print $2}' "/proc/$pid/status" 2>/dev/null) || threads=0
            [ "$threads" -gt "$peak_threads" ] 2>/dev/null && peak_threads=$threads
        fi
        fd=$(ls "/proc/$pid/fd" 2>/dev/null | wc -l) || fd=0
        [ "$fd" -gt "$peak_fd" ] 2>/dev/null && peak_fd=$fd
        sleep 3
    done

    # Final HBM snapshot
    hbm_pct=$(npu-smi info -t usages -i 0 2>/dev/null | grep -oP 'HBM Usage Rate\s*\(\s*%?\s*\)\s*:\s*\K[0-9]+' | head -1) || hbm_pct=0

    cat > "$outfile" << EOF
peak_rss_kb=${peak_rss}
peak_fd=${peak_fd}
peak_threads=${peak_threads}
hbm_usage_pct=${hbm_pct}
EOF
}

# ─── Cache Helpers ──────────────────────────────────────────────────
delete_cache() {
    rm -f "${CACHE_DIR}"/omni_kvcache_*.bin
}

corrupt_cache() {
    local cf
    cf=$(ls "${CACHE_DIR}"/omni_kvcache_*.bin 2>/dev/null | head -1) || cf=""
    if [ -n "$cf" ]; then
        python3 -c "
import sys
with open('$cf', 'r+b') as f:
    f.seek(128)
    b = f.read(1)
    f.seek(128)
    f.write(bytes([b[0] ^ 0x01]))
" 2>/dev/null || true
    fi
}

get_cache_count() {
    local n
    n=$(ls "${CACHE_DIR}"/omni_kvcache_*.bin 2>/dev/null | wc -l) || n=0
    echo "$n"
}

# ─── Mode Execution ─────────────────────────────────────────────────
run_iteration() {
    local mode="$1"
    local iter="$2"
    local kv_env=1
    local test_start=0

    case "$mode" in
        H|R)
            # HIT baseline / Re-ON: cache enabled, default prefix
            kv_env=1
            test_start=0
            ;;
        M)
            # MISS rebuild: delete all cache files first
            delete_cache
            kv_env=1
            test_start=0
            ;;
        F)
            # Force OFF: disable cache
            kv_env=0
            test_start=0
            ;;
        P)
            # Prefix change: use test-start 1 (different system prompt)
            kv_env=1
            test_start=1
            ;;
        C)
            # Corruption: flip one bit in existing cache, then enable
            corrupt_cache
            kv_env=1
            test_start=0
            ;;
        *)
            echo "ERROR: unknown mode $mode" >> "${RUNDIR}/errors.log"
            return 1
            ;;
    esac

    local start_ns end_ns wall_sec
    start_ns=$(date +%s%N)

    # ─── Launch binary in background ──────────────────────────────
    local child_pid
    env OMNI_KV_CACHE_REUSE=$kv_env OMNI_T2W_DEVICE=cann-flow-only \
        OMP_NUM_THREADS=8 OMNI_T2W_DRAIN_TIMEOUT_MS=10000 \
        OMNI_KV_CACHE_PATH=$CACHE_DIR \
        timeout "$ADAPTIVE_TIMEOUT" \
        "$BINARY" -m "$MODEL" -ngl 0 --omni --test "${TEST_PREFIX}" 1 --test-start "$test_start" \
        > "${RUNDIR}/iter_${iter}.stdout" 2> "${RUNDIR}/iter_${iter}.stderr" &
    child_pid=$!

    # Sample resources while binary runs
    local res_file="${RUNDIR}/iter_${iter}.res"
    sample_child_resources "$child_pid" "$res_file" &
    local sampler_pid=$!

    # Wait for binary
    local exit_code=0
    wait "$child_pid" || exit_code=$?

    # Wait for sampler to finish (it exits on its own when child dies)
    wait "$sampler_pid" 2>/dev/null || true

    end_ns=$(date +%s%N)
    wall_sec=$(python3 -c "print(round(($end_ns - $start_ns) / 1_000_000_000, 3))" 2>/dev/null) || wall_sec=0

    # ─── Resource metrics ─────────────────────────────────────────
    local peak_rss_kb=0 peak_fd=0 peak_threads=0 hbm_usage_pct=0
    if [ -f "$res_file" ]; then
        peak_rss_kb=$(awk -F= '/^peak_rss_kb=/{print $2}' "$res_file" 2>/dev/null) || peak_rss_kb=0
        peak_fd=$(awk -F= '/^peak_fd=/{print $2}' "$res_file" 2>/dev/null) || peak_fd=0
        peak_threads=$(awk -F= '/^peak_threads=/{print $2}' "$res_file" 2>/dev/null) || peak_threads=0
        hbm_usage_pct=$(awk -F= '/^hbm_usage_pct=/{print $2}' "$res_file" 2>/dev/null) || hbm_usage_pct=0
    fi
    local cgroup_mem
    cgroup_mem=$(cat /sys/fs/cgroup/memory/memory.usage_in_bytes 2>/dev/null) || cgroup_mem=0

    # ─── Cache status detection ───────────────────────────────────
    local cache_status="NO_STATS"
    if grep -q "KV cache HIT" "${RUNDIR}/iter_${iter}.stdout" 2>/dev/null; then
        cache_status="HIT"
    elif grep -q "KV cache MISS" "${RUNDIR}/iter_${iter}.stdout" 2>/dev/null; then
        cache_status="MISS"
    fi

    # ─── Write metadata ───────────────────────────────────────────
    cat > "${RUNDIR}/iter_${iter}.meta" << EOF
mode=${mode}
wall_sec=${wall_sec}
exit_code=${exit_code}
cache_status=${cache_status}
kv_env=${kv_env}
test_start=${test_start}
timeout_sec=${ADAPTIVE_TIMEOUT}
peak_rss_kb=${peak_rss_kb}
peak_fd=${peak_fd}
peak_threads=${peak_threads}
hbm_usage_pct=${hbm_usage_pct}
cgroup_mem_bytes=${cgroup_mem}
EOF

    # ─── Track wall time for adaptive timeout ──────────────────────
    echo "$wall_sec" >> "$WALL_TIMES_FILE"

    # ─── Error logging ────────────────────────────────────────────
    if [ "$exit_code" -eq 124 ]; then
        echo "TIMEOUT,${iter},${wall_sec},mode=${mode},adaptive_to=${ADAPTIVE_TIMEOUT}" >> "${RUNDIR}/errors.log"
    fi
    if [ "$cache_status" = "MISS" ] && [ "$mode" = "H" ]; then
        echo "UNEXPECTED_MISS,${iter},${wall_sec},mode=${mode}" >> "${RUNDIR}/errors.log"
    fi
    if [ "$cache_status" = "MISS" ] && [ "$mode" = "R" ]; then
        echo "UNEXPECTED_MISS_REON,${iter},${wall_sec},mode=${mode}" >> "${RUNDIR}/errors.log"
    fi
    if [ "$mode" = "M" ] && [ "$cache_status" != "MISS" ]; then
        echo "EXPECTED_MISS_NOT_SEEN,${iter},${wall_sec},mode=${mode},actual=${cache_status}" >> "${RUNDIR}/errors.log"
    fi
    if [ "$mode" = "C" ] && [ "$cache_status" != "MISS" ]; then
        echo "CORRUPTION_NOT_DETECTED,${iter},${wall_sec},mode=${mode},actual=${cache_status}" >> "${RUNDIR}/errors.log"
    fi

    return 0
}

# ─── Main ────────────────────────────────────────────────────────────
echo "=== P3 Stage ${STAGE_LABEL}: Mixed-Workload Soak — $TIMESTAMP ===" | tee "$RUNDIR/progress.log"
echo "Output dir: $RUNDIR" | tee -a "$RUNDIR/progress.log"
echo "Duration: ${DURATION_SEC}s (~$(python3 -c "print(round($DURATION_SEC/3600, 1))")h)" | tee -a "$RUNDIR/progress.log"
echo "Modes: H(HIT) → M(MISS) → H(HIT) → F(OFF) → R(Re-ON) → P(Prefix) → C(Corrupt)" | tee -a "$RUNDIR/progress.log"

# Clean stale temps
rm -f "${CACHE_DIR}"/omni_kvcache_*.tmp.* "${CACHE_DIR}"/omni_kvcache_*.state.* "${CACHE_DIR}"/omni_kvcache_*.load.*

# ─── Prime cache for HIT baseline ────────────────────────────────────
echo "$(date) Priming cache (baseline prefix)..." | tee -a "$RUNDIR/progress.log"
timeout 600 env OMNI_KV_CACHE_REUSE=1 OMNI_T2W_DEVICE=cann-flow-only \
    OMP_NUM_THREADS=8 OMNI_T2W_DRAIN_TIMEOUT_MS=10000 \
    OMNI_KV_CACHE_PATH=$CACHE_DIR \
    "$BINARY" -m "$MODEL" -ngl 0 --omni --test "$TEST_PREFIX" 1 --test-start 0 \
    > "${RUNDIR}/prime.stdout" 2> "${RUNDIR}/prime.stderr" || {
    echo "FATAL: Prime failed" | tee -a "$RUNDIR/progress.log"
    exit 1
}

CACHE_COUNT=$(get_cache_count)
if [ "$CACHE_COUNT" -lt 1 ]; then
    echo "FATAL: Cache not primed (no .bin in $CACHE_DIR)" | tee -a "$RUNDIR/progress.log"
    exit 1
fi
CACHE_SIZE=$(stat -c%s "${CACHE_DIR}"/omni_kvcache_*.bin 2>/dev/null | head -1)
echo "$(date) Cache primed: $CACHE_SIZE bytes, $CACHE_COUNT files" | tee -a "$RUNDIR/progress.log"

# ─── Soak loop ───────────────────────────────────────────────────────
MODES=("H" "M" "H" "F" "R" "P" "C")
MODE_INDEX=0
START_TIME=$(date +%s)
ITERATION=0
TOTAL_HITS=0
TOTAL_MISSES=0
TIMEOUTS=0
LAST_LOG_TIME=$START_TIME

echo "$(date) Starting ${STAGE_LABEL} mixed-workload soak..." | tee -a "$RUNDIR/progress.log"

while true; do
    CURRENT_TIME=$(date +%s)
    ELAPSED=$(( CURRENT_TIME - START_TIME ))
    if [ $ELAPSED -ge $DURATION_SEC ]; then
        echo "$(date) Duration reached: ${ELAPSED}s" | tee -a "$RUNDIR/progress.log"
        break
    fi

    ITERATION=$(( ITERATION + 1 ))
    MODE="${MODES[$MODE_INDEX]}"
    MODE_INDEX=$(( (MODE_INDEX + 1) % ${#MODES[@]} ))

    # Recalculate adaptive timeout periodically
    if [ $(( ITERATION % ADAPT_INTERVAL )) -eq 0 ]; then
        recalc_timeout
        if [ $(( ITERATION % 35 )) -eq 0 ]; then
            echo "$(date) Adaptive timeout updated: ${ADAPTIVE_TIMEOUT}s" >> "$RUNDIR/progress.log"
        fi
    fi

    # Run iteration
    echo "$(date) Iter $ITERATION: mode=$MODE, timeout=${ADAPTIVE_TIMEOUT}s" >> "${RUNDIR}/progress.log"
    run_iteration "$MODE" "$ITERATION"

    # Tally from metadata
    if grep -q "cache_status=HIT" "${RUNDIR}/iter_${ITERATION}.meta" 2>/dev/null; then
        TOTAL_HITS=$(( TOTAL_HITS + 1 ))
    elif grep -q "cache_status=MISS" "${RUNDIR}/iter_${ITERATION}.meta" 2>/dev/null; then
        TOTAL_MISSES=$(( TOTAL_MISSES + 1 ))
    fi
    if grep -q "exit_code=124" "${RUNDIR}/iter_${ITERATION}.meta" 2>/dev/null; then
        TIMEOUTS=$(( TIMEOUTS + 1 ))
    fi

    # Periodic cache file integrity check
    if [ $(( ITERATION % 10 )) -eq 0 ]; then
        for cf in "${CACHE_DIR}"/omni_kvcache_*.bin; do
            [ -f "$cf" ] || continue
            CS=$(stat -c%s "$cf" 2>/dev/null || echo 0)
            if [ "$CS" -eq 0 ]; then
                echo "ZERO_SIZE_CACHE,${ITERATION},${ELAPSED},${cf}" >> "${RUNDIR}/errors.log"
            fi
        done
        TMPC=$(ls "${CACHE_DIR}"/omni_kvcache_*.tmp.* "${CACHE_DIR}"/omni_kvcache_*.state.* "${CACHE_DIR}"/omni_kvcache_*.load.* 2>/dev/null | wc -l) || TMPC=0
        if [ "$TMPC" -gt 0 ]; then
            echo "TEMP_FILE_LEAK,${ITERATION},${ELAPSED},${TMPC}" >> "${RUNDIR}/errors.log"
        fi
    fi

    # Progress log every 15 min
    if [ $(( CURRENT_TIME - LAST_LOG_TIME )) -ge 900 ]; then
        LAST_LOG_TIME=$CURRENT_TIME
        echo "$(date) Progress: ${ITERATION} iters, ${ELAPSED}s, hits=${TOTAL_HITS}, misses=${TOTAL_MISSES}, timeouts=${TIMEOUTS}, adaptive_to=${ADAPTIVE_TIMEOUT}s" | tee -a "$RUNDIR/progress.log"
    fi
done

# ─── Final ──────────────────────────────────────────────────────────
END_TIME=$(date +%s)
TOTAL_ELAPSED=$(( END_TIME - START_TIME ))

echo "" | tee -a "$RUNDIR/progress.log"
echo "=== Stage ${STAGE_LABEL} Mixed-Workload Complete ===" | tee -a "$RUNDIR/progress.log"
echo "Duration: ${TOTAL_ELAPSED}s (target: ${DURATION_SEC}s)" | tee -a "$RUNDIR/progress.log"
echo "Iterations: $ITERATION" | tee -a "$RUNDIR/progress.log"
echo "Cache hits: $TOTAL_HITS" | tee -a "$RUNDIR/progress.log"
echo "Cache misses: $TOTAL_MISSES" | tee -a "$RUNDIR/progress.log"
echo "Timeouts: $TIMEOUTS" | tee -a "$RUNDIR/progress.log"
echo "Final adaptive timeout: ${ADAPTIVE_TIMEOUT}s" | tee -a "$RUNDIR/progress.log"

CACHE_COUNT=$(get_cache_count)
echo "Cache files: $CACHE_COUNT" | tee -a "$RUNDIR/progress.log"
for cf in "${CACHE_DIR}"/omni_kvcache_*.bin; do
    [ -f "$cf" ] || continue
    echo "  $(basename "$cf"): $(stat -c%s "$cf" 2>/dev/null || echo 0) bytes" | tee -a "$RUNDIR/progress.log"
done

ERROR_COUNT=$(cat "${RUNDIR}/errors.log" 2>/dev/null | wc -l)
echo "Error events: $ERROR_COUNT" | tee -a "$RUNDIR/progress.log"

TMPC=$(ls "${CACHE_DIR}"/omni_kvcache_*.tmp.* "${CACHE_DIR}"/omni_kvcache_*.state.* "${CACHE_DIR}"/omni_kvcache_*.load.* 2>/dev/null | wc -l) || TMPC=0
echo "Stale temp files: $TMPC" | tee -a "$RUNDIR/progress.log"

# ─── Write meta-summary for audit tool ──────────────────────────────
cat > "${RUNDIR}/TELEMETRY_SUMMARY.txt" << EOF
stage=${STAGE_LABEL}
duration_sec=${TOTAL_ELAPSED}
iterations=${ITERATION}
total_hits=${TOTAL_HITS}
total_misses=${TOTAL_MISSES}
timeouts=${TIMEOUTS}
final_adaptive_timeout=${ADAPTIVE_TIMEOUT}
error_events=${ERROR_COUNT}
stale_temp_files=${TMPC}
cache_file_count=${CACHE_COUNT}
EOF

echo "Output: $RUNDIR" | tee -a "$RUNDIR/progress.log"

# Write gate marker
echo "GATE_WAITING" > "$RUNDIR/GATE_STATUS"
echo "Stage ${STAGE_LABEL} mixed-workload complete. Gate audit required before next stage." >> "$RUNDIR/GATE_STATUS"
echo "Exit code: 0" >> "$RUNDIR/GATE_STATUS"
touch "$RUNDIR/DONE"
