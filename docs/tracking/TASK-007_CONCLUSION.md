# TASK-007 Conclusion — Optimization Candidate Prioritization

**Date:** 2026-07-16
**Profile:** 20260716-131033-full-omni-msprof
**Baseline:** 3f7a7f0

---

## 1. Candidate Count

- Total candidates: 8
- Layers: L2 (low-risk source) = 4, L3 (pipeline) = 2, L5 (operator) = 2
- No L1 (zero-code) candidates — none identified that would change the profile meaningfully
- No L4 (scheduling/concurrency) candidates — single-session omni test does not exercise this

## 2. Ranking Method

- **Formula:** priority_score = Potential_Gain × Confidence × Reproducibility ÷ (Correctness_Risk × Engineering_Cost)
- Each dimension scored 1–5 (higher = more gain/confidence/repro/risk/cost)
- Tiebreaker: lower engineering cost wins
- Key insight: E2E wall time is 130s, but device time is only 2.6s (2%). Host-side optimizations affect 10.3s (8%). Pipeline optimizations affect the CPU TTS path (~110s, 85%).

## 3. Top 5 Candidates

**1. CAND-002: Sync memcpy → Async memcpy** (Score: 8.89, Layer 2)
- Cost: 2325ms, Gain: MEDIUM (2–5% of host API path)
- Risk: MEDIUM, Engineering: MEDIUM

**2. CAND-003: Memory allocation pooling (buffer reuse)** (Score: 6.67, Layer 2)
- Cost: 1170ms, Gain: MEDIUM (2–5% of host API path)
- Risk: MEDIUM, Engineering: MEDIUM

**3. CAND-004: Reduce Cast + Transpose + Contiguous overhead** (Score: 2.25, Layer 2)
- Cost: 336ms, Gain: MEDIUM (2–5% of device time)
- Risk: MEDIUM, Engineering: HIGH

**4. CAND-001: Reduce aclrtSynchronizeStream calls** (Score: 7.50, Layer 2)
- Cost: 173ms, Gain: LOW (<2% of host API path)
- Risk: LOW, Engineering: LOW

**5. CAND-005: Fuse element-wise operations** (Score: 0.50, Layer 5)
- Cost: 126ms, Gain: LOW (<2% of device time)
- Risk: MEDIUM, Engineering: HIGH

## 4. First Batch — 3 Experiments

| Exp | Candidate | Target | Layer | Risk |
|-----|-----------|--------|-------|------|
| EXP-001 | CAND-002 | Sync memcpy → Async memcpy | L2 | MEDIUM |
| EXP-002 | CAND-003 | Memory allocation pooling | L2 | MEDIUM |
| EXP-003 | CAND-004 | Reduce Cast + Transpose + Contiguous overhead | L2 | MEDIUM-HIGH |

**Execution order:** EXP-001 → EXP-002 → EXP-003 (sequential, each verified before next)

## 5. Why Not Optimize MatMul First?

- MatMulV2 is 68-75% of device time, but **device time is only 2.6s out of 130s E2E**
- The E2E is dominated by CPU Token2Wav (~110s) and host-side API overhead (~10s)
- Host-side memcpy (2.3s) alone approaches the total device compute time
- MatMul optimization has HIGH engineering cost (shape analysis, per-shape tuning) and LOW confidence (median cube utilization is already 87%)
- Fixing host overhead first frees resources and clarifies what the true device bottleneck is

## 6. Why Not AscendC?

**AscendC Gate: NOT SATISFIED**

Required conditions (none met):
1. ❌ Specific inefficient MatMul shape identified
2. ❌ ACLNN GEMM proven suboptimal for target shape
3. ❌ Cast/Transpose/sync/memory overhead eliminated as confounding factors
4. ❌ Frozen operator contract for custom kernel
5. ❌ Measurable E2E gain estimate from custom kernel

## 7. Current Risks

- **Correctness:** All L2 changes touch the GGML CANN backend — numerical regression is possible
- **Measurement:** E2E wall time has high variance (68s baseline, 36-121s range) — small improvements may be lost in noise
- **Scope creep:** TTS (CPU, 85% of E2E) is the real bottleneck — NPU optimizations have limited E2E impact
- **Reproducibility:** Single-profile evidence — needs verification across multiple runs

## 8. Next Task

**EXP-001: Sync memcpy → Async memcpy**

- Status: PLANNED (not executing)
- Directory: `harness/experiments/EXP-001-sync-memcpy/`
- Do NOT auto-execute — wait for explicit instruction
- After EXP-001: evaluate, then EXP-002, then EXP-003
- After all 3: re-profile, re-evaluate MatMul/AscendC gate
