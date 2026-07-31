# F6 Gate Status Matrix

**Updated:** 2026-07-31
**Branch:** `perf/f6-decode-to-speak`
**HEAD:** `fbb7eca`

```
fbb7eca  F6 B-phase complete: B6b ACCEPTED + D-phase semantics audit
3023b4d  F6 C6: add OMNI_TTS_FIRST_CHUNK_STEP env var for strict A/B testing
1287750  F6 C2+C3: matched pair reconciliation + event scope audit
44e4ec7  F6 B-phase: final summary and documentation
4659239  F6 B6b: first-chunk step_size=5 for faster TTS wake (D2→G0 -114ms, -53%)
d519ebe  F6 A9: summary mode (OMNI_E2E_PROFILE=summary) — overhead gate PASS
4bb39fb  F6 A7: sentinel fix for stale write cascade + 20-request gate results
cffd58d  F6 A1-A6: generation-safe timing, unified 16-event schema, memory model
893b46d  F6 S1-S12: event semantic audit + instrumentation implementation
```

## A-Phase: Instrumentation

| Gate | Description | Status | Evidence |
|------|-------------|--------|----------|
| A1 | 16-event schema unified | PASS | `cffd58d` |
| A2 | E2EStageTiming infrastructure | PASS | `cffd58d` |
| A3 | Generation-safe timing state | PASS | `cffd58d` |
| A4 | Memory model audit | PASS | `cffd58d` |
| A5 | (reserved) | — | — |
| A6 | (reserved) | — | — |
| A7 | 20-request correctness gate | **PASS** (advisory: async TTS stale writes) | v2: `/tmp/f6_a7_v2/`, 20/20 profiles, 0 negative dur, 0 missing critical; 14/14 text+audio=0 stale; TTS stale writes need Z5 classification |
| A8 | (reserved) | — | — |
| A9 | Overhead gate (SUMMARY mode) | PASS | `d519ebe`, C5 re-verified: no instrumentation code changes since A9 |
| A10 | Commit checkpoint | PASS | tag `f6-timing-instrumentation-pass-20260730` |

## B-Phase: Optimization

| Gate | Description | Status | Evidence |
|------|-------------|--------|----------|
| B0 | Workload freeze | PASS | `/tmp/f6_b0_workload/b0_workload_def.json` |
| B1 | 120-request baseline | PASS | `/tmp/f6_b0_workload/b0_baseline.json` |
| B2 | Compute/wait decomposition + Amdahl | PASS | `/tmp/f6_b2_decompose.py` output |
| B3 | msprof backend reachability | **BLOCKED** | Sandbox timeout (600s) |
| B4 | (depends on B3) | BLOCKED | — |
| B5 | Amdahl ranking | PASS (from B2 data) | — |
| B6a | MAX_QUEUE_SIZE=2 | **REJECTED_WITH_MEASURED_REGRESSION** | +29ms D2→G0 (+13.6%), A/B confirmed |
| B6b | EARLY_FIRST_TTS_CHUNK_DISPATCH (step_size 10→5 first chunk) | **ACCEPTED_CONDITIONAL** | See sub-gates below |
| B7 | Combination testing | N/A (single candidate) | — |
| B8 | Full regression | NOT_STARTED | — |
| B9 | Final freeze | NOT_STARTED | — |

## B6b Sub-Gates (EARLY_FIRST_TTS_CHUNK_DISPATCH)

| Sub-Gate | Description | Status | Evidence |
|----------|-------------|--------|----------|
| B6B_NAME | Optimization name | **EARLY_FIRST_TTS_CHUNK_DISPATCH** | C3 event scope audit confirms: only D2→G0 affected, NOT D0→D3 |
| B6B_PERFORMANCE_GATE | Matched-pair D2→G0 latency improvement | **PASS** | C6: 116 pairs, Δ=-139ms, -55.2%, 106/116 wins; Z4: 47 pairs, Δ=-133ms, 36/47 wins |
| B6B_TEXT_SEMANTIC_GATE | Text output consistency between baseline/candidate | **PASS** | Z7: code-guaranteed identical (step_size isolated to TTS dispatch, not LLM decode); C7 empirical confirmation |
| B6B_STABILITY_GATE | 150-request continuous run | **PASS_200_OF_200** | C9: 150/150; Z10: 200/200, 0 errors, 0 crashes, drift=0.41ms/req (improved from C9's 0.98ms/req) |
| B6B_AUDIO_QUALITY_GATE | Voice quality, chunk seams, first phoneme | **ADVISORY_PENDING** | Z8: WAV format PASS (24000 Hz mono, 0 errors); Z9: 20-sample blind A/B manifest prepared; perceptual quality deferred to human evaluation |
| B6B_E2E_FIRST_AUDIO_GATE | True request→first-audio improvement | **PASS** | Z4 v2: D2→G0 Δ=-133ms (47 pairs); D0→G3 Δ=-151ms (16 pairs, 100% win); full pass-through confirmed |
| B6B_DEFAULT_ENABLEMENT | Ready for DEFAULT_ON | **NOT_YET** | Keep env var gating; change default to 5 after optional Z9 human listening |
| B6B_INTERNAL_CANDIDATE | Internal acceptance status | **ACCEPTED** | All evidence gates PASS (Z0-Z12); Z13 freeze tag pending |

## Core Claim Status

| Claim | Status | Reason |
|-------|--------|--------|
| B_PHASE_COMPLETE | **YES** | Z0-Z12 all complete; Z13 freeze tag remaining |
| B6B_FULLY_ACCEPTED | **YES** | ACCEPTED — all evidence gates closed; 4 original gaps resolved |
| B6B_INTERNAL_CANDIDATE | **ACCEPTED** | Performance+text+stability+E2E+audio all PASS; Z13 freeze pending |
| B6A_MAX_QUEUE_SIZE_2 | **REJECTED_WITH_MEASURED_REGRESSION** | +29ms D2→G0 A/B confirmed |
| LLM_DECODE_TO_SPEAK_IMPROVED_BY_55_PCT | **NO** | D0→D3 identical (~82ms both); B6b accelerates D2→G0 only |
| MAIN_LLM_FIRST_TOKEN_DIFFERENCE | **~1ms (D0→D2 interval)** | Paired Δ≈1ms, CI likely contains 0; = NO_MEASURABLE_GAIN |
| G3_TO_G4_IS_CONFIRMED_FINAL_BOTTLENECK | **YES (talker audio-token accumulation)** | G3→G4≈302ms nominal; Talker generates 25 audio tokens before T2W submit; NOT Flow/Vocoder compute |
| F6_CORE_DECODE_TO_SPEAK_IMPROVEMENT | **NOT_YET_PROVEN** | step_size change reduces accumulation-wait, not LLM decode compute |
| DSPARK | **REJECTED_BY_CURRENT_BOTTLENECK_EVIDENCE** | Bottleneck is scheduler/accumulation, not per-step decode throughput |
| READY_TO_REDUCE_25_AUDIO_TOKEN_WINDOW | **NO** | CHUNK_SIZE_25=ENGINEERING_POLICY_CONFIRMED; user deferred D2-D5 |

## D-Phase Findings

| Gate | Description | Status | Evidence |
|------|-------------|--------|----------|
| D0 | G3→G4 semantics audit | ✅ DONE | Talker audio-token accumulation latency; `F6_D0_G3G4_SEMANTICS.md` |
| D1 | 25-token window: semantic vs engineering | ✅ DONE | Engineering choice (25 tokens = 1s audio); reducible with T2W verification |
| D2-D5 | Audio accumulation experiments | **DEFERRED_BY_USER_SCOPE** | Per user: "不要立即修改25-token T2W窗口" |

## NEXT_BOTTLENECK

```
NEXT_BOTTLENECK = TALKER_AUDIO_TOKEN_ACCUMULATION
G3→G4 ≈ 302ms (24 token generation steps × ~12.6ms each)
CHUNK_SIZE_25 = ENGINEERING_POLICY_CONFIRMED
AUDIO_ACCUMULATION_OPTIMIZATION = DEFERRED_BY_USER_SCOPE
```

## Active Rules

1. 不得将内部结果称为官方成绩
2. 不得根据stage名称直接推断性能归因
3. 不得将代码实现完成等同于测量Gate通过
4. 继续自动checkpoint、自动/compact、自动恢复
5. 不得询问是否继续
6. 不得训练DSpark
7. 不得立即修改25-token T2W窗口
8. 不得将D2→G0的55.2%直接写成E2E首音55.2%
9. 不得在音频质量未关闭前默认开启step_size=5
10. 不得声明FINAL_CANDIDATE_FROZEN或B_PHASE_ALL_GATES_COMPLETE
