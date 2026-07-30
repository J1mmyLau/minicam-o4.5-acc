# C7 V2 Failure Classification

**Date**: 2026-07-30 11:30
**Binary**: OLD (build 09:38, has fix-1: removed `!ctx_omni->async`; does NOT have fix-2: save-before-threads reorder)
**Server PID**: 1878297 (still running, still OLD binary)
**Test Script**: /tmp/c7_kv_cache_v2.py (205 lines, 2-prefix design)
**Exit Code**: 1

---

## Failure Timeline

| # | Label          | E2E (ms) | Wall (s) | Result |
|---|----------------|----------|----------|--------|
| 1 | PREFIX_A_OFF   | 625      | 6.7      | ✅ MISS→SAVE (key=21aeb5cc...) |
| 2 | PREFIX_B_OFF   | 219      | 8.0      | ✅ MISS→SAVE (key=ce45059b...) |
| 3 | PREFIX_A_HIT_1 | 76       | 7.7      | ✅ HIT (loaded key=21aeb5cc...) |
| 4 | PREFIX_A_HIT_2 | 0        | 307.7    | ❌ TimeoutError in omni_init |

## Server Log Evidence

### Request 1 (PREFIX_A_OFF): MISS → thread started → SAVED
```
11:26:44.291 KV cache MISS
11:26:44.838 create llm thread success         ← threads started BEFORE save (OLD code)
11:26:44.892 KV cache SAVED: 9291376 bytes key=21aeb5cc25b1358e
```

### Request 2 (PREFIX_B_OFF): MISS → thread started → SAVED
```
11:26:52.703 KV cache MISS
11:26:52.848 create llm thread success
11:26:52.899 KV cache SAVED: 9291376 bytes key=ce45059badc1ebb9
```

### Request 3 (PREFIX_A_HIT_1): HIT → thread NOT started → decode by accident
```
11:27:00.614 KV cache HIT: loaded 63 positions key=21aeb5cc25b1358e
                              ↑ NO "create llm thread success" after this!
11:27:00.615 wait prefill done                 ← returned immediately (prefill_done=true from req2)
```

### Request 4 (PREFIX_A_HIT_2): omni_init TIMEOUT
```
[NO SERVER LOG ENTRIES AFTER 11:27:00.648]
```

Server's last log entry is PREFIX_A_HIT_1 completing decode. No omni_init for request 4.

## Root Cause Chain

### Primary: THREAD_NOT_STARTED_ON_HIT

In the running binary (fix-1 only: `!ctx_omni->async` removed from line 11726):

```
KV cache HIT (line 11754):
  goto kv_cache_system_prompt_done;
  ↓
  Jumps to line 11925 (label)
  ↓
  Thread start is at line 11888 (BEFORE the label in OLD code)
  ↓
  Threads ARE NEVER STARTED on a HIT
```

### Secondary: prefill_done MASKING

`prefill_done` is global (line 4498), initialized `true`:

```
Request 2 (B_OFF): LLM thread sets prefill_done=true before exit
Request 3 (A_HIT_1): prefill_done=true → wait returns immediately → set to false
Request 4 (A_HIT_2): prefill_done=false → WAITS FOREVER (no thread to set it)
```

This explains why the FIRST HIT request (request 3) succeeded but subsequent HIT requests (request 4) hang.

### Tertiary: Stream Decode Hang Blocks Next omni_init

When `stream_decode` hangs waiting for `prefill_done`, the SSE connection stays open indefinitely. The next `omni_init` HTTP request either:
- Hangs because `omni_free` races with the hung SSE callback's usage of `state.octx`
- Or is never dispatched because the HTTP thread pool is exhausted

Result: client timeout after 300s.

## Failure Classification

**Primary**: THREAD_NOT_STARTED_ON_HIT
**Secondary**: HARNESS_TIMEOUT (triggered by primary)
**Contributing**: The test script's `CACHE_OFF` naming is wrong (KV cache is always ON with env var set)

## Fix Verification Required

The fix (move thread-start block AFTER `kv_cache_system_prompt_done:` label) is ALREADY APPLIED in source but NOT COMPILED or TESTED.

This fix ensures:
- On MISS: system prompt computed → SAVE → threads start ✓
- On HIT: goto label → save skipped → threads start ✓
- Threads always start regardless of HIT/MISS

A fresh build and binary verification is required before the fix can be validated.

## Status

- [ ] Fresh build with fix-2
- [ ] Verify new binary SHA256
- [ ] Stop OLD server (PID 1878297)
- [ ] Start NEW server with canonical env
- [ ] Verify single-key smoke test
- [ ] Run corrected multi-prefix test
- [ ] Thread ownership audit
- [ ] KV boundary audit
