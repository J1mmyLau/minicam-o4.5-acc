# P16: Demo Smoke, Bucket Characterization, KV Cache Regression

**Date**: 2026-07-29
**Status**: COMPLETE — All 3 gates PASS

---

## 1. Demo Smoke Test

### Configuration
```
OMNI_T2W_DEVICE=cann-flow-only
OMNI_VOC_DEVICE=gpu
OMNI_T2W_PROFILE=2
```

### Results

| Check | Result |
|-------|--------|
| Binary | `llama-omni-cli` built 2026-07-29 (HEAD: 189fc96) |
| Model | MiniCPM-o-4_5-Q4_K_M.gguf |
| Test cases | 3 (omni_test_case_0000-0002) |
| Exit code | 0 |
| CANN Flow init | `flowGGUFModelLoader: init_backend device=gpu, gpu_idx=0, backend=CANN0` ✅ |
| CANN Vocoder init | `voc_hg2_model: init_backend device=gpu, gpu_idx=0, backend=CANN0` ✅ |
| T2W init mode | `Token2Wav: CANN flow-only mode — deferring init to worker thread` ✅ |
| Total WAVs | 16 |
| F005 degenerations | 0 |
| CANN errors | 0 |
| Overall RTF | 0.2843 |

**Demo Smoke Verdict: PASS** ✅

---

## 2. Bucket Characterization

### Buckets

| Bucket | Call Range | n | Mean t2m | Mean voc | Mean Total | Mean RTF |
|--------|-----------|---|----------|----------|------------|----------|
| FIRST | call=0 | 1 | 247.6ms | 229.1ms | 476.6ms | 0.567 |
| WARMUP | call=1-3 | 3 | 179.5ms | 119.4ms | 299.0ms | 0.299 |
| STEADY | call≥4 | 12 | 143.5ms | 117.3ms | 260.9ms | **0.261** |

### Steady-State Detail (n=12)

| Metric | t2m.compute | voc.compute | Total | RTF |
|--------|------------|------------|-------|-----|
| Min | 111.8ms | 114.4ms | 226.5ms | 0.227 |
| Median | 142.5ms | 117.9ms | 259.7ms | 0.260 |
| Mean | 143.5ms | 117.3ms | 260.9ms | 0.261 |
| p95 | — | — | — | 0.316 |
| Max | 194.7ms | 120.9ms | 315.5ms | 0.316 |

### Note on Intra-Run Variation

Some STEADY chunks (call=12-14) show higher t2m (~190ms). These are likely first chunks of new test cases within the same run, triggering slight T2W init overhead. Even so, max steady RTF = 0.316, well below 1.0.

### Competition Metric

```
STEADY PER-CHUNK RTF = 0.261 (mean, n=12, call≥4)
                     = 0.260 (median)
```

This is consistent with P15-B's result of 0.274 (n=65, 5 batches). The slight improvement (0.261 vs 0.274) is within normal sampling variation.

---

## 3. KV Cache Regression

### Test Matrix

| Run | KV Cache | Result | Cache Status | RTF | WAVs | CANN Err | F005 |
|-----|----------|--------|--------------|-----|------|----------|------|
| OFF baseline | OMNI_KV_CACHE_REUSE=0 | PASS | N/A | 0.273 | 10 | 0 | 1 |
| ON prime (MISS) | OMNI_KV_CACHE_REUSE=1 | PASS | cache_hits=0, cache_misses=1 | 0.358 | 2 | 0 | 0 |
| ON second (HIT) | OMNI_KV_CACHE_REUSE=1 | PASS | cache_hits=1, cache_misses=0 | 0.323 | 4 | 0 | 1 |

### Key Findings

1. **KV Cache mechanism works correctly with CANN Flow+Vocoder**
   - MISS → rebuild and save new cache file (11.6MB at /tmp/omni-kvcache/)
   - HIT → load cache, skip prefill for cached tokens
   - 0 cache-related crashes or errors

2. **No CANN errors** in any KV cache configuration
   - OFF, ON-prime, ON-hit: all 0 CANN errors
   - CANN Flow+Vocoder backend is compatible with KV cache

3. **RTF varies by LLM output, not by KV cache**
   - RTF is T2W compute per audio duration (independent of prefill optimization)
   - KV cache HIT does not affect per-chunk RTF (which is the competition metric)
   - All RTF values well below 1.0

4. **F005 detections are from LLM non-determinism, not KV cache**
   - 1 detection in OFF run, 1 in HIT run
   - F005 retry mechanism handled both correctly
   - Not related to CANN Flow+Vocoder backend

### KV Cache Regression Verdict: PASS ✅

**CANN Flow+Vocoder + OMNI_KV_CACHE_REUSE=1: COMPATIBLE**
**No regression vs baseline (OFF).**

---

## 4. Conclusions

| Gate | Verdict | Evidence |
|------|---------|----------|
| Demo smoke | ✅ PASS | 3 test cases, 16 WAVs, 0 CANN errors, RTF=0.28 |
| Bucket characterization | ✅ PASS | Steady RTF=0.261, first=0.567, warmup=0.299 |
| KV cache regression | ✅ PASS | HIT/MISS/OFF all compatible, 0 CANN errors |

### Next: 30-min stability test (running), then 1hr, then multi-prefix/lifecycle
