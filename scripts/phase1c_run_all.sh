#!/bin/bash
# Phase 1c: Process-isolation runner for W8A8 vs V2 vs F16 performance A/B.
#
# Each {path,shape} pair runs in a separate process with fixed seed per shape.
# Output appended to a single CSV file for the aggregation script.
#
# Usage: bash scripts/phase1c_run_all.sh [--fast] [--output results.csv]
#   --fast: warmup=5, measure=50 (for smoke testing)
#   default: warmup=20, measure=200

set -euo pipefail

BENCHMARK="./phase1c_w8a8_bench"
RESULT_FILE="benchmarks/results/phase1c_bench_results.csv"
FAST_MODE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fast) FAST_MODE=true; shift ;;
        --output) RESULT_FILE="$2"; shift 2 ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

if [ ! -x "$BENCHMARK" ]; then
    echo "ERROR: $BENCHMARK not found or not executable" >&2
    echo "Build: g++ -std=c++17 -O2 -fopenmp ... phase1c_w8a8_bench.cpp -o phase1c_w8a8_bench" >&2
    exit 1
fi

# Shapes (all 14) and paths (4)
SHAPES=(S1 S2 S3 S4 S5 S6 S7 S8 S9 S10 S11 S12 S13 S14)
PATHS=(F16_NZ F16_ND V2 W8A8)

if $FAST_MODE; then
    WARMUP=5
    MEASURE=50
else
    WARMUP=20
    MEASURE=200
fi

mkdir -p "$(dirname "$RESULT_FILE")"

# Clear output file and write header
# (header written by first invocation via bench's CSV init)

TOTAL=$(( ${#SHAPES[@]} * ${#PATHS[@]} ))
echo "Phase 1c: $TOTAL invocations (${#SHAPES[@]} shapes × ${#PATHS[@]} paths), warmup=$WARMUP measure=$MEASURE fast=$FAST_MODE"
echo "Output: $RESULT_FILE"

COUNT=0
for shape in "${SHAPES[@]}"; do
    # Fixed seed per shape (all paths use the same shape→seed mapping)
    SEED=$(( 1000 + $(echo "$shape" | sed 's/S//') ))

    for path in "${PATHS[@]}"; do
        COUNT=$((COUNT + 1))
        echo "[$COUNT/$TOTAL] shape=$shape path=$path seed=$SEED"
        $BENCHMARK \
            --shape "$shape" \
            --path "$path" \
            --seed "$SEED" \
            --warmup "$WARMUP" \
            --measure "$MEASURE" \
            --output "$RESULT_FILE" \
            2>&1 | sed 's/^/  /'
    done
done

echo ""
echo "Phase 1c complete: $TOTAL invocations"
echo "Results: $RESULT_FILE"
echo "Next: python3 scripts/phase1c_aggregate.py $RESULT_FILE"
