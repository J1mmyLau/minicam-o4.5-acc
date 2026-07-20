#!/bin/bash
# Resource monitor — samples CPU/NPU/HBM/RSS during benchmark
set -euo pipefail

SERVER_PID="${1:-}"
if [ -z "$SERVER_PID" ]; then
    echo "Usage: $0 <server-pid>"
    exit 1
fi

OUTFILE="${OUTFILE:-resource_monitor.csv}"
INTERVAL="${INTERVAL:-5}"  # seconds between samples

echo "timestamp,pid,rss_mb,cpu_percent,hbm0_used_mb,hbm1_used_mb,thread_count" > "$OUTFILE"

echo "Monitoring PID=$SERVER_PID every ${INTERVAL}s. Output: $OUTFILE"
echo "Press Ctrl+C to stop."

while true; do
    TS=$(date -u +%Y-%m-%dT%H:%M:%S)

    # RSS in MB
    RSS=$(awk '/VmRSS/{print int($2/1024)}' "/proc/$SERVER_PID/status" 2>/dev/null || echo "0")

    # CPU % — cumulative, approximate
    CPU_PCT=$(ps -p "$SERVER_PID" -o %cpu --no-headers 2>/dev/null | tr -d ' ' || echo "0")

    # Thread count
    THREADS=$(awk '/Threads/{print $2}' "/proc/$SERVER_PID/status" 2>/dev/null || echo "0")

    # HBM usage
    HBM0=$(npu-smi info -t usages -i 0 2>/dev/null | grep "Memory" | awk '{print $3}' || echo "0")
    HBM1=$(npu-smi info -t usages -i 1 2>/dev/null | grep "Memory" | awk '{print $3}' || echo "0")

    echo "$TS,$SERVER_PID,$RSS,$CPU_PCT,$HBM0,$HBM1,$THREADS" >> "$OUTFILE"

    sleep "$INTERVAL"
done
