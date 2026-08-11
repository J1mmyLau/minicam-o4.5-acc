# CANN Vocoder — Dataflow

**Date**: 2026-07-29
**Phase**: P3 (sub-deliverable)
**Status**: DRAFT (to be updated with measured timings from P8 profiling)

---

## Current Dataflow (P3 source audit)

```
Flow (CANN NPU)
        │
        ▼ D2H (aclrtMemcpy device→host)
CPU memory: mel_bct (std::vector<float>)
        │
        ▼ CPU prepend mel cache
CPU memory: mel_in_bct
        │
        ▼ H2D (hg_backend_tensor_set)
Vocoder (CANN NPU)  ←  OMNI_VOC_DEVICE=gpu
        │
        ▼ D2H (hg_read_tensor_2d_tb_f32)
CPU memory: wave_bt_out
        │
        ▼ write WAV
```

## Key Observations

1. **Double transfer**: Flow output must D2H → CPU cache → H2D to Vocoder. This is the primary data residency optimization target (P10).

2. **Separate backends**: Flow and Vocoder each create independent `ggml_backend_cann_init()` instances. Each has its own stream, context, and device buffers.

3. **No buffer sharing**: Mel tensors are in CPU `std::vector<float>` between flow and vocoder. No shared NPU buffer exists.

## Target Dataflow (P10 optimization)

```
Flow (CANN NPU)
        │
        ▼ NPU-resident mel tensor (shared/aliased buffer)
        │  (skip D2H+H2D round-trip if Flow output dtype==Vocoder input dtype)
        │
Vocoder (CANN NPU)
        │
        ▼ D2H (audio output must go to CPU for WAV writing)
CPU memory: wave_bt_out
```

Requires:
- Flow output tensor must be in a dtype/layout compatible with Vocoder input
- Stream synchronization between flow and vocoder backends
- Lifetime management (flow tensor must outlive until vocoder compute completes)
- Feature flag: `OMNI_VOC_CANN_DEVICE_HANDOFF=1` (default 0)
