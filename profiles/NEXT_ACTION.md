# NEXT ACTION

**Date**: 2026-07-29
**Session**: BREAKTHROUGH_CHECKPOINT complete
**Current State**: CANN_FLOW = INTEGRATION_CANDIDATE, CANN_VOCODER = INTEGRATION_CANDIDATE, RTF=0.274

---

## Immediate (Complete Before Session End)

1. ✅ 4 audits complete (number reconciliation, reachability, env semantics, profile percentage)
2. ✅ Evidence manifest + SHA256SUMS written
3. ✅ STATUS.md, HANDOFF.md updated
4. ⬜ AUDIT.md appended with checkpoint entries
5. ⬜ Git commit all checkpoint docs
6. ⬜ Git tag `cann-flow-vocoder-rtf027-20260729`
7. ⬜ Prompt user to manually type `/compact`

---

## Next Session — Phase 2: Production Gates

### Priority Order

1. **Demo smoke** — basic end-to-end test with CANN Flow+Vocoder. Does it produce sensible audio end-to-end?
2. **Bucket characterization** — first/warmup/steady/tail per-chunk RTF with proper bucketing
3. **Internal audio correctness** — blind A/B listening test (CANN vs CPU reference)
4. **30min stability** — extended soak with CANN Flow+Vocoder, verify no crash/degradation
5. **1hr stability** — longer stability test
6. **KV cache regression** — verify OMNI_KV_CACHE_REUSE=1 with CANN Flow+Vocoder (HIT/MISS/OFF)
7. **Multi-prefix + T2W lifecycle** — multiple system prompts, T2W lifecycle validation

### Gate Criteria

| Gate | Criteria |
|------|----------|
| Demo smoke | Produces valid audio, no crash |
| Bucket characterization | All 4 buckets quantified, first-chunk overhead explained |
| Internal audio correctness | No statistically detectable degradation vs CPU reference |
| 30min stability | 0 crashes, 0 CANN errors, RTF consistent |
| 1hr stability | 0 crashes, 0 CANN errors, no memory leak |
| KV cache regression | HIT produces valid audio, performance not degraded |

---

## Next Session — Phase 3: Further Optimization

### Optimization Priority (Corrected)

1. **Graph execution reuse** — #1 target (launch overhead ~112ms, 72% of Flow wall time)
2. **Operator fusion** — reduce 188k kernels (element-wise fusion, norm+scale, transpose elimination)
3. **Im2col optimization** — fused conv1d or custom AscendC kernel (15ms/chunk, 10% of Flow)
4. **Async H2D/D2H** — reduce 4ms transfer overhead

### Constraint

- Single variable change per experiment
- No silent CANN→CPU fallback
- No cross-chunk caching without semantic equivalence proof
- No new NPU profiler while one is already running

---

## Canonical Command (for all future experiments)

```bash
OMNI_T2W_DEVICE=cann-flow-only \
OMNI_VOC_DEVICE=gpu \
OMNI_T2W_PROFILE=2 \
./build/bin/llama-omni-cli \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
  --mmproj /workspace/models/MiniCPM-o-4_5-gguf/mmproj-Q4_K_M.gguf \
  -ngl 8 \
  --test-start 0 \
  -tc 4
```
