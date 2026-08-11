# Release Status — 2026-08-06

**Binary:** 2bfb2e5028c4f0cf5b8a9e17b22c2cd071505db9e0baa9afc456c00bae84ceb4
**Server PID:** 377377 (restarted 2026-08-05 19:13:06 after thread exhaustion crash)
**Model:** MiniCPM-o-4_5-Q4_K_M.gguf
**NPU:** Ascend 910C die 0, CANN 9.1.0-beta1
**Source:** FROZEN at bdd4550 (4 lifecycle fix commits on top)
**Branch:** fix/ws-session-lifecycle

---

## Gate Summary

| Gate | Status | Evidence | Notes |
|------|--------|----------|-------|
| T3 Sequential ×10 text | **PASS** | T3-A lifecycle 10/10 | turn_based mode, correct text output |
| T6 Exception injection | **PASS** | 5/5 patterns | All injection patterns recover cleanly |
| T7A Server TTS generation | **PASS** | 3 prompt lengths (S/M/L), 17/72/72 WAVs | WAVs valid 24kHz, chunk continuity confirmed |
| T7B Client audio delivery | **PASS** | WS_INCREMENTAL_STREAMING=YES | Protocol: `response.output.delta`, `kind=audio`, field=`audio` |
| T8 Text isolation | **PASS** | 3 intervals (100ms/500ms/1000ms) | No cross-contamination between sessions |
| T8 WAV isolation | **PASS** | 3 intervals | Distinct session IDs = distinct WAV directories |
| **FUNCTIONAL_TTS_GATE** | **PASS** | T7A + T7B + T8 all PASS | Streaming audio confirmed with correct protocol |
| **TTS_ISOLATION_GATE** | **PASS** | T8 3/3 intervals | Cross-session isolation verified |

---

## Stability Status

| Gate | Status | Evidence |
|------|--------|----------|
| **LONG_RUNNING_STABILITY** | **FAIL** | Thread leak confirmed: +319 threads/session (short), +800 threads/session (medium) |
| **THREAD_EXHAUSTION** | **CONFIRMED** | Monotonic growth: 1598 → 1917 → 3524 threads after 3 sessions |
| **CRASH_MECHANISM** | **CGROUP_PID_EXHAUSTION** | cgroup pids.max=10000, ~7-18 sessions to crash |
| **PREVIOUS_CRASH** | **CONFIRMED** | 2026-08-05 19:12 — "libgomp: Thread creation failed: Resource temporarily unavailable" |

### Thread Leak Evidence

| Measurement | Threads | Δ | Cgroup PIDs |
|-------------|---------|---|-------------|
| Baseline (~7h idle) | 1,598 | — | 2,528 |
| After 1 short session | 1,917 | +319 | 2,842 |
| After 2+ more sessions | 3,524 | +1,607 | 4,453 |
| After long session cleanup | 2,555 | -969 | 3,482 |

Key observations:
- Threads grow monotonically with each session
- Some threads reclaimed after session cleanup (long session released ~969 threads)
- Net leak: ~957 threads above baseline after 4 sessions
- cgroup pids.max=10000 is the binding constraint

### DRAIN_TIMEOUT Attribution

| Phase | Sessions | DRAIN_TIMEOUT Count |
|-------|----------|---------------------|
| T3-T7-T8 (pre-crash) | ~24 | 35 |
| RTF tests (post-restart) | ~5 | 4 |
| **Total post-restart** | ~4 | 4 |

All DRAIN_TIMEOUT entries show `final_dequeued == final_completed` — drain completes correctly.
DRAIN_TIMEOUT is a symptom of thread contention from leaked threads, not a data loss issue.

---

## Official RTF Status

| Metric | Status | Value |
|--------|--------|-------|
| Official harness | **FOUND** | `/workspace/llama.cpp-omni-official-eval/competition/benchmark_client.py` |
| WebSocket adapter | **NOT_IMPLEMENTED** | Placeholder only (all methods raise NotImplementedError) |
| HTTP endpoint | **NOT_AVAILABLE** | Frozen binary is WebSocket-only (/backend), no `/v1/stream/decode` |
| Official baseline | **KNOWN** | SPEAK→WAV RTF = 1.087 (F16, single concurrency) |
| WS-based measurement | **IN_PROGRESS** | Custom WS RTF script running |
| **OFFICIAL_SPEAK_TO_WAV_RTF** | **NOT_RUN** | Requires WebSocket adapter implementation or HTTP endpoint |

---

## Release Decision

| Attribute | Value |
|-----------|-------|
| FUNCTIONAL_TTS_GATE | PASS |
| TTS_ISOLATION_GATE | PASS |
| WS_INCREMENTAL_STREAMING | YES |
| TEXT_SESSION_LIFECYCLE | PASS |
| LONG_RUNNING_STABILITY | FAIL |
| THREAD_EXHAUSTION | CONFIRMED |
| OFFICIAL_RTF | NOT_RUN |
| **FIX_BRANCH_RELEASE_CANDIDATE** | **NO** |

**Blocking issues:**
1. **THREAD_EXHAUSTION** — Thread leak means server cannot sustain >10-20 sessions without restart
2. **OFFICIAL_RTF** — Cannot measure official SPEAK→WAV RTF without WebSocket adapter

---

## Evidence Index

| Document | Path |
|----------|------|
| Evidence freeze (35 files) | `demo_runs/overnight_20260806/evidence_freeze_20260806/` |
| SHA256 manifest | `evidence_freeze_20260806/artifact_manifest.sha256` |
| Protocol verification | `evidence_freeze_20260806/protocol_verification/PROTOCOL_VERIFICATION.txt` |
| Thread exhaustion report | `demo_runs/overnight_20260806/thread_exhaustion/ROOT_CAUSE_REPORT.md` |
| DRAIN_TIMEOUT attribution | `demo_runs/overnight_20260806/thread_exhaustion/DRAIN_TIMEOUT_ATTRIBUTION.md` |
| Thread time series | `demo_runs/overnight_20260806/thread_exhaustion/thread_count_timeseries.csv` |
| T7/T8 gate report | `demo_runs/overnight_20260806/T7_T8_GATE_REPORT.md` |
| Overnight summary | `demo_runs/overnight_20260806/OVERNIGHT_SUMMARY.md` |
| Release status (this file) | `demo_runs/overnight_20260806/RELEASE_STATUS_20260806.md` |
