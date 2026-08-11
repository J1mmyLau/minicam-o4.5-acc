# F6 Phase 2 — Step 5: Candidate Amdahl Ranking
## 2026-08-04 | COMPLETE

Data basis: S13 strict 120 budget (Step 2). W0 p50 = 4830ms:
`decode→speak 142ms (2.9%) + overhead 320ms (6.6%) + T2W_inf 4490ms (93.0%)`.
request→W0 adds prefill 102ms (2.1%, already KV-cached 2.5×).

**Amdahl law governs every row below: no candidate can remove more than its
target bucket's share of W0.** A 3% bucket, perfectly removed, is worth 3%.

---

## Ranking (most → least attractive)

| # | Candidate | Target stage | % of W0 | Theoretical cap | Runtime reachability | Impl complexity | Correctness risk | Audio quality risk | **Decision** |
|---|-----------|--------------|--------:|-----------------|----------------------|-----------------|------------------|--------------------|--------------|
| **1** | **T2W CANN device move** (`OMNI_T2W_DEVICE=cann-flow-only` + `OMNI_VOC_DEVICE=gpu`) | T2W_inf (CPU flow+vocoder) | **93.0%** | W0 4830→**~990ms** (≈79% cut). Validated in `3fc0ed5`: first-audio 5921→1754ms (3.4×), per-window 4194→648ms (6.5×), RTF 4.19→0.65 | **REACHABLE NOW** — env vars honored by committed worker-thread CANN backend; zero code change | **LOW** | MED — must re-validate on current FP16 build (thread-ownership fix already merged) | LOW-MED — device placement; verify PCM (wav sample rate/shape) | **OPTIMIZE_FIRST** |
| 2 | Workspace reuse / allocation reduction (T2W per-window) | overhead + per-window alloc | ≤6.6% | ≤320ms | Reachable | MED-HIGH | MED | LOW | EXPERIMENT (secondary) |
| 3 | Reduce decode steps (earlier first-speak) | decode→speak + TTS audio-gen | 2.9% + partial overhead | ≤ ~450ms (9%) | Changes generation semantics (skip think, earlier EOS) | HIGH | HIGH | MED | EXPERIMENT (semantic risk — not first) |
| 4 | Sampler CPU optimization | decode→speak (sampler) | 2.9% | ≤142ms | Reachable | MED | MED | LOW | DEFER |
| 5 | Sync reduction | decode→speak + T2W handoff | 2.9% + ~0 | ≤142ms | Reachable | MED | MED | LOW | DEFER |
| 6 | Stable-shape CANN graph (LLM decode) | decode→speak (CANN forward) | 2.9% | ≤142ms | Reachable (LLM already on CANN) | HIGH | MED | LOW | DEFER |
| 7 | Talker trigger path | decode→speak (trigger check) | ≈0 (queue≈0ms) | ≈0 | — | — | — | — | **REJECT_BY_AMDAHL** |
| 8 | Queue/CV optimization | queue→T2W | ≈0 (measured 0ms) | ≈0 | — | — | — | — | **REJECT_BY_AMDAHL** |
| 9 | MTP / NextN speculative | decode→speak | 2.9% theoretical | ≤142ms | **NOT_REACHABLE** (Step 4: no head tensors, no runtime, forbidden by scope) | — | — | — | **REJECT_BY_SCOPE** |
| 10 | Operator fusion (flow/vocoder on CANN) | T2W_inf | 93% | post-#1 additional | Requires CANN flow/voc first (#1) | HIGH | MED | MED | EXPERIMENT (after #1) |

---

## Rationale for the top pick

1. **Amdahl** — T2W_inf is 93.0% of W0. It is the only bucket where an optimization
   can move the number by *seconds*, not milliseconds. Every decode-side candidate
   (#3–#9) is bounded by ≤2.9–9%.

2. **Reachability** — the CANN path is already implemented and committed
   (`3fc0ed5` worker-thread flow backend, `0828de2` fail-fast guards,
   `23a2f96` harness env). The S13 baseline simply never set the two env vars,
   so it ran the CPU fallback. This is a **runtime config change, not a code
   change** — it cannot violate any Phase 2 constraint (CHUNK_SIZE=25 untouched,
   B6b untouched, MTP untouched).

3. **Validated upside** — `3fc0ed5` measured 3.4× first-audio and 6.5× per-window
   on the Q4-era build. Reproducing on the current FP16 canonical build is Step 6.

4. **Risk is manageable** — the thread-ownership root cause (CANN backend created
   on main thread, used on worker) was the blocker; the worker-thread init fix is
   merged. Remaining risk is FP16-specific behavior + PCM fidelity, both verifiable.

---

## Explicit non-candidates (why)

- **prefill (102ms, 2.1%)** — already optimized 2.5× by static-prefix KV cache
  (Step 8/9 closure). Remaining 102ms is largely CANN graph warm + prompt append.
- **TTS audio-gen (318ms)** — lives in the overhead bucket; no separate operator
  cost available in the log. Subsumed by #2/#3 as secondary work.

---

## Artifacts

| Artifact | Path |
|----------|------|
| Ranking (this file) | `docs/F6_PHASE2_STEP5_AMDAHL_RANKING.md` |
