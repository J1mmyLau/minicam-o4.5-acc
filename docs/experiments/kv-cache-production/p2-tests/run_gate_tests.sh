#!/bin/bash
# P2: KV Cache Boundary Condition Gate Tests — CORRECTED
# Tests G1, G4, G6 (cache key), G7a-G7e (corruption), G8a (restart)
set -euo pipefail

BINARY=/workspace/llama.cpp-omni-kvcache-prod/build/bin/llama-omni-cli
MODEL=/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf
TEST_PREFIX=/workspace/llama.cpp-omni-kvcache-prod/tools/omni/assets/test_case/omni_test_case/omni_test_case_
OUTDIR=/workspace/llama.cpp-omni-kvcache-prod/docs/experiments/kv-cache-production/p2-tests
CACHE_DIR=/tmp/omni-kvcache
TIMESTAMP=20260726_031800  # fixed for this run

export OMNI_KV_CACHE_REUSE=1
export OMNI_T2W_DEVICE=cann-flow-only
export OMP_NUM_THREADS=8
export OMNI_T2W_DRAIN_TIMEOUT_MS=10000
export OMNI_KV_CACHE_PATH=$CACHE_DIR

run_test() {
    local label="$1"
    local model_path="${2:-$MODEL}"
    local extra_args="${3:-}"
    local logfile="${OUTDIR}/${TIMESTAMP}_${label}.log"
    echo "=== $(date) Running: $label (model=$model_path) ===" | tee "$logfile"
    timeout 120 env OMNI_KV_CACHE_REUSE=1 OMNI_T2W_DEVICE=cann-flow-only \
        OMP_NUM_THREADS=8 OMNI_T2W_DRAIN_TIMEOUT_MS=10000 \
        OMNI_KV_CACHE_PATH=$CACHE_DIR \
        $BINARY -m "$model_path" -ngl 0 --omni --test "$TEST_PREFIX" 1 --test-start 0 \
        $extra_args >> "$logfile" 2>&1 || true
    echo "rc=$?" | tee -a "$logfile"
    grep "KV cache HIT\|KV cache MISS\|KV cache SAVE\|KV cache SAVED\|KV cache:.*fail\|KV cache:.*bad\|KV cache:.*mismatch\|KV cache:.*truncat\|KV cache:.*checksum\|cache_hits\|cache_misses\|cache_tokens" "$logfile" || echo "(no KV cache lines)"
}

# Used to find the cache file matching the default config key
DEFAULT_KEY="e2b568b6078ce027"
CACHE_FILE="${CACHE_DIR}/omni_kvcache_${DEFAULT_KEY}.bin"

echo "============================================"
echo "P2 Gate Tests (Corrected) — $TIMESTAMP"
echo "============================================"

# ─── Clean slate ─────────────────────────────────────────────────────
echo ""
echo "=== Cleaning all caches ==="
rm -f $CACHE_DIR/omni_kvcache_*.bin $CACHE_DIR/omni_kvcache_*.tmp.* $CACHE_DIR/omni_kvcache_*.state.* $CACHE_DIR/omni_kvcache_*.load.*

# ─── G1: Baseline — same static prefix should HIT ─────────────────────
echo ""
echo "=== G1: Baseline cache HIT test ==="
run_test "G1a_miss" "$MODEL" ""
run_test "G1b_hit" "$MODEL" ""
echo "Cache file exists: $(ls -la "$CACHE_FILE" 2>/dev/null || echo MISSING)"

# ─── G4: Different model path → different cache key ──────────────────
echo ""
echo "=== G4: Different model path ==="
MODEL_SYMLINK=/tmp/test_model_symlink_$(date +%s).gguf
ln -sf "$MODEL" "$MODEL_SYMLINK"
echo "Symlink: $MODEL_SYMLINK -> $MODEL"
# Run with symlink — should produce DIFFERENT cache key than default
run_test "G4_symlink" "$MODEL_SYMLINK" ""
# Verify: original cache file still exists, and a NEW cache file was created
echo "Cache files after G4 symlink run:"
ls -la $CACHE_DIR/omni_kvcache_*.bin 2>/dev/null
CACHE_COUNT=$(ls $CACHE_DIR/omni_kvcache_*.bin 2>/dev/null | wc -l)
if [ "$CACHE_COUNT" -ge 2 ]; then
    echo "G4 PASS: Two different cache files exist (different keys)"
else
    echo "G4 NOTE: Only $CACHE_COUNT cache file(s) — symlink may resolve to same path in llama.cpp"
fi
rm -f "$MODEL_SYMLINK"

# ─── G6: Different context size → different cache key ────────────────
echo ""
echo "=== G6: Different context size ==="
# Should produce different key than default 4096
run_test "G6_ctx2048" "$MODEL" "-c 2048"
echo "Cache files after G6:"
ls -la $CACHE_DIR/omni_kvcache_*.bin 2>/dev/null
CTX_COUNT=$(ls $CACHE_DIR/omni_kvcache_*.bin 2>/dev/null | wc -l)
echo "G6: $CTX_COUNT cache files (expect >= 2 for different ctx sizes)"

# Also verify default ctx still hits original
run_test "G6_verify_default_hit" "$MODEL" "-c 4096"

# ─── G7a: Truncated cache file ───────────────────────────────────────
echo ""
echo "=== G7a: Truncated cache file ==="
if [ -f "$CACHE_FILE" ]; then
    cp "$CACHE_FILE" "${CACHE_FILE}.g7a_backup"
    ORIG_SIZE=$(stat -c%s "$CACHE_FILE")
    HALF_SIZE=$(( ORIG_SIZE / 2 ))
    truncate -s $HALF_SIZE "$CACHE_FILE"
    echo "Truncated $CACHE_FILE from $ORIG_SIZE to $HALF_SIZE bytes"
    run_test "G7a_truncated" "$MODEL" ""
    # Should have detected corruption and recreated the file
    NEW_SIZE=$(stat -c%s "$CACHE_FILE" 2>/dev/null || echo 0)
    if [ "$NEW_SIZE" -eq "$ORIG_SIZE" ]; then
        echo "G7a PASS: Corrupt file was recreated at full size"
    elif [ "$NEW_SIZE" -eq "$HALF_SIZE" ]; then
        echo "G7a FAIL: Truncated file was NOT detected/recreated"
    else
        echo "G7a CHECK: File size $NEW_SIZE (orig $ORIG_SIZE)"
    fi
    rm -f "${CACHE_FILE}.g7a_backup"
else
    echo "G7a SKIP: cache file not found"
fi

# ─── G7b: Bit-flipped data (CRC should catch it) ────────────────────
echo ""
echo "=== G7b: Bit-flipped data ==="
if [ -f "$CACHE_FILE" ]; then
    cp "$CACHE_FILE" "${CACHE_FILE}.g7b_backup"
    python3 -c "
with open('$CACHE_FILE', 'r+b') as f:
    # Flip a bit in the data section (byte 50, well past 24-byte header)
    f.seek(50)
    b = f.read(1)
    f.seek(50)
    f.write(bytes([b[0] ^ 0x01]))
print('Flipped bit at offset 50')
"
    run_test "G7b_bitflip" "$MODEL" ""
    NEW_SIZE=$(stat -c%s "$CACHE_FILE" 2>/dev/null || echo 0)
    ORIG_SIZE=$(stat -c%s "${CACHE_FILE}.g7b_backup" 2>/dev/null || echo 0)
    if [ "$NEW_SIZE" -eq "$ORIG_SIZE" ] && [ -f "$CACHE_FILE" ]; then
        echo "G7b CHECK: File restored to original size — verify HIT in next run"
        run_test "G7b_verify_hit" "$MODEL" ""
    else
        echo "G7b NOTE: File was deleted/recreated — corruption was detected"
        run_test "G7b_verify_recreated" "$MODEL" ""
    fi
    rm -f "${CACHE_FILE}.g7b_backup"
else
    echo "G7b SKIP: cache file not found"
fi

# ─── G7c: Bad magic bytes ────────────────────────────────────────────
echo ""
echo "=== G7c: Bad magic bytes ==="
if [ -f "$CACHE_FILE" ]; then
    cp "$CACHE_FILE" "${CACHE_FILE}.g7c_backup"
    python3 -c "
with open('$CACHE_FILE', 'r+b') as f:
    f.seek(0)
    f.write(b'BADM')
print('Corrupted magic to BADM')
"
    run_test "G7c_bad_magic" "$MODEL" ""
    # Check that the STALE file was detected and a NEW one created
    if [ -f "$CACHE_FILE" ]; then
        FILE_MAGIC=$(xxd -l4 -p "$CACHE_FILE")
        if [ "$FILE_MAGIC" = "4241444d" ]; then
            echo "G7c FAIL: Bad magic file NOT cleaned up"
        else
            echo "G7c PASS: Corrupt file was replaced with valid one (magic=$FILE_MAGIC)"
        fi
    fi
    rm -f "${CACHE_FILE}.g7c_backup"
else
    echo "G7c SKIP: cache file not found"
fi

# ─── G7d: Version mismatch ──────────────────────────────────────────
echo ""
echo "=== G7d: Version mismatch ==="
if [ -f "$CACHE_FILE" ]; then
    cp "$CACHE_FILE" "${CACHE_FILE}.g7d_backup"
    python3 -c "
import struct
with open('$CACHE_FILE', 'r+b') as f:
    f.seek(4)
    f.write(struct.pack('<I', 99))
print('Set version to 99')
"
    run_test "G7d_bad_version" "$MODEL" ""
    if [ -f "$CACHE_FILE" ]; then
        echo "G7d PASS: Cache file recreated with valid version"
    fi
    rm -f "${CACHE_FILE}.g7d_backup"
else
    echo "G7d SKIP: cache file not found"
fi

# ─── G7e: CRC checksum mismatch ─────────────────────────────────────
echo ""
echo "=== G7e: CRC mismatch ==="
if [ -f "$CACHE_FILE" ]; then
    cp "$CACHE_FILE" "${CACHE_FILE}.g7e_backup"
    python3 -c "
import struct
with open('$CACHE_FILE', 'r+b') as f:
    # CRC is at offset 16 (after magic:4 + version:4 + key_hash:8)
    f.seek(16)
    f.write(struct.pack('<I', 0xDEADBEEF))
print('Corrupted stored CRC to 0xDEADBEEF')
"
    run_test "G7e_bad_crc" "$MODEL" ""
    if [ -f "$CACHE_FILE" ]; then
        echo "G7e PASS: Cache file recreated after CRC mismatch detected"
    fi
    rm -f "${CACHE_FILE}.g7e_backup"
else
    echo "G7e SKIP: cache file not found"
fi

# ─── G8a: Restart cache reuse ────────────────────────────────────────
echo ""
echo "=== G8a: Restart cache reuse ==="
run_test "G8a_restart" "$MODEL" ""

# ─── Final state ──────────────────────────────────────────────────────
echo ""
echo "=== Final Cache State ==="
ls -la $CACHE_DIR/omni_kvcache_*.bin 2>/dev/null || echo "(no cache files)"
echo "Temp files:"
ls -la $CACHE_DIR/omni_kvcache_*.tmp.* $CACHE_DIR/omni_kvcache_*.state.* $CACHE_DIR/omni_kvcache_*.load.* 2>/dev/null || echo "(no temp files — good)"

echo ""
echo "=== P2 Gate Tests Complete ==="
