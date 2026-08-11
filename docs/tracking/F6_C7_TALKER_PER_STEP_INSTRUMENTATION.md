# F6 C7: Talker Per-Step Instrumentation Plan (P9)

**Date:** 2026-08-01
**Target:** Add low-overhead per-step Talker profiling without per-token print

---

## Instrumentation Points

### TTS Simplex path: `tools/omni/omni.cpp:6768-6900`

```
for (int t = 0; t < max_audio_tokens; ++t) {
    // [HOOK 1] step_begin_ns ← record here
    llama_token sampled_token_abs = sample_tts_token_simplex(...);
    // [HOOK 2] sample_end_ns ← record here (covers llama_decode + sampling)
    output_audio_tokens.push_back(relative_idx);
    // [HOOK 3] token_accepted_ns ← record here
}
```

### sample_tts_token_simplex internals (line 3850):

```
sample_tts_token_simplex():
    // [HOOK 1a] compute_begin_ns
    prefill_with_emb_tts() → llama_decode() for TTS model
    // [HOOK 1b] compute_end_ns
    // ... logits processing ...
    // [HOOK 1c] sampling_begin_ns
    common_sampler_sample()
    // [HOOK 1d] sampling_end_ns
```

### TTS Local path: `tools/omni/omni.cpp:7447-7490`

Same pattern as simplex, using `sample_tts_token()` instead.

---

## Ring Buffer Structure

Fixed-size per-request ring buffer (no dynamic allocation, no per-token print):

```cpp
#define TALKER_MAX_STEPS 500  // max_audio_tokens = 500

struct TalkerStepRecord {
    int16_t  step_index;            // 0-based step in current chunk
    int64_t  step_start_ns;         // absolute clock (steady_clock)
    int64_t  step_compute_end_ns;   // after llama_decode
    int64_t  step_sample_end_ns;    // after sampling
    int16_t  input_token_count;     // tokens fed to this step
    int32_t  sampled_token_id;      // absolute audio token ID
    int16_t  token_type;            // 0=audio, 1=EOS, 2=text_eos
    int16_t  is_audio_token;        // 1 if audio token (not EOS/pad)
    int16_t  audio_token_count_before; // accumulated before this step
    int16_t  audio_token_count_after;  // accumulated after this step
    int32_t  backend_cpu_op_count;  // number of CPU backend ops this step
    int32_t  backend_cann_op_count; // number of CANN backend ops this step
    int16_t  allocation_count;      // new allocations this step
    int32_t  allocation_bytes;      // bytes allocated this step
    int64_t  stream_sync_ns;        // time spent in stream sync
    int64_t  queue_wait_ns;         // time spent waiting for queue
};
// sizeof(TalkerStepRecord) = 72 bytes × 500 = 36 KB per request (fixed)
```

---

## Ring Buffer Management

```cpp
struct TalkerStepBuffer {
    TalkerStepRecord steps[TALKER_MAX_STEPS];
    int count = 0;        // number of steps recorded
    bool truncated = false;
    
    void record_step(const TalkerStepRecord &rec) {
        if (count < TALKER_MAX_STEPS) {
            steps[count++] = rec;
        } else {
            truncated = true;
            // Do NOT overrun — silently drop beyond 500
        }
    }
    
    void reset() {
        count = 0;
        truncated = false;
    }
};
```

---

## Per-Request Aggregation (computed at dump time)

```cpp
struct TalkerStepSummary {
    int   steps_before_first_audio_token;  // G3 step index
    int   steps_G3_to_threshold;           // G3 → A1 (25-token accumulation)
    int64_t first_step_ns;                 // step 0 duration
    int64_t steady_step_median_ns;         // p50 of steps 1..N
    int64_t steady_step_p95_ns;            // p95
    int64_t total_talker_compute_ns;       // sum of compute durations
    int64_t total_sampling_ns;             // sum of sampling durations
    int64_t total_sync_ns;                 // sum of stream sync
    int64_t total_allocation_ns;           // sum of allocation overhead
    int64_t total_wait_ns;                 // sum of queue/CV wait
    int     total_steps;
    int     total_audio_tokens;
    int     total_cpu_ops;
    int     total_cann_ops;
    int     total_allocations;
    int64_t total_allocation_bytes;
};
```

---

## JSON Output (per request, at request completion)

```json
{
  "talker_step_summary": {
    "steps_before_first_audio_token": 4,
    "steps_G3_to_threshold": 21,
    "first_step_ns": 12500000,
    "steady_step_median_ns": 11800000,
    "steady_step_p95_ns": 14200000,
    "total_talker_compute_ns": 310000000,
    "total_sampling_ns": 45000000,
    "total_sync_ns": 1200000,
    "total_allocation_ns": 800000,
    "total_wait_ns": 3500000,
    "total_steps": 28,
    "total_audio_tokens": 25,
    "total_cpu_ops": 0,
    "total_cann_ops": 168
  },
  "talker_steps": [
    {"i":0, "start":123456789000, "compute":11800000, "sample":1200000, "audio":0, "acc_before":0},
    {"i":1, "start":123468589000, "compute":11600000, "sample":1100000, "audio":0, "acc_before":0},
    ...
  ]
}
```

The `talker_steps` array is only emitted when `OMNI_E2E_PROFILE=1` (full mode). Summary mode only emits `talker_step_summary`.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `F6_PHASE3_TALKER_STATS` | `0` | 1 = enable per-step recording |
| `F6_PHASE3_TALKER_STATS_MAX_STEPS` | `500` | Ring buffer size |
| `OMNI_E2E_PROFILE` | (unchanged) | `1` = full (emit steps array), `summary` = summary only |

---

## Overhead Budget

| Component | Budget |
|-----------|--------|
| Per-step record (72 bytes write) | < 100 ns |
| 500-step ring buffer (36 KB) | Pre-allocated at request init |
| JSON serialization (500 steps) | ~50 KB output, ~500 μs |
| **Total per-request overhead** | **< 0.1% of ~922ms D0→W0** |

---

## Gate: C10 Overhead Check

After implementation:
```
F6_PHASE3_TALKER_STATS=0 vs F6_PHASE3_TALKER_STATS=1
20 strict matched pairs
D0→W0 median Δ ≤ 1% (≤ 9.2ms)
```

---

## Implementation Order

1. Add `TalkerStepRecord`, `TalkerStepBuffer`, `TalkerStepSummary` to `omni.h`
2. Add hooks in `sample_tts_token_simplex()` and `sample_tts_token()`
3. Add hooks in TTS simplex/local decode loops
4. Compute summary at request completion (in JSON dump function)
5. Emit `talker_step_summary` in both full and summary modes
6. Emit `talker_steps` in full mode only
7. Build, smoke test with 5 requests
8. C9 correctness gate: 30 requests, verify all critical stages present
9. C10 overhead gate: 20 matched pairs with stats on/off
