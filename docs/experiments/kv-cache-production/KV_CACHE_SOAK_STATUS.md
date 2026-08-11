# KV Cache Soak Status

**Date:** 2026-07-26
**Last update:** 2026-07-27 03:30 UTC (Pre-Stage-C checkpoint — Stage C unblocked, all entry gates met)
**Soak started:** 2026-07-26 03:33 UTC
**Current stage:** Stage C (24h mixed) UNBLOCKED — launch after /compact.

---

## Gates Passed Before Soak

- **P1**: Production-grade cache storage (b2e45ce)
- **P2**: 8 boundary condition gates (58c1fd9) — 20/20 PASS

---

## Stage Progress

| Stage | Duration | Type | Status | Started | Completed | Verdict | Evidence |
|-------|----------|------|--------|---------|-----------|---------|----------|
| A | 1h | HIT_PATH | COMPLETE | 03:33 UTC | 04:33 UTC | PASS (hit) / NOT_CONFIRMED (mixed) | stage_a_20260726_033330/ |
| B | 6h | HIT_PATH | **COMPLETE** ✅ | 05:08 UTC (restart) | 11:10 UTC | **PASS** (13/14 gates) / NOT_CONFIRMED (mixed) | stage_b_20260726_050817/ + STAGE_B_GATE_REPORT.md |
| C (HIT) | 24h | HIT_PATH | **CANCELLED** | — | — | Replaced by M1 mixed-workload | — |
| M1 | 1h | MIXED | **COMPLETE** ✅ | 11:29 UTC | 12:30 UTC | **PASS** (CORE_MIXED_PATHS=PASS, MULTI_PREFIX=DESIGN_VERIFIED, TIMEOUT=PASS, TELEMETRY=DESIGN_LIMIT) | stage_mixed_20260726_112936/ + STAGE_M1_GATE_REPORT.md (d0999ab) |
| M6 | 6h | MIXED | **COMPLETE** ✅ | 12:50 UTC | 18:51 UTC | **PASS** (M6_CORE_MIXED_PATHS, 12/12 gates, 464 iters, 0 crash) | stage_mixed_20260726_125045/ + STAGE_M6_GATE_REPORT.md |
| PREFIX | — | ISOLATION | **COMPLETE** ✅ | 03:08 UTC | 03:15 UTC | **PASS** (7/7, MULTI_ENTRY, 3 keys, 0 false-HIT) | KV_CACHE_MULTI_PREFIX_VALIDATION.md |
| C (MIXED) | 24h | MIXED | **UNBLOCKED** | — | — | All 6 entry gates met | Launch after /compact |
| D | 72h | MIXED | PENDING | — | — | After C gate | — |
| E | 168h | MIXED | PENDING | — | — | After D gate | — |

### Stage A (1h) — Final

**Classification** (99 iterations):
- cache HIT: 94 (94.9%)
- cache MISS: 0 (0%)
- TIMEOUT (180s): 5 (5.1%)

**STAGE_A_HIT_PATH_SOAK = PASS** ✅
- 94 consecutive cache HITs, prefill p50=36.8ms, 0 crashes, 0 leaks

**STAGE_A_MIXED_WORKLOAD_GATE = NOT_CONFIRMED** ⚠️

### Stage B (6h) — COMPLETE ✅

- **Run dir**: `p3-soak/stage_b_20260726_050817/`
- **Duration**: 21,669s (6h 1min), target 21,600s
- **Iterations**: 532
- **Cache HIT**: 532 (100%), **MISS**: 0, **TIMEOUT**: 15 (2.8%)
- **Crash**: 0, **CANN error**: 0, **rc0_without_audio**: 0
- **Temp leaks**: 0, **Cache size change**: 0
- **Prefill**: p50=39.1ms, p95=40.0ms, max=43.5ms
- **Prefill drift**: +0.00% (flat)
- **All 15 timeouts**: HARNESS_TIMEOUT_LONG_VALID_OUTPUT (180s budget, not pipeline defect)

**Gate evaluation**: 13 PASS, 0 FAIL, 1 DESIGN_LIMIT (GATE_10: resource metrics not collected), 1 PENDING → now done (GATE_14)
**Full report**: `p3-soak/STAGE_B_GATE_REPORT.md`
**Audit tool**: `scripts/kv-cache-production/audit_stage_b.py`
**Commit**: f136961

**Coverage**: HIT_PATH_ONLY. MISS/rebuild/ON-OFF/prefix variation/restart/corruption NOT tested.

### Stage M1 (1h Mixed) — COMPLETE ✅ (d0999ab)

**Run dir**: `p3-soak/stage_mixed_20260726_112936/`
**Duration**: 3,641s (1h 0min 41s), 81 iterations
**Modes**: HIT (24+11+11=46), MISS (12+11=23), NO_STATS (12), Timeout (2)
**Cache**: 9,143,932 bytes stable, 0 size changes
**Crash**: 0, CANN: 0, rc0_no_audio: 0, temp leak: 0

**Gate categories**:
- CORE_MIXED_PATHS = PASS ✅ (HIT, MISS→SAVE, OFF, Re-ON, Corruption detection)
- TIMEOUT_ROBUSTNESS = PASS ✅ (2/2 classified, 0 UNKNOWN)
- MULTI_PREFIX_ISOLATION = DESIGN_VERIFIED / SINGLE_SLOT_CACHE_LIMITATION ⚠️
- RESOURCE_TELEMETRY = DESIGN_LIMIT ⚠️ (PID bug fixed in b113687, v2 runner not validated)

**Audit fixes**:
- Emoji grep bug: cache log lines contain 🔁 — use `grep -a` not bare `grep`
- MISS_REBUILD: 12/12 (not 11/12), emoji grep was root cause of false count

### Stage M6 (6h Mixed) — COMPLETE ✅ (479ecdb)

**Run dir**: `p3-soak/stage_mixed_20260726_125045/`
**Duration**: 21,612s (6h 0min 12s), 464 iterations
**Per-mode breakdown**: H(133H), M(67M all SAVED), F(66 NO_STATS), R(66H), P(66H same prefix), C(66M all corrupted)
**Crash**: 0, CANN error: 0, rc0_without_audio: 0, temp leak: 0
**Cache**: 9,143,932 bytes stable
**14 timeouts**: all HARNESS_TIMEOUT_LONG_VALID_OUTPUT, 0 degeneration

**Gates** (12/12 PASS — 10 mode gates + 2 meta gates):
- Per-mode correctness: 10/10 (HIT/MISS→SAVE/OFF/Re-ON/Corruption all 100%)
- TIMEOUT_ROBUSTNESS: PASS (14/14 classified)
- RESOURCE_TELEMETRY: PASS (v2 runner validated: 0 drift over 6h)
- CACHE_KEY_ISOLATION: NOT_TESTED (mode P used same ref_audio as other modes)

### CACHE_KEY_ISOLATION — COMPLETE ✅ (ae1b0f9, e2b05ca)

**Flag**: `OMNI_KV_CACHE_PER_CASE_REF_AUDIO=1` (default-off, test only)
**Storage model**: MULTI_ENTRY (not SINGLE_SLOT). Different keys → different files → coexist.
**7-step isolation matrix** with 3 prefixes (A/B/C = --test-start 0/1/2):
- 3 distinct keys: `3679...` ≠ `446a...` ≠ `9bd1...` ✅
- CACHE_KEY_ISOLATION: B→MISS (not false-HIT A), C→MISS (not false-HIT A/B) ✅
- MULTI_ENTRY_RETENTION: A→HIT, B→HIT, A→HIT again (all 3 files coexist) ✅

**Score: 7/7 PASS.**
Report: `p3-soak/KV_CACHE_MULTI_PREFIX_VALIDATION.md`

### Stage C Entry Conditions (ALL MET)

| # | Condition | Status |
|---|-----------|--------|
| 1 | M6_CORE_MIXED_PATHS = PASS | ✅ 479ecdb |
| 2 | CACHE_KEY_ISOLATION = PASS | ✅ ae1b0f9 |
| 3 | Storage model documented | ✅ MULTI_ENTRY |
| 4 | mode=P no longer mislabeled | ✅ Root cause identified |
| 5 | Runner supports multi-prefix | ✅ 5e2140c |
| 6 | Reports committed, git clean | ✅ |

---

## Current State Terminology

| What to write | What NOT to write |
|--------------|-------------------|
| STAGE_B_HIT_PATH_SOAK: PASS (532/532 HIT, 0 crash) | Stage B all-clear / production-ready |
| STAGE_M1: PASS (CORE_MIXED_PATHS, TIMEOUT_ROBUSTNESS) / DESIGN_VERIFIED (MULTI_PREFIX) | DEFAULT_ON |
| STAGE_M6: PASS (M6_CORE_MIXED_PATHS, 12/12 gates) | Full production mixed gate |
| CACHE_KEY_ISOLATION = PASS (7/7, 3 keys, 0 false-HIT) | All prefix scenarios covered |
| MULTI_ENTRY_RETENTION = PASS (native design) | — |
| KV_CACHE_PRODUCTION: OPT_IN_READY / DEFAULT_OFF | DEFAULT_ON |

## Production Status

```
KV_CACHE_PRODUCTION: OPT_IN_READY / DEFAULT_OFF
```

**Rationale**: P1 storage + P2 boundary gates + Stage A+B hit-path soak + M1/M6 mixed core paths + CACHE_KEY_ISOLATION all pass.
Stage C (24h mixed) pending. Minimum 72h mixed-workload soak needed before DEFAULT_ON consideration.
**Do NOT claim DEFAULT_ON.**

---

## Stage C Launch (after /compact)

```bash
cd /workspace/llama.cpp-omni-kvcache-prod
OMNI_MIXED_DURATION=86400 OMNI_MIXED_STAGE=C \
  bash docs/experiments/kv-cache-production/p3-soak/run_stage_mixed.sh
```

Runner: 7-mode mixed cycle, multi-prefix cycling in P mode (3 distinct keys), adaptive timeout [180,600], multi_prefix.csv tracking.

---

## CANNBot Phase 1

| Item | Status |
|------|--------|
| Skills discoverable | 17 |
| Core profiling skills | 6 installed |
| Agents | 6 SOTA subagents |
| CLAUDE.md | Restored regular file (NOT symlink) |
| .claude/CLAUDE.md | Plugin symlink retained |

---

## Audit Tool

```
python3 scripts/kv-cache-production/audit_stage_b.py <run_dir>
```

Read-only. No modification of runner files or binary.

---

**最后更新:** 2026-07-27 03:30 UTC (Pre-Stage-C checkpoint — Stage C unblocked, ready for /compact)
