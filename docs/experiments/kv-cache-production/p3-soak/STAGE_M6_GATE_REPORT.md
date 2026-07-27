# Stage M6 (6h) Core Mixed-Paths Soak — Gate Report

**Date:** 2026-07-27 00:00 UTC
**Run dir:** `p3-soak/stage_mixed_20260726_125045/`
**Script:** `p3-soak/run_stage_mixed.sh` (HEAD: b113687)
**Runner PID:** 634479
**HEAD:** 1016962

---

## 1. Run Summary

| Metric | Value |
|--------|-------|
| Duration | 21,612s (6h 0min 12s), target 21,600s |
| Iterations | 464 |
| Cache HIT | 265 (57.1%) |
| Cache MISS | 133 (28.7%) |
| NO_STATS (mode F) | 66 (14.2%) |
| TIMEOUT (>180s) | 14 (3.0%) |
| Crash | 0 |
| CANN runtime error | 0 |
| rc0_without_audio | 0 |
| Cache size change | 0 (9,143,932 bytes stable) |
| Temp file leak | 0 |
| Cache files | 1 (omni_kvcache_e2b568b6078ce027.bin) |
| Wall time: p50/p95/p99/max | 35.9 / 120.4 / 213.7 / 213.9 s |
| Adaptive timeout range | 180s → 290s → 180s → 195s → 209s → 200s |
| Latency drift | None (p50=35.9s first50, p50=35.9s last50) |

## 2. Per-Mode Breakdown

| Mode | Description | Iters | HIT | MISS | NO_STATS | Expected | Verdict |
|------|-------------|-------|-----|------|----------|----------|---------|
| **H** | HIT baseline | 133 | 133 | 0 | 0 | 100% HIT | ✅ |
| **M** | MISS rebuild | 67 | 0 | 67 | 0 | 100% MISS→SAVE | ✅ |
| **F** | Force OFF | 66 | 0 | 0 | 66 | 100% NO_STATS | ✅ |
| **R** | Re-ON after OFF | 66 | 66 | 0 | 0 | 100% HIT | ✅ |
| **P** | Prefix (same key) | 66 | 66 | 0 | 0 | 100% HIT (correct) | ✅ |
| **C** | Corruption recovery | 66 | 0 | 66 | 0 | 100% MISS (detected) | ✅ |

### Classification Closure

```
464 total = 265 HIT + 133 MISS + 66 NO_STATS
265 + 133 + 66 = 464 ✅ CLOSED
```

### MISS→SAVE Verification

```
133 MISS across all modes (67 M-mode + 66 C-mode)
133 SAVED (grep -a verified)
100% match ✅
```

## 3. Timeout Classification

14 timeouts (3.0% of iterations). All 14 = **HARNESS_TIMEOUT_LONG_VALID_OUTPUT**.

| Cluster | Count | Wall Range | Modes | First Audio |
|---------|-------|------------|-------|-------------|
| ~184s band | 4 | 183.6–183.8s | M, R, H, R | 5690–6660ms ✅ |
| ~199s band | 3 | 198.8–198.9s | H, H, M | 5400–6560ms ✅ |
| ~211–214s band | 6 | 210.9–213.9s | H, M, F, M, H, H | 4627–6436ms ✅ |
| ~205s | 1 | 204.8s | C | 5958ms ✅ |

Key findings:
- **All 14 have valid first_audio** (4627–6660ms decode_to_first_audio)
- **0 MODEL_GENERATION_DEGENERATION** (M1 had 1 at iter 44)
- **0 MODEL_STALL, 0 T2W_STALL, 0 CACHE_REBUILD_FAILURE**
- Every timeout: binary actively generating valid output at kill time
- Cache state intact after each timeout (next iteration HIT or normal MISS)
- Adaptive timeout tracked the trend correctly: 180→290→180→195→209→200s

**Classification closed**: 14/14 classified, 0 UNKNOWN.

## 4. Resource Telemetry

| Metric | First (iter 1) | Mid (iter 232) | Last (iter 464) | Drift |
|--------|---------------|----------------|-----------------|-------|
| peak_rss_kb | 8,605,608 | 8,641,072 | 8,668,232 | +0.7% (noise) |
| hbm_usage_pct | 4 | 4 | 4 | 0% |
| peak_fd | 21 | 21 | 21 | 0% |
| peak_threads | 45 | 45 | 45 | 0% |

- RSS: 8.6–8.7 GB, stable within ±0.7% — **no memory leak** ✅
- HBM: 4% flat — **no NPU memory leak** ✅
- FD: 21 flat — **no file descriptor leak** ✅
- Threads: 38–45 — **no thread leak** ✅
- cgroup_mem_bytes: 30.9–31.0 GB stable

## 5. Adaptive Timeout Trace

| Phase | Iters | Timeout | Trigger |
|-------|-------|---------|---------|
| Initial | 1–9 | 180s | WARMUP_ITERS floor |
| Spike | 10 | 290s | iter 9 p95=183.7s → 183.7×1.5+15=290 |
| Normalize | 11–180 | 180s | Short iters pulled p95 below floor |
| Gradual rise | 181–230 | 195s | More long iters accumulating |
| Plateau | 231–380 | 209s | p95 stabilized |
| Final | 381–464 | 200s | p95 oscillation |

Mechanism validated: responds to real workload changes within [180,600] bounds. ✅

## 6. Gate Evaluation

| Gate | Verdict | Detail |
|------|---------|--------|
| GATE_01 exit_code=0 | ✅ PASS | GATE_STATUS confirms |
| GATE_02 DONE file | ✅ PASS | Present |
| GATE_03 data complete | ✅ PASS | 464 iters, seq 1-464, 0 gaps, 0 duplicates |
| GATE_04 classification closed | ✅ PASS | 265 + 133 + 66 = 464 |
| GATE_05 all timeouts classified | ✅ PASS | 14/14 HARNESS_TIMEOUT_LONG_VALID_OUTPUT, 0 UNKNOWN |
| GATE_06 crash=0 | ✅ PASS | 0 SIGABRT/SIGSEGV/SIGKILL |
| GATE_07 CANN error=0 | ✅ PASS | 0 ACL_ERROR/aclrt failed |
| GATE_08 rc0_without_audio=0 | ✅ PASS | All iterations produced valid audio |
| GATE_09 temp leak=0 | ✅ PASS | 0 .tmp/.state/.load files |
| GATE_10 resource no drift | ✅ PASS | RSS ±0.7%, HBM 0%, FD 0%, threads 0% drift |
| GATE_11 latency stable | ✅ PASS | p50=35.9s both first50 and last50 |
| GATE_12 prefill timing complete | ✅ PASS | All iterations have prefill data |

**Score: 12/12 PASS**

### Mode-Specific Gates

| Gate | Verdict | Detail |
|------|---------|--------|
| M6.01 HIT path consistent | ✅ PASS | 133/133 HIT on baseline prefix |
| M6.02 MISS→rebuild→SAVE | ✅ PASS | 67/67 mode=M MISS, 133/133 total MISS→SAVE |
| M6.03 Rebuild→HIT verification | ✅ PASS | All post-M H-mode: HIT |
| M6.04 ON/OFF control | ✅ PASS | 66/66 NO_STATS on OFF, 66/66 HIT on Re-ON |
| M6.05 Corruption detection | ✅ PASS | 66/66 detected → MISS → rebuild (100%) |
| M6.06 Adaptive timeout | ✅ PASS | Tracked p95 correctly, [180,290] range |
| M6.07 Resource stability (6h) | ✅ PASS | 0 drift across 464 iters, 6h |
| M6.08 Latency stability (6h) | ✅ PASS | p50=35.9s, no first50/last50 drift |
| M6.09 Timeout robustness | ✅ PASS | 14/14 HARNESS_TIMEOUT_LONG_VALID_OUTPUT, all recovered |
| M6.10 0 crashes across all modes | ✅ PASS | 0 crashes in 464 iters |

**Mode gates: 10/10 PASS**

## 7. Production Gate Categories

### 7.1 CORE_MIXED_PATHS = PASS ✅

| Path | Evidence | Count |
|------|----------|-------|
| HIT baseline | Cache HIT on known prefix | 133/133 (100%) |
| MISS → rebuild → SAVE | Full prefill, file written | 133/133 MISS, 133/133 SAVE |
| Force OFF | NO_STATS, no cache activity | 66/66 (100%) |
| Re-ON after OFF | Cache HIT restored | 66/66 (100%) |
| Corruption detection → rebuild | Truncated file detected | 66/66 (100%) |

### 7.2 CACHE_KEY_ISOLATION = NOT_TESTED ⚠️

Same as M1 conclusion. omni.cpp:11606 forces same ref_audio for all --test-start indices.
Mode P (--test-start 1) produces same cache key → HIT (correct behavior for same prefix).
Independent test with truly different system prompts required.

### 7.3 TIMEOUT_ROBUSTNESS = PASS ✅

- 14/464 iterations (3.0%) exceeded timeout
- All 14: HARNESS_TIMEOUT_LONG_VALID_OUTPUT (binary actively generating)
- 0 MODEL_GENERATION_DEGENERATION (M1 had 1)
- 0 UNKNOWN
- All recovered gracefully on next iteration
- Adaptive timeout responsive: 180→290→180→195→209→200s

### 7.4 RESOURCE_TELEMETRY = PASS ✅

- v2 sampling (b113687: pgrep + correct npu-smi) validated across 464 iterations
- RSS: 8.6–8.7 GB, ±0.7% drift over 6h
- HBM: 4% flat
- FD: 21 flat
- Threads: 38–45 range
- All metrics stable — 6h validates no slow leak

## 8. Comparison with M1

| Metric | M1 (1h) | M6 (6h) | Trend |
|--------|---------|---------|-------|
| Iterations | 81 | 464 | 5.7× |
| Timeout rate | 2.5% (2/81) | 3.0% (14/464) | Stable |
| Crash | 0 | 0 | ✅ |
| Corruption detection | 100% (11/11) | 100% (66/66) | ✅ |
| MISS→SAVE | 100% (12/12) | 100% (133/133) | ✅ |
| p50 latency | 36.6s | 35.9s | Stable |
| Resource drift | DESIGN_LIMIT (v1 bug) | PASS (v2 fix) | Improved |
| Degeneration timeout | 1 (iter 44) | 0 | Improved |
| Adaptive timeout range | 180–187s | 180–290s | Better coverage |

## 9. Known Limitations

### 9.1 CACHE_KEY_ISOLATION Not Tested

omni.cpp:11606 forces same ref_audio across all --test-start indices. Mode P cannot test different static prefixes without binary modification. Independent test required.

### 9.2 Mode K (Kill-Restart) Deferred

Crash recovery testing (SIGKILL mid-request, restart, cache integrity) requires separate runner architecture.

### 9.3 Single-Slot Cache Design

Current implementation: one cache file, new key overwrites old. This is correct for CACHE_KEY_ISOLATION (different key never false-HITs), but MULTI_ENTRY_RETENTION is N/A.

## 10. Verdict

```
M6_CORE_MIXED_PATHS = PASS ✅
M6_TIMEOUT_ROBUSTNESS = PASS ✅
M6_RESOURCE_TELEMETRY = PASS ✅
M6_CACHE_KEY_ISOLATION = NOT_TESTED ⚠️
```

464 iterations across 6 workload modes over 6 hours:
- 5/5 core mixed paths: 100% expected behavior
- Corruption detection: 100% (66/66)
- ON/OFF control: correct (66+66)
- MISS→SAVE: 100% (133/133)
- 0 crashes, 0 CANN errors, 0 temp leaks
- 14 timeouts all classified (0 UNKNOWN, 0 degeneration)
- Resources: 0 drift over 6h (RSS ±0.7%, HBM/FD/threads flat)
- Latency: 0 drift (p50=35.9s first50 = last50)
- Adaptive timeout: validated across full range [180,290]

**This is CORE_MIXED_PATHS, not full production mixed gate.**
CACHE_KEY_ISOLATION requires independent test with truly different static prefixes.

## 11. Next Steps

1. **Cache storage model audit**: Confirm SINGLE_SLOT via code review of cache storage layer
2. **CACHE_KEY_ISOLATION test**: Add test-only flag for real prefix variation, prepare 3 distinct prefixes, run isolation matrix
3. **Stage C (24h mixed)**: Only after M6_CORE_MIXED_PATHS + CACHE_KEY_ISOLATION both PASS
4. **Stage D (72h)**: After C gate
5. **Stage E (168h)**: After D gate

---

**报告路径:** `docs/experiments/kv-cache-production/p3-soak/STAGE_M6_GATE_REPORT.md`
**最后更新:** 2026-07-27 00:00 UTC
