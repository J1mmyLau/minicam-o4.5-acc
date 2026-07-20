#!/bin/bash
# Concurrency matrix scan: 1, 2, 4, 8 concurrent sessions
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_URL="${SERVER_URL:-http://localhost:9060}"
REQUESTS="${REQUESTS:-20}"
WARMUP="${WARMUP:-3}"
OUTDIR="${OUTDIR:-$SCRIPT_DIR/results}"
TIMESTAMP=$(date -u +%Y%m%d-%H%M%S)

mkdir -p "$OUTDIR"

echo "=== Concurrency Matrix Scan ==="
echo "Server:  $SERVER_URL"
echo "Requests per level: $REQUESTS"
echo "Warmup:  $WARMUP"
echo "Output:  $OUTDIR"
echo ""

for C in 1 2 4 8; do
    echo "--- C=$C ---"
    python3 "$SCRIPT_DIR/benchmark_client.py" \
        --url "$SERVER_URL" \
        --concurrency "$C" \
        --requests "$REQUESTS" \
        --warmup "$WARMUP" \
        --output-dir "$OUTDIR" \
        --debug-dir "/tmp/competition-debug-c${C}-${TIMESTAMP}"

    echo "  C=$C done."
    echo ""
done

echo "=== All concurrency levels complete ==="
echo "Results: $OUTDIR"
ls -la "$OUTDIR"/benchmark_c*.jsonl
