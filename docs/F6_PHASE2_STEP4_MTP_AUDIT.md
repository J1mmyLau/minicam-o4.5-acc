# F6 Phase 2 — Step 4: MTP Reachability Audit (zero-change)
## 2026-08-04 | COMPLETE

**Verdict: `MTP_NOT_REACHABLE_WITH_CURRENT_MODEL`**

Multi-Token Prediction (MTP / NextN / speculative decode) is **not reachable** on the current build+model, and is explicitly out of scope per Phase 2 constraints (不得训练 MTP head, 不得直接启用 MTP). No code, model, or runtime changes were made.

---

## Audit Evidence

| Check | Result |
|-------|--------|
| **1. Binary draft/MTP flags** | `llama-omni-cli --help`: 14 flags total — `--audio --bench-vision --no-tts --omni --projector --ref-audio --t2w-coreml --test --test-start --tts --vision --vision-backend --vision-batch-encode --vision-coreml`. **No `--mtp`, `--draft`, `--speculative`, `--n_extend`, `--nextn`.** |
| **2. Source MTP verifier** | No `llama-mtp*` / `llama-speculative*` source files under `ggml/`. Zero refs to `mtp|multi-token|nextn|draft|speculative` in `tools/omni/omni.cpp` or `ggml/src/ggml-cann/ggml-cann.cpp`. |
| **3. Model MTP/NextN tensors** | `MiniCPM-o-4_5-F16.gguf` parsed (GGUF v3, **399 tensors**, 27 KV). **No `token_embd_next`, `ntn`, `*.mtp.*`, or NextN tensors.** Only the shared `token_embd.weight` exists. |
| **4. omni stream_decode speculative path** | None. `stream_decode` has no draft/speculative branch; decode is single-stream autoregressive into the talker/TTS handoff. |
| **5. CANN backend status** | LLM transformer fully on CANN: 246 CANN markers in S13 log, `n_gpu_layers` → 123 layers offloaded. T2W (flow/vocoder) on CPU (`voc_hg2_model: CPU backend using 8 threads`). No MTP/speculative operator support in the CANN backend. |

---

## Conclusion

MTP would require **both**:
1. a **new model file** with a trained MTP/NextN head (current GGUF has none), and
2. a **runtime port** (speculative decode path + CANN operators for the head).

The user's constraints explicitly forbid (1) training the MTP head and (2) enabling MTP. Combined with zero existing support, MTP is **doubly not reachable**:

- `MTP_NOT_REACHABLE_WITH_CURRENT_MODEL` (no head tensors)
- Even `MTP_REQUIRES_RUNTIME_PORT` is moot without a model that has the head.

**Decision: REJECT_BY_SCOPE (not an Amdahl candidate).** The speculative-decode class of optimization is off the table for this phase.

---

## Artifacts

| Item | Path |
|------|------|
| Audit (this file) | `docs/F6_PHASE2_STEP4_MTP_AUDIT.md` |
| Tensor-name parser (inline) | reproduced above; no artifact persisted |
