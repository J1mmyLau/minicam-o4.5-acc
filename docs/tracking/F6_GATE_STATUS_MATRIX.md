# F6 Gate Status Matrix

**Updated:** 2026-07-31 (R0-R9 all completed)
**Branch:** `perf/f6-decode-to-speak`
**HEAD:** `2776217`
**Tag:** `fp16-f6-early-tts-dispatch-internal-20260731`

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

## B6b Sub-Gates (R0-R9 Corrected)

| Sub-Gate | Description | Status | Evidence |
|----------|-------------|--------|----------|
| B6B_NAME | Optimization name | **EARLY_FIRST_TTS_CHUNK_DISPATCH** | C3: only D2→G0 affected, NOT main LLM decode |
| B6B_INTERNAL_PERFORMANCE_GATE | D2→G0 reduction | **PASS** | C6: 116 pairs, Δ=-139ms; Z4: 47 pairs, Δ=-133ms; R1 canonical: 16 pairs, Δ=-141.5ms (95% CI [-148, -137]) |
| B6B_TEXT_CONSISTENCY_GATE | Text consistency | **PASS_ON_TESTED_CASES** | R4: MAIN_LLM_GENERATION_LOGIC_UNCHANGED (code audit) + TESTED_MAIN_TOKEN_SEQUENCES_IDENTICAL (runtime); see `F6_R4_TEXT_CONSISTENCY_WORDING.md` |
| B6B_STABILITY_GATE | Continuous run | **PASS_350_OF_350** | C9: 150/150 + Z10: 200/200 = 350/350, 0 errors, 0 crashes |
| B6B_BASIC_AUDIO_QC_GATE | Format + basic validity | **PASS** | R6 split: AUDIO_FORMAT_GATE=PASS (24000 Hz mono), AUDIO_BASIC_QC_GATE=PASS (duration range, no silence/truncation) |
| B6B_HUMAN_LISTENING | Perceptual quality | **PENDING** | Z9: 20-sample blind A/B manifest at `/tmp/f6_z9_listening/LISTENING_MANIFEST.csv`; not executed |
| B6B_OBJECTIVE_TTS_SCORING | WER/SIM metrics | **PENDING_EXTERNAL** | Requires ASR + speaker embedding pipeline; not in F6 scope |
| B6B_DEFAULT_ENABLEMENT | Production default | **NO** | Awaiting HUMAN_LISTENING or OBJECTIVE_TTS_SCORING before DEFAULT_ON |
| B6B_STATUS | Current status | **OPT_IN_READY / DEFAULT_OFF** | Env var `OMNI_TTS_FIRST_CHUNK_STEP=5` for opt-in |
| B6B_INTERNAL_CANDIDATE | Freeze status | **FROZEN** | Tag: `fp16-f6-early-tts-dispatch-internal-20260731` |

## Core Claim Status (R0-R9 Corrected)

| Claim | Status | Reason |
|-------|--------|--------|
| B6B_INTERNAL_CANDIDATE | **FROZEN** | All measurable gates PASS; tag applied at HEAD `00a2755` |
| MAIN_LLM_FIRST_TOKEN_LATENCY (D0→D2) | **UNCHANGED** | R1 canonical 16 pairs: Δ=-2.0ms (95% CI [-3, -1]), within measurement noise |
| FIRST_TEXT_CHUNK_ACCUMULATION_AND_TTS_WAKE (D2→G0) | **-141.5ms** (-56.6%) | R1 canonical 16 strict pairs, 100% win rate |
| DECODE_TO_FIRST_TALKER_AUDIO_TOKEN (D0→G3) | **-151.0ms** (-41.1%) | R1 canonical 16 strict pairs, 100% win rate |
| SCHEDULING_GAIN_PASSES_THROUGH_TO_FIRST_TALKER_AUDIO_TOKEN | **CONFIRMED** | R2: delta(D0→G3) = delta(D0→D2) + delta(D2→G0) + delta(G0→G3), residual=0.0ms on same 16 pairs |
| DECODE_TO_FIRST_VALID_WAV (D0→W0) | **NOT_MEASURED_ON_MATCHED_PAIRS** | R3 confirmed: 0/36 baseline, 1/28 candidate; async Flow+Vocoder (~4.2s) + shared atomics prevent per-request W0 tracking |
| REQUEST_TO_FIRST_VALID_WAV (R0→W0) | **NOT_MEASURED_ON_MATCHED_PAIRS** | Same as D0→W0; R3: 0 matched pairs; requires client-side audio onset or architectural change |
| DSPARK | **REJECTED_BY_CURRENT_BOTTLENECK_EVIDENCE** | R9: decode compute=13.7% of D0→G4; bottleneck is scheduler+Talker accumulation, not decode throughput |
| NEXT_BOTTLENECK | **G3→G4: TALKER_AUDIO_TOKEN_ACCUMULATION** (~302ms, 57.3%) | R8: 24 Talker steps × ~12.6ms; CHUNK_SIZE=25 is ENGINEERING_POLICY, not model constraint |
| CHUNK_SIZE_25 | **ENGINEERING_POLICY_CONFIRMED** | R8: `F6_AUDIO_TOKEN_WINDOW_CONTRACT.md`; AUDIT_ONLY, no modification

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
11. 不得将D0→G3称为first audio或first WAV — 正确名称: DECODE_TO_FIRST_TALKER_AUDIO_TOKEN
12. 不得用不同样本集的D2→G0和D0→G3做pass-through — 必须在同一canonical intersection上验证
13. 不得仅用code-guaranteed代表text consistency — 必须拆为CODE_AUDIT + RUNTIME_MEASUREMENT
14. 不得仅用24000Hz mono代表音质 — 必须拆为FORMAT/BASIC_QC/HUMAN_LISTENING/OBJECTIVE四个Gate
15. 不得写DEFAULT_ON、OFFICIAL_AUDIO_QUALITY_PASS、OFFICIAL_FIRST_AUDIO_RESULT、LLM_DECODE_ACCELERATED

## Canonical Event Names (R0)

See `F6_R0_CANONICAL_EVENT_NAMES.md` for full registry.

| Interval | Canonical Name | ❌ DO NOT CALL IT |
|----------|---------------|-------------------|
| D0→D2 | MAIN_FIRST_TOKEN_LATENCY | "LLM speedup" |
| D2→G0 | FIRST_TEXT_CHUNK_ACCUMULATION_AND_TTS_WAKE | "TTS dispatch" |
| G0→G3 | TALKER_TO_FIRST_AUDIO_TOKEN | — |
| D0→G3 | DECODE_TO_FIRST_TALKER_AUDIO_TOKEN | "first audio", "first speak", "E2E first audio" |
| G3→G4 | TALKER_AUDIO_TOKEN_ACCUMULATION | "T2W wait" (it's Talker compute, not wait) |
| D0→W0 | DECODE_TO_FIRST_VALID_WAV | "decode-to-audio" unless W0 measured |
| R0→W0 | REQUEST_TO_FIRST_VALID_WAV | "user-perceived latency" unless W0 measured |

## R0-R9 Document Index

| Reference | Document | Content |
|-----------|----------|---------|
| R0 | `F6_R0_CANONICAL_EVENT_NAMES.md` | Event name registry, forbidden equivalences |
| R1 | `/tmp/f6_r1_canonical/F6_B6B_CANONICAL_MATCHED_INTERSECTION.csv` | 16 strict pairs (D0+D2+G0+G3) |
| R2 | (embedded in R1 output) | Pass-through verification on same 16 pairs |
| R3 | `F6_R3_W0_GAP_FINAL.md` | Single-request W0 measurement: 0 matched D0→W0 pairs — NOT_MEASURABLE (async pipeline limitation) |
| R4 | `F6_R4_TEXT_CONSISTENCY_WORDING.md` | CODE_AUDIT + RUNTIME_MEASUREMENT split |
| R5 | `F6_R5_STALE_WRITE_FINAL.md` | stale_write_accepted=0, cross_request_contamination=0 |
| R6 | `F6_R6_AUDIO_QUALITY_GATE_SPLIT.md` | FORMAT/BASIC_QC/HUMAN_LISTENING/OBJECTIVE split |
| R7 | `F6_B6B_INTERNAL_CANDIDATE_MANIFEST.md` | SHA256s, launcher, rollback, known limitations |
| R8 | `F6_G3_G4_SEMANTIC_AUDIT.md`, `F6_AUDIO_TOKEN_WINDOW_CONTRACT.md`, `F6_G3_G4_LATENCY_BUDGET.md` | G3→G4: 302ms = 24×12.6ms Talker compute |
| R9 | `F6_R9_DSPARK_FINAL_RECORD.md` | DSpark REJECTED_BY_CURRENT_BOTTLENECK_EVIDENCE |
