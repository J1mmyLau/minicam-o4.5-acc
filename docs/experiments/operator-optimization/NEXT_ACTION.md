# NEXT_ACTION — CANN Flow + Vocoder Phase 3 → Phase 4

**HEAD:** 3e7bcf0
**Tag:** cann-flow-vocoder-aclgraph-rtf0229-20260729
**Updated:** 2026-07-29 12:50 UTC

---

## GATE SEQUENCE (execute in order, no skip)

### G1: Performance number consistency audit (P0)
- Command: Review PHASE3_PERFORMANCE_RECONCILIATION.md
- Verify: 155ms canonical vs 145ms internal correctly attributed
- Verify: RTF 0.229 calculation (111+118)/1000 correct
- Output: AUDIT.md entry + PASS/FAIL annotation

### G2: ACL Graph Capture cache-key / lifetime correctness
- File: `ggml/src/ggml-cann/ggml-cann.cpp`
- Locate: `graph_lru_cache` key derivation and `ggml_cann_graph::create_from_cgraph`
- Verify: each component of cache key
- Verify: LRU eviction logic
- Verify: capacity 12 vs utilization
- Output: written evidence in `profiles/GRAPH_CAPTURE_CACHE_AUDIT.md`

### G3: Graph ON/OFF × Fusion ON/OFF 4-quadrant A/B
- Command template:
```
GGML_CANN_ACL_GRAPH=X GGML_CANN_OPERATOR_FUSION=Y \
OMNI_T2W_DEVICE=cann-flow-only OMNI_VOC_DEVICE=gpu OMNI_T2W_PROFILE=2 \
./build/bin/llama-omni-cli \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
  --omni --test tools/omni/assets/test_case/omni_test_case/omni_test_case_ 4
```
- Quadrants: (OFF,OFF), (OFF,ON), (ON,OFF), (ON,ON)
- Per quadrant: n>=12 per-chunk samples, t2m.compute mean/p50, RTF
- Output: CSV + `profiles/GRAPH_FUSION_FOUR_QUADRANT.md`

### G4: first/warmup/steady/tail chunk statistics
- Requires G3 (ON,ON) data
- Buckets: call=0 (first), call=1-3 (warmup), call>=4 (steady), last 2 (tail)
- Per bucket: t2m.compute mean/p50/p99, n
- Output: `profiles/CHUNK_BUCKET_STATISTICS.md`

### G5: Official Benchmark harness audit
- Check: `tools/omni/assets/test_case/` — inventory all test cases
- Check: `tools/omni/` — benchmark mode flags
- Check: `Daily-Omni`, `TTS-Seed`, `Video-MME` availability
- If missing: BENCHMARK_GATE = BLOCKED_BY_EXTERNAL_HARNESS, log missing items, continue

### G6: Demo full validation
- If benchmark harness available: run and verify all WAV outputs
- Otherwise: manual 16 test cases, verify audio validity (size>1KB, no clipping)

### G7: 30-min stability
- Command: loop 30min with steady chunks, 0 CANN errors, all WAV valid
- Gate: >=30min, 0 errors, all audio passes

### G8: 1-hr stability (if G7 PASS)
- Same as G7 but 60min

### G9: KV Cache HIT/MISS/OFF regression
- Command variations with KV cache mode flags
- Verify: graph capture still works in all modes
- Verify: no performance regression vs Phase 2 baseline

### G10: Multi-prefix + corruption regression
- Command: multiple prefix tests
- Verify: cache isolation, no corruption

### G11: T2W lifecycle regression
- Command: T2W L2-L6 lifecycle
- Verify: all transitions pass

### G12: Clean-worktree reproduction
- Fresh worktree from tag
- Build from clean
- Run G3 ON,ON quadrant
- Verify RTF matches within ±3%

### G13: Submission package
- Collect all evidence
- SHA256SUMS
- Canonical command
- Performance tables

### G14: Im2col decision gate
- Only if all prior gates pass
- Calculate: Im2col_time / complete_flow_wall
- Gate: >= 3% wall share AND >= 1% projected RTF gain
- Otherwise: IM2COL_OPTIMIZATION = DEFERRED_BY_AMDAHL_OR_RISK

---

## COMMIT STRATEGY

After each gate that produces a PASS/FAIL conclusion:
1. Commit evidence docs
2. Update AUDIT.md
3. Update this NEXT_ACTION.md
4. Do NOT commit raw A/B test data unless it supports a conclusion
