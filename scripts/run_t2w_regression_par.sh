#!/bin/bash
# P7.3 P9: Fast T2W Lifecycle Regression — parallel execution
# 150 requests (50 passes × 3 fast cases)
# Gate: rc=0-without-audio MUST be ZERO
set -o pipefail

BINARY="/workspace/llama.cpp-omni-ngl8-e2e/build/bin/llama-omni-cli"
MODEL="/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf"
TEST_PREFIX="/workspace/llama.cpp-omni-ngl8-e2e/tools/omni/assets/test_case/omni_test_case/omni_test_case_"
OUTDIR="/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/p7_3-regression"
LOGDIR="${OUTDIR}/logs"
CSV="${OUTDIR}/regression_par.csv"
PROGRESS="${OUTDIR}/.progress_par"

PASSES=50
# Only fast cases (skip case 2 which generates very long responses)
CASES="0 1 3"
NCASES=$(echo $CASES | wc -w)
TOTAL=$((PASSES * NCASES))
MAX_PARALLEL=3  # concurrent cases (NPU serializes at kernel level)
PER_CASE_TIMEOUT=120

mkdir -p "$OUTDIR" "$LOGDIR"

echo "PID: $$"
echo "Started: $(date -Iseconds)"
echo "Total: $PASSES × $NCASES = $TOTAL cases"
echo "Max parallel: $MAX_PARALLEL"
echo "Timeout per case: ${PER_CASE_TIMEOUT}s"
echo "CSV: $CSV"
echo ""

cleanup() { echo "[$(date -Iseconds)] CLEANUP"; }
trap cleanup EXIT

is_completed() { grep -q "^${1},${2}$" "${PROGRESS}" 2>/dev/null; }
mark_completed() { echo "${1},${2}" >> "${PROGRESS}"; }

if [ ! -f "$CSV" ]; then
    echo "timestamp,pass_id,case_id,exit_code,wav_count,terminal,gate" > "$CSV"
fi

run_case() {
    local pass_id=$1 case_id=$2
    local label="P${pass_id}_c${case_id}"
    local stdout_log="${LOGDIR}/${label}_stdout.log"
    local stderr_log="${LOGDIR}/${label}_stderr.log"

    local rc=0
    env OMNI_T2W_DEVICE=cann-flow-only OMP_NUM_THREADS=8 OMNI_T2W_DRAIN_TIMEOUT_MS=10000 \
        timeout $PER_CASE_TIMEOUT "$BINARY" \
        -m "$MODEL" -ngl 0 --omni \
        --test "$TEST_PREFIX" 1 --test-start "$case_id" \
        > "$stdout_log" 2> "$stderr_log" || rc=$?

    local timestamp=$(date -Iseconds)
    local wav_count=$(grep -c 'T2W.*wav_.*\.wav' "$stdout_log" 2>/dev/null || echo "0")
    [ -z "$wav_count" ] && wav_count="0"
    local terminal=$(grep -oP 'T2W terminal:\s*\K\w+' "$stderr_log" 2>/dev/null | tail -1)
    [ -z "$terminal" ] && terminal="UNKNOWN"

    local gate="PASS"
    if [ "$rc" = "0" ] && [ "$wav_count" = "0" ]; then
        gate="FAIL_rc0_without_audio"
    elif [ "$terminal" = "DRAIN_TIMEOUT" ]; then
        gate="FAIL_drain_timeout"
    elif [ "$terminal" = "PIPELINE_FAILURE" ]; then
        gate="FAIL_pipeline"
    fi

    echo "${timestamp},${pass_id},${case_id},${rc},${wav_count},${terminal},${gate}" >> "$CSV"

    if [ "$gate" = "PASS" ]; then
        echo "[$(date -Iseconds)] OK    ${label}: rc=${rc} wavs=${wav_count} terminal=${terminal}"
    else
        echo "[$(date -Iseconds)] ${gate} ${label}: rc=${rc} wavs=${wav_count} terminal=${terminal}"
    fi
}

# ─── Main: parallel execution ───

running=0
for pass_id in $(seq 1 $PASSES); do
    for case_id in $CASES; do
        if is_completed "$pass_id" "$case_id"; then
            continue
        fi

        # Wait if we've reached max parallelism
        while [ $running -ge $MAX_PARALLEL ]; do
            wait -n 2>/dev/null || true
            running=$((running - 1))
        done

        run_case "$pass_id" "$case_id" &
        mark_completed "$pass_id" "$case_id"
        running=$((running + 1))
        sleep 1  # stagger starts to avoid kernel resource contention
    done
done

# Wait for remaining jobs
echo ""
echo "Waiting for remaining $running jobs..."
wait

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  P7.3 Regression Complete               ║"
echo "╚══════════════════════════════════════════╝"
echo "Finished: $(date -Iseconds)"

if [ -f "$CSV" ]; then
    echo ""
    tail -n +2 "$CSV" | awk -F, '{
        total++; gate=$7;
        gates[gate]++; wavs=$5;
        if (wavs+0==0 && $4+0==0) zero_wav++;
        if (gate=="PASS") pass_count++;
    }
    END {
        printf "Total: %d | PASS: %d | FAIL: %d | rc0_without_audio: %d\n", total, pass_count, total-pass_count, zero_wav
        for (g in gates) printf "  %s: %d\n", g, gates[g]
    }'
fi

echo ""
echo "CSV: $CSV"
exit 0
