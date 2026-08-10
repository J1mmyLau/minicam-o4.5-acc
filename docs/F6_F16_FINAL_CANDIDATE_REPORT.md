# F16 Final Candidate Report — MiniCPM-o 4.5 Ascend 910C

**Date:** 2026-08-10
**Status:** LAST_PERF_STABLE_BASELINE — New P0 correctness bug discovered (WS multimodal NaN logits). Binary preserved as performance anchor.
**Binary SHA:** `768614abd68f93ff5b57a3eb99cb79ad14d2a839f0fcb7ebf0990c88f39d189e`
**Git HEAD:** `051e9932957318a882395744fcf3d5f9888d112c`
**Branch:** `fix/ws-multimodal-nan` (investigation branch from `main` at 051e993)

## 1. Configuration

| Parameter | Value |
|-----------|-------|
| Model | MiniCPM-o-4_5-F16.gguf (16.4 GB) |
| Quantization | F16 (no weight quantization) |
| Device | Single Ascend 910C (CANN0) |
| CANN version | 9.1.0-beta.1 |
| Context size | 4096 |
| Batch/UBatch | 512/512 |
| Split mode | layer |
| Layers on GPU | 999 (all) |
| CPU threads | 4 |
| Flash attention | off |
| T2W device | cann-flow-only (Flow on CANN, Vocoder on CPU) |
| Pipeline | OMNI_T2W_PIPELINE_OVERLAP=1 (Flow ∥ Vocoder) |
| Drain timeout | OMNI_T2W_DRAIN_TIMEOUT_MS=5000 |

### Canonical Launch Command

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

### Key Feature: Flow ∥ Vocoder Pipeline

The T2W pipeline was re-architected to overlap Flow Matching (CANN) with Vocoder (CPU):
- Flow produces mel spectrograms on CANN → enqueues to bounded queue (capacity=2)
- Vocoder consumes mel from queue on CPU → produces WAV audio
- Default: `OMNI_T2W_PIPELINE_OVERLAP=0` (serial). Competitive mode: `=1` (pipeline)

## 2. Performance

### Phase 2: LOCAL_BEST_EFFORT SPEAK→WAV RTF

| Metric | Pipeline ON | Pipeline OFF | Speedup |
|--------|------------|--------------|---------|
| LOCAL_BEST_EFFORT_SPEAK_TO_WAV_RTF (client) | **0.452** | 0.575 | **1.27×** |
| Server per-window T2W p50 | **5334 ms** | 15723 ms | **2.95×** |
| SPEAK chunks | 34/35 | 34/35 | — |
| LISTEN chunks | 0 | 0 | — |

**Measurement:** Client-side `response.done` wall time, 35-chunk omni_duplex1.mp4.
**Label:** LOCAL_BEST_EFFORT (NOT official organizer harness).
**Official reference:** SPEAK→WAV_RTF = 1.087 (comparison only, NOT_PROVEN).

Results: `benchmarks/results/formal/phase2_v2_*.json`

### Phase 1: Per-Window Micro-Benchmark

| Metric | Pipeline OFF | Pipeline ON | Speedup |
|--------|-------------|------------|---------|
| T2W per-window p50 | 543 ms | 332 ms | **1.63×** |

## 3. Stability Gates

### 3A: 50-Session Reuse → PASS

| Metric | Result |
|--------|--------|
| Sessions | 50/50 (100%) |
| Rejections | 0 |
| Drain timeouts | 0 |
| Bad WAVs | 0 |
| RSS | 6114MB → 14253MB (+8.1GB) |
| Duration | 439s (8.8s/session) |

### 3B: 100-Round Single-Session Soak → PASS

| Metric | Result |
|--------|--------|
| Rounds | 100/100 (100%) |
| Failures | 0 |
| Drain timeouts | 0 |
| T2W tasks processed | 537 enqueued / 537 dequeued |
| Queue depth max | 3 (healthy; 531× depth=0) |
| Bad WAVs | 0/477 |
| RSS | 4345MB → 5200MB (+855MB) |
| Duration | 830s (8.3s/round) |

### 3C: Resource Monitoring → PASS

- No thread leaks across 50-session or 100-round tests
- Queue backlog slope = 0.00 (clean drain at every EOS)
- No CANN errors, no NaN/Inf in any output

## 4. Demo Path Gates (Phase 3)

| Gate | Status | Details |
|------|--------|---------|
| G1: Service Health | ✅ PASS | Backend + Worker + Gateway all start |
| G2: Text Chat | ✅ PASS | Turn-based via Gateway→Worker→Backend, valid Chinese UTF-8, 1549ms |
| G3: Duplex Audio | ✅ PASS | Full-duplex via Gateway→Worker→Backend, valid WAV output |

**Protocol note:** Turn-based chat requires `messages` array format: `{"messages":[{"role":"user","content":"..."}]}`.

**Known limitation:** Worker remote-backend mode doesn't reset state after session (pre-existing Demo stack issue). Session reuse proven at backend level (Phase 3A: 50/50).

## 5. Accuracy Gates (Phase 1) — Updated 2026-08-10

| Metric | Official Ref | Threshold | Candidate Score | Status |
|--------|-------------|-----------|-----------------|--------|
| VideoMME | 69.0 | ≥67.0 | N/A | BLOCKED (95GB/20 zips present, not extracted; WS NaN bug) |
| Daily-Omni | 79.5 | ≥77.5 | ~40% (single-frame pilot) | **FAIL** (below threshold; multi-frame blocked by NaN) |
| TTS-Seed ASV | 0.709 | ≥0.689 | N/A | BLOCKED (WS full_duplex NaN) |
| WER | 1.414 | ≤1.56 | N/A | BLOCKED (WS full_duplex NaN) |

**Discovery (2026-08-10):** A pre-existing WS multimodal NaN logits bug was found to affect not only full_duplex audio (previously documented) but also turn_based audio/video paths. Image-only and text-only through WS are clean. This blocks all accuracy evaluations requiring audio or video input.

**Daily-Omni Pilot:** 20-item single-frame image test gave 40% accuracy (above 25% chance, far below 77.5% threshold). Vision encoding confirmed working (60 encodes, ~300ms/frame). Multi-frame needed for competitive accuracy, blocked by WS NaN bug with video content parts.

**VideoMME Data:** 95GB / 20 zip archives present at `/workspace/shared_assets/datasets/lmms-lab/Video-MME/`. `subtitle.zip` + `videomme/` dir also present. Archives NOT extracted, evaluator directory structure NOT prepared.

## 6. Known Limitations

1. **Pipeline default-OFF:** `OMNI_T2W_PIPELINE_OVERLAP=1` must be explicitly exported. Default serial path unchanged.
2. **Vocoder on CPU:** Flow Matching is on CANN, but Vocoder remains CPU-bound. Vocoder CANN port deferred (11-operator placement failure, silent audio risk).
3. **RSS growth across sessions:** +8.1GB over 50 sessions. Single-session growth modest (+855MB over 100 rounds).
4. **Official RTF comparability:** NOT_PROVEN. LOCAL_BEST_EFFORT measurement methodology differs from official harness.
5. **Worker state in remote-backend mode:** Pre-existing Demo stack issue; each Demo test requires fresh worker.
6. **WS Multimodal NaN Logits (P0, scope expanded 2026-08-10):** Previously documented for full_duplex audio path only. Now confirmed to affect turn_based audio/video paths as well. Image-only + text-only through WS are clean. Root cause: undetermined (active investigation on `fix/ws-multimodal-nan` branch).

## 7. Complete Gate Matrix

| Gate | Status | Key Result |
|------|--------|------------|
| Config Freeze | ✅ PASS | 4 files canonicalized |
| Pipeline Cross-Validation | ✅ PASS | 1.63× speedup, 0 errors |
| E2E Performance ON | ✅ PASS | RTF=0.452 |
| E2E Performance OFF | ✅ PASS | RTF=0.575 |
| 50-Session Reuse | ✅ PASS | 50/50, 0 rejections |
| 100-Round Soak | ✅ PASS | 100/100, 537 T2W, depth≤3 |
| Resource Monitoring | ✅ PASS | No leaks, 0 backlog |
| Demo Health | ✅ PASS | Backend+Worker+Gateway |
| Demo Text Chat | ✅ PASS | Valid UTF-8 via Gateway |
| Demo Duplex Audio | ✅ PASS | Valid WAV via Gateway |
| Accuracy (4 metrics) | ❌ BLOCKED/FAIL | WS multimodal NaN bug; Daily-Omni single-frame 40% |

## 8. Fallback Path

If pipeline causes issues at submission time:
```bash
# Disable pipeline, use serial F16:
OMNI_T2W_DEVICE=cann-flow-only \
OMNI_T2W_DRAIN_TIMEOUT_MS=5000 \
ASCEND_RT_VISIBLE_DEVICES=0 \
build/bin/llama-omni-server \
  -m .../MiniCPM-o-4_5-F16.gguf \
  --host 127.0.0.1 --port 18094 \
  -ngl 999 --device CANN0 \
  --ctx-size 4096 --batch-size 512 --ubatch-size 512 \
  --split-mode layer -t 4
```
Serial F16 RTF=0.575 (LOCAL_BEST_EFFORT), still competitive.

## 9. Artifacts

| Artifact | Path |
|----------|------|
| Binary | `build/bin/llama-omni-server` |
| Model | `/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf` |
| Gate table | `submission/FINAL_GATE_TABLE.md` |
| Phase 2 results | `benchmarks/results/formal/phase2_v2_*.json` |
| Phase 3 results | `benchmarks/results/formal/phase3_demo_*.json` |
| Cross-validation | `benchmarks/results/final_f16_freeze_e2e.json` |
| 50-reuse gate | `scripts/f6_freeze_p3a_50_reuse.py` |
| Soak gate | `scripts/f6_freeze_p3b_soak.py` |
| Phase 2 test | `scripts/f6_phase2_perf_v2.py` |
| Phase 3 test | `scripts/f6_phase3_demo_path_v2.py` |
| Pipeline impl | `b458846`, `051e993` |
| Plan | `/root/.claude/plans/shiny-dancing-acorn.md` |

## 10. Submission Checklist

- [x] Binary frozen (SHA verified)
- [x] Canonical launch command documented
- [x] All env vars documented
- [x] Performance gates PASS
- [x] Stability gates PASS
- [x] Demo path gates PASS
- [x] Fallback path preserved
- [x] Final gate table published
- [x] Known limitations documented
- [ ] Accuracy benchmarks (evaluators present, data prep needed)
- [ ] Official RTF (local measurement done, comparability NOT_PROVEN)
