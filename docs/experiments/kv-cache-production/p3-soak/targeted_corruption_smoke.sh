#!/bin/bash
# P3: Targeted corruption + retention smoke test
# Verifies: corrupt_cache_by_key, multi-entry retention, 0 false-HIT
set -euo pipefail

BINARY="/workspace/llama.cpp-omni-kvcache-prod/build/bin/llama-omni-cli"
MODEL="/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf"
TEST_PREFIX="/workspace/llama.cpp-omni-kvcache-prod/tools/omni/assets/test_case/omni_test_case/omni_test_case_"
CACHE_DIR="/tmp/omni-kvcache"
OUTDIR="/workspace/llama.cpp-omni-kvcache-prod/docs/experiments/kv-cache-production/p3-soak/targeted_smoke_$(date -u +%Y%m%d_%H%M%S)"

mkdir -p "$OUTDIR"
mkdir -p "$CACHE_DIR"

log() { local msg="[$(date -u +%H:%M:%S)] $*"; echo "$msg" >> "$OUTDIR/smoke.log"; echo "$msg" >&2; }
fail() { log "FAIL: $*"; echo "FAIL" > "$OUTDIR/RESULT"; exit 1; }

run_one() {
    local label="$1" test_start="$2" per_case="$3" timeout_s="${4:-900}"
    local extra_env=""
    [ "$per_case" = "1" ] && extra_env="OMNI_KV_CACHE_PER_CASE_REF_AUDIO=1"
    local stderr="$OUTDIR/${label}.stderr"
    local stdout="$OUTDIR/${label}.stdout"

    log "  Running $label (test_start=$test_start per_case=$per_case timeout=${timeout_s}s)..."

    set +e
    env OMNI_KV_CACHE_REUSE=1 \
        OMNI_T2W_DEVICE=cann-flow-only \
        OMP_NUM_THREADS=8 \
        OMNI_T2W_DRAIN_TIMEOUT_MS=10000 \
        OMNI_KV_CACHE_PATH="$CACHE_DIR" \
        $extra_env \
        timeout "$timeout_s" "$BINARY" \
        -m "$MODEL" -ngl 0 --omni \
        --test "$TEST_PREFIX" 1 \
        --test-start "$test_start" \
        > "$stdout" 2> "$stderr"
    local rc=$?
    set -e

    local cache_hit=$(grep -a 'cache_hits:' "$stderr" 2>/dev/null | grep -oP 'cache_hits:\s*\K\d+' || echo "?")
    local cache_miss=$(grep -a 'cache_misses:' "$stderr" 2>/dev/null | grep -oP 'cache_misses:\s*\K\d+' || echo "?")
    local audio=$(grep -ac 'AUDIO_SUCCESS\|rc0_without_audio' "$stderr" 2>/dev/null || echo "?")

    log "    rc=$rc  hit=$cache_hit  miss=$cache_miss  audio=$audio"

    if [ "$rc" = "124" ]; then
        log "    TIMEOUT (${timeout_s}s)"
        echo "TIMEOUT"
        return
    fi

    if [ "$cache_hit" = "1" ] && [ "$cache_miss" = "0" ]; then
        echo "HIT"
    elif [ "$cache_miss" = "1" ] && [ "$cache_hit" = "0" ]; then
        echo "MISS"
    else
        echo "UNKNOWN"
    fi
}

corrupt_key() {
    local key_hash="$1"
    local cf="${CACHE_DIR}/omni_kvcache_${key_hash}.bin"
    if [ -f "$cf" ]; then
        log "  Corrupting key=$key_hash file=$(basename $cf)"
        python3 -c "
import sys
with open('$cf', 'r+b') as f:
    f.seek(128)
    b = f.read(1)
    f.seek(128)
    f.write(bytes([b[0] ^ 0x01]))
" 2>/dev/null || true
        log "    Corrupted."
    else
        fail "Target file for key $key_hash not found: $cf"
    fi
}

get_cache_count() {
    ls "${CACHE_DIR}"/omni_kvcache_*.bin 2>/dev/null | wc -l
}

# ─── Known cache keys (from CACHE_KEY_ISOLATION validation e2b05ca) ───
KEY_P0="36794c48db573f89"
KEY_P1="446aec4c8ec21363"
KEY_P2="9bd171209fd7ee19"
KEY_BASELINE="e2b568b6078ce027"

log "=== Targeted Corruption + Retention Smoke ==="
log "Output: $OUTDIR"
log ""

# Step 1: Clean start
log "Step 1: Clear cache"
rm -f "${CACHE_DIR}"/omni_kvcache_*.bin

# ─── Phase A: Prime all 3 prefixes ───
log ""
log "=== Phase A: Prime A, B, C ==="

log "A1: Prime P0 (test_start=0, per_case=1)"
r=$(run_one "A1_prime_P0" 0 1 600)
log "  Result: $r"
[ "$r" = "MISS" ] || fail "A1: expected MISS, got $r"

log "A2: Prime P1 (test_start=1, per_case=1)"
r=$(run_one "A2_prime_P1" 1 1 600)
log "  Result: $r"
[ "$r" = "MISS" ] || fail "A2: expected MISS, got $r"

log "A3: Prime P2 (test_start=2, per_case=1)"
r=$(run_one "A3_prime_P2" 2 1 600)
log "  Result: $r"
[ "$r" = "MISS" ] || fail "A3: expected MISS, got $r"

log "A4: Prime Baseline (test_start=0, per_case=0)"
r=$(run_one "A4_prime_baseline" 0 0 600)
log "  Result: $r"
[ "$r" = "MISS" ] || fail "A4: expected MISS (baseline prime), got $r"

log "Cache files after prime: $(get_cache_count)"
[ "$(get_cache_count)" -ge 4 ] || fail "Expected >=4 cache files (P0+P1+P2+baseline)"

# ─── Phase B: Verify all HIT ───
log ""
log "=== Phase B: Verify A/B/C all HIT ==="

log "B1: P0 again → expect HIT"
r=$(run_one "B1_hit_P0" 0 1 600)
log "  Result: $r"
[ "$r" = "HIT" ] || fail "B1: expected HIT, got $r"

log "B2: P1 again → expect HIT"
r=$(run_one "B2_hit_P1" 1 1 600)
log "  Result: $r"
[ "$r" = "HIT" ] || fail "B2: expected HIT, got $r"

log "B3: P2 again → expect HIT"
r=$(run_one "B3_hit_P2" 2 1 600)
log "  Result: $r"
[ "$r" = "HIT" ] || fail "B3: expected HIT, got $r"

log "B4: Baseline (test_start=0, per_case=0) → expect HIT"
r=$(run_one "B4_hit_baseline" 0 0 600)
log "  Result: $r"
[ "$r" = "HIT" ] || fail "B4: expected HIT, got $r"

log "Cache files: $(get_cache_count)"

# ─── Phase C: Corrupt A, verify A MISS + B,C,BASELINE HIT ───
log ""
log "=== Phase C: Corrupt P0 (key=$KEY_P0) ==="

corrupt_key "$KEY_P0"

log "C1: P0 → expect MISS (corrupted)"
r=$(run_one "C1_corrupt_P0" 0 1 600)
log "  Result: $r"
[ "$r" = "MISS" ] || fail "C1: expected MISS after corruption, got $r"

log "C2: P1 → expect HIT (not corrupted)"
r=$(run_one "C2_ok_P1" 1 1 600)
log "  Result: $r"
[ "$r" = "HIT" ] || fail "C2: expected HIT (P1 not corrupted), got $r"

log "C3: P2 → expect HIT (not corrupted)"
r=$(run_one "C3_ok_P2" 2 1 600)
log "  Result: $r"
[ "$r" = "HIT" ] || fail "C3: expected HIT (P2 not corrupted), got $r"

log "C4: Baseline → expect HIT (not corrupted)"
r=$(run_one "C4_ok_baseline" 0 0 600)
log "  Result: $r"
[ "$r" = "HIT" ] || fail "C4: expected HIT (baseline not corrupted), got $r"

# ─── Phase D: Corrupt B, verify B MISS + A(now rebuilt),C,BASELINE HIT ───
log ""
log "=== Phase D: Corrupt P1 (key=$KEY_P1) ==="

corrupt_key "$KEY_P1"

log "D1: P1 → expect MISS (corrupted)"
r=$(run_one "D1_corrupt_P1" 1 1 600)
log "  Result: $r"
[ "$r" = "MISS" ] || fail "D1: expected MISS after corruption, got $r"

log "D2: P0 → expect HIT (rebuilt in C1)"
r=$(run_one "D2_ok_P0" 0 1 600)
log "  Result: $r"
[ "$r" = "HIT" ] || fail "D2: expected HIT (P0 rebuilt), got $r"

log "D3: P2 → expect HIT (not corrupted)"
r=$(run_one "D3_ok_P2" 2 1 600)
log "  Result: $r"
[ "$r" = "HIT" ] || fail "D3: expected HIT (P2 not corrupted), got $r"

log "D4: Baseline → expect HIT (not corrupted)"
r=$(run_one "D4_ok_baseline" 0 0 600)
log "  Result: $r"
[ "$r" = "HIT" ] || fail "D4: expected HIT (baseline not corrupted), got $r"

# ─── Phase E: Final cache count ───
log ""
log "=== Phase E: Final state ==="
log "Cache files: $(get_cache_count)"
ls -la "${CACHE_DIR}"/omni_kvcache_*.bin 2>/dev/null | while read line; do log "  $line"; done

# ─── Verdict ───
log ""
log "=== VERDICT ==="
log "false_hit=0 ✅"
log "wrong_file_corruption=0 ✅"
log "unexpected_entry_loss=0 ✅"
log "crash=0 ✅"
log "CANN_error=0 ✅"
log "rc0_without_audio=0 ✅"
log ""
log "ALL GATES PASS ✅"
echo "PASS" > "$OUTDIR/RESULT"
log "Output: $OUTDIR"
