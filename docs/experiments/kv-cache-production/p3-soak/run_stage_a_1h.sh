#!/bin/bash
# P3 Stage A: 1-hour KV Cache stability soak
# Repeated cache HIT runs for 1 hour with periodic metric collection
set -euo pipefail

BINARY=/workspace/llama.cpp-omni-kvcache-prod/build/bin/llama-omni-cli
MODEL=/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf
TEST_PREFIX=/workspace/llama.cpp-omni-kvcache-prod/tools/omni/assets/test_case/omni_test_case/omni_test_case_
OUTDIR=/workspace/llama.cpp-omni-kvcache-prod/docs/experiments/kv-cache-production/p3-soak
CACHE_DIR=/tmp/omni-kvcache
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUNDIR="${OUTDIR}/stage_a_${TIMESTAMP}"
DURATION_SEC=3600  # 1 hour
METRICS_INTERVAL=60  # Collect metrics every 60s (runs take ~2 min, so every other run)
CACHE_KEY="e2b568b6078ce027"
CACHE_FILE="${CACHE_DIR}/omni_kvcache_${CACHE_KEY}.bin"

mkdir -p "$RUNDIR"

export OMNI_KV_CACHE_REUSE=1
export OMNI_T2W_DEVICE=cann-flow-only
export OMP_NUM_THREADS=8
export OMNI_T2W_DRAIN_TIMEOUT_MS=10000
export OMNI_KV_CACHE_PATH=$CACHE_DIR

# ─── Metric collection helpers ─────────────────────────────────────
collect_metrics() {
    local label="$1"
    local mfile="${RUNDIR}/metrics_${label}.csv"
    if [ ! -f "$mfile" ]; then
        echo "timestamp,label,elapsed_s,iteration,rss_kb,hbm_used_mb,fd_count,thread_count,cache_size,cache_mtime,cache_hits,cache_misses,tokens_reused,prefill_time_s" > "$mfile"
    fi
    local ts=$(date +%H:%M:%S)
    local rss=$(awk '/VmRSS/ {print $2}' /proc/$PID/status 2>/dev/null || echo 0)
    local fd_count=$(ls /proc/$PID/fd 2>/dev/null | wc -l)
    local thread_count=$(ls /proc/$PID/task 2>/dev/null | wc -l)
    local cache_size=$(stat -c%s "$CACHE_FILE" 2>/dev/null || echo 0)
    local cache_mtime=$(stat -c%Y "$CACHE_FILE" 2>/dev/null || echo 0)
    local hbm_used="N/A"  # CANN HBM not easily queried from shell
    echo "${ts},${label},${ELAPSED},${ITERATION},${rss},${hbm_used},${fd_count},${thread_count},${cache_size},${cache_mtime},${CACHE_HITS},${CACHE_MISSES},${TOKENS_REUSED},${PREFILL_TIME}" >> "$mfile"
}

# ─── Clean slate ───────────────────────────────────────────────────
echo "=== P3 Stage A: 1-Hour Soak — $TIMESTAMP ==="
echo "Output dir: $RUNDIR"
rm -f $CACHE_DIR/omni_kvcache_*.bin $CACHE_DIR/omni_kvcache_*.tmp.* $CACHE_DIR/omni_kvcache_*.state.* $CACHE_DIR/omni_kvcache_*.load.*

# ─── Prime the cache (first run: MISS → SAVE) ─────────────────────
echo ""
echo "=== Priming cache (MISS → SAVE) ==="
PRIME_LOG="${RUNDIR}/prime.log"
timeout 180 env OMNI_KV_CACHE_REUSE=1 OMNI_T2W_DEVICE=cann-flow-only \
    OMP_NUM_THREADS=8 OMNI_T2W_DRAIN_TIMEOUT_MS=10000 \
    OMNI_KV_CACHE_PATH=$CACHE_DIR \
    $BINARY -m "$MODEL" -ngl 0 --omni --test "$TEST_PREFIX" 1 --test-start 0 \
    > "${PRIME_LOG}.stdout" 2> "${PRIME_LOG}.stderr" || true

# Verify cache was created
if [ ! -f "$CACHE_FILE" ]; then
    echo "FATAL: Cache file not created during prime. Aborting."
    exit 1
fi
CACHE_SIZE=$(stat -c%s "$CACHE_FILE")
echo "Cache primed: $CACHE_FILE ($CACHE_SIZE bytes)"
grep "KV cache SAVED\|cache_hits\|cache_misses" "${PRIME_LOG}.stdout" || true

# ─── Soak loop ─────────────────────────────────────────────────────
echo ""
echo "=== Starting 1-hour soak loop ==="
START_TIME=$(date +%s)
ITERATION=0
CACHE_HITS=0
CACHE_MISSES=0
TOKENS_REUSED=0
PREFILL_TIME=0

while true; do
    CURRENT_TIME=$(date +%s)
    ELAPSED=$(( CURRENT_TIME - START_TIME ))
    if [ $ELAPSED -ge $DURATION_SEC ]; then
        echo "$(date) Soak duration reached: ${ELAPSED}s"
        break
    fi

    ITERATION=$(( ITERATION + 1 ))
    ITER_LOG="${RUNDIR}/iter_${ITERATION}.log"

    echo "$(date) Iteration $ITERATION (elapsed=${ELAPSED}s)..."

    timeout 180 env OMNI_KV_CACHE_REUSE=1 OMNI_T2W_DEVICE=cann-flow-only \
        OMP_NUM_THREADS=8 OMNI_T2W_DRAIN_TIMEOUT_MS=10000 \
        OMNI_KV_CACHE_PATH=$CACHE_DIR \
        $BINARY -m "$MODEL" -ngl 0 --omni --test "$TEST_PREFIX" 1 --test-start 0 \
        > "${ITER_LOG}.stdout" 2> "${ITER_LOG}.stderr" || {
        echo "WARNING: Iteration $ITERATION timed out or failed"
        echo "TIMEOUT_OR_ERROR,${ITERATION},${ELAPSED}" >> "${RUNDIR}/errors.log"
    }

    # Extract metrics from this run
    HIT_COUNT=$(grep -a "cache_hits:" "${ITER_LOG}.stderr" | tail -1 | awk '{print $2}' || echo 0)
    MISS_COUNT=$(grep -a "cache_misses:" "${ITER_LOG}.stderr" | tail -1 | awk '{print $2}' || echo 0)
    REUSED=$(grep -a "tokens_reused:" "${ITER_LOG}.stderr" | tail -1 | awk '{print $2}' || echo 0)
    PREFTIME=$(grep -a "prefill 0 (audio+vision)" "${ITER_LOG}.stdout" | tail -1 | awk '{print $NF}' || echo "N/A")

    CACHE_HITS=$(( CACHE_HITS + HIT_COUNT ))
    CACHE_MISSES=$(( CACHE_MISSES + MISS_COUNT ))
    TOKENS_REUSED=$(( TOKENS_REUSED + REUSED ))
    PREFILL_TIME="$PREFTIME"

    # Collect system metrics at intervals
    if [ $(( ITERATION % 2 )) -eq 0 ]; then
        collect_metrics "periodic"
    fi

    # Verify cache file is intact
    CURRENT_CACHE_SIZE=$(stat -c%s "$CACHE_FILE" 2>/dev/null || echo 0)
    if [ "$CURRENT_CACHE_SIZE" -ne "$CACHE_SIZE" ]; then
        echo "WARNING: Cache file size changed! Expected $CACHE_SIZE, got $CURRENT_CACHE_SIZE"
        echo "SIZE_CHANGE,${ITERATION},${ELAPSED},${CACHE_SIZE},${CURRENT_CACHE_SIZE}" >> "${RUNDIR}/errors.log"
    fi

    # Brief progress every 10 iterations
    if [ $(( ITERATION % 10 )) -eq 0 ]; then
        echo "  Progress: $ITERATION iterations, $ELAPSED s elapsed, hits=$CACHE_HITS, misses=$CACHE_MISSES"
    fi
done

# ─── Final metrics ─────────────────────────────────────────────────
END_TIME=$(date +%s)
TOTAL_ELAPSED=$(( END_TIME - START_TIME ))
echo ""
echo "=== Soak Complete ==="
echo "Duration: ${TOTAL_ELAPSED}s (target: ${DURATION_SEC}s)"
echo "Iterations: $ITERATION"
echo "Cache hits: $CACHE_HITS"
echo "Cache misses: $CACHE_MISSES"
echo "Tokens reused: $TOKENS_REUSED"
echo "Errors: $(cat ${RUNDIR}/errors.log 2>/dev/null | wc -l)"
echo ""

# Final cache state
echo "Cache file: $CACHE_FILE"
ls -la "$CACHE_FILE" 2>/dev/null
echo "Cache file size: $(stat -c%s "$CACHE_FILE" 2>/dev/null || echo MISSING) bytes (expected: $CACHE_SIZE)"

# Check for stale temp files
TEMP_COUNT=$(ls $CACHE_DIR/omni_kvcache_*.tmp.* $CACHE_DIR/omni_kvcache_*.state.* $CACHE_DIR/omni_kvcache_*.load.* 2>/dev/null | wc -l)
if [ "$TEMP_COUNT" -gt 0 ]; then
    echo "WARNING: $TEMP_COUNT stale temp files found"
    ls -la $CACHE_DIR/omni_kvcache_*.tmp.* $CACHE_DIR/omni_kvcache_*.state.* $CACHE_DIR/omni_kvcache_*.load.* 2>/dev/null
else
    echo "No stale temp files — clean"
fi

# Summary
echo ""
echo "=== Stage A Summary ===" > "${RUNDIR}/summary.txt"
echo "timestamp: $TIMESTAMP" >> "${RUNDIR}/summary.txt"
echo "duration_s: $TOTAL_ELAPSED" >> "${RUNDIR}/summary.txt"
echo "iterations: $ITERATION" >> "${RUNDIR}/summary.txt"
echo "cache_hits: $CACHE_HITS" >> "${RUNDIR}/summary.txt"
echo "cache_misses: $CACHE_MISSES" >> "${RUNDIR}/summary.txt"
echo "cache_file_size_bytes: $(stat -c%s "$CACHE_FILE" 2>/dev/null || echo 0)" >> "${RUNDIR}/summary.txt"
echo "errors: $(cat ${RUNDIR}/errors.log 2>/dev/null | wc -l)" >> "${RUNDIR}/summary.txt"
echo "stale_temp_files: $TEMP_COUNT" >> "${RUNDIR}/summary.txt"
cat "${RUNDIR}/summary.txt"

echo ""
echo "Stage A output: $RUNDIR"
