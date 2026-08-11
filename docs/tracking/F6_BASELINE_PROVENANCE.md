# F6 BASELINE PROVENANCE — LLM Decode → First Speak Token

**Created:** 2026-07-30
**Mission:** Decompose and Optimize LLM Decode → First Speak Token (T0→T6)

---

## Frozen Source

```
BRANCH:       perf/f6-decode-to-speak
WORKTREE:     /workspace/llama.cpp-omni-f6
BASE TAG:     fp16-async-kv-production-ready-internal-20260730
BASE COMMIT:  a50cece
SUBJECT:      K2: propagate voice_audio to ctx_omni->ref_audio_path for KV cache key safety
PARENT BRANCH: perf/flow-chunk-rtf (READ-ONLY from this worktree)
PARENT WORKTREE: /workspace/llama.cpp-omni-operator (READ-ONLY from this worktree)
```

## Frozen Binaries

```
llama-omni-server:
  PATH:   /workspace/llama.cpp-omni-operator/build/bin/llama-omni-server
  SHA256: c8546f4416f51bb7873e3aaada9688e5dd9d69b2ca1d7ed9f7340084ba1b6ca3

libomni.so:
  PATH:   /workspace/llama.cpp-omni-operator/build/bin/libomni.so
  SHA256: c84447320ecf4524db81e6577cbc05695735285a902afd37d27e56d74e06fcab
```

## Frozen Model

```
MODEL:   MiniCPM-o-4_5-F16.gguf
PATH:    /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf
SIZE:    16384959136 bytes (~15.3 GiB)
SHA256:  d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de
```

## Canonical Launch

```bash
-ngl 999 -fa off -c 4096 -b 512 -ub 512 --split-mode layer
```

## Hardware

```
NPU:      2× Ascend 910C (Chip Name: Ascend910)
HBM:      64 GB per device
CANN:     9.1.0-beta.1
ASCEND_HOME_PATH: /usr/local/Ascend/cann-9.1.0-beta.1
```

## KV Cache Status

```
KV_CACHE:                    OPT_IN_READY / DEFAULT_OFF
FP16_RUNTIME_CANDIDATE:      FROZEN_INTERNAL
INTERNAL GATES:               11/11 PASS (K0-K10)
EXTERNAL GATE (K11):         BLOCKED_EXTERNAL (benchmark assets)

KV_CACHE_VERSION:            2 (112-byte extended fingerprint)
KV_CACHE_SAFETY:             ref_audio hash in key, runtime verified (a50cece)
KV_CACHE_STABILITY:          151/151 requests, 0 errors
```

## Performance Boundaries (DO NOT CONFLATE)

```
ORIGINAL_Q4_REQUEST_TO_FIRST_AUDIO_REDUCTION:
  59.0% on earlier frozen Q4_K_M workload
  (request start → first audio, 30 matched pairs)

FP16_FINAL_PREFIX_STAGE_REDUCTION:
  approximately 65.5% (system-prompt processing only)
  MISS ≈ 220ms → HIT ≈ 76ms, 2.89× stage speedup

FP16_FINAL_REQUEST_TO_FIRST_AUDIO_REDUCTION:
  NO_DATA / PENDING
  (must be measured on this exact binary with matched CACHE_DISABLED vs CACHE_HIT pairs)

⚠️  Prefix-stage 2.89× ≠ E2E first-audio acceleration
⚠️  Prefix-stage 65.5% ≠ original 59% E2E reduction
⚠️  Do NOT claim "FP16 has reproduced 59%"
```

## F6 Mission Constraints

```
READ-ONLY: KV tag, KV binary, KV model, KV launch flags
ISOLATED:  F6 branch and worktree — no modification to parent perf/flow-chunk-rtf
TARGET:    T0 (dynamic prefill complete) → T6 (first speak token accepted)
PROHIBITED: AscendC kernel without runtime path evidence
PROHIBITED: msprof total time substituted for wall-clock critical path
PROHIBITED: T2W latency re-attributed to Talker
AUTONOMOUS: No "continue?" prompts, auto checkpoint/compact/recover
```
