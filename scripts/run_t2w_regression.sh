#!/bin/bash
# P7.3 P9: Formal T2W Lifecycle Regression
# 15 passes × 9 cases = 135 requests
# Gate: rc=0-without-audio must be ZERO
# Also validates: drain state machine, terminal output classification
set -o pipefail

BINARY="/workspace/llama.cpp-omni-ngl8-e2e/build/bin/llama-omni-cli"
MODEL="/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf"
TEST_PREFIX="/workspace/llama.cpp-omni-ngl8-e2e/tools/omni/assets/test_case/omni_test_case/omni_test_case_"
OUTDIR="/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/p7_3-regression"
LOGDIR="${OUTDIR}/logs"
CSV="${OUTDIR}/regression_raw.csv"
PROGRESS="${OUTDIR}/.progress"

PASSES=15
CASES=9
PER_CASE_TIMEOUT=180

mkdir -p "$OUTDIR" "$LOGDIR"

echo "PID: $$"
echo "Started: $(date -Iseconds)"
echo "Passes: $PASSES × $CASES = $((PASSES * CASES)) cases"
echo "Binary: $BINARY"
echo "CSV:    $CSV"
echo ""

# Trap
cleanup() {
    echo "[$(date -Iseconds)] CLEANUP: runner exiting"
}
trap cleanup EXIT

# Progress tracking
is_completed() { grep -q "^${1},${2}$" "${PROGRESS}" 2>/dev/null; }
mark_completed() { echo "${1},${2}" >> "${PROGRESS}"; }

# CSV header
if [ ! -f "$CSV" ]; then
    echo "timestamp,pass_id,case_id,exit_code,wav_count,drain_state,terminal_output,decode_to_first_audio_ms,request_to_first_audio_ms" > "$CSV"
fi

run_case() {
    local pass_id=$1 case_id=$2
    local label="P${pass_id}_c${case_id}"
    local stdout_log="${LOGDIR}/${label}_stdout.log"
    local stderr_log="${LOGDIR}/${label}_stderr.log"

    echo "[$(date -Iseconds)] START ${label}"

    local rc=0
    env OMNI_T2W_DEVICE=cann-flow-only OMP_NUM_THREADS=8 OMNI_T2W_DRAIN_TIMEOUT_MS=10000 \
        timeout $PER_CASE_TIMEOUT "$BINARY" \
        -m "$MODEL" -ngl 0 --omni \
        --test "$TEST_PREFIX" 1 --test-start "$case_id" \
        > "$stdout_log" 2> "$stderr_log" || rc=$?

    local timestamp=$(date -Iseconds)

    # Extract metrics
    local wav_count=$(grep -c 'T2W.*wav_.*\.wav' "$stdout_log" 2>/dev/null || echo "0")
    [ -z "$wav_count" ] && wav_count="0"

    local decode_fa=$(grep -oP '首响时间.*?:\s*\K\d+' "$stdout_log" | head -1 | tr -d ' ')
    [ -z "$decode_fa" ] && decode_fa=""

    local request_fa=""
    if grep -q 'request_to_first_audio' "$stdout_log"; then
        request_fa=$(grep -oP 'request_to_first_audio\):\s*\K\d+' "$stdout_log" | head -1 | tr -d ' ')
    fi
    [ -z "$request_fa" ] && request_fa=""

    local terminal=$(grep -oP 'T2W terminal:\s*\K\w+' "$stderr_log" | tail -1)
    [ -z "$terminal" ] && terminal="UNKNOWN"

    local drain_state=$(grep -oP 'T2W drain:\s*\K\w+' "$stderr_log" | tail -1)
    [ -z "$drain_state" ] && drain_state="UNKNOWN"

    # Gate: rc=0 with 0 wavs is a FAILURE
    local gate="PASS"
    if [ "$rc" = "0" ] && [ "$wav_count" = "0" ]; then
        gate="FAIL_rc0_without_audio"
    elif [ "$rc" != "0" ] && [ "$rc" != "124" ] && [ "$rc" != "143" ]; then
        gate="FAIL_nonzero_rc_${rc}"
    elif [ "$terminal" = "DRAIN_TIMEOUT" ]; then
        gate="FAIL_drain_timeout"
    elif [ "$terminal" = "PIPELINE_FAILURE" ]; then
        gate="FAIL_pipeline"
    fi

    local csv_line="${timestamp},${pass_id},${case_id},${rc},${wav_count},${drain_state},${terminal},${decode_fa},${request_fa},${gate}"
    echo "$csv_line" >> "$CSV"

    if [ "$gate" = "PASS" ]; then
        echo "[$(date -Iseconds)] OK    ${label}: rc=${rc} wavs=${wav_count} terminal=${terminal} decode_fa=${decode_fa}ms request_fa=${request_fa}ms"
    else
        echo "[$(date -Iseconds)] ${gate} ${label}: rc=${rc} wavs=${wav_count} terminal=${terminal}"
    fi
}

# ─── Main ───

total=0 skipped=0 failed=0

for pass_id in $(seq 1 $PASSES); do
    echo ""
    echo "───── Pass ${pass_id}/${PASSES} ─────"
    for case_id in $(seq 0 $((CASES - 1))); do
        if is_completed "$pass_id" "$case_id"; then
            skipped=$((skipped + 1))
            continue
        fi
        run_case "$pass_id" "$case_id"
        mark_completed "$pass_id" "$case_id"
        total=$((total + 1))
        sleep 2
    done
done

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  P7.3 Regression Complete               ║"
echo "╚══════════════════════════════════════════╝"
echo "Finished: $(date -Iseconds)"
echo "Total ran:     $total"
echo "Total skipped: $skipped"

if [ -f "$CSV" ]; then
    echo ""
    echo "─── Results Summary ───"
    tail -n +2 "$CSV" | awk -F, '{
        total++;
        gate=$10;
        gates[gate]++;
        terminal=$7;
        terminals[terminal]++;
        wavs=$5;
        if (wavs==0) zero_wav++;
        if (gate=="PASS") pass_count++;
        req_fa=$9;
        if (req_fa != "") { req_sum += req_fa; req_n++ }
    }
    END {
        printf "Total requests: %d\n", total
        printf "PASS: %d\n", pass_count
        printf "FAIL: %d\n", total - pass_count
        printf "rc=0 with 0 WAVs: %d (MUST BE 0)\n", zero_wav
        printf "\nGates:\n"
        for (g in gates) printf "  %s: %d\n", g, gates[g]
        printf "\nTerminals:\n"
        for (t in terminals) printf "  %s: %d\n", t, terminals[t]
        if (req_n > 0) printf "\nMean request_to_first_audio_ms: %.0f\n", req_sum/req_n
    }'
fi

echo ""
echo "CSV: $CSV"
exit 0
