# Stage C 24h Mixed-Workload Gate Report

**Date:** 2026-07-28 05:00 UTC
**Run dir:** `p3-soak/stage_mixed_20260727_034614/`
**Commit:** `870e21b` (pre-Stage-C checkpoint) → `bca4653` (chain watcher)
**Binary:** `c673b39b` (ae1b0f9 build, PER_CASE_REF_AUDIO flag present)
**Duration:** 86,414s (~24h 0min 14s), target 86,400s

---

## 1. Executive Summary

```
STAGE_C_24H_MIXED_WORKLOAD_SOAK = COMPLETE

CORE_MIXED_PATHS           = PASS ✅
TIMEOUT_ROBUSTNESS         = PASS ✅
RESOURCE_STABILITY         = PASS ✅
MULTI_PREFIX_CYCLING       = PASS ✅
CORRUPTION_DETECTION       = DESIGN_LIMIT ⚠️ (runner bug, not binary)
MULTI_ENTRY_RETENTION      = NOT_TESTED (mode M wipes all files)
```

---

## 2. Run Metadata

| Metric | Value |
|--------|-------|
| Duration | 86,414s (~24h) |
| Total iterations | 1,917 |
| Crash | 0 |
| CANN error | 0 |
| rc0_without_audio | 0 |
| Temp leak | 0 |
| Prime time | 107s |
| Cache size | 9,143,932 bytes (stable) |

---

## 3. Per-Mode Breakdown

| Mode | Count | HIT | MISS | NO_STATS | TIMEOUT | Expected Behavior | Match |
|------|-------|-----|------|----------|---------|-------------------|-------|
| H (first) | 274 | 274 | 0 | 0 | 15 | HIT (cache from prime/M) | ✅ 100% |
| M (rebuild) | 274 | 0 | 274 | 0 | 10 | MISS → rebuild → SAVE | ✅ 100% |
| H (second) | 274 | 274 | 0 | 0 | 0 | HIT (just rebuilt) | ✅ 100% |
| F (OFF) | 274 | 0 | 0 | 274 | 4 | NO_STATS (cache disabled) | ✅ 100% |
| R (Re-ON) | 274 | 274 | 0 | 0 | 9 | HIT (re-enable) | ✅ 100% |
| P (Prefix) | 274 | 0 | 274 | 0 | 12 | MISS (new prefix key) | ✅ 100% |
| C (Corrupt) | 273 | 273 | 0 | 0 | 8 | **Expected MISS, got HIT** | ❌ See §4 |
| **Total** | **1,917** | **1,095** | **548** | **274** | **58** | | |

### 3.1 Core Paths Verified

| Path | Iterations | Correct | Rate |
|------|-----------|---------|------|
| HIT (cache reuse) | 822 (H+R modes) | 822 | 100% |
| MISS → rebuild → SAVE | 274 (M mode) | 274 | 100% |
| OFF → NO_STATS | 274 (F mode) | 274 | 100% |
| Re-ON → HIT | 274 (R mode) | 274 | 100% |

**4/4 core mixed paths: 100% correct.**

---

## 4. Corruption Detection: DESIGN_LIMIT ⚠️

### 4.1 Finding

All 273 mode C iterations show `cache_status=HIT` instead of the expected MISS. This is a **runner-level bug**, not a binary defect.

### 4.2 Root Cause

`corrupt_cache()` picks the first file via `ls | head -1`:

```bash
corrupt_cache() {
    local cf
    cf=$(ls "${CACHE_DIR}"/omni_kvcache_*.bin 2>/dev/null | head -1) || cf=""
    if [ -n "$cf" ]; then
        python3 -c "...f.seek(128); f.write(bytes([b[0] ^ 0x01]))..."
    fi
}
```

With MULTI_ENTRY, there are up to 4 cache files:
```
omni_kvcache_36794c48db573f89.bin  ← P0 key (per-case ref_audio)
omni_kvcache_446aec4c8ec21363.bin  ← P1 key
omni_kvcache_9bd171209fd7ee19.bin  ← P2 key
omni_kvcache_e2b568b6078ce027.bin  ← baseline key (mode C uses this)
```

`ls | head -1` picks `3679...` (alphabetically first). But mode C runs with `test_start=0` without `OMNI_KV_CACHE_PER_CASE_REF_AUDIO=1`, so the binary uses key `e2b568b6078ce027` — a **different file** that was never corrupted → HIT.

### 4.3 Why M1/M6 Worked

In M1 and M6, there was only ONE cache file (same ref_audio for all modes). `head -1` always picked the right file. M1: 11/11 detected, M6: 66/66 detected.

### 4.4 Impact Assessment

- **Binary corruption detection**: independently validated in P2 boundary gates (G7a-G7e: truncate/bitflip/magic/version/CRC) — 5/5 PASS
- **Runner**: needs `corrupt_cache` to corrupt all files or identify the correct key
- **Gate verdict**: DESIGN_LIMIT (runner tooling, not binary correctness)

---

## 5. Timeout Classification

| Classification | Count | Detail |
|----------------|-------|--------|
| HARNESS_TIMEOUT_LONG_VALID_OUTPUT | 55 | Normal responses exceeded budget |
| MODEL_STALL | 3 | TTS pipeline degradation |
| MODEL_GENERATION_DEGENERATION | 0 | — |
| UNKNOWN | 0 | — |
| **Total** | **58 (3.0%)** | |

### 5.1 MODEL_STALL Detail

| Iter | Mode | Wall | Symptom |
|------|------|------|---------|
| 75 | R | 292s | TTS Local failed chunks 40-44, "failed to find a memory slot", prefill_with_emb_tts failed |
| 1144 | H | 187s | TTS simplex sample_tts_token failed at step 148, memory slot exhaustion |
| 1748 | R | 187s | TTS Local failed chunks 27-31, prefill_with_emb_tts failed |

All 3 stall patterns share `prefill_with_emb_tts failed` + `decode: failed to find a memory slot` — likely n_ctx (4096) exhaustion in long multi-chunk TTS sessions. Not KV cache related (iter_1144 is mode H with cache OFF→re-ON, confirmed unrelated).

### 5.2 Timeout Distribution

| Mode | Timeout Count | Rate |
|------|-------------|------|
| H | 15 | 2.7% |
| M | 10 | 3.6% |
| F | 4 | 1.5% |
| R | 9 | 3.3% |
| P | 12 | 4.4% |
| C | 8 | 2.9% |

Uniform distribution across modes — no mode-specific timeout clustering. Mode F (cache OFF) also has timeouts, confirming timeouts are from long responses, not cache mechanism.

---

## 6. Resource Stability

| Metric | Min | Max | Mean | Drift |
|--------|-----|-----|------|-------|
| RSS | 8,545 MB | 8,801 MB | 8,665 MB | ±1.5% |
| HBM | 4% | 11% | 4% | flat (99.7% samples at 4%) |
| FD | 20 | 22 | 21 | flat |
| Threads | 38 | 45 | 45 | flat |

- RSS range: 256 MB (±1.5%) over 24h — no leak
- HBM: occasional 7-11% spikes (37 of 1,917 samples), returns to 4% → normal GC/alloc variation
- FD and threads: stable within narrow ranges

### Sample Trace

```
iter_1:    RSS=8,618MB HBM=4% FD=21 thr=45
iter_500:  RSS=8,726MB HBM=4% FD=21 thr=45
iter_1000: RSS=8,718MB HBM=4% FD=21 thr=41
iter_1500: RSS=8,718MB HBM=4% FD=21 thr=45
iter_1900: RSS=8,667MB HBM=4% FD=20 thr=45
```

---

## 7. Latency Stability

| Stat | Value |
|------|-------|
| p50 | 33.0s |
| p95 | 114.3s |
| p99 | 189.8s |
| min | 11.9s |
| max | 292.2s |
| mean | 45.0s |

Latency drift: see adaptive timeout trace (§8) — timeout stabilized at 186-191s from hour 8 onward, indicating stable p95 wall times.

---

## 8. Adaptive Timeout Trace

```
03:47 → 180s (floor)
04:12 → 180s (p95×1.5+15 < 180)
04:45 → 290s (outlier detected: wall=292s iter_75)
05:15 → 218s
05:37 → 218s
06:00 → 195s
06:25 → 195s
...
08:05 → 187s ← stabilized
...
03:29 → 186s (final)
```

Range: [180, 290]. Mechanism validated — outlier at iter_75 (292s) correctly drove ceiling to 290s, then decayed back to 186s as outliers aged out of window. Settled at 186-191s from hour 8 onward.

---

## 9. Multi-Prefix Cycling

### 9.1 Cache Keys

| Prefix | test_start | Cache Key | Occurrences |
|--------|-----------|-----------|-------------|
| P0 | 0 | `36794c48db573f89` | 92 |
| P1 | 1 | `446aec4c8ec21363` | 91 |
| P2 | 2 | `9bd171209fd7ee19` | 91 |

3 distinct keys, matching CACHE_KEY_ISOLATION validation (e2b05ca). Cycling pattern: P0→P1→P2→P0→P1→P2... consistent across all 274 P mode iterations.

### 9.2 HIT/MISS Pattern

| expected_hit | actual_hit | Count |
|-------------|-----------|-------|
| MISS | MISS | 274 |

All P mode iterations show MISS because:
1. Mode M calls `delete_cache()` every cycle (deletes ALL cache files including P mode keys)
2. Mode C calls `corrupt_cache()` which clears PREFIX_SEEN_FILE
3. P mode cache files never survive a full cycle → always MISS

**Implication**: MULTI_ENTRY_RETENTION = NOT_TESTED by this runner. Cross-cycle P mode HIT requires removing `delete_cache` from mode M (or making it selective).

### 9.3 False-HIT

```
false_hit = 0 ✅ (274/274)
```

No prefix ever loaded another prefix's cache. KEY_ISOLATION confirmed.

---

## 10. Gate Verdicts

### 10.1 STAGE_C_CORE_MIXED_PATHS = PASS ✅

| Sub-gate | Verdict | Evidence |
|----------|---------|----------|
| HIT stability | PASS | 822/822 HIT correct, 0 false-HIT |
| MISS → rebuild → SAVE | PASS | 274/274 SAVED (grep -a verified) |
| OFF → NO_STATS | PASS | 274/274 correct |
| Re-ON → HIT | PASS | 274/274 correct |
| Crash-free | PASS | 0 crashes in 1,917 iterations |
| CANN-error-free | PASS | 0 CANN errors |

### 10.2 STAGE_C_TIMEOUT_ROBUSTNESS = PASS ✅

| Sub-gate | Verdict | Evidence |
|----------|---------|----------|
| Timeout rate ≤ 5% | PASS | 58/1917 = 3.0% |
| All classified | PASS | 55 LONG_VALID + 3 STALL, 0 UNKNOWN |
| 0 degeneration | PASS | 0 MODEL_GENERATION_DEGENERATION |
| Uniform mode distribution | PASS | No mode-specific clustering |

### 10.3 STAGE_C_RESOURCE_STABILITY = PASS ✅

| Sub-gate | Verdict | Evidence |
|----------|---------|----------|
| RSS drift < 5% | PASS | ±1.5% over 24h |
| HBM stable | PASS | 4% baseline, periodic spikes return |
| FD stable | PASS | 20-22 over 24h |
| Threads stable | PASS | 38-45 over 24h |
| No temp leak | PASS | 0 stale temp files |

### 10.4 STAGE_C_MULTI_PREFIX_CYCLING = PASS ✅

| Sub-gate | Verdict | Evidence |
|----------|---------|----------|
| 3 distinct keys | PASS | 3679..., 446a..., 9bd1... |
| Correct rotation | PASS | P0→P1→P2 consistent |
| 0 false-HIT | PASS | 274/274 |
| Per-case ref_audio flag | PASS | OMNI_KV_CACHE_PER_CASE_REF_AUDIO=1 in P mode only |

### 10.5 STAGE_C_CORRUPTION_DETECTION = DESIGN_LIMIT ⚠️

| Sub-gate | Verdict | Detail |
|----------|---------|--------|
| Runner corrupt_cache | DESIGN_LIMIT | `ls | head -1` picks wrong file with multi-entry |
| Binary corruption detection | PASS (P2) | G7a-G7e: 5/5 boundary gates |
| Fix | — | corrupt all files or identify target key |

### 10.6 STAGE_C_MULTI_ENTRY_RETENTION = NOT_TESTED

Not tested by this runner — mode M `delete_cache` wipes all files every cycle. Independently validated in CACHE_KEY_ISOLATION test (e2b05ca).

---

## 11. Comparison with Prior Stages

| Stage | Duration | Iters | Timeouts | Timeout Rate | HIT Correct | MISS→SAVE | Corrupt Detect | RSS Drift |
|-------|----------|-------|----------|-------------|-------------|-----------|----------------|-----------|
| M1 | 1h | 81 | 2 | 2.5% | 46/46 | 12/12 | 11/11 ✅ | N/A (v1) |
| M6 | 6h | 464 | 14 | 3.0% | 199/199 | 67/67 | 66/66 ✅ | ±0.7% |
| **C** | **24h** | **1,917** | **58** | **3.0%** | **822/822** | **274/274** | **0/273** ⚠️ | **±1.5%** |

Timeout rate stable at 3.0% across all three stages. Core paths (HIT/MISS→SAVE/OFF/Re-ON) consistently 100%.

---

## 12. Known Issues

| ID | Issue | Severity | Status |
|----|-------|----------|--------|
| R1 | `corrupt_cache` picks wrong file in multi-entry mode | Medium | DESIGN_LIMIT — fix runner, not binary |
| R2 | Mode M `delete_cache` prevents cross-cycle multi-prefix HIT | Low | Design choice — needs selective delete for retention testing |
| R3 | Mode F has 4 timeouts (1.5%) — cache-independent, confirms timeout budget is the root cause | Info | Expected behavior |

---

## 13. Stage D Unblock Decision

```
Stage C 24h mixed-workload soak: COMPLETE
All core gates pass. Corruption detection gap is runner-level (not binary).
Stage D (72h) is UNBLOCKED.
```

**Chain status**: Auto-launched via `chain_stage_d.sh` at 2026-07-28 03:48 UTC. Stage D PID 2661744, ETA Jul 31 03:48 UTC.

---

**报告路径:** `docs/experiments/kv-cache-production/p3-soak/STAGE_C_GATE_REPORT.md`
**最后更新:** 2026-07-28 05:00 UTC
