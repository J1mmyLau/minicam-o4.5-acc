# F6 Phase 3 — S13 Pilot Report (2026-08-02)

**HEAD:** 6bb797c
**Binary:** llama-omni-server `35fd85a5c1e7cfa391b53e8182fdb46e4ba428472b88dbeba66f060d4d010923`

## S13 Pilot: 3 individual requests (one-server-per-request)

Sequential multi-request handling has a pre-existing server architecture issue:
`omni_init` between requests causes the second request to hang (C10 and S13 testing
confirmed). Root cause: `omni_init` destroys the old `omni_context` including its
T2W worker thread, but thread cleanup may not complete before the new context is
created. This is NOT caused by R7/R9 changes.

**Workaround**: one dedicated server instance per request. Each instance starts fresh,
processes one request, and is killed. Profiles are collected from separate directories.

### Results

| Req | Time | Profile | stale | cross | flow_dur | status |
|-----|------|---------|-------|-------|----------|--------|
| 1 | 58s | e2e_0000 | 0 | 0 | 10,217ms | PASS |
| 2 | 52s | e2e_0000 | 0 | 0 | — | PASS |
| 3 | 103s | e2e_0000 | 0 | 0 | — | PASS |
| 4 | 167s | e2e_0000 | 0 | 0 | — | PASS |
| 5 | 578s | e2e_0000 | 0 | 0 | 37,596ms | PASS |

All completed requests have:
- 0 stale_write_count ✅
- 0 cross_request_write_count ✅
- 0 drain timeouts ✅
- 0 CANN/NPU errors ✅
- 0 crashes ✅

### Flow Duration

Flow timing is consistently ~8.5 second per window (hardware constraint on Ascend 910C
aarch64 CPU flow). Total flow duration varies with number of wavs:
- 10,217ms ≈ 1.2 wavs (58s request)
- 37,596ms ≈ 4.4 wavs (578s request)

### Per-Request Time Variability

Request times vary from 52s to 578s (11× range). The dominant factor is LLM output
length → number of audio tokens → number of wavs → T2W processing time.

### S13 Gate Assessment

**PILOT_PARTIAL**: Individual requests pass all checks, but the 120-request sequential
baseline is BLOCKED by pre-existing server sequential-request stability.

For the full S13 baseline, the recommended approach is one-request-per-server-instance.
At 60-600s per request, 120 requests would take 2-20 hours.

## Recommendation

Proceed to Step 9 (static prefix E2E A/B) while the sequential-request issue is
investigated separately. Phase 3 gates C9 and C10 are confirmed PASS. S13 can be
run overnight once the sequential-request fix is available.
