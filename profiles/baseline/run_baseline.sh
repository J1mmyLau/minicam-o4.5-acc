#!/bin/bash
# Baseline measurement: decode-to-speak wall-clock timing
# Runs 3 test cases (SHORT/MEDIUM/LONG), each 5 iterations
set -euo pipefail

source /usr/local/Ascend/cann-9.1.0-beta.1/set_env.sh 2>/dev/null

BINARY="/workspace/llama.cpp-omni-operator/build/bin/llama-omni-cli"
MODEL="/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf"
TEST_PREFIX="/workspace/llama.cpp-omni-operator/tools/omni/assets/test_case/omni_test_case/omni_test_case_"
OUTDIR="/workspace/llama.cpp-omni-operator/profiles/baseline"
N_RUNS=5

# Test cases: 0 (small image), 4 (medium), 7 (large)
declare -A TC_LABELS
TC_LABELS[0]="SHORT"
TC_LABELS[4]="MEDIUM"
TC_LABELS[7]="LONG"

mkdir -p "$OUTDIR"

echo "# Baseline Report: Decode-to-Speak Wall-Clock Timing"
echo "## $(date -u +'%Y-%m-%d %H:%M UTC')"
echo "## Binary: $(sha256sum $BINARY | cut -c1-16)"
echo "## Model: $(basename $MODEL)"
echo ""

for tc in 0 4 7; do
    label="${TC_LABELS[$tc]}"
    echo "## Test Case $tc ($label)"
    echo ""
    echo "| Run | Wall (ms) | Exit | stderr lines |"
    echo "|-----|-----------|------|-------------|"

    times=()
    for run in $(seq 1 $N_RUNS); do
        rm -rf tools/omni/output/round_* 2>/dev/null

        T0=$(date +%s%N)
        "$BINARY" -m "$MODEL" -ngl 0 --omni \
            --test "$TEST_PREFIX" 1 --test-start "$tc" \
            > "${OUTDIR}/baseline_tc${tc}_r${run}.stdout" 2> "${OUTDIR}/baseline_tc${tc}_r${run}.stderr"
        rc=$?
        T1=$(date +%s%N)

        wall_ms=$(( (T1 - T0) / 1000000 ))
        stderr_lines=$(wc -l < "${OUTDIR}/baseline_tc${tc}_r${run}.stderr")

        echo "| $run | $wall_ms | $rc | $stderr_lines |"
        times+=($wall_ms)
    done

    # Calculate p50, p95, p99
    sorted=($(printf '%s\n' "${times[@]}" | sort -n))
    p50=${sorted[2]}   # 5 runs: index 2 = median
    p95=${sorted[4]}   # index 4 = 95th percentile (max in 5 samples)
    min=${sorted[0]}
    max=${sorted[4]}

    # mean
    sum=0
    for t in "${times[@]}"; do sum=$((sum + t)); done
    mean=$((sum / ${#times[@]}))

    echo ""
    echo "**Summary ($label):**"
    echo ""
    echo "| Stat | Value |"
    echo "|------|-------|"
    echo "| n | $N_RUNS |"
    echo "| min | ${min}ms |"
    echo "| p50 | ${p50}ms |"
    echo "| p95 | ${p95}ms |"
    echo "| max | ${max}ms |"
    echo "| mean | ${mean}ms |"
    echo ""
done

echo "## Raw data: $OUTDIR/baseline_tc*_r*.{stdout,stderr}"
