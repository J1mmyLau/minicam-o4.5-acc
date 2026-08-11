# F6 Phase 3 — S13 Failure Root Cause Analysis (R2)

**Date:** 2026-08-02
**HEAD:** `aabd12e`

## Executive Summary

**S13 classification: FAILED_PARTIAL_61_OF_120**
**Failure type: SERVER_EXITED (unexplained termination during decode)**
**Client exit code: 1 (63/120 < 90% threshold)**

## Timeline

| Time | Event |
|------|-------|
| 17:53:06 | Server init started |
| 17:53:14 | LLM thread started, first prefill |
| 17:53:14–18:11:24 | Requests 1–63 processed successfully |
| 18:10:48.479 | Request 62 (index 61): prefill started |
| 18:11:10.391 | Request 62: decode complete |
| 18:11:11.446 | Request 63 (index 62): prefill started |
| 18:11:23.850 | Request 63: decode complete |
| 18:11:24.919 | Request 64 (index 63): prefill started |
| 18:11:27.099 | Request 64: prefill done (n_past=2091, 2069 tokens consumed) |
| 18:11:28.077 | Request 64: decode started — **SERVER LOG ENDS HERE** |
| ~18:11 | Client: "Connection to remote host was lost" at req 64 |

## Server State at Failure

| Parameter | Value |
|-----------|-------|
| n_past (KV cache position) | 2091 |
| n_ctx (context size) | 4096 |
| Remaining context | ~2005 tokens |
| Request index | 64 (0-indexed) |
| Profile files written | 63 (e2e_0000.json through e2e_0062.json) |
| No profile for request 64 | Request did not complete |

## Evidence Inventory

| Evidence | Result |
|----------|--------|
| Server log tail | Ends at 18:11:28.077 mid-decode, no error message |
| Server log grep for ERROR/crash/SIG | **No matches** — clean log |
| Core dumps | **None found** in /tmp, workspace, or /var/crash |
| dmesg OOM/SIG entries | **None** |
| Client stdout | 63/64 passed, "Connection to remote host was lost." at req 64 |
| Client stderr | No additional errors |
| Last complete profile | e2e_0062.json (request index 62 = 63rd request) |
| First incomplete | Request 64 (index 63) — no profile generated |

## Root Cause Classification

| Classification | Evidence | Likelihood |
|---------------|----------|------------|
| SERVER_EXITED | Log ends abruptly, no error, client lost connection | **HIGH** |
| RESOURCE_EXHAUSTION | KV=2091/4096, no OOM in dmesg | LOW |
| CANN_ERROR | No CANN error in log | LOW |
| MANUAL_TERMINATION | Server was being monitored by PID; possible cleanup race | **MEDIUM** (see R3) |
| SERVER_CRASH | No core dump, no SIG marker in log | LOW-MEDIUM |
| REQUEST_TIMEOUT | Client timeout was 30s; decode should complete in ~20s | LOW |
| CPU_FALLBACK | Not applicable (text-only request) | N/A |

## Request 64 Specifics

- Prompt: "苹果和橙子哪个更甜？" (index 63 in PROMPTS array)
- Prefill completed normally in 2.2s (18:11:24.919 → 18:11:27.099)
- KV: 2069 tokens consumed, 2027 remaining
- Decode started at 18:11:28.077, was expected to complete in ~20s
- Server process terminated before decode completion

## Key Finding: 63 Profiles, Not 61

The original report claimed "61/120" but:
- `s13_results.json`: n_total=64, n_passed=63
- Profiles on disk: 63 (e2e_0000.json through e2e_0062.json)
- Server log shows 63 completed rounds + request 64 started

**Corrected count: 63 valid requests, request 64 failed.**

The discrepancy comes from the runner output which printed progress at indices 1, 11, 21, 31, 41, 51, **61** (every 10th), then the error at 64. The "61" in the original report was a misreading of the last progress print, not the total count.

## Server Log Sanity Check

All 63 completed requests show clean lifecycle:
- `stream_prefill` → `prefill done` → `LLM decode` → `detected end token` → `轮次 N 结束`
- No errors, warnings, or anomalies in any completed request
- KV cache grew monotonically: 53 → 351 → 709 → 1007 → 1365 → 1663 → 2021
- Context remaining at request 63: 2015 tokens (safe)

## Next Steps

1. **R3**: Determine if manual kill caused server exit during request 64
2. **R11**: Resume S13 from request 64 after root cause fixed
3. If server crash: diagnose via core dump, address sanitizer, or reduced test case
4. If manual kill: fix cleanup contract, re-run with strict PID management
