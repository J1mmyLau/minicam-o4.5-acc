# DRAIN_TIMEOUT Per-Session Attribution
**Date:** 2026-08-06

## Summary

| Phase | Sessions | DRAIN_TIMEOUT Count | Notes |
|-------|----------|---------------------|-------|
| T3 lifecycle | 10 sequential | ~3 | Post-session cleanup |
| T6 exception injection | 5 patterns | ~2 | Recovery sessions |
| T7-S (short) | 1 | 2 | T2W drain for 17 chunks |
| T7-M (medium) | 1 | 2 | T2W drain for 72 chunks |
| T7-L (long) | 1 | 2 | T2W drain for 72 chunks |
| T8-A/B pairs | 3 pairs × 2 = 6 | 8 | Per-pair drain |
| RTF measurements | ~5 | 4 | Current log |
| **Pre-crash total** | ~28 | **35** | Accumulated over ~3h |

## Message Pattern

All DRAIN_TIMEOUT messages follow the same pattern:
```
T2W terminal: DRAIN_TIMEOUT — is_final dequeued but Flow+Vocoder incomplete
(gen=N, wav_count=M, errors=0, final_dequeued=N, final_completed=N)
```

Key observation: **final_dequeued == final_completed in ALL cases** — the drain actually completes; it just takes longer than the drain timeout polling interval.

## Per-Session Analysis

### T7 Sessions
- T7-S: 2 DRAIN_TIMEOUT entries (generation #1, 14 WAV chunks)
- T7-M: 2 DRAIN_TIMEOUT entries (generation #2, 14 WAV chunks)  
- T7-L: 2 DRAIN_TIMEOUT entries (generation #3, 25 WAV chunks)
- Each case: final_dequeued == final_completed → drain was successful

### T8 Isolation Pairs
- Each pair produces 2-3 DRAIN_TIMEOUT entries
- Drain always completes (final_dequeued == final_completed)

### Historical (pre-crash)
- 35 entries from ~24 sessions across T3/T6/T7/T8
- Increasing frequency in later sessions suggests thread contention slowing drain

## Root Cause Analysis

**DRAIN_TIMEOUT is a SYMPTOM, not a root cause.**

The underlying mechanism:
1. Each TTS session leaks 300-800 OpenMP threads
2. Thread count grows from ~1,500 to 3,500+ after a few sessions
3. Thread contention from leaked threads slows T2W drain processing
4. Drain polling hits the timeout interval before Flow+Vocoder completes
5. Drain still finishes (final_dequeued == final_completed) — just slower

**DRAIN_TIMEOUT severity is directly correlated with thread count:**
- Low thread count: drain completes within timeout → no DRAIN_TIMEOUT
- Medium thread count (after 5-10 sessions): drain slows → occasional DRAIN_TIMEOUT
- High thread count (after 15+ sessions): drain very slow → frequent DRAIN_TIMEOUT
- Critical (after 20+ sessions): thread creation fails → server crash

## Verdict

| Metric | Value |
|--------|-------|
| T7_DRAIN_TIMEOUT_COUNT | 6 (2 per prompt length) |
| T8_DRAIN_TIMEOUT_COUNT | 8 (2-3 per pair) |
| HISTORICAL_DRAIN_TIMEOUT_COUNT | 35 (pre-crash) |
| CURRENT_DRAIN_TIMEOUT_COUNT | 4 (post-restart) |
| DRAIN_COMPLETION_RATE | 100% (all final_dequeued == final_completed) |
| ROOT_CAUSE | Thread leak → thread contention → slow T2W drain |
| SEVERITY | MEDIUM — sessions complete correctly; messages indicate performance degradation, not data loss |
| RELATION_TO_CRASH | DRAIN_TIMEOUT is an early warning sign of thread exhaustion; frequency increases before crash |
