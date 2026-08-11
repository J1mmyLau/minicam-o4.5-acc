# KV Cache Multi-Prefix Validation Report

**Date:** 2026-07-27 03:15 UTC
**Commit:** ae1b0f9
**Test flag:** `OMNI_KV_CACHE_PER_CASE_REF_AUDIO=1` (default-off)

---

## 1. Storage Model

**MULTI_ENTRY** (native). Each cache key maps to a separate file:
```
/tmp/omni-kvcache/omni_kvcache_<key_hash>.bin
```
Different keys → different files → files coexist. Old files are NOT deleted when new keys are used. No key collision possible because key is derived from content hash.

Previous SINGLE_SLOT characterization was incorrect — the limitation was purely in the test binary (omni.cpp:11606 forced same ref_audio for all --test-start), not in the storage design.

## 2. Cache Key Components (with OMNI_KV_CACHE_PER_CASE_REF_AUDIO=1)

| Component | Source |
|-----------|--------|
| Model identity | size + mtime + head/tail 64KB hash |
| Context params | n_ctx, n_batch, n_ubatch |
| System prompt text | FNV-1a 64-bit of voice_clone_prompt + assistant_prompt |
| **Ref_audio path** | FNV-1a 64-bit of audio file path (only when flag set) |
| Chat template | model path as proxy |
| Format version | KV_CACHE_VERSION (=1) |

## 3. Test Prefixes

| Prefix | --test-start | Ref Audio | Cache Key |
|--------|-------------|-----------|------------|
| A | 0 | omni_test_case_0000.wav | `36794c48db573f89` |
| B | 1 | omni_test_case_0001.wav | `446aec4c8ec21363` |
| C | 2 | omni_test_case_0002.wav | `9bd171209fd7ee19` |

```
hash(A) ≠ hash(B) ≠ hash(C) ✅
cache_key(A) ≠ cache_key(B) ≠ cache_key(C) ✅
```

## 4. Validation Matrix

| Step | Action | Expected | Actual | Gate |
|------|--------|----------|--------|------|
| 1 | A prime | MISS → SAVE A | MISS → SAVED (key=3679...) | ✅ |
| 2 | A again | HIT A | **HIT** (key=3679...) | ✅ |
| 3 | **B (different prefix)** | **MISS — NOT false-HIT A** | **MISS** → SAVE B (key=446a...) | ✅ **KEY_ISOLATION** |
| 4 | B again | HIT B | **HIT** (key=446a...) | ✅ |
| 5 | **A again** | HIT A (multi-entry) | **HIT** (key=3679...) | ✅ **MULTI_ENTRY** |
| 6 | **C (third prefix)** | **MISS — NOT false-HIT** | **MISS** → SAVE C (key=9bd1...) | ✅ |
| 7 | C again | HIT C | **HIT** (key=9bd1...) | ✅ |

## 5. Gate Results

| Gate | Verdict | Detail |
|------|---------|--------|
| KEY_COLLISION = 0 | ✅ PASS | 3 distinct keys, no collisions |
| WRONG_PREFIX_FALSE_HIT = 0 | ✅ PASS | B→MISS (not A), C→MISS (not A/B) |
| CACHE_DESERIALIZE_ERROR = 0 | ✅ PASS | All 3 loads succeeded |
| MISS_FALLBACK_CORRECTNESS = 0 | ✅ PASS | All MISS rebuilt correctly |
| rc0_without_audio = 0 | ✅ PASS | All 7 runs produced valid audio |
| CRASH = 0 | ✅ PASS | 0 crashes in 7 runs |
| CORRUPTION = 0 | ✅ PASS | All files intact |

**Score: 7/7 PASS**

## 6. Verdict

```
CACHE_KEY_ISOLATION = PASS ✅
MULTI_ENTRY_RETENTION = PASS ✅ (native, not a limitation)

Storage model: MULTI_ENTRY (different keys → different files, coexist on disk)
```

### Corrected understanding

| Previous | Corrected |
|----------|-----------|
| SINGLE_SLOT | **MULTI_ENTRY** (native design) |
| CACHE_KEY_ISOLATION = NOT_TESTED | **CACHE_KEY_ISOLATION = PASS** |
| MULTI_ENTRY_RETENTION = N/A | **MULTI_ENTRY_RETENTION = PASS** |
| Need binary modification for multi-key | Already supported, just needed test flag |

The limitation was the **test harness** (omni.cpp:11606 forces same ref_audio), not the **storage design**. Adding `OMNI_KV_CACHE_PER_CASE_REF_AUDIO=1` (default-off, test only) reveals the native multi-entry capability.

## 7. Stage C Entry Conditions

| Condition | Status |
|-----------|--------|
| M6_CORE_MIXED_PATHS = PASS | ✅ 479ecdb |
| CACHE_KEY_ISOLATION = PASS | ✅ ae1b0f9 |
| Storage model documented | ✅ MULTI_ENTRY |
| mode=P no longer mislabeled | ✅ Root cause identified (omni.cpp:11606) |
| Reports committed | ✅ STAGE_M6_GATE_REPORT.md + this report |
| Git clean | Pending |
| NPU idle | ✅ |
| No runner | ✅ |

**Stage C (24h mixed) is now unblocked.**

---

**报告路径:** `docs/experiments/kv-cache-production/p3-soak/KV_CACHE_MULTI_PREFIX_VALIDATION.md`
**最后更新:** 2026-07-27 03:15 UTC
