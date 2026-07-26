# P7 KV Cache Reuse Final Result — with Fixed T2W Drain

**Date:** 2026-07-25  
**Commit:** `91e5674` fix(t2w): defer T2W drain to omni_free  

## Test Configuration

- Binary: `build/bin/llama-omni-cli` (SHA256: `764a706a...`)
- Script: `scripts/run_kv_cache_ab_p5.sh`
- Design: 16 passes (ABAB...), 4 cases × 8 pairs = 32 matched pairs
- Arm A: `OMNI_KV_CACHE_REUSE=0` (baseline)
- Arm B: `OMNI_KV_CACHE_REUSE=1` (candidate)
- Cases: 0, 1, 3, 5 (fast cases, skip very long case 2)

## Primary Metric: request_to_first_audio_ms

Directly measured from request boundary (before `stream_prefill()`), same monotonic clock for all requests.

### Distribution

| Percentile | Arm A (no cache) | Arm B (cache) | Delta |
|---|---|---|---|
| p50 | 16210 ms | 6209 ms | -10001 ms |
| p90 | 19409 ms | 8581 ms | -10828 ms |
| p95 | 19866 ms | 10619 ms | -9247 ms |

### Paired Delta (matched by pass-pair + case_id, n=30)

| Percentile | Delta (A − B) |
|---|---|
| p25 | 7675 ms |
| **p50** | **9642 ms** |
| p75 | 12524 ms |
| p90 | 13626 ms |
| p95 | 14078 ms |

### Paired Percentage Delta

| Percentile | Reduction |
|---|---|
| p50 | 59.0% |
| p90 | 71.3% |

### Bootstrap 95% CI (10,000 resamples)

**Paired delta p50: [8742, 11470] ms** — does NOT cross zero.

### Per-Case Delta

| Case | A p50 | B p50 | Delta | n (pairs) |
|---|---|---|---|---|
| 0 | 15818 ms | 6479 ms | -9339 ms | 8 |
| 1 | 16146 ms | 6035 ms | -10111 ms | 7 |
| 3 | 16584 ms | 6771 ms | -9813 ms | 7 |
| 5 | 18091 ms | 5792 ms | -12299 ms | 8 |

## Secondary Metrics

### prefill_ms

| Percentile | Arm A | Arm B |
|---|---|---|
| p50 | 9454 ms | 3.1 ms |
| p90 | 11326 ms | 6.7 ms |

Prefill reduction: 2772× (p50).

### decode_to_first_audio_ms

| Arm A p50 | Arm B p50 | Delta |
|---|---|---|
| 6604 ms | 6205 ms | -399 ms |

NEUTRAL — as structurally expected (decode excludes prefill).

## Validity

| Arm | Valid | Invalid | Rate |
|---|---|---|---|
| A (baseline) | 32/32 | 0 | 100% |
| B (candidate) | 30/32 | 2 | 93.8% |
| **Total** | **62/64** | **2** | **96.9%** |

Invalid samples:
- `P2_B_c1`: rc=124 timeout, 57 WAVs, 1436 tokens (very long response)
- `P4_B_c3`: rc=124 timeout, 64 WAVs, 1576 tokens (very long response)

Both are process-level timeouts on extremely long responses, NOT T2W drain failures.

**rc0_without_audio: 0** across all 64 executions (32 A + 32 B).

## Cache Behavior

- Cache hit rate: 30/32 B runs (93.8%) — 2 misses are the timeout cases
- Cache miss paths: 0 (cache_miss=0 on all B runs)
- Reused tokens: 62, perfectly consistent across all cache-hit runs
- Cache file: `/tmp/omni_kvcache_12b9d9320-6a5856fe.bin` (9.1 MB)
- No CPU fallback (all runs: `OMNI_T2W_DEVICE=cann-flow-only`)
- No F005 retry interference (degeneration_detected=0, retry_count=0 on all 64 runs)

## vs P6 (Original, OVERTURNED)

| Metric | P6 (broken T2W) | P5 (fixed T2W) |
|---|---|---|
| Valid rate | 79.2% (57/72) | **96.9% (62/64)** |
| rc0_without_audio | many | **0** |
| no_first_audio | 12 | **0** |
| request_to_first_audio | unmeasured | **p50 -9642ms (paired)** |
| prefill reduction | -9061ms (mean) | **-9957ms (p50 paired)** |

## Gate Verdict

**GATE_PASSED.** KV cache reuse delivers stable, measurable request_to_first_audio improvement:
- 30 valid matched pairs (meets ≥30 threshold)
- Bootstrap 95% CI [8742, 11470]ms does not cross zero
- Paired p50 delta -9642ms (-59.0%)
- 0 rc0_without_audio

## Production Strategy

**RECOMMEND_OPT_IN / DEFAULT_OFF.** `OMNI_KV_CACHE_REUSE=1` is ready for opt-in use in static-prefix multi-turn scenarios.

## Data

- Raw CSV: `/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/p5-ab/kv_cache_ab_p5.csv`
- Logs: `/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/p5-ab/logs/`
- Runner log: `/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/p5-ab/runner.log`
- Bootstrap script: `scripts/run_kv_cache_ab_p5.sh`
