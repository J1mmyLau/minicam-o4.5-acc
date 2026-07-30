# F0: Gate Count Reconciliation

**Date:** 2026-07-30
**Issue:** Previous status reported "13/14 PASS + 1 BLOCKED + 1 DEFERRED" — arithmetic inconsistency (13+1+1=15 ≠ 14).

---

## Complete Gate Inventory

| gate_id | gate_name | status | evidence_file | run_count | blocking_reason |
|---------|-----------|--------|---------------|-----------|-----------------|
| G1 | Perf consistency audit | ✅ PASS | `PHASE3_PERFORMANCE_RECONCILIATION.md` | — | — |
| G2 | Graph cache audit | ✅ PASS | `GRAPH_CAPTURE_CACHE_AUDIT.md` | — | — |
| G3 | 4-quadrant A/B | ✅ PASS | `GRAPH_FUSION_FOUR_QUADRANT.md` | 4 quadrants | — |
| G4 | Chunk bucket statistics | ✅ PASS | `CHUNK_BUCKET_STATISTICS.md` | — | — |
| G5 | Official benchmark harness | ⏭️ BLOCKED | `G5_BENCHMARK_HARNESS_AUDIT.md` | 0 | External harnesses unavailable |
| G6 | Demo validation | ✅ PASS | `G6_DEMO_REPORT.md` | 9 cases | — |
| G7 | 30-min stability | ✅ PASS | `G7_30MIN_STABILITY_REPORT.md` | 37 iters, 661 WAVs | — |
| G8 | 1-hr stability | ✅ PASS | `G8_1HR_STABILITY_REPORT.md` | 66 iters, 1368 WAVs | — |
| G9 | KV cache final-binary | ✅ PASS | `G9_KV_CACHE_FINAL_BINARY_REPORT.md` | 36 runs | — |
| G10 | Multi-prefix + corruption | ✅ PASS | `G10_MULTI_PREFIX_REPORT.md` | ~24 runs | — |
| G11 | T2W lifecycle | ⚠️ PROVISIONAL | `G11_T2W_LIFECYCLE_REPORT.md` | 154 runs | Awaiting F1 non-audio classification |
| G12 | Clean reproduction | ✅ PASS | `G12_CLEAN_REPRODUCTION.md` | 1 build + verify | — |
| G13 | Submission package | ✅ DONE | `G13_SUBMISSION_PACKAGE.md` | — | — |
| G14 | Im2col decision | ⏭️ DEFERRED | — | 0 | Amdahl-limited, benefit < 3% |

---

## Corrected Count

```
Total gates:        14
Confirmed PASS:     11  (G1-G4, G6-G10, G12, G13)
Provisional PASS:    1  (G11 — pending F1 classification)
BLOCKED:             1  (G5 — external benchmark harness)
DEFERRED:            1  (G14 — Im2col)
──────────────────────
                    14
```

## Previous Error

"13/14 PASS + 1 BLOCKED + 1 DEFERRED" summed to 15 because G11 was incorrectly counted as both "PASS" and distinct from the 14-gate denominator. The correct formulation:

```
12 of 14 gates in PASS-or-DONE state (11 confirmed + 1 provisional)
 1 of 14 BLOCKED (external)
 1 of 14 DEFERRED (post-gate)
```

## Removed Language

- ❌ "13/14 PASS"
- ❌ "ALL_PRODUCTION_GATES_CLOSED" (replaced with INTERNAL_INTEGRATION_GATES_COMPLETE)
