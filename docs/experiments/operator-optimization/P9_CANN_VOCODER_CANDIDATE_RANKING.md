# P9: CANN Vocoder Optimization Candidate Ranking

**Date**: 2026-07-29
**Phase**: P9 — Candidate Ranking (O2-A through O2-J)
**Status**: COMPLETE

---

## 1. Ranking Methodology

Candidates ranked by **competition metric impact**: reduction in per-chunk total RTF (currently 3.71 with CANN vocoder).

Impact = (time_saved / 3710ms total T2W time) × 100%

Risk assessment: LOW (reversible flag, no correctness risk), MEDIUM (needs testing), HIGH (architectural change).

---

## 2. Candidate Ranking

### Tier 1: High Impact (total RTF improvement > 5%)

| Rank | ID | Candidate | Savings | Total RTF Impact | Risk | Effort |
|------|----|-----------|---------|------------------|------|--------|
| **1** | **O2-F** | **Flow model optimization** | 1,000-3,000ms | **27-80%** | HIGH | HIGH |
| | | Quantize/optimize token2mel (Flow) | Largest single bottleneck | Game-changing | Accuracy risk | Weeks |

> O2-F is outside the "vocoder" scope but is the only path to competition-significant improvement.

### Tier 2: Moderate Impact (total RTF improvement 1-5%)

| Rank | ID | Candidate | Savings | Total RTF Impact | Risk | Effort |
|------|----|-----------|---------|------------------|------|--------|
| **2** | **O2-A** | **Graph reuse** | 50-70ms | **1.3-1.9%** | MEDIUM | MEDIUM |
| | | Cache `ggml_cgraph` across chunks, rebuild only when T_mel changes | Eliminates per-chunk graph construction | Reuse correctness | 2-3 days |
| **3** | **O2-B** | **Galloc reuse** | 10-20ms | **0.3-0.5%** | MEDIUM | MEDIUM |
| | | Reuse `ggml_gallocr` reservation across same-shaped graphs | Combined with O2-A | Must pair with O2-A | 1-2 days |
| **4** | **P10** | **Device handoff** | 20-30ms | **0.5-0.8%** | HIGH | HIGH |
| | | Share NPU buffer between Flow→Vocoder, skip D2H+H2D | Eliminates round-trip | Stream sync, lifetimes | 3-5 days |

### Tier 3: Low Impact (total RTF improvement < 1%)

| Rank | ID | Candidate | Savings | Total RTF Impact | Risk | Effort |
|------|----|-----------|---------|------------------|------|--------|
| **5** | **O2-C** | **Context reuse** | 5-10ms | **0.1-0.3%** | LOW | LOW |
| | | Reuse `ggml_context` across chunks | Avoid per-chunk init/free | Memory management | 1 day |
| **6** | **O2-D** | **Const cache** | 5-10ms | **0.1-0.3%** | LOW | LOW |
| | | Cache STFT/sine params upload | Uploaded every chunk | Thread safety | 1 day |
| **7** | **O2-E** | **Vocoder kernel fusion** | 1-2ms | **0.03-0.05%** | HIGH | HIGH |
| | | Fuse Snake+conv1d+iSTFT into single CANN kernel | NPU time already tiny (3ms) | AscendC dev | 1-2 weeks |
| **8** | **O2-G** | **Multi-stream overlap** | 5-10ms | **0.1-0.3%** | MEDIUM | MEDIUM |
| | | Overlap upload with compute on separate streams | Limited by small vocoder graph | Stream mgmt | 2-3 days |
| **9** | **O2-H** | **FP16 vocoder** | 5-10ms | **0.1-0.3%** | MEDIUM | MEDIUM |
| | | Run vocoder in FP16 instead of FP32 | May affect audio quality | Precision audit | 2-3 days |
| **10** | **O2-I** | **Batch multi-chunk** | 10-20ms | **0.3-0.5%** | HIGH | MEDIUM |
| | | Process multiple chunks in single graph | Increases latency | Batching logic | 3-5 days |
| **11** | **O2-J** | **CPU fallback tuning** | 0ms | **0%** | LOW | LOW |
| | | Improve CPU path as fallback | CPU already 3× slower | N/A | N/A |

---

## 3. Recommended Implementation Order

### Phase 1: Quick Wins (Tier 3, implement together)

| Order | ID | Savings | Cumulative RTF | Cumulative Improvement |
|-------|----|---------|----------------|----------------------|
| 1 | O2-C + O2-D | 10-20ms | 3.71 → 3.69 | +0.5% |
| 2 | O2-A + O2-B | 60-90ms | 3.69 → 3.60 | +3.0% |

**Phase 1 total: RTF 3.71 → 3.60 (+3.0%)**

### Phase 2: Device Handoff

| Order | ID | Savings | Cumulative RTF | Cumulative Improvement |
|-------|----|---------|----------------|----------------------|
| 3 | P10 | 20-30ms | 3.60 → 3.57 | +3.8% |

### Phase 3: Beyond Vocoder

| Order | ID | Savings | Cumulative RTF | Cumulative Improvement |
|-------|----|---------|----------------|----------------------|
| 4 | O2-F (Flow opt) | 1,000-3,000ms | 3.57 → 0.5-2.5 | **+33-87%** |

---

## 4. Decision Matrix

```
                    Impact (% total RTF)
                   0%  1%  2%  3%  5%  10%  30%  80%
                   |   |   |   |   |    |    |    |
O2-A (graph)       ████████░░░░
O2-B (galloc)      ██░░
P10 (handoff)      ███░░
O2-C (context)     █░░
O2-D (const)       █░░
O2-E (kernel fus)  ░
O2-G (multi-str)   █░░
O2-H (fp16)        █░░
O2-I (batch)       ██░░
O2-J (cpu fallbck) ░
O2-F (Flow opt)    ████████████████████████████████████████████████░░░░
```

---

## 5. Top-1 Selection: O2-A + O2-B (Combined)

**Selected candidate: Graph + Galloc Reuse (O2-A + O2-B together)**

Rationale:
1. **Highest vocoder-only impact**: 60-90ms savings (55-82% of vocoder overhead)
2. **Medium risk**: Feature flag gated, reversible
3. **Medium effort**: 2-3 days implementation
4. **Synergistic**: Galloc reuse depends on graph reuse; must implement together
5. **Enables P10**: Device handoff becomes simpler with persistent graph/galloc

Implementation approach:
```cpp
// Feature flag: OMNI_VOC_GRAPH_REUSE=1 (default 0)
// In voc_hg2_runner_eval_stream:
//   if (graph_reuse_enabled && T_mel == cached_T_mel) {
//       skip ggml_init + graph build + galloc_alloc_graph
//       reuse cached ggml_context, ggml_cgraph, galloc reservation
//   }
//   Only rebuild when T_mel (mel length) changes
```

T_mel changes only when token count differs between chunks. With the same test case, T_mel is typically constant after the first chunk.

---

## 6. P10 Pre-assessment

Device handoff (P10) is ranked #3 due to high implementation risk:
- Requires stream synchronization between Flow and Vocoder backends
- Requires buffer lifetime management (Flow tensor must outlive until vocoder consumes it)
- Potential for subtle race conditions
- Savings ceiling: 20-30ms (0.5-0.8% total RTF)

**Verdict: DEFER P10 until O2-A+O2-B are implemented and validated.** The incremental benefit of P10 over O2-A+O2-B is small (~20ms), and the risk/effort ratio is unfavorable.

---

## 7. Next Action

**P11: Implement O2-A + O2-B (Graph + Galloc Reuse)**

Feature flags:
- `OMNI_VOC_GRAPH_REUSE=1` — enable graph reuse across chunks
- `OMNI_VOC_CANN_DEVICE_HANDOFF=1` — stub for P10 (future)

Implementation location: `tools/omni/token2wav/token2wav-impl.cpp`, function `voc_hg2_runner_eval_stream`
