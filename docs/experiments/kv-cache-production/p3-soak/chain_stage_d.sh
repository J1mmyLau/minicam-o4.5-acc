#!/bin/bash
# Auto-chain: wait for Stage C to finish, then launch Stage D (72h)
# DISABLED: require explicit approval for 72h/168h stage chaining
# Set AUTO_CHAIN_LONG_SOAK=1 to re-enable
set -euo pipefail

if [ "${AUTO_CHAIN_LONG_SOAK:-0}" != "1" ]; then
    echo "AUTO_CHAIN_LONG_SOAK=0 — skipping automatic Stage D launch" >&2
    echo "Set AUTO_CHAIN_LONG_SOAK=1 to enable automatic long-soak chaining" >&2
    exit 0
fi

STAGE_C_PID=1110033
RUN_DIR_C="docs/experiments/kv-cache-production/p3-soak/stage_mixed_20260727_034614"
LOGFILE="${RUN_DIR_C}/chain_to_d.log"

exec >> "$LOGFILE" 2>&1

echo "=== Chain C→D watcher started at $(date -u) ==="
echo "Waiting for Stage C PID $STAGE_C_PID to exit..."

while kill -0 "$STAGE_C_PID" 2>/dev/null; do
    sleep 60
done

echo "Stage C runner exited at $(date -u)"

# Verify DONE file
if [ -f "${RUN_DIR_C}/DONE" ]; then
    echo "DONE file found. Stage C completed successfully."
    cat "${RUN_DIR_C}/DONE"
else
    echo "WARNING: No DONE file found. Checking progress..."
    tail -20 "${RUN_DIR_C}/progress.log" 2>/dev/null || echo "No progress log"
fi

# Clear old cache
echo "Clearing cache..."
rm -f /tmp/omni-kvcache/omni_kvcache_*.bin
echo "Cache cleared."

# Wait a moment
sleep 5

# Launch Stage D
echo ""
echo "=== Launching Stage D (72h mixed) at $(date -u) ==="
cd /workspace/llama.cpp-omni-kvcache-prod

OMNI_MIXED_DURATION=259200 OMNI_MIXED_STAGE=D \
    nohup bash docs/experiments/kv-cache-production/p3-soak/run_stage_mixed.sh \
    > /dev/null 2>&1 &

STAGE_D_PID=$!
echo "Stage D PID: $STAGE_D_PID"
echo "Target completion: $(date -u -d '+72 hours')"

# Record in audit
AUDIT_FILE="docs/tracking/AUDIT.md"
cat >> "$AUDIT_FILE" << EOF

## $(date -u +'%Y-%m-%d %H:%M') | START | STAGE_D_72H_AUTO_LAUNCHED

- Auto-chained from Stage C completion
- Stage D PID: $STAGE_D_PID
- Duration: 259,200s (72h)
- Stage C run dir: $RUN_DIR_C
- Target completion: $(date -u -d '+72 hours' +'%Y-%m-%d %H:%M UTC')
EOF

echo "Chain complete. Stage D running."
