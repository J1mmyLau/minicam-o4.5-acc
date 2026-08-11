# F6 Phase 3 — Corrected Gate Matrix After S13 Failure

**Date:** 2026-08-02
**HEAD:** `aabd12e` (via `6320bd3`)
**Trigger:** S13 exit code 1, Flow 9547ms anomaly, incomplete C9/C10/S13 gates

---

## Corrected Gate Status

| Gate | Status | Evidence | Previous (Incorrect) |
|------|--------|----------|----------------------|
| N2 | PASS | Enum comment Q1→Q2 fixed; 21≡21 proof | PASS |
| N3 | PASS | Q0/Q1/Q2 semantics confirmed | PASS |
| N4 | PASS | 4 global ptrs removed; C8ProfileScope RAII | PASS |
| N5 | PASS | thread_local context; exception/nesting-safe | PASS |
| N6 | CLOSED | Generation guard + finalize + 3 rejection counters | CLOSED |
| N7 | PASS | Binary provenance recorded | PASS |
| **N8** | **PASS_7_OF_7** | Server async smoke: 7/7 requests (5 text-only + KV MISS + TTS) | CLOSED (overstated) |
| **N9** | **PENDING_COUNTER_RECONCILIATION** | 183 write_after_finalize detected; must verify accepted=0, partial=0, no critical-stage rejection | CLOSED (overstated) |
| **S9** | **PROVISIONAL_17_OF_18** | CLI vs Server: 17/18 stages identical; 18th stage NOT identified | PASS (overstated) |
| **C9** | **PARTIAL_25_OF_30** | 25/30 completed; 5 missing requests NOT classified | PASS (overstated) |
| **C10_STATIC** | **PASS** | < 10μs hot-path, < 0.001% analytically bounded | PASS |
| **C10_RUNTIME** | **NOT_RUN** | No matched-pair Stats OFF vs ON empirical measurement | PASS (overstated) |
| **S13** | **FAILED_PARTIAL_61_OF_120** | 63/64 attempted, exit code 1, "Connection to remote host was lost" at req 64 | PASS (wrong) |
| **F6_PHASE3_COMPLETE** | **NO** | Multiple gates incomplete or unverified | — |
| **F6_PHASE3_OPTIMIZATION_READY** | **NO** | Flow timing suspect, baseline incomplete | — |

---

## Suspended Claims

The following claims from the previous report are **RETRACTED** pending re-verification:

| Claim | Status | Reason |
|-------|--------|--------|
| FLOW_TIMING (9547ms) | **SUSPECT** | ~100× expected value; cross-request attribution, multi-chunk aggregation, or CPU fallback suspected |
| VOCODER_TIMING (639ms) | **NEEDS_REVALIDATION** | Depends on Flow endpoint validity |
| PHASE3_FINE_GRAIN_LATENCY_BUDGET | **INVALID_PENDING_RECONCILIATION** | All per-stage budgets derived from suspect Flow/Vocoder timestamps |
| "113 total requests" | **UNVERIFIED** | Count does not reconcile across gates (see R13 ledger) |
| "Server stable across 113 requests" | **MISLEADING** | S13 server log ends abruptly mid-decode at request 64 |

---

## Active Rules

1. **Do NOT declare F6_PHASE3_COMPLETE** until all gates pass at their contracted thresholds
2. **Do NOT modify CHUNK_SIZE=25**
3. **Do NOT re-enable B6b** (OMNI_TTS_FIRST_CHUNK_STEP=10)
4. **Do NOT train DSpark**
5. **Do NOT write AscendC kernels**
6. **Use only PID files** for process management; never `ps | grep | xargs kill`
7. **Keep existing tags**; mark `fp16-f6-phase3-server-gates-closed-20260801` as PROVISIONAL_MISNAMED
8. **Preserve all raw data** — 61 S13 profiles, N8 profiles, N9 data, C9 data

---

## Tag Status

| Tag | Status | Notes |
|-----|--------|-------|
| `fp16-f6-phase3-instrumentation-server-pass-20260801` | PROVISIONAL_CHECKPOINT | Valid checkpoint after N8/N9 instrumentation verification |
| `fp16-f6-phase3-server-gates-closed-20260801` | **PROVISIONAL_MISNAMED** | NOT_ALL_GATES_CLOSED; tag claims gates closed but C9/C10/S13 were incomplete |

---

## Recovery Task Map

| Task | Description | Dependencies |
|------|-------------|-------------|
| R0 | ✅ Gate matrix corrected (this document) | — |
| R1 | Suspend suspect timing claims | R0 |
| R2 | Audit S13 exit code 1 root cause | R0 |
| R3 | Confirm whether manual kill caused S13 failure | R2 |
| R4 | Audit Flow=9547ms anomaly | R0 |
| R5 | Verify first-chunk stage recording semantics | R4 |
| R6 | Reconcile N9 183 late writes | R0 |
| R7 | Fix profile finalization lifecycle | R4,R6 |
| R8 | Identify S9 missing 18th stage | R0 |
| R9 | Complete C9 remaining 5 requests | R7 |
| R10 | Run real C10 matched overhead | R7 |
| R11 | S13 resume contract | R2,R3,R4 |
| R12 | S13 midpoint gates | R11 |
| R13 | Request ledger reconciliation | R0 |
| R14 | Re-decide Phase 3 status | R9,R10,R11 |
| R15 | Tag handling | R14 |
