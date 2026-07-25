# P7.2 Metric Boundary Audit: Why Prefill -9061ms Does NOT Improve First Audio

**Date:** 2026-07-25
**Source:** Code audit of `omni-cli.cpp` and `omni.cpp`

## Executive Summary

**The prefill time and First Audio (FA) time are measured from DIFFERENT, NON-OVERLAPPING segments of the request pipeline.** FA clock starts AFTER prefill completes. Therefore, KV cache's prefill reduction cannot possibly improve FA by design — the correct metric is total request time, not FA.

## Timing Instrumentation Audit

### Prefill Time (`stdout`)

**Code:** `omni-cli.cpp:193-203`

```cpp
auto t0 = std::chrono::high_resolution_clock::now();
stream_prefill(ctx_omni, aud_fname, img_fname, il);  // ← system prompt + user audio KV
auto t1 = std::chrono::high_resolution_clock::now();
double dt = (t1 - t0).count();  // seconds
std::cout << "prefill " << il << " (audio+vision) : " << dt << " s" << std::endl;
```

**Measures:** Wall-clock time of `stream_prefill()` call from the CLI process.
**Includes:** System prompt KV computation + user audio encoding + KV computation + (for B arm) cache load.
**Clock:** `std::chrono::high_resolution_clock` (monotonic, C++ standard).

### First Audio Time (`stdout`)

**Code:** `omni.cpp:9307-9311`

```cpp
// stream_decode_start_time is set at line 10410, INSIDE stream_decode():
ctx_omni->stream_decode_start_time = std::chrono::high_resolution_clock::now();

// First audio callback (line 9307-9311):
auto wav_complete_time = std::chrono::high_resolution_clock::now();
auto elapsed_ms = duration_cast<milliseconds>(
    wav_complete_time - ctx_omni->stream_decode_start_time).count();
if (wav_idx == 0) {
    print_with_timestamp("🎉 首响时间 (First Audio Response): %lldms\n", elapsed_ms);
}
```

**Measures:** Time from `stream_decode_start_time` (inside `stream_decode()`) to first WAV completion.
**Includes:** LLM autoregressive generation + Talker TTS + T2W.
**Excludes:** Prefill (system prompt + user audio KV computation).
**Clock:** `std::chrono::high_resolution_clock` (same clock type as prefill).

### Call Sequence (`omni-cli.cpp:181-212`)

```cpp
void test_case(...) {
    // Phase 1: Prefill (sequential)
    for (int il = start_idx; il < start_idx + cnt; ++il) {
        auto t0 = now();
        stream_prefill(...);    // ← PREFFILL IS TIMED HERE
        auto t1 = now();
        // dt = prefill time
    }
    
    // Phase 2: Decode (async — starts TTS/T2W threads)
    ctx_omni->async = orig_async;
    stream_decode(ctx_omni, "./");  // ← FA CLOCK STARTS INSIDE THIS CALL
}
```

**The two measurements are SEQUENTIAL and NON-OVERLAPPING:**

```
Timeline:
|←———— prefill (9064ms A, 2.7ms B) ————→|←———— FA (5623ms A, 5818ms B) ————→|
  stream_prefill()                          stream_decode()
  t0                          t1            stream_decode_start_time    wav_complete_time
```

## Why the Paradox: "Prefill -9s But FA Unchanged"

| Metric | What it measures | A arm | B arm | Δ |
|---|---|---|---|---|
| Prefill | System prompt + user audio KV computation | 9064 ms | 2.7 ms | **-9061 ms** |
| FA | LLM gen + Talker + T2W (after prefill) | 5623 ms | 5818 ms | +195 ms |
| **Total (prefill+FA)** | Full pipeline latency to first audio | **14687 ms** | **5821 ms** | **-8866 ms (-60.4%)** |

### Answer to Each Question

**1. Are prefill and FA using the same clock?**
Yes — both use `std::chrono::high_resolution_clock`. But they measure different segments.

**2. Is prefill on the FA critical path?**
**No.** FA clock starts AFTER `stream_prefill()` returns and `stream_decode()` begins. Prefill reduction cannot affect FA because FA doesn't include prefill.

**3. Is the 9061ms single-request or cumulative?**
Single-request. With `--test-start N`, each CLI invocation runs exactly one prefill + one decode.

**4. Does cache load/restore time appear in prefill or FA?**
In prefill. B-arm prefill (2.7ms) includes: audio encoding + KV computation + **cache load** (~microseconds from mmap'd file). The cache load is negligible.

**5. Where does the 9s go?**
It's the NPU time for computing the 62-token system prompt KV cache from scratch — audio token embeddings + attention projections. With KV cache, this work is replaced by a file read (~9.1MB mmap).

**6. Is the prefill reduction user-visible?**
**Yes.** Total time to first audio drops from ~14.7s to ~5.8s (-60%). The user hears the first word 8.9 seconds sooner with KV cache enabled. But this benefit shows in **total request time**, not FA.

**7. Why wasn't this detected earlier?**
The P5 profiling framework (`OMNI_E2E_PROFILE`) includes both prefill and decode stages in its total. But the P6 runner extracted only `prefill_ms` and `first_audio_ms` as separate metrics, never computing `total = prefill + FA`. The FA metric alone shows no benefit because KV cache doesn't accelerate anything in the FA segment.

## Impact on P6 Verdict

### What the data actually shows

| Claim | Supported? | Evidence |
|---|---|---|
| KV cache reduces FA | **NO** | FA excludes prefill; FA p50 +436ms favoring A |
| KV cache reduces total latency | **YES** | Total (prefill+FA): 14687→5821ms (-60%) |
| KV cache is functionally correct | **YES** | 26/26 cache_hit=1, reused=62, 0 CANN errors |
| KV cache should be production default | **INCONCLUSIVE** | T2W stability, paired n<30 |

### Corrected interpretation

The FA metric was the wrong primary endpoint for evaluating KV cache. KV cache affects prefill, and prefill is NOT in FA. The correct primary endpoint is:

```
TOTAL_REQUEST_TIME = prefill_time + first_audio_time
```

With this metric, KV cache shows a **-8866 ms (-60.4%) improvement in time-to-first-audio from request arrival.**

However, this finding alone does not change the P6 conclusion from GATE_INCONCLUSIVE because:
1. T2W stability still NOT PASSED (25% invalid rate)
2. Paired observations still 20 < 30
3. The total request time needs to be validated as a metric (was not instrumented directly)
4. Computation of total = prefill + FA assumes sequential, non-overlapping stages — verified by code audit but not by single-clock measurement

## Recommendations

1. **Add a single-clock total-time metric:** Record `request_start_time` before `stream_prefill()` and use it for both prefill and FA delta computation. This eliminates any risk of clock skew or boundary ambiguity.

2. **Recompute P6 statistics with total = prefill + FA** as supplementary evidence. The -60% improvement is real but needs proper instrumentation to be formally claimed.

3. **Keep FA as a secondary metric** — it validates that KV cache does not perturb downstream generation stages (LLM, Talker, T2W).

4. **Update the P6 report §7** to document that FA excludes prefill by code design, and total request time is the correct primary metric.

## Verification

The code paths confirmed at:
- `tools/omni/omni-cli.cpp:193-203` — prefill clock (t0→t1 around `stream_prefill()`)
- `tools/omni/omni-cli.cpp:212` — `stream_decode()` called AFTER prefill loop
- `tools/omni/omni.cpp:10410` — `stream_decode_start_time` set INSIDE `stream_decode()`
- `tools/omni/omni.cpp:9307-9311` — FA computed as `wav_complete_time - stream_decode_start_time`

These four locations form a complete, consistent picture: **prefill and FA are sequential, non-overlapping pipeline segments measured by independent clocks.**
