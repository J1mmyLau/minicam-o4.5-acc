# Official Benchmark Status — llama.cpp-omni Race Track 1

**Date:** 2026-07-30
**Status:** BLOCKED_EXTERNAL — official harness not yet available in workspace

---

## Competition Rules (Published 2026-07-30)

Per the official competition page (ascend.openbmb.cn):

### Sub-Track: llama.cpp-omni
- **Primary metric:** Per-chunk RTF
- **Three required benchmarks:**
  1. Daily-Omni
  2. TTS-Seed
  3. Video-MME
- **Accuracy requirement:** Candidate accuracy vs baseline ≤ 2 percentage point drop on each benchmark

### Required Deliverables
1. Reproducible code + environment config
2. Benchmark scripts and evaluation results
3. Performance test and optimization analysis report
4. Runnable Demo for the sub-track
5. Deployment, usage, and reproduction documentation

---

## Current Availability

| Component | Status | Location |
|-----------|--------|----------|
| llama-omni-cli (optimized binary) | ✅ Available | `/workspace/llama.cpp-omni-operator/build/bin/` |
| Competition eval infrastructure | ⚠️ Partial | `/workspace/llama.cpp-omni-official-eval/competition/` |
| benchmark_client.py | ✅ Available | Server-based testing framework |
| Official metric definition | ⚠️ Provisional | `METRIC_CONTRACT.md` — needs starter kit verification |
| Daily-Omni harness | ❌ Not found | Not in workspace |
| TTS-Seed harness | ❌ Not found | Not in workspace |
| Video-MME harness | ❌ Not found | Not in workspace |
| Official starter kit | ❌ Not arrived | Referenced in METRIC_CONTRACT.md as "pending" |
| Official RTF timing script | ❌ Not found | Internal timing used instead |

---

## Key Gap: Server vs CLI

The competition evaluation infrastructure (`benchmark_client.py`) targets the **llama-omni-server** (long-running HTTP/WebSocket service), not the CLI binary (`llama-omni-cli`). This means:

1. Need to build and configure `llama-omni-server` with the same CANN optimizations
2. Need to verify the server binary incorporates CANN Flow, CANN Vocoder, ACL Graph Capture, and Fusion
3. The CLI-based RTF measurements (0.229 internal) may not directly translate to server-based measurements

---

## Pre-Flight Actions (When Harness Arrives)

### P1: Obtain official materials
- [ ] Daily-Omni dataset and evaluation scripts
- [ ] TTS-Seed dataset and evaluation scripts
- [ ] Video-MME dataset and evaluation scripts
- [ ] Official RTF timing script (or confirm internal timing is acceptable)
- [ ] Official baseline configuration

### P2: Build server binary
- [ ] Build `llama-omni-server` from `llama.cpp-omni-official-eval` with CANN optimizations
- [ ] Verify it uses the same `libggml-cann.so`
- [ ] Configure CANN feature flags

### P3: Run official baseline
- [ ] Daily-Omni baseline accuracy
- [ ] TTS-Seed baseline accuracy
- [ ] Video-MME baseline accuracy
- [ ] Save all raw outputs, scores, and SHA256SUMS

### P4: Run candidate
- [ ] Same benchmarks with CANN optimizations enabled
- [ ] Compute accuracy delta (candidate - baseline)
- [ ] Verify each delta ≤ 2pp

### P5: Official RTF measurement
- [ ] Use official timing script
- [ ] Report official RTF (not internal 0.229)
- [ ] Document any difference from internal measurement

### P6: Complete submission
- [ ] Fill all sections of submission package
- [ ] Include reproduction script
- [ ] Demo recording + usage guide
- [ ] Optimization analysis report

---

## Current State for Submission

```
INTERNAL_PERFORMANCE_STACK    = PASS (RTF 0.229, 18.4× vs CPU)
INTERNAL_STABILITY            = PASS (1-hr, 0 CANN errors)
DEMO_VALIDATION               = PASS (9 cases)
CLEAN_REPRODUCTION            = PASS (RTF 0.236)
KV_CACHE_FUNCTIONAL           = PASS (OPT_IN_READY / DEFAULT_OFF)

OFFICIAL_BENCHMARK_HARNESS    = BLOCKED_EXTERNAL
OFFICIAL_ACCURACY_VALIDATION  = NOT_STARTED
OFFICIAL_RTF_SCORE            = NOT_AVAILABLE
SUBMISSION_READY              = NO
```

---

## While Waiting

Continue to:
1. Complete F0-F7 evidence reconciliation
2. Finalize submission package with corrected terminology
3. Prepare server build configuration for CANN
4. Prepare canonical reproduction scripts
5. Ensure all artifacts have verifiable SHA256 checksums
