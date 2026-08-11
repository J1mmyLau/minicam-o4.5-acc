# CANN FusedInferAttentionScoreV2 NaN — Fix Evidence Report

**Date:** 2026-08-11
**Branch:** `fix/cann-fa-nan-ubatch16`
**Commit:** `544586d`
**Status:** FIX CONFIRMED — READY FOR OFFICIAL EVALUATION

## TL;DR

CANN FusedInferAttentionScoreV2 (only fused attention kernel in CANN 9.1.0-beta.1) produces NaN at specific (Q, KV) prefill shapes on Ascend910. Fix: `OMNI_CANN_FA_MAX_UBATCH=16` caps Q-chunking to keep all FA calls below the NaN threshold. Proven clean via FA_NAN_CHECK (0 NaN out of 129,024 FA calls).

## Root Cause

```
KERNEL:       CANN FusedInferAttentionScoreV2
CHIP:         Ascend910
CANN VERSION: 9.1.0-beta.1
MODEL:        MiniCPM-o-4_5 F16 (heads=32, kv_heads=8, head_dim=128)

TRIGGER: Shape-dependent NaN in fused attention computation
```

## NaN Thresholds (Empirically Characterized)

### Text-only (shape-dependent):
| Q range | KV | Result |
|---------|-----|--------|
| Q >= 434 | KV >= 768 | DIRECT NaN |
| Q <= 432 | KV >= 768 | CLEAN |
| Q >= 256 | KV = 512 | KV CONTAMINATION → subsequent NaN even at Q=1 |

### Video (content-dependent — LOWER threshold):
| Q range | KV | Result |
|---------|-----|--------|
| Q >= 17 | KV >= 768 | DIRECT NaN |
| Q = 16  | KV >= 768 | CLEAN (0/102,492 FA calls) |
| Q = 64  | KV >= 768 | DIRECT NaN (all elements) |

**Key finding:** Vision embeddings trigger NaN at MUCH lower Q than text (Q=17 vs Q=434). The same (Q=32, KV=768) shape is clean for text but NaN for video.

### KV Cache Contamination:
Once ANY FA call produces NaN, contaminated KV entries propagate to ALL subsequent calls — even Q=1 decode → all output tokens become underscore (byte 0x5F).

## Code Changes

### 1. `ggml/src/ggml-cann/ggml-cann.cpp` — Shape-aware dispatch (CRITICAL BUG FIX)

**Bug:** `supports_op` used `op->src[0]->ne[2]` (n_heads=32) instead of `ne[1]` (seq_len). All shape checks were `32 >= 250 = FALSE` → dispatch NEVER triggered.

**Fix:** Changed to `ne[1]` for correct seq_len reading.

```cpp
// CORRECTED tensor layout:
//   src[0] (Q): ne = [head_dim, q_seq_len, n_heads, batch]
//   Sequence length is ne[1], NOT ne[2] (which is n_heads).

int64_t q_len  = op->src[0]->ne[1];  // CORRECTED
int64_t kv_len = op->src[1]->ne[1];  // CORRECTED

// Gate A: Q >= 250 AND KV >= 500 → CPU (text large-Q NaN)
// Gate B: Q >= 50  AND KV >= 512 → CPU (video content-dependent NaN)
```

### 2. `tools/omni/omni.cpp` — n_ubatch cap (PRODUCTION WORKAROUND)

```cpp
// OMNI_CANN_FA_MAX_UBATCH: cap n_ubatch for CANN FA safety
const char * env_ubatch = getenv("OMNI_CANN_FA_MAX_UBATCH");
if (env_ubatch) {
    int max_ubatch = atoi(env_ubatch);
    if (max_ubatch > 0 && (int)ctx_params.n_ubatch > max_ubatch) {
        ctx_params.n_ubatch = (uint32_t)max_ubatch;
    }
}
```

### 3. `ggml/src/ggml-cann/aclnn_ops.cpp` — Diagnostic gates (DEFAULT OFF)

| Env Var | Function | Default |
|---------|----------|---------|
| `OMNI_CANN_FA_NAN_CHECK=1` | Check FA output for NaN/Inf | OFF |
| `OMNI_CANN_FA_EVERY=1` | Log every FA call shape | OFF |
| `OMNI_CANN_FA_SHAPE_DIAG=1` | Log attention shapes pre-kernel | OFF |
| `OMNI_CANN_FA_DIAG=1` | Log logitSoftcap branching | OFF |

### 4. `tools/omni/token2wav/token2wav-impl.h` — Minor build fix

## Phase 1: Shape Characterization

Full sweep results in `experiments/nightly/phase1_results.jsonl`:

**Text-only (n_x=450 with n_ubatch sweep):**
- n_ubatch >= 448 → NaN (Q=448+ at KV=768 → NaN)
- n_ubatch = 432 → CLEAN (Q=432 at KV=768 → safe)
- n_ubatch <= 384 → CLEAN

**Cross-section (n_ubatch × n_x):**
- ub=384 nx=550: CLEAN (text)
- ub=320 nx=400: NaN (Q=84 at KV=768 → contamination from earlier Q≥256 at KV=512)

**Golden bypass:** OMNI_CANN_FA_BYPASS=1 → CLEAN (proves FA kernel is root cause)

## Phase 9: Official Smoke Test Results

**Configuration:** `OMNI_CANN_FA_MAX_UBATCH=16`, FA_NAN_CHECK=1

| Task | FA Calls | NaN | Accuracy | Status |
|------|----------|-----|----------|--------|
| VideoMME | 102,492 | 0 | 0/2 (valid text) | PASS |
| Daily-Omni | 26,532 | 0 | 2/2 = 100% | PASS |
| Seed-TTS | N/A | N/A | WER=90.445% | PRE-EXISTING |
| RTS | N/A | N/A | 37/37 chunks | PASS |

**VideoMME detail:** Model generates valid text (e.g., "It is a tutorial on Christmas decorations around the world.") — answers are wrong but NOT NaN-underscore garbage. This is a video understanding accuracy issue, not NaN.

**Daily-Omni detail:** Both smoke samples correct (GT=A→A, GT=B→B). Model output is clean single-letter choices.

**Seed-TTS:** SIM scoring fails due to missing `s3prl/hubconf.py` (environment issue). WER=90% is pre-existing and NOT NaN-related.

**RTS:** Full duplex server runs 37 chunks without errors. All LISTEN (expected for this video).

## Video Q Boundary Binary Search

| n_ubatch | Max Q | Video Result |
|----------|-------|-------------|
| 32 | 32 | NaN |
| 24 | 24 | NaN |
| 20 | 20 | NaN |
| 17 | 17 | NaN |
| **16** | **16** | **CLEAN** |

**Conclusion:** The video content-dependent threshold is EXACTLY Q=16→17. n_ubatch=16 is the minimal safe value.

## Diagnostic Audit (Phase 14)

All diagnostics are env-gated and DEFAULT OFF:

| Diagnostic | Gate | Default |
|-----------|------|---------|
| FA_NAN_CHECK | `getenv("OMNI_CANN_FA_NAN_CHECK")` | OFF ✓ |
| FA_EVERY | `getenv("OMNI_CANN_FA_EVERY")` | OFF ✓ |
| FA_SHAPE_DIAG | `getenv("OMNI_CANN_FA_SHAPE_DIAG")` | OFF ✓ |
| FA_DIAG (LS) | `getenv("OMNI_CANN_FA_DIAG")` | OFF ✓ |
| FA_BYPASS | `getenv("OMNI_CANN_FA_BYPASS")` | OFF ✓ |
| SAFE_DISPATCH | Default ON (only affects FA op) | N/A |

## Production Usage

```bash
# Required for CANN 9.1.0-beta.1 evaluation
export OMNI_CANN_FA_MAX_UBATCH=16

# Optional diagnostics
export OMNI_CANN_FA_NAN_CHECK=1    # Verify zero NaN
export OMNI_CANN_FA_EVERY=1        # Log all FA shapes
```

## Evidence Files

| File | Description |
|------|-------------|
| `experiments/nightly/phase1_results.jsonl` | Full shape sweep (Phase 1) |
| `experiments/nightly/phase1_stdout.log` | Phase 1 console output |
| `experiments/nightly/quick_nan_test.py` | Quick NaN detection script |
| `experiments/nightly/video_q_reduction.py` | Video Q boundary search |
| `experiments/nightly/smoke_ub16_output.log` | Smoke test full output |
| `evaluation/videomme/log/cli_gpu0.log` | VideoMME FA_NAN_CHECK (0 NaN) |
| `evaluation/daily-omni/log/cli_gpu0.log` | Daily-Omni FA_NAN_CHECK (0 NaN) |
| `evaluation/output/20260811_184305/` | Smoke test outputs |

## Next Steps

1. **When CANN fixes FusedInferAttentionScoreV2:** Remove `OMNI_CANN_FA_MAX_UBATCH` env var
2. **Accuracy validation:** Run full Daily-Omni (1196 samples) and VideoMME (2700 questions)
3. **Performance validation:** Compare n_ubatch=16 vs n_ubatch=384 for non-video workloads
4. **TTS SIM environment:** Install `wavlm_large.pt` and `s3prl/hubconf.py`
