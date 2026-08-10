# MiniCPM-o 4.5 Ascend 910C Track A — Final Gate Table

**Date:** 2026-08-10 (last updated)
**Binary SHA256:** `768614abd68f93ff5b57a3eb99cb79ad14d2a839f0fcb7ebf0990c88f39d189e`
**Git HEAD:** `051e993` (Flow ∥ Vocoder pipeline)
**Status:** LAST_PERF_STABLE_BASELINE — Performance + Stability validated. New P0 correctness bug (WS multimodal NaN logits) blocks accuracy gates.

## Canonical Launch Configuration

```bash
OMNI_T2W_DEVICE=cann-flow-only \
OMNI_T2W_PIPELINE_OVERLAP=1 \
OMNI_T2W_DRAIN_TIMEOUT_MS=5000 \
ASCEND_RT_VISIBLE_DEVICES=0 \
build/bin/llama-omni-server \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf \
  --host 127.0.0.1 --port 18094 \
  -ngl 999 --device CANN0 \
  --ctx-size 4096 --batch-size 512 --ubatch-size 512 \
  --split-mode layer -t 4
```

## Gate Summary

| # | Gate | Status | Key Result | Evidence |
|---|------|--------|------------|----------|
| P0 | Config Freeze | ✅ PASS | 4 files canonicalized | Phase 0 |
| P1 | F16 Pipeline Cross-Validation | ✅ PASS | 1.63× speedup, 0 NaN/Inf | `benchmarks/results/final_f16_freeze_e2e.json` |
| P2 | E2E Performance | ✅ PASS | Pipeline ON RTF=0.452, OFF RTF=0.575 | `benchmarks/results/formal/phase2_v2_*.json` |
| P3A | 50-Session Reuse | ✅ PASS | 50/50, 0 rejections | `scripts/f6_freeze_p3a_50_reuse.py` |
| P3B | 100-Round Soak | ✅ PASS | 100/100, 537 T2W tasks, depth≤3 | `scripts/f6_freeze_p3b_soak.py` |
| P3C | Resource Monitoring | ✅ PASS | No thread leaks, 0 backlog | Phase 3B server log |
| P4A | Performance RTF | ✅ PASS | LOCAL_BEST_EFFORT RTF=0.452 (ON), 0.575 (OFF) | Phase 2 v2 |
| P4B | Demo Text Chat | ✅ PASS | Gateway→Worker→Backend, valid UTF-8, 30/30 | Phase 3 G2, `F6 Demo Full-Chain UTF-8 Gate` |
| P4C | Demo Duplex Audio | ✅ PASS | Gateway→Worker→Backend, valid WAV output | Phase 3 G3 |
| P4D | Packaging | ✅ PASS | Report written, SHA frozen | `docs/F6_F16_FINAL_CANDIDATE_REPORT.md` |

## Accuracy Gates

| Metric | Official Ref | Threshold | Candidate Score | Delta | Status | Detail |
|--------|-------------|-----------|-----------------|-------|--------|--------|
| VideoMME | 69.0 | ≥67.0 | N/A | N/A | BLOCKED | 95GB / 20 zips present, NOT extracted; evaluator dir not prepared. Also blocked by WS NaN bug. |
| Daily-Omni | 79.5 (80.2 adapter) | ≥77.5 | ~40% (single-frame pilot) | −37.5pp | **FAIL** | Single-frame only (multi-frame blocked by WS NaN). Eval pipeline mismatch not yet ruled out. |
| TTS-Seed ASV | 0.709 | ≥0.689 | N/A | N/A | BLOCKED | WS full_duplex NaN bug. Tar present (1.2GB), not extracted. Prompts wavs not extracted. |
| WER | 1.414 | ≤1.56 | N/A | N/A | BLOCKED | Same as TTS-Seed above. |

### Accuracy Gate Details

**Daily-Omni Pilot (2026-08-10):**
- Protocol: WebSocket turn_based, single middle-frame JPEG via `type: "image"` content part
- Vision encoding: CONFIRMED WORKING (60 encode ops in 20 items, ~300ms/frame)
- Accuracy: 8/20 = 40.0% (above 25% chance, far below 77.5% threshold)
- By type: AV Event Alignment 4/7, Comparative 3/3, Event Sequence 1/6, Inference 0/2
- Limitation: Only ONE frame used (server's `extra_image_paths` mechanism only works with video container, which triggers NaN). Multi-frame + audio needed for competitive accuracy.
- Evidence: `/tmp/daily_omni_20/daily_omni_pilot.json`, server log: `/tmp/daily_omni_20/server.log`

**Root Cause — WS Multimodal NaN Logits Bug:**
- **Scope:** Affects ALL WebSocket code paths when multimedia content (audio or video) is present
- **Reproduction:** 
  - String content (text-only, no audio): CLEAN text ✅
  - Array content [text only]: CLEAN text ✅  
  - Array content [text + image]: CLEAN text ✅ (vision encodes but no audio trigger)
  - Array content [text + audio]: ALL `?` (NaN logits) ❌
  - Array content [text + video]: ALL `?` (NaN logits) ❌
  - Single `type: "image"` part: CLEAN text ✅
- **Impact:** Blocks Daily-Omni (needs video/multi-frame), TTS-Seed (needs full_duplex audio), VideoMME (needs video)
- **Status:** PRE-EXISTING (documented in `F6 Duplex NaN Logits`, previously only known for full_duplex audio path — now confirmed for turn_based video/audio too)
- **HTTP path:** NOT affected (text + image confirmed working through HTTP prefill/decode in earlier tests)

## Performance — LOCAL_BEST_EFFORT

| Metric | Pipeline ON | Pipeline OFF | Official Published Ref | Direct Comparability |
|--------|------------|--------------|------------------------|----------------------|
| SPEAK_TO_WAV_RTF (client) | 0.452 | 0.575 | 1.087 | NOT_PROVEN |
| Per-Window T2W (server) | 5334ms p50 | 15723ms p50 | — | — |
| Pipeline Speedup | 1.27× (client) / 2.95× (server) | — | — | — |

**Label:** LOCAL_BEST_EFFORT
**Timer:** client-side `response.done` wall time, per-chunk measurement
**Test Video:** `omni_duplex1.mp4` (35s, 34 SPEAK chunks, 0 LISTEN)
**Official reference:** 1.087 (published F16 baseline). Timer boundary differs — values are NOT directly comparable. Do NOT report as "X× official" without qualification.

## Demo Path Gates

| Gate | Status | Details |
|------|--------|---------|
| G1: Service Health | ✅ PASS | Backend + Worker + Gateway all start |
| G2: Text Chat | ✅ PASS | Turn-based via Gateway, valid Chinese UTF-8, 30/30 (2026-08-07) |
| G3: Duplex Audio | ✅ PASS | Full-duplex via Gateway, valid WAV output |
| G4: Demo Video | NOT_RUN | Gateway infrastructure not running; same WS NaN bug would affect video |
| Session Reuse | ✅ PROVEN | Backend-level 50/50 (Phase 3A). Worker remote-backend mode has state reset limitation (pre-existing, not regression) |

## Known Limitations

1. **WS Multimodal NaN Logits Bug (CRITICAL):** Any WebSocket input containing audio or video content parts triggers NaN logits in the LLM, producing all-`?` output. This is a pre-existing bug that blocks all accuracy evaluations requiring multimodal input. Image-only (JPEG via `type: "image"`) works correctly. The bug was previously documented for the full_duplex audio path but this investigation has confirmed it also affects the turn_based path.
2. **Worker state reset in remote-backend mode:** The Demo worker's `_handle_remote_backend_runtime_ws` does not reset `WorkerState.status` to IDLE after session completion. Each session requires a fresh worker. This is a pre-existing Demo stack issue, not related to the frozen binary.
3. **Official RTF comparability:** LOCAL_BEST_EFFORT measurement uses client-side `response.done` timing, not the organizer's benchmark harness. Timer boundary documented as NOT_PROVEN.
4. **Accuracy benchmarks:** Daily-Omni single-frame pilot shows 40% accuracy (vision encoding verified working). Full multi-frame evaluation blocked by WS NaN bug. TTS-Seed and VideoMME similarly blocked.
5. **Vocoder CANN:** Deferred. CPU vocoder is the T2W bottleneck. Pipeline overlap partially mitigates.

## Readiness Assessment

| Dimension | Status | Verdict |
|-----------|--------|---------|
| Performance (SPEAK→WAV RTF) | ✅ PASS | LOCAL_BEST_EFFORT=0.452, official published ref=1.087, direct comparability NOT_PROVEN |
| Stability (lifecycle/soak) | ✅ PASS | 50-reuse + 100-round soak, 0 failures |
| Demo Text Chat | ✅ PASS | 30/30 valid Chinese UTF-8 |
| Demo Duplex Audio | ✅ PASS | Valid WAV output |
| Daily-Omni Accuracy | ❌ FAIL/BLOCKED | 40% single-frame vs 77.5% threshold; multi-frame blocked |
| TTS-Seed Accuracy | ❌ BLOCKED | WS full_duplex NaN bug |
| VideoMME Accuracy | ❌ BLOCKED | Data missing + WS NaN bug |
| **READY_FOR_SUBMISSION** | **NO** | Accuracy gates not passable with frozen binary's known limitations |

## Fallback Path

If pipeline (`OMNI_T2W_PIPELINE_OVERLAP=1`) causes issues:
```bash
# Serial mode (omit PIPELINE_OVERLAP or set to 0)
OMNI_T2W_DEVICE=cann-flow-only OMNI_T2W_DRAIN_TIMEOUT_MS=5000 \
  build/bin/llama-omni-server ... 
```
Serial F16 RTF=0.575 (LOCAL_BEST_EFFORT), still competitive.

## Model Identity

- **Model:** MiniCPM-o-4_5-F16.gguf (16.4 GB)
- **Path:** `/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf`
- **Precision:** F16 (all weights, no quantization)
- **Device:** Single Ascend 910C (CANN0)
- **Inference Stack:** llama.cpp-omni C++ server + CANN backend
