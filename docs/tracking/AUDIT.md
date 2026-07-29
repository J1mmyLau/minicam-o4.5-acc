# AUDIT LOG — CANN Flow + Vocoder Optimization

**Project:** llama.cpp-omni-operator / Ascend 910C / CANN 9.1.0-beta.1
**Branch:** perf/flow-chunk-rtf

---

## 2026-07-29 15:00 | SUBMISSION | G13_SUBMISSION_PACKAGE_READY
- HEAD: 01fdf71
- 10/14 gates PASS, 1 BLOCKED (external harness), 3 DEFERRED
- RTF: 0.229 (18.4× vs CPU)
- Submission: profiles/G13_SUBMISSION_PACKAGE.md

## 2026-07-29 14:57 | GATE | G12_CLEAN_REPRODUCTION PASS
- Clean binary: RTF 0.236 vs original 0.245 (±3.6%)
- Functional equivalence verified

## 2026-07-29 14:53 | GATE | G8_1HR_STABILITY PASS
- 66 iters, 1368 WAVs, 0 CANN errors, 2 false-positive timeouts

## 2026-07-29 13:51 | GATE | G7_30MIN_STABILITY PASS
- 37 iters, 661 WAVs, 0 CANN errors, 1 false-positive timeout

## 2026-07-29 13:22 | GATE | G6_DEMO PASS
- 9 test cases, 0 CANN errors, AUDIO_SUCCESS

## 2026-07-29 13:06 | GATE | G3_G4 PASS
- Q4(ON,ON): RTF=0.245, steady RTF=0.224
- Graph capture primary driver (-8.2% t2m p50)
- Fusion alone harmful without graph

## 2026-07-29 12:50 | GATE | G1_G2 PASS
- Perf consistency, graph cache audit

## 2026-07-29 12:50 | FREEZE | PHASE3_CANDIDATE_FROZEN
- Tag: cann-flow-vocoder-aclgraph-rtf0229-20260729
- RTF: 0.229 (18.4× vs CPU)

## 2026-07-29 12:50 | POLICY | AUTONOMOUS_CONTEXT_ROLLOVER_ENABLED
## 2026-07-29 17:36 | GATE | G10_MULTI_PREFIX_PASS — 3 distinct keys, isolation confirmed, corruption detected+rebuilt
## 2026-07-29 19:38 | GATE | G11_T2W_LIFECYCLE_PASS — 154 runs, 0 crashes, 0 CANN errors, 145 audio
## 2026-07-29 19:45 | REVIEW | P4_FINAL_INTEGRATED_PERFORMANCE — KV cache HIT preserves Phase 3 performance (P50=0.250)
## 2026-07-29 19:46 | TAG | cann-flow-vocoder-aclgraph-kvcache-final-20260729 — all production gates closed
## 2026-07-29 19:50 | CHECKPOINT | G13_SUBMISSION_PACKAGE_FINAL — 13/14 PASS, 1 BLOCKED, 1 DEFERRED
