# F6 Project Status — 2026-08-10 (END OF DAY)

## DECISION: WAIT FOR OFFICIAL UNIFIED EVAL BRANCH

Organizer stated: "预计明天上午提供有统一测评的分支"

All current Cookbook/custom evaluator accuracy results are **NOT final official results**.
Accuracy work is FROZEN until the official unified evaluation branch arrives tomorrow.

## Current State

```
FROZEN_CANDIDATE_051e993
├─ Performance         ✅ PASS (LOCAL_BEST_EFFORT RTF=0.452)
├─ Stability           ✅ PASS (50-reuse + 100-soak)
├─ Demo Text           ✅ PASS (30/30 valid Chinese UTF-8)
├─ Demo Audio          ✅ PASS (valid WAV via Gateway)
├─ Accuracy            ⏸️  FROZEN (WAIT_OFFICIAL_UNIFIED_EVAL_BRANCH)
│   ├─ Daily-Omni      ⏸️  40% single-frame → INVALID_AS_FINAL_GATE_RESULT
│   ├─ TTS-Seed        ⏸️  BLOCKED (WS NaN — may be non-unified-path artifact)
│   └─ VideoMME        ⏸️  BLOCKED (WS NaN + data not extracted)
├─ WS Multimodal NaN   🔬 ROOT CAUSE TRACED, FIX DEFERRED
├─ Q8_0 Contiguous-Y   🔬 REPRODUCED, BACKEND_LAYOUT_COMPATIBILITY_HYPOTHESIS
└─ READY               ❌ NO (WAIT_OFFICIAL_EVAL)
```

## Branches

```
main                    — final submission (f12b59a)
fix/ws-multimodal-nan   — NaN investigation (7d3c80c), DO NOT MERGE yet
```

## Preserved Baseline

```
LAST_PERF_STABLE_COMMIT = 051e993
Binary SHA: 768614abd68f93ff5b57a3eb99cb79ad14d2a839f0fcb7ebf0990c88f39d189e
```

---

## P0-A: WS Multimodal NaN Logits (TRACED, NOT FIXED)

### Root Cause Found

**NaN originates in audio mel spectrogram preprocessing**, before the Whisper encoder.

### NaN Propagation Chain (OMNI_NAN_DIAG=1 trace)

```
whisper_input_mel  → nan=160/2400 (6.67%), valid=-1.5 (silent audio → log10(1e-10))
whisper_embed_output → nan=12288/12288 (100%, 3 tokens × 4096 dims)
audio_embed_memcpy   → nan=12288/12288
audio_only_prefill   → nan=12288/12288
logits_ith           → nan=151748/151748 (100% vocab)
→ all text output = "?" (token 30)
```

### Key Finding

- 160/2400 = exactly 2 full mel frames (80 bins × 2) are NaN
- All valid values are exactly -1.5: `(log10(1e-10) + 4.0) / 4.0` — correct for silent input
- The NaN is in the mel data BEFORE Whisper encoder runs
- `log_mel_spectrogram()` → `log_mel_spectrogram_worker_thread()` produces the NaN

### Code Location

- `tools/omni/audition.cpp:log_mel_spectrogram_worker_thread()` (L1839-1901)
- `tools/omni/audition.cpp:log_mel_spectrogram()` (L1905-1993) — normalization at L1965-1978
- NaN guard exists at L1890: `sum = log10(std::max(sum, 1e-10))`

### Instrumentation

- Branch: `fix/ws-multimodal-nan` (7d3c80c)
- 8 nan_diag_check boundaries across omni.cpp, audition.cpp, vision.cpp
- Gated behind `OMNI_NAN_DIAG=1` env var (zero-cost when disabled)
- Repro script: `scripts/f6_nan_repro_matrix.py`

### Hypothesis for 160 NaN

FFT/mel filterbank output for 2 specific frames produces values ≤ 0 despite `max(sum, 1e-10)` guard.
Possible causes: FFT buffer alias, uninitialized memory in recursive Cooley-Tukey workspace,
or mel filterbank producing negative magnitude.

### DECISION: DO NOT FIX NOW

This bug may be specific to the current non-unified evaluation path (custom Cookbook evaluator,
specific WS protocol, specific audio preprocessing). The official unified evaluation branch
tomorrow may use different:
- Prompt Bundle format
- Input organization
- Adapter layer
- Media format
- Prefill token layout
- Evaluation protocol

**If NaN reproduces on official unified eval branch → true P0 correctness bug.**
**If NaN does NOT reproduce → artifact of current non-unified path.**

---

## P0-B: Q8_0 Prompt Bundle Contiguous-Y Error (REPRODUCED, NOT CONFIRMED)

### Repro

```
Prompt Bundle enabled
output.weight activation input = [4096, 17]
ggml CANN backend
→ aclnnWeightQuantBatchMatmulV2
→ EZ1001: "only support y tensor is contiguous"
```

### Classification

```
Q8_CONTIGUOUS_Y_REPRODUCED = YES
ROOT_CAUSE = NOT_CONFIRMED
USER_CONFIG_ERROR = NOT_PROVEN
BACKEND_LAYOUT_COMPATIBILITY_ISSUE = STRONG_HYPOTHESIS
```

From operator semantics: `aclnnWeightQuantBatchMatmulV2` requires contiguous ND output.
Multi-token prefill (`[4096, 17]`) may create ggml view/stride tensors incompatible with
this constraint. Huawei CANN docs explicitly require contiguous y tensor.

### DECISION: DO NOT PATCH NOW

Same rationale as NaN — the official unified eval branch may use different Prompt Bundle
or input organization that avoids this shape. If it reproduces on the official branch,
it becomes a clean backend fix target.

---

## Tomorrow's Plan (When Official Branch Arrives)

1. Pull/checkout official unified evaluation branch separately
2. Record exact organizer commit SHA
3. Run unchanged official instructions first
4. Test F16 candidate first (accuracy baseline)
5. Then test Q8_0
6. Re-evaluate:
   - Daily-Omni accuracy
   - VideoMME accuracy
   - TTS-Seed ASV/WER
   - Audio/video NaN (with OMNI_NAN_DIAG=1)
   - Q8_0 contiguous-y error
7. Only bugs reproduced on unified eval branch → promoted to submission blockers
8. Do NOT start new performance optimization work

## Completed (Today)

- [x] Phase 2: OMNI_NAN_DIAG=1 instrumentation at 8 pipeline boundaries
- [x] Phase 3: Embedding dimension audit (dimensions match, Candidate A refuted)
- [x] Phase 4: First NaN boundary located (whisper_input_mel, 160/2400 NaN)
- [x] NaN propagation chain fully documented
- [x] WS NaN confirmed in mel spectrogram preprocessing (not Whisper, not LLM)
- [x] Q8_0 contiguous-y error documented
- [x] Decision: FREEZE accuracy work, wait for official unified eval branch
