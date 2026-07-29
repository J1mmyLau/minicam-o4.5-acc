# P17: T2W Lifecycle Test Plan

**Date**: 2026-07-29
**Status**: PLANNED — awaiting 30min stability gate

---

## 1. Background

The CANN Flow+Vocoder setup uses deferred worker-thread initialization (`cann-flow-only`). Each T2W request undergoes a full lifecycle:

```
T2W worker thread created
  → flowGGUFModelLoader::load_from_gguf(device="gpu")  [CANN backend init]
  → voc_hg2_model init (device="gpu")                   [CANN backend init]
  → prompt_cache load
  → [processing loop: receive tokens → flow compute → vocoder compute → WAV output]
  → EOS detection → drain remaining chunks → thread shutdown
```

The lifecycle test verifies correct behavior across request boundaries.

---

## 2. Test Scenarios

### T2W-L1: Single Request Correctness (already covered)
- ✅ P15-A: 60/60 WAVs valid
- ✅ Demo smoke: 16 WAVs, 0 CANN errors
- ✅ Stability 30min: in progress

### T2W-L2: Request → Request Transition
```
R1: full lifecycle → thread shutdown
R2: full lifecycle (fresh worker thread)
```
- Verify R2 init is clean (no stale CANN context)
- Verify R2 audio is valid (no carryover from R1)
- Covered by: stability test (each iter = new request)

### T2W-L3: Rapid Successive Requests (No Cooldown)
```
R1: full lifecycle
[NO sleep gap]
R2: full lifecycle (immediate restart)
```
- Risk: CANN driver resource exhaustion, thread pool contention
- NOT covered by stability test (2s sleep between iters)

### T2W-L4: Very Short Response (Single Chunk)
- Risk: EOS drain logic edge case (buffer empty on first drain attempt)
- Covered by: some test cases produce few WAVs (case 3 → 2 WAVs)

### T2W-L5: Very Long Response (Many Chunks)
- Risk: memory leak across chunks, CANN graph accumulation
- Covered by: test case 0 → 35 WAVs

### T2W-L6: Audio Validity Across Lifecycle
- Verify all WAVs: non-silent, non-clipped, valid header
- Already verified in P15-A (60/60)

---

## 3. Execution Plan

### Step 1: T2W-L3 (Rapid Successive) — Quick Smoke
```bash
# 5 rapid iterations, no sleep
for i in 0 1 2 3 4; do
  timeout 300 env OMNI_T2W_DEVICE=cann-flow-only OMNI_VOC_DEVICE=gpu \
    OMNI_T2W_PROFILE=2 \
    /workspace/llama.cpp-omni-operator/build/bin/llama-omni-cli \
      -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
      -ngl 8 --test tools/omni/assets/test_case/omni_test_case/omni_test_case_ 1 \
      --test-start $i \
      2>/tmp/lifecycle_rapid_${i}.stderr 1>/tmp/lifecycle_rapid_${i}.stdout
  echo "Iter $i: RC=$?"
done
```

### Step 2: T2W-L4+L5 (Edge Cases) — Already Covered
- Stability test covers both short (2 WAVs) and long (35 WAVs) responses

### Step 3: T2W-L6 (Audio Validity)
- Random sampling from stability test WAVs
- Verify non-silent, non-clipped

---

## 4. Success Criteria

| Test | Criteria |
|------|----------|
| T2W-L1 | RTF < 1.0, 0 CANN errors, WAVs valid |
| T2W-L2 | 0 failures across ≥30 request transitions |
| T2W-L3 | 0 failures in 5 rapid iterations, no CANN errors |
| T2W-L4 | WAV > 0 for all test cases, no crash on drain |
| T2W-L5 | Memory stable across long responses, no crash |
| T2W-L6 | Non-silent WAVs, RMS > 0.001, no clipping |

---

## 5. Multi-Prefix Note

The current test infrastructure uses `--test` with omni test cases which all share the same system prompt. The KV cache multi-prefix test requires different system prompts to verify cache key isolation. This requires either:
1. Binary modification to change system prompt per test case
2. A separate test binary with different hardcoded prompts

Multi-prefix KV cache isolation was already verified in the KV cache production branch (`CACHE_KEY_ISOLATION = PASS`). For the CANN Flow+Vocoder context, the key finding is that KV cache ON/OFF does not affect CANN backend behavior, so multi-prefix is a KV cache concern, not a CANN concern.
