# F6 Project Status — 2026-08-10

## Current State

```
FROZEN_CANDIDATE_051e993
├─ Performance         ✅ PASS (RTF=0.452 LOCAL_BEST_EFFORT)
├─ Stability           ✅ PASS (50-reuse + 100-soak)
├─ Demo Text           ✅ PASS (30/30 valid Chinese UTF-8)
├─ Demo Audio          ✅ PASS (valid WAV via Gateway)
├─ Multimodal WS       ❌ P0 NaN logits — ACTIVE INVESTIGATION
├─ Daily-Omni          ❌ 40% single-frame (below 77.5% threshold)
├─ TTS-Seed            ❌ BLOCKED (WS NaN)
├─ VideoMME            ❌ BLOCKED (WS NaN + data not extracted)
└─ READY               ❌ NO
```

## Active Branch

```
fix/ws-multimodal-nan (from 051e993)
```

## Preserved Baseline

```
LAST_PERF_STABLE_COMMIT = 051e993
Binary SHA: 768614abd68f93ff5b57a3eb99cb79ad14d2a839f0fcb7ebf0990c88f39d189e
```

## P0: WS Multimodal NaN Logits

**Scope:** All WS paths containing audio or video content parts → NaN logits → all `?` (token 30).
**Not affected:** Text-only (string content), image-only (`type: "image"` content part).
**Key signal:** Video WITHOUT audio track still triggers NaN → trigger is video content type or multi-packet prefill, NOT audio data.

### Repro Matrix

| Input | Output | Status |
|-------|--------|--------|
| Text-only (string) | CLEAN | ✅ |
| Text-only (array) | CLEAN | ✅ |
| Image-only [text+image] | CLEAN | ✅ |
| Audio [text+audio] | ALL `?` | ❌ |
| Video [text+video] | ALL `?` | ❌ |
| Video no-audio-track | ALL `?` | ❌ |

### Structural Candidates
- Candidate A: `audition_n_mmproj_embd != llama_n_embd` → heap over-read in audio_embed memcpy (omni.cpp:13955)
- Candidate D: Multi-packet prefill for video → position/n_past misalignment
- Candidate E: Empty audio_embed in video-no-audio path → prefill_with_emb(n_pos=0)
- Candidate B: audition_batch_encode buffer ±1 overflow
- Candidate C: NaN already in audio mel spectrogram

### Investigation Plan
See: `/root/.claude/plans/shiny-dancing-acorn.md`

## Next Step

Phase 2: Add `OMNI_NAN_DIAG=1` instrumentation to trace first non-finite value through the multimodal pipeline.

## Completed

- [x] Performance optimization (RTF=0.452 LOCAL_BEST_EFFORT, Flow ∥ Vocoder)
- [x] Stability gates (50-reuse + 100-soak, 0 failures)
- [x] Demo text chat (30/30 valid UTF-8)
- [x] WS lifecycle fix
- [x] Reporting corrections (RTF comparison language, VideoMME data status)
- [x] Phase 0: FINAL_GATE_TABLE.md + FINAL_CANDIDATE_REPORT.md updated
- [x] Phase 1: fix/ws-multimodal-nan branch created from 051e993
- [x] Vision encoding confirmed working through WS (correct content-part protocol)
- [x] WS NaN scope expanded: affects ALL paths with audio/video, not just full_duplex
