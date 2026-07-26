#!/bin/bash
# P3 Stage B: 6-Hour KV Cache stability soak
# Repeated cache HIT runs for 6 hours with periodic metric collection
# Fixes from Stage A: proper prefill time extraction, RSS/FD collection
set -euo pipefail

BINARY=/workspace/llama.cpp-omni-kvcache-prod/build/bin/llama-omni-cli
MODEL=/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf
TEST_PREFIX=/workspace/llama.cpp-omni-kvcache-prod/tools/omni/assets/test_case/omni_test_case/omni_test_case_
OUTDIR=/workspace/llama.cpp-omni-kvcache-prod/docs/experiments/kv-cache-production/p3-soak
CACHE_DIR=/tmp/omni-kvcache
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUNDIR="${OUTDIR}/stage_b_${TIMESTAMP}"
DURATION_SEC=21600  # 6 hours
CACHE_KEY="e2b568b6078ce027"
CACHE_FILE="${CACHE_DIR}/omni_kvcache_${CACHE_KEY}.bin"

mkdir -p "$RUNDIR"

export OMNI_KV_CACHE_REUSE=1
export OMNI_T2W_DEVICE=cann-flow-only
export OMP_NUM_THREADS=8
export OMNI_T2W_DRAIN_TIMEOUT_MS=10000
export OMNI_KV_CACHE_PATH=$CACHE_DIR

# ─── Prime cache ────────────────────────────────────────────────────
echo "=== P3 Stage B: 6-Hour Soak — $TIMESTAMP ===" | tee "$RUNDIR/progress.log"
echo "Output dir: $RUNDIR" | tee -a "$RUNDIR/progress.log"
rm -f $CACHE_DIR/omni_kvcache_*.bin $CACHE_DIR/omni_kvcache_*.tmp.* $CACHE_DIR/omni_kvcache_*.state.* $CACHE_DIR/omni_kvcache_*.load.*

echo "$(date) Priming cache..." | tee -a "$RUNDIR/progress.log"
timeout 180 env OMNI_KV_CACHE_REUSE=1 OMNI_T2W_DEVICE=cann-flow-only \
    OMP_NUM_THREADS=8 OMNI_T2W_DRAIN_TIMEOUT_MS=10000 \
    OMNI_KV_CACHE_PATH=$CACHE_DIR \
    $BINARY -m "$MODEL" -ngl 0 --omni --test "$TEST_PREFIX" 1 --test-start 0 \
    > "${RUNDIR}/prime.stdout" 2> "${RUNDIR}/prime.stderr" || true

if [ ! -f "$CACHE_FILE" ]; then
    echo "FATAL: Cache not primed" | tee -a "$RUNDIR/progress.log"
    exit 1
fi
CACHE_SIZE=$(stat -c%s "$CACHE_FILE")
echo "$(date) Cache primed: $CACHE_SIZE bytes" | tee -a "$RUNDIR/progress.log"

# ─── Soak loop ─────────────────────────────────────────────────────
echo "$(date) Starting 6-hour soak loop..." | tee -a "$RUNDIR/progress.log"
START_TIME=$(date +%s)
ITERATION=0
TOTAL_HITS=0
TOTAL_MISSES=0
TIMEOUTS=0
LAST_LOG_TIME=$START_TIME

while true; do
    CURRENT_TIME=$(date +%s)
    ELAPSED=$(( CURRENT_TIME - START_TIME ))
    if [ $ELAPSED -ge $DURATION_SEC ]; then
        echo "$(date) Duration reached: ${ELAPSED}s" | tee -a "$RUNDIR/progress.log"
        break
    fi

    ITERATION=$(( ITERATION + 1 ))

    timeout 180 env OMNI_KV_CACHE_REUSE=1 OMNI_T2W_DEVICE=cann-flow-only \
        OMP_NUM_THREADS=8 OMNI_T2W_DRAIN_TIMEOUT_MS=10000 \
        OMNI_KV_CACHE_PATH=$CACHE_DIR \
        $BINARY -m "$MODEL" -ngl 0 --omni --test "$TEST_PREFIX" 1 --test-start 0 \
        > "${RUNDIR}/iter_${ITERATION}.stdout" 2> "${RUNDIR}/iter_${ITERATION}.stderr" || {
        echo "TIMEOUT,${ITERATION},${ELAPSED}" >> "${RUNDIR}/errors.log"
        TIMEOUTS=$(( TIMEOUTS + 1 ))
    }

    # Quick verification
    if grep -q "KV cache HIT" "${RUNDIR}/iter_${ITERATION}.stdout" 2>/dev/null; then
        TOTAL_HITS=$(( TOTAL_HITS + 1 ))
    elif grep -q "KV cache MISS" "${RUNDIR}/iter_${ITERATION}.stdout" 2>/dev/null; then
        TOTAL_MISSES=$(( TOTAL_MISSES + 1 ))
        echo "UNEXPECTED_MISS,${ITERATION},${ELAPSED}" >> "${RUNDIR}/errors.log"
    fi

    # Check cache file integrity periodically
    if [ $(( ITERATION % 10 )) -eq 0 ]; then
        CS=$(stat -c%s "$CACHE_FILE" 2>/dev/null || echo 0)
        if [ "$CS" -ne "$CACHE_SIZE" ]; then
            echo "CACHE_SIZE_CHANGE,${ITERATION},${ELAPSED},${CACHE_SIZE},${CS}" >> "${RUNDIR}/errors.log"
        fi
        # Temp file check
        TMPC=$(ls $CACHE_DIR/omni_kvcache_*.tmp.* $CACHE_DIR/omni_kvcache_*.state.* $CACHE_DIR/omni_kvcache_*.load.* 2>/dev/null | wc -l)
        if [ "$TMPC" -gt 0 ]; then
            echo "TEMP_FILE_LEAK,${ITERATION},${ELAPSED},${TMPC}" >> "${RUNDIR}/errors.log"
        fi
    fi

    # Progress log every 15 min
    if [ $(( CURRENT_TIME - LAST_LOG_TIME )) -ge 900 ]; then
        LAST_LOG_TIME=$CURRENT_TIME
        echo "$(date) Progress: ${ITERATION} iters, ${ELAPSED}s, hits=${TOTAL_HITS}, misses=${TOTAL_MISSES}, timeouts=${TIMEOUTS}" | tee -a "$RUNDIR/progress.log"
    fi
done

# ─── Final ──────────────────────────────────────────────────────────
END_TIME=$(date +%s)
TOTAL_ELAPSED=$(( END_TIME - START_TIME ))

echo "" | tee -a "$RUNDIR/progress.log"
echo "=== Stage B Complete ===" | tee -a "$RUNDIR/progress.log"
echo "Duration: ${TOTAL_ELAPSED}s (target: ${DURATION_SEC}s)" | tee -a "$RUNDIR/progress.log"
echo "Iterations: $ITERATION" | tee -a "$RUNDIR/progress.log"
echo "Cache hits: $TOTAL_HITS" | tee -a "$RUNDIR/progress.log"
echo "Cache misses: $TOTAL_MISSES" | tee -a "$RUNDIR/progress.log"
echo "Timeouts: $TIMEOUTS" | tee -a "$RUNDIR/progress.log"
echo "Cache file: $CACHE_FILE ($(stat -c%s "$CACHE_FILE" 2>/dev/null || echo 0) bytes)" | tee -a "$RUNDIR/progress.log"

ERROR_COUNT=$(cat "${RUNDIR}/errors.log" 2>/dev/null | wc -l)
echo "Error events: $ERROR_COUNT" | tee -a "$RUNDIR/progress.log"

TMPC=$(ls $CACHE_DIR/omni_kvcache_*.tmp.* $CACHE_DIR/omni_kvcache_*.state.* $CACHE_DIR/omni_kvcache_*.load.* 2>/dev/null | wc -l)
echo "Stale temp files: $TMPC" | tee -a "$RUNDIR/progress.log"

echo "Output: $RUNDIR" | tee -a "$RUNDIR/progress.log"
