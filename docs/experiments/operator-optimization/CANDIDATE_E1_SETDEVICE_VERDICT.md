# Candidate E1: aclrtSetDevice Caching — DEFINITIVE VERDICT

**Date:** 2026-07-28
**Binary:** `eaffbe35` (libggml-cann, V0 runtime diag counters)
**Method:** Single diagnostic run with `GGML_CANN_RUNTIME_DIAG=1`, ngl=8
**Test case:** omni_test_case_0 (SHORT, 1 WAV)

---

## 1. Verdict

```text
CANDIDATE_E1_SET_DEVICE_CACHE = REJECTED_WITH_EVIDENCE
```

## 2. Evidence

| Metric | Value |
|--------|-------|
| `ggml_cann_set_device()` requests | 9,296 |
| Actual `aclrtSetDevice()` calls | 408 |
| Redundant (guard-skipped) | 8,888 |
| **Redundancy guard hit rate** | **95.6%** |

### Root Cause: Guard Already Exists

The project already has an efficient thread-local device cache:

```cpp
// ggml-cann.cpp:74
thread_local int g_current_cann_device = -1;

void ggml_cann_set_device(const int32_t device) {
    if (device == g_current_cann_device) {  // ← catches 95.6% of calls
        return;
    }
    ACL_CHECK(aclrtSetDevice(device));
    g_current_cann_device = device;
}
```

### Where the 408 Actual Calls Come From

| Source | Count | Removable? |
|--------|-------|-----------|
| Thread first-use (thread_local init = -1) | Majority | No — legitimate per-thread init |
| Real device switch | Rare | No — multi-device setups |
| `stream()` creation in common.h:617 (bypasses guard) | Small | Code audit needed, but infrequent (lazy init) |

### Why P4 Saw 6,559 Calls

The P4 msprof trace captured ALL `aclrtSetDevice` at the ACL driver level. Our `ggml_cann_set_device` accounts for only 408 of those. The remaining ~6,150 calls come from **ACLNN/CANN library internals** — outside project code control.

## 3. Optimization Attempts Considered and Rejected

| Approach | Feasibility | Reason |
|----------|------------|--------|
| Replace thread_local with std::atomic global | REJECTED | Per-thread device affinity is correct semantics; global would break multi-threaded correctness |
| Add `ggml_cann_set_device` guard to `stream()` (common.h:617) | LOW ROI | Already lazy — only called on first stream creation per index |
| Environment variable cache | REJECTED | Duplicates existing thread_local logic |

## 4. Conclusion

**No further SetDevice optimization is warranted.** The existing `thread_local g_current_cann_device` guard already provides 95.6% redundancy elimination. The remaining 408 actual calls are legitimate (thread first-use, device switch, stream creation). The majority of runtime `aclrtSetDevice` calls originate from the CANN/ACLNN library stack and are not modifiable from project code.

## 5. Next: Candidate E2 — Stream Synchronization

Pivot to `CANDIDATE_E2_STREAM_SYNCHRONIZATION = AUDIT_REQUIRED`.

Preliminary data from the same diagnostic run:
- `aclrtSynchronizeStream`: 4,887 calls (4.3× graph evaluations)
- Source: only 2 explicit call sites in `ggml-cann.cpp`
- But internal ACLNN syncs may contribute additional calls visible only at the driver level
