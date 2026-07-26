# KV Cache Mixed-Workload Soak Plan

**Date:** 2026-07-26
**Status:** DRAFT — not yet executed
**Depends on:** Stage B (6h hit-path) completion + gate review

---

## 1. Problem Statement

Stage A (1h) and Stage B (6h) only test the **cache HIT path** — same model, same prefix, same cache key, OMNI_KV_CACHE_REUSE=1 always. This validates:

- Cache file can be loaded 94/174+ times consecutively ✅
- Prefill latency is stable (~39ms) ✅
- No crashes, CANN errors, or temp leaks ✅

But does NOT validate:

| Path | Covered? | Risk if Untested |
|------|:--------:|------------------|
| cache MISS (first run, no cache file) | Prime only | MISS→SAVE logic may have latent bugs |
| cache REBUILD (delete + recreate) | No | Rebuild integrity unknown |
| ON/OFF control (OMNI_KV_CACHE_REUSE=0/1) | No | Env var gating may not work correctly |
| Different prefix (different cache key) | No | Multi-key isolation unknown |
| Process restart (crash recovery) | No | Cache survives unclean shutdown? |
| Corrupted cache detection + fallback | P2 only (single-shot) | Detection may fail under load |

**⇒ Mixed-workload soaks are REQUIRED before any DEFAULT_ON consideration.**

---

## 2. Test Matrix

### 2.1 Workload Types

| ID | Name | Description | Expected KV Behavior |
|----|------|-------------|---------------------|
| **H** | HIT baseline | Standard cache HIT iteration | HIT → 62 pos loaded |
| **M** | MISS rebuild | Delete cache file before run | MISS → full prefill → SAVE |
| **F** | OFF (force no cache) | OMNI_KV_CACHE_REUSE=0 | Skip cache, full prefill, no save |
| **R** | Re-ON after OFF | OMNI_KV_CACHE_REUSE=1 (cache exists) | HIT → 62 pos loaded |
| **P** | Prefix change | Different `--test-start` value | Different cache key → MISS → new key SAVE |
| **C** | Corruption recovery | Corrupt 1 byte in cache file | Detect bad CRC → MISS → rebuild → SAVE |
| **K** | Kill-restart | Kill process mid-decode, restart | Cache file intact → next iter should HIT |

### 2.2 Cycle Design (7 iterations per cycle)

```
Iter 1: H — HIT baseline
Iter 2: M — Delete cache → MISS → rebuild → SAVE
Iter 3: H — HIT (cache just rebuilt)
Iter 4: F — OMNI_KV_CACHE_REUSE=0 → skip cache
Iter 5: R — OMNI_KV_CACHE_REUSE=1 → HIT
Iter 6: P — Different prefix → new cache key → MISS → SAVE
Iter 7: C — Corrupt cache → detect → MISS → rebuild → SAVE
```

**Cycle duration**: ~7 × 2.5 min ≈ 17.5 min (varies with generation length)
**~3.4 cycles/hour, ~82 cycles/24h, ~574 iterations/24h**

### 2.3 Per-Path Expected Counts (24h soak)

| Path | ID | Expected Iterations | Expected HIT | Expected MISS |
|------|----|--------------------|-------------|---------------|
| HIT baseline | H | ~164 | ~164 | 0 |
| MISS rebuild | M | ~82 | 0 | ~82 |
| Force OFF | F | ~82 | 0 | 0 (no cache lookup) |
| Re-ON | R | ~82 | ~82 | 0 |
| Prefix change | P | ~82 | 0 | ~82 |
| Corruption recovery | C | ~82 | 0 | ~82 |
| **TOTAL** | | **~574** | **~246** | **~246** |

---

## 3. Staged Execution

### Stage M1: Mixed-Workload 1h (Smoke Test)

- **Duration**: 1 hour (~3 cycles, ~21 iterations)
- **Purpose**: Verify all 7 workload types function correctly before long soak
- **Gate**: All 7 types produce expected KV behavior, 0 crashes

### Stage M2: Mixed-Workload 6h

- **Duration**: 6 hours (~20 cycles, ~140 iterations)
- **Purpose**: Detect infrequent failures, verify no resource leaks with cache delete/recreate
- **Gate**: Classification closed, 0 crashes, 0 CANN errors, 0 leaks

### Stage M3: Mixed-Workload 24h

- **Duration**: 24 hours (~82 cycles, ~574 iterations)
- **Purpose**: Production-grade mixed workload stability
- **Gate**: All 15 Stage C gates, plus:
  - cache MISS→SAVE success rate ≥ 99%
  - cache corruption detection rate = 100%
  - ON/OFF control works without state leak
  - different prefix → different cache key isolation verified
  - no cache file size creep across rebuild cycles

### Stage M4: Mixed-Workload 72h (if M3 passes)

- **Duration**: 72 hours
- **Purpose**: Long-tail stability for DEFAULT_ON consideration
- **Gate**: Same as M3, plus latency drift analysis

---

## 4. Implementation Notes

### 4.1 Corruption Injection

```bash
# Single-bit corruption at byte 128 (past header)
corrupt_cache() {
    local CACHE_FILE="$1"
    python3 -c "
import sys
with open('$CACHE_FILE', 'r+b') as f:
    f.seek(128)
    b = f.read(1)
    f.seek(128)
    f.write(bytes([b[0] ^ 0x01]))
"
}
```

### 4.2 Prefix Change Implementation

```bash
# Alternates between two test cases with different system prompts
# --test-start 0: default prefix (cache key e2b568b6078ce027)
# --test-start 1: different system prompt → different cache key
```

### 4.3 Cache Delete (MISS rebuild)

```bash
rm -f /tmp/omni-kvcache/omni_kvcache_*.bin
# Next run: MISS → full prefill → SAVE
```

### 4.4 Kill-Restart (K path)

The K path is destructive (kills the running process) and requires a separate runner architecture. **Defer to a dedicated K-test stage** rather than integrating into the cyclic mixed-workload script.

---

## 5. Success Criteria for DEFAULT_ON Consideration

| Criterion | Required | Stage |
|-----------|----------|-------|
| Hit-path soak 24h | PASS | Stage C (pending) |
| Mixed-workload soak 24h | PASS | Stage M3 |
| Corruption detection rate | 100% | M1-M3 |
| MISS→SAVE success rate | ≥ 99% | M1-M3 |
| ON/OFF control correctness | 100% | M1-M3 |
| Multi-key isolation | VERIFIED | M1 |
| 0 crashes across all paths | REQUIRED | ALL |
| 0 CANN runtime errors | REQUIRED | ALL |
| 0 temp file leaks | REQUIRED | ALL |
| Latency no unexplained drift | REQUIRED | M3+ |
| Resource no monotonic growth | REQUIRED | M2+ |

---

## 6. Production Decision Gates

```
STAGE_A_HIT_PATH  (1h)  ✅ PASS
STAGE_B_HIT_PATH  (6h)  ⏳ RUNNING
STAGE_C_HIT_PATH  (24h) ⏳ PENDING_GATE_REVIEW
STAGE_M1_MIXED    (1h)  ⏳ PENDING
STAGE_M2_MIXED    (6h)  ⏳ PENDING
STAGE_M3_MIXED    (24h) ⏳ PENDING
STAGE_M4_MIXED    (72h) ⏳ PENDING
====================================
DEFAULT_ON consideration      ⏳ PENDING (min M3+M4 required)
```

### Minimum Path to DEFAULT_ON

1. Stage B (6h hit): PASS ✅
2. Stage C (24h hit): PASS
3. Stage M1 (1h mixed): PASS
4. Stage M2 (6h mixed): PASS
5. Stage M3 (24h mixed): PASS
6. Stage M4 (72h mixed): PASS
7. All 15 gates satisfied for each stage
8. Production decision document written

**Estimated timeline**: ~5 days (24h + 72h mixed = 96h minimum + gate reviews)

---

## 7. Script Template

The mixed-workload runner will follow the same pattern as `run_stage_b_6h.sh` but with a mode rotation:

```bash
# Mode rotation array
MODES=("H" "M" "H" "F" "R" "P" "C")
MODE_INDEX=0

while [ $ELAPSED -lt $DURATION_SEC ]; do
    MODE="${MODES[$MODE_INDEX]}"
    MODE_INDEX=$(( (MODE_INDEX + 1) % ${#MODES[@]} ))

    case "$MODE" in
        H) run_hit_baseline ;;
        M) run_miss_rebuild ;;
        F) run_force_off ;;
        R) run_re_on ;;
        P) run_prefix_change ;;
        C) run_corruption_recovery ;;
    esac
done
```

Full script: `p3-soak/run_stage_mixed.sh` (to be written after Stage B gate review)

---

**Plan path:** `docs/experiments/kv-cache-production/KV_CACHE_MIXED_WORKLOAD_PLAN.md`
**Status:** DRAFT — awaiting Stage B completion + gate review
**最后更新:** 2026-07-26 07:05 UTC
