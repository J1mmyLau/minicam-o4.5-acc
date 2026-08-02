# F6 Phase 3 — S13 Resume Contract & Midpoint Gates (R11+R12)

**Date:** 2026-08-02
**Prepared for:** S13 re-run after R7 cross-request contamination fix

## R11: S13 Resume Contract

### Preconditions (all must be satisfied before S13 re-run)

| # | Condition | Status |
|---|-----------|--------|
| P1 | R7 cross-request contamination fix verified | ✅ C9 30/30: 0 stale, 0 cross, sync/audio matched |
| P2 | Drain-before-dump in stream_decode | ✅ All sync profiles have complete flow data |
| P3 | Default drain timeout ≥ 120s | ✅ Hardcoded default 120000ms |
| P4 | Release-store mirror writes (aarch64 ordering) | ✅ memory_order_release |
| P5 | Server managed by exact PID file | ✅ server.pid |
| P6 | ctx-size ≥ 4096 for 120-request endurance | Required (S13v1 used 4096) |
| P7 | Robust WebSocket client with connection retry | Required (S13v1 failed at req 64 due to timeout) |
| P8 | E2E profiling enabled (OMNI_E2E_PROFILE=1) | Required |
| P9 | Binary provenance recorded (SHA256) | Required |
| P10 | No other NPU processes running | Required (ABBA sequential) |

### Recovery Procedure (if S13 is interrupted)

1. **Do NOT kill server** unless it's crashed. Check `server.pid`.
2. Record: last completed request index, partial profile count, server log tail.
3. Save partial results to `s13_checkpoint_N/` directory.
4. Diagnose root cause before restarting.
5. If server stable but client failed: restart client from `request_index = last_completed + 1`.
6. If server crashed: full restart from request 0 with new PID file.

### Success Criteria

- 120/120 requests completed
- 0 crashes, 0 CANN errors
- 120 sync profiles, all with valid stage data
- Sync/audio profiles matched for TTS requests
- flow_start present in all profiles where flow is used
- Aggregate latency report generated

## R12: S13 Midpoint Gates

Each gate is a checkpoint. Partial results are saved at each gate. If the test fails after gate M_k, resume from M_k's checkpoint.

| Gate | Checkpoint | Success Criteria | Evidence |
|------|-----------|-----------------|----------|
| **M0** | Server started | Model loaded, PID recorded, port listening | server.log, server.pid |
| **M1** | 20 requests | 0 crashes, 0 CANN errors, 20 profiles | `s13_checkpoint_020/` |
| **M2** | 40 requests | 0 crashes, 0 CANN errors, 40 profiles | `s13_checkpoint_040/` |
| **M3** | 60 requests | Same as above (S13v1 reached here) | `s13_checkpoint_060/` |
| **M4** | 80 requests | 0 crashes, 0 CANN errors, 80 profiles | `s13_checkpoint_080/` |
| **M5** | 100 requests | 0 crashes, 0 CANN errors, 100 profiles | `s13_checkpoint_100/` |
| **M6** | 120 requests | **FINAL**: 0 crashes, 0 CANN, 120 profiles, report generated | `s13_checkpoint_120/` + report |

### Gate Check at Each Midpoint

At each gate, verify:
1. `request_count >= gate_target` — correct count
2. `crashes == 0` — no server crashes
3. `cann_errors == 0` — no CANN errors
4. `profile_count >= gate_target` — profiles written
5. `grep -c "E2E Stage Profiler: ENABLED" server.log` — profiling active
6. `grep -c "DRAIN_TIMEOUT" server.log == 0` — no drain timeouts
7. `grep -c "CANN error\|NPU error\|acl error" server.log == 0` — no hardware errors

### Resume from Checkpoint

If test fails at request N (M_k < N < M_{k+1}):
1. Save profiles 0..N-1 to `s13_checkpoint_<N>/`
2. Analyze failure: server crash, client timeout, or protocol error?
3. If server stable: restart server, resume client from request N
4. If server crashed: restart server from request 0 (new session)
5. Append results to checkpoint log

### Test Script Requirements

The S13 re-run script must:
- Accept `--start-index N` to resume from request N
- Save partial results every 20 requests (JSON checkpoint)
- Use WebSocket timeout ≥ 180s (not 60s as in S13v1)
- Implement connection retry (3 attempts, 5s delay)
- Log each request with index, latency, status
- Write `s13_status.json` with current progress after each request
