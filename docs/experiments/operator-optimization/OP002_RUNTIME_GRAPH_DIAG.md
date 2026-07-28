# OP002: ADD+RMSNorm Runtime Fusion Qualification — DEFINITIVE

**Date:** 2026-07-28
**Binary:** `6913c972` (llama-omni-cli), `43dad63e` (libggml-cann)
**Method:** Source-level instrumentation of `ggml_backend_cann_graph_compute` + `ggml_cann_can_fuse`
**Env:** `GGML_CANN_FUSION_DIAG=1`, `GGML_CANN_OPERATOR_FUSION=1`, `-ngl 8`

---

## 1. Graph Trace Summary

| Metric | Value |
|--------|-------|
| Total CANN graph evaluations | 1,132 (full run) |
| Graphs with max_dim=128 | 10 (first graphs, ROPE-only) |
| Graphs with max_dim=4096 | 1,065 (flow model) |
| Graphs with max_dim=1152 | **0** (Talker LLM NEVER reaches CANN) |
| Graphs with ADD+RMS_NORM | 1,065 (all 4096-dim flow model) |
| Fused dispatches | ~18 (g=58, 118, 321, ... periodic) |

### Graph Fingerprints

```
 994  nodes=3  max_dim=4096  add=1 rms=1  rope=0   (flow model decode forward)
  71  nodes=5  max_dim=4096  add=1 rms=1  rope=0   (flow model prefill forward)
  57  nodes=2  max_dim=4096  add=1 rms=0  rope=0   (flow model residual only)
  10  nodes=2  max_dim=128   add=0 rms=0  rope=1   (flow model attention ROPE warmup)
```

## 2. Root Cause: GGML_OP_OFFLOAD_MIN_BATCH

The CANN backend's offload gate (`ggml-cann.cpp:3207`):

```cpp
const int min_batch_size = getenv("GGML_OP_OFFLOAD_MIN_BATCH")
    ? atoi(getenv("GGML_OP_OFFLOAD_MIN_BATCH")) : 32;
```

`ggml_backend_cann_offload_op()` (line 3085):

```cpp
return op->ne[1] >= dev_ctx->op_offload_min_batch_size && op->op != GGML_OP_GET_ROWS;
```

**During decode, `ne[1] = 1` (single token).** All element-wise ops (ADD, RMS_NORM, ROPE, MUL, SiLU) fail the `ne[1] >= 32` threshold and stay on CPU.

### Why MatMul Still Works on CANN

MatMul and other weight-bearing ops are pre-assigned to the weight tensor's backend by the scheduler — they bypass the `offload_op` threshold. Only "free-floating" element-wise ops without weight affinity are subject to the threshold.

### Crash with MIN_BATCH=1

Setting `GGML_OP_OFFLOAD_MIN_BATCH=1` causes a `GGML_ABORT` in `ggml_backend_sched_graph_compute_async` — the scheduler cannot handle offloading single-token element-wise ops because pre-allocated CPU buffer tensors clash with CANN backend assignment.

## 3. Talker LLM Fusion Qualification

| Condition | Status | Evidence |
|-----------|--------|----------|
| ADD→RMS_NORM in source | ✅ | `voxcpm2_transformer.cpp:692-700` |
| Pattern exists in GGML graph | ✅ | 27 layers × 2 = 54 per decode step |
| Nodes on CANN backend | ❌ | `op_offload_min_batch_size=32 > ne[1]=1` |
| ADD next op = RMS_NORM in graph | ❌ UNREACHABLE | Not on CANN |
| use_count = 1 | ❌ UNREACHABLE | Not on CANN |
| CANN fusion would activate | ❌ UNREACHABLE | Never reaches `ggml_cann_can_fuse` |

**FINAL_QUALIFICATION: FAILED — Talker LLM element-wise ops are intentionally CPU-resident during decode.**

## 4. What DOES Fuse

The 4096-dim flow model (cross-modal LLM→T2W projector) has ~18 successful fusions per run at ~58-graph intervals. These are prefill-like graphs with `ne[1] >= 32`. The fusion reduces ADD+RMS_NORM from 2 kernel launches to 1 for these graphs.

**The V0 fusion is already working for the flow model at no additional development cost.**

## 5. Impact on Optimization Strategy

### Ineffective for Talker LLM Decode
- V0 CANN fusion: cannot reach Talker LLM ops
- V1 AscendC custom fusion: same blocking constraint
- Any CANN-based element-wise fusion: blocked by `op_offload_min_batch_size`

### Effective Optimization Targets
1. **Candidate E: Runtime Overhead** — `aclrtSetDevice` caching (6,559 calls), `aclrtSynchronizeStream` reduction. Host-side, benefits ALL models.
2. **Talker LLM CANN compute offload** — Investigate whether raising `op_offload_min_batch_size→1` can be made safe (requires scheduler changes)
3. **Weight-level optimizations** — MatMul, attention kernels (already on CANN)

## 6. Verdict — Precise Terminology

```text
OP002_ADD_RMSNORM_SOURCE_PATTERN        = PRESENT
OP002_TALKER_RUNTIME_CANN_REACHABILITY  = NOT_REACHABLE_UNDER_CURRENT_OFFLOAD_POLICY
OP002_CURRENT_TOPOLOGY_VERDICT          = REJECTED_FOR_CURRENT_TALKER_DECODE_PATH
```

**Not "architecturally impossible"** — the constraint is policy-driven (`GGML_OP_OFFLOAD_MIN_BATCH=32`). If the scheduler/offload policy is modified in the future, OP002 should be re-evaluated. But under current policy, element-wise ops are CPU-resident during Talker decode.

If a future change modifies the offload policy or Talker backend placement, OP002 should be re-evaluated with the same diagnostic methodology.

## 7. Next Action

**Pivot to Candidate E: Runtime Overhead Reduction.**

This requires:
1. Audit `aclrtSetDevice` call sites in ggml-cann.cpp
2. Implement device caching (only call `aclrtSetDevice` when device actually changes)
3. Reduce `aclrtSynchronizeStream` calls where safe
4. A/B test with msprof kernel timing as primary metric

---

**Evidence files:**
- `/tmp/gtrace2.stderr` (full graph trace, 1,132 graphs)
- `/tmp/diag_final.stderr` (fusion diagnostic, 9,094 summaries)
- `V0_FUSION_VERDICT.md` (V0 A/B results)
- `ROPE_FP16_DEFINITIVE_VERDICT.md` (RoPE rejection)
