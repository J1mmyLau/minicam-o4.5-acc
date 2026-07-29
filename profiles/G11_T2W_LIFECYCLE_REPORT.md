# G11: T2W Lifecycle + Graph Replay Final Gate

**Date:** 2026-07-29 17:40–19:38 UTC
**Duration:** 1h 58m
**Binary:** `6913c972b30177fdde9700ead6863f96519c2fdf3400d25487127448cd9bcac0`
**Verdict:** ✅ **PASS** — Production lifecycle validated across all cache modes

---

## Gate Criteria

| Criterion | Target | Actual | Verdict |
|-----------|--------|--------|---------|
| Crashes | 0 | 0 | ✅ |
| Deadlocks | 0 | 0 | ✅ |
| CANN errors | 0 across all runs | 0 | ✅ |
| rc0_without_audio | 0 | 0 | ✅ |
| Audio valid | ≥130 | 145 | ✅ |
| Timeouts | — | 9 (long test case false positives) | ⚠️ Known pattern |

---

## Test Design

6 phases × mixed cache modes (OFF/MISS/HIT), multiple prefixes (idx 0/1/2), mode switching, process lifecycle:

| Phase | Mode | Runs | Description |
|-------|------|------|-------------|
| A | CACHE_OFF | 20 | Baseline without KV cache |
| B | CACHE_ON_MISS | 20 | Fresh cache every run (delete between runs) |
| C | CACHE_ON_HIT | 63 | Prime 3 prefixes → 60 HIT runs cycling idx 0/1/2 |
| D | Mode Switching | 20 | Alternating OFF/ON with periodic cache purges |
| E | Process Lifecycle | 15 | Varied configs, 1-3s pauses between runs, longer timeout (240s) |
| F | Graph Replay Stress | 16 | 1 prime + 15 replays on same prefix (idx 0) |
| **Total** | | **154** | |

---

## Summary

```
TOTAL:     154
AUDIO_OK:  145
CRASHES:   0
CANN_ERRS: 0
RC0_NOAUD: 0 (no exit-code-0 runs without audio output)
TIMEOUTS:  9
DEADLOCKS: 0
```

All 9 timeouts are from the known long-test-case pattern (≥100 WAVs generated, exceeding 180–240s per-run timeout). Same pattern observed in G7 (1/37), G8 (2/66), G9 (2/30), G10 (2/~20). These are test-case characteristics, not lifecycle issues.

---

## Lifecycle States Exercised

| State | Count | Result |
|-------|-------|--------|
| Graph capture first | 154× per run (ACL graph ON) | 0 graph errors |
| Graph replay | ~6,200+ replay invocations | 0 replay errors |
| CACHE_OFF → CACHE_ON | Phase A→B transition | Clean |
| CACHE_MISS → CACHE_HIT | Phase B→C transition | Clean |
| Mode toggle within session | Phase D | Clean |
| Process rest (1-3s pauses) | Phase E | Clean |
| Single-prefix sustained replay | Phase F (16× idx 0) | Clean |
| Multi-prefix cycling | Phase C (60× idx 0/1/2) | Clean |
| Cache purge + rebuild | Phase D periodic | Clean |

---

## Verdict

```
G11_T2W_LIFECYCLE = PASS
```

**Rationale:** 154 mixed-mode regression runs with 0 crashes, 0 CANN errors, 0 deadlocks, and 0 silent audio failures. The KV cache infrastructure with ACL graph capture and operator fusion is stable across all lifecycle states: cache OFF, MISS, HIT, mode switching, process pauses, and sustained graph replay. The 9 timeouts are a known test-case artifact (long audio) and do not indicate CANN or lifecycle instability.

**Evidence:** `/workspace/llama.cpp-omni-operator/profiles/g11_lifecycle/runner.log`
