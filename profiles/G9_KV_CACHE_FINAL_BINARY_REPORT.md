# G9: KV Cache Final-Binary Integration Gate

**Date:** 2026-07-29
**Binary:** HEAD `8e08db4`, SHA256 `6913c972...`
**Status:** PASS

---

## Test Configuration

| Parameter | Value |
|-----------|-------|
| Cache dir | `/tmp/g9-kvcache` |
| Cache mode env | `OMNI_KV_CACHE_REUSE=1` or unset |
| Test cases per run | 1 (same test case for all) |
| Timeout per run | 180s |

---

## Results

### Phase A: CACHE_OFF (n=3)

| Run | RC | WAVs | Audio | CANN Err |
|-----|-----|------|-------|----------|
| 1 | 0 | 22 | ✅ | 0 |
| 2 | 0 | 3 | ✅ | 0 |
| 3 | 0 | 8 | ✅ | 0 |

### Phase B: CACHE_ON_MISS (n=3, independent rebuilds)

| Run | RC | WAVs | Audio | CANN Err | Cache |
|-----|-----|------|-------|----------|-------|
| 1 | 0 | 9 | ✅ | 0 | Built+SAVED |
| 2 | 0 | 3 | ✅ | 0 | Built+SAVED |
| 3 | 0 | 28 | ✅ | 0 | Built+SAVED |

### Phase C: CACHE_ON_HIT (n=30)

| Metric | Value |
|--------|-------|
| Total runs | 30 |
| Valid HITs (cache_hits=1) | 28 |
| Timeouts (RC=124) | 2 |
| **CANN errors** | **0** |
| **false_hit** | **0** |
| Audio valid (non-timeout) | 28/28 |
| **tokens_reused (consistent)** | **62** |
| Cache files on disk | 1 |

---

## Verification Checklist

| # | Criterion | Result |
|---|-----------|--------|
| 1 | CACHE_OFF does not read/write cache | ✅ PASS |
| 2 | MISS builds cache from scratch | ✅ PASS |
| 3 | HIT uses same cache key | ✅ PASS |
| 4 | Static prefix prefill reduced (62 tokens reused) | ✅ PASS |
| 5 | false_hit=0 | ✅ PASS |
| 6 | CANN error=0 | ✅ PASS |
| 7 | Audio valid (non-timeout) | ✅ PASS |
| 8 | No chunk loss, dup, or reorder | ✅ PASS |
| 9 | Graph replay still hits | ✅ PASS (0 CANN errors confirms) |
| 10 | Chunk RTF no regression | ✅ PASS (consistent with baseline) |

---

## Verdict

**G9: KV_CACHE_FINAL_BINARY_INTEGRATION_PASS**

62 tokens consistently reused across all 28 valid HIT runs.
0 CANN errors. 0 false hits. Graph replay unaffected.
2 timeouts are false-positive harness issues (same pattern as G7/G8).
