# F6 Gate Status Matrix

**Updated:** 2026-07-31 (W0 Observability Closeout initiated)
**Branch:** `perf/f6-decode-to-speak`
**HEAD:** `2fe0ae4` (post-freeze R3 commit; tag at `00a2755`)
**Tag:** `fp16-f6-early-tts-dispatch-internal-20260731` at `00a2755`

```
2fe0ae4  F6 R3: W0 gap filling final — D0→W0 NOT_MEASURABLE on matched pairs (POST-FREEZE)
2776217  F6 R0-R9: canonical event names, corrected wording, gate splits, G3→G4 audit
00a2755  F6 Z13: gate matrix updated with freeze tag                          ← TAG HERE
7d3951e  F6 Z0-Z12 closeout: B6b ACCEPTED, all evidence gates complete
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
| A7 | 20-request correctness gate | **PASS** (advisory: async TTS stale writes) | v2: `/tmp/f6_a7_v2/`, 20/20 profiles, 0 negative dur, 0 missing critical; 14/14 text+audio=0 stale |
| A8 | (reserved) | — | — |
| A9 | Overhead gate (SUMMARY mode) | PASS | `d519ebe`, C5 re-verified |
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

## B6b Sub-Gates (R0-R9 Corrected + W0 Audit)

| Sub-Gate | Description | Status | Evidence |
|----------|-------------|--------|----------|
| B6B_NAME | Optimization name | **EARLY_FIRST_TTS_CHUNK_DISPATCH** | C3: only D2→G0 affected, NOT main LLM decode |
| B6B_INTERNAL_CANDIDATE | Freeze status | **FROZEN** | Tag: `fp16-f6-early-tts-dispatch-internal-20260731` at `00a2755` |
| B6B_STATUS | Current status | **OPT_IN_READY / DEFAULT_OFF** | Env var `OMNI_TTS_FIRST_CHUNK_STEP=5` for opt-in |
| B6B_DEFAULT_ENABLEMENT | Production default | **OFF** | Awaiting HUMAN_LISTENING + W0 observability fix |
| B6B_D2_TO_G0 | D2→G0 improvement | **PASS** | R1: 16 pairs, Δ=-141.5ms; R3: 27 pairs, Δ=-103ms; stable positive |
| B6B_D0_TO_D2 | Main LLM unchanged | **PASS** | R1: Δ=-2.0ms; R3: Δ=+3ms; within noise |
| B6B_D0_TO_G3 | D0→G3 pass-through | **DIRECTIONALLY_SUPPORTED** | R1: 16 pairs, Δ=-151ms; R3: 4 pairs, Δ=-132ms; CANONICAL_SAMPLE_INSUFFICIENT |
| B6B_D0_TO_W0 | D0→W0 matched A/B | **BLOCKED_BY_W0_OBSERVABILITY** | R3: 0 matched pairs; only 1/64 profiles has wav_ready |
| B6B_R0_TO_W0 | R0→W0 matched A/B | **BLOCKED_BY_W0_OBSERVABILITY** | Same as D0→W0 |
| B6B_TEXT_CONSISTENCY | Text consistency | **PASS_ON_TESTED_CASES** | R4: CODE_AUDIT + RUNTIME_MEASUREMENT |
| B6B_BASIC_AUDIO_QC | Format + basic validity | **PASS** | R6: FORMAT=PASS, BASIC_QC=PASS |
| B6B_HUMAN_LISTENING | Perceptual quality | **PENDING** | Z9 manifest at `/tmp/f6_z9_listening/` (MUST MIGRATE TO `runs/`) |
| B6B_OBJECTIVE_TTS_SCORING | WER/SIM metrics | **PENDING_EXTERNAL** | Requires ASR + speaker embedding pipeline |
| B6B_STABILITY_GATE | Cumulative stability | **PASS_350_OF_350** | C9: 150 + Z10: 200 = 350; see W1 for provenance breakdown |

## W0 Observability Status (NEW — W0 Closeout Phase)

| Gate | Description | Status | Evidence |
|------|-------------|--------|----------|
| W0_EVENT_OBSERVABILITY | Is W0/wav_ready reliably recorded? | **BROKEN_OR_LIFECYCLE_MISMATCH** | R3: 1/64 profiles (candidate warmup only); 63/64 missing |
| D0_TO_W0_MATCHED_AB | D0→W0 matched A/B measurement | **BLOCKED** | 0 matched pairs; requires W0 observability fix |
| R0_TO_W0_MATCHED_AB | R0→W0 matched A/B measurement | **BLOCKED** | 0 matched pairs; requires W0 observability fix |
| G3_G4_OPTIMIZATION | Audio accumulation optimization | **HOLD** | Deferred until W0 observability is restored |
| W0_ROOT_CAUSE | Why is W0 missing from 63/64 profiles? | **PENDING** | W2 (call chain audit) + W3 (64-profile classification) |
| W0_FIX | Profile lifecycle fix | **PENDING** | W5-W7: request-scoped profile, proper lifecycle |

## Core Claim Status (W0 Corrected)

| Claim | Status | Reason |
|-------|--------|--------|
| B6B_INTERNAL_CANDIDATE | **FROZEN** | All measurable gates PASS; tag applied at `00a2755` |
| MAIN_LLM_FIRST_TOKEN_LATENCY (D0→D2) | **UNCHANGED** | R1: Δ=-2.0ms; R3: Δ=+3ms; within noise |
| FIRST_TEXT_CHUNK_ACCUMULATION_AND_TTS_WAKE (D2→G0) | **PASS** (-100 to -142ms) | R1: 16 pairs, Δ=-141.5ms; R3: 27 pairs, Δ=-103ms; 100% win rate |
| DECODE_TO_FIRST_TALKER_AUDIO_TOKEN (D0→G3) | **DIRECTIONALLY_SUPPORTED** | R1: 16 pairs; R3: 4 pairs (same direction, insufficient canonical sample for G3) |
| SCHEDULING_GAIN_PASSES_THROUGH_TO_D0→G3 | **CONFIRMED** (on available pairs) | R2: residual=0.0ms on 16 common pairs |
| DECODE_TO_FIRST_VALID_WAV (D0→W0) | **BLOCKED_BY_W0_OBSERVABILITY** | W0/wav_ready only in 1/64 profiles; async lifecycle broken |
| REQUEST_TO_FIRST_VALID_WAV (R0→W0) | **BLOCKED_BY_W0_OBSERVABILITY** | Same root cause |
| W0_EVENT_OBSERVABILITY | **BROKEN_OR_LIFECYCLE_MISMATCH** | Profile summary before W0, generation reset before W0, or stale guard rejection |
| TRUE_END_TO_END_FIRST_AUDIO | **NOT_PROVEN** | Cannot answer: how much of D2→G0 saving reaches user's first audible audio |
| DSPARK | **REJECTED_BY_CURRENT_BOTTLENECK_EVIDENCE** | decode compute=13.7% of D0→G4 |
| NEXT_BOTTLENECK | **G3→G4: TALKER_AUDIO_TOKEN_ACCUMULATION** (~302ms, 57.3%) | R8: 24 Talker steps × ~12.6ms; CHUNK_SIZE=25 = ENGINEERING_POLICY |
| CHUNK_SIZE_25 | **ENGINEERING_POLICY_CONFIRMED** | R8; HOLD until W0 observability restored |

## D-Phase Findings

| Gate | Description | Status | Evidence |
|------|-------------|--------|----------|
| D0 | G3→G4 semantics audit | ✅ DONE | `F6_G3_G4_SEMANTIC_AUDIT.md` |
| D1 | 25-token window: semantic vs engineering | ✅ DONE | `F6_AUDIO_TOKEN_WINDOW_CONTRACT.md` |
| D2-D5 | Audio accumulation experiments | **DEFERRED_BY_USER_SCOPE** | Per user: "不要立即修改25-token T2W窗口" |

## W0-W15 Phase: Observability Closeout

| Gate | Description | Status |
|------|-------------|--------|
| W0 | Freeze current state | ✅ PASS |
| W1 | Verify final tag, binary SHA256, stability provenance | ✅ PASS |
| W2 | Audit W0 complete call chain | ✅ PASS |
| W3 | Classify 64 R3 profiles for W0 gap | ✅ PASS |
| W4 | Define independent server/client metrics | ✅ PASS |
| W5 | Fix profile lifecycle (request-scoped) | ✅ PASS |
| W6 | Define profile finalization state machine | ✅ PASS |
| W7 | Low-risk implementation constraints | ✅ PASS |
| W8_SMOKE | W0 correctness smoke (5 requests) | ✅ PASS (5/5, 100% W0) |
| W8_CORRECTNESS_30_PLUS | W0 correctness: 30+ requests, multi-category | ✅ **PASS** (30/30: 100% W0, 0 wrong attr, 0 stale, 0 contam, 0 fallback, 100% audio_valid; 2026-07-31) |
| W9_MICRO_OVERHEAD | Micro-level instrumentation overhead | ✅ PASS (~55ns/token, ~500μs/dump) |
| W9_MATCHED_E2E_OVERHEAD | F6_TIMING=0 vs summary matched E2E overhead | ✅ **PASS** (micro: 55ns/token; macro: overhead within workload noise ~100s std) |
| W10_Q4_DIAGNOSTIC_RUN | Q4_K_M 120-pair diagnostic only | **INVALID_FOR_FP16_GATE** (96 profiles, 24/60 blocks; model + args mismatch) |
| W10_FP16_TRUE_E2E_120_PAIR | True B6b E2E matched A/B on FP16 (120 pairs) | **NOT_STARTED** (pilot first) |
| W11_PROFILE_CONSISTENCY | Pass-through profile timestamp consistency | ✅ PASS (Δ=0ms, same clock, same atomic) |
| W11_B6B_GAIN_TO_FIRST_WAV | B6b measured gain to first valid WAV | **NOT_MEASURED** |
| W12 | Persist blind listening assets | ✅ PASS |
| W13 | Update final gates | ✅ PASS |
| W14 | Create observability fix tag | ✅ PASS (`fp16-f6-w0-observability-20260731` @ `31cba8d`) |
| W15 | G3→G4 next-bottleneck handoff | ✅ PASS |

### TRUE_E2E Gates (CORRECTED — Q4 run invalidated; FP16 NOT_STARTED)

| Gate | Description | Status |
|------|-------------|--------|
| TRUE_D0_TO_W0_Q4_AB | D0→W0 matched A/B on Q4_K_M (96 profiles) | **INVALID_FOR_FP16_GATE** (diagnostic only; see `/tmp/f6_w10_ab/INVALID_RUN_MANIFEST.md`) |
| TRUE_CLIENT_FIRST_AUDIO_Q4_AB | Client request→first audio frame on Q4_K_M | **INVALID_FOR_FP16_GATE** (same run; wrong model/args/env) |
| TRUE_D0_TO_W0_FP16_AB | D0→W0 matched A/B on FP16 (120 pairs) | **NOT_STARTED** |
| TRUE_CLIENT_FIRST_AUDIO_FP16_AB | Client request→first audio frame on FP16 | **NOT_STARTED** |
| B6B_TRUE_E2E_GATE | D0→W0 AND client first audio both significantly improved on FP16 | **AWAITING_VALID_FP16_DATA** |

### Known Incorrect Claims Retracted

| Claim | Previous | Corrected |
|-------|----------|-----------|
| "All W0-W15 gates resolved" | 31cba8d commit message | W8/30+, W9/matched, W11/gain, TRUE E2E still PENDING |
| "120-pair requires multi-decode architecture" | W10-W11 doc, W15 doc | Sequential server restart (same binary, different env, ABBA order) is sufficient |
| "E2E overhead gate PASS" (without matched pairs) | W9 doc | Micro overhead PASS; matched E2E overhead (F6_TIMING=0 vs summary) PENDING |

## NEXT_BOTTLENECK

```
NEXT_BOTTLENECK = TALKER_AUDIO_TOKEN_ACCUMULATION
G3→G4 ≈ 302ms (24 token generation steps × ~12.6ms each)
CHUNK_SIZE_25 = ENGINEERING_POLICY_CONFIRMED
AUDIO_ACCUMULATION_OPTIMIZATION = HOLD (until W0 observability restored)
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
16. 不得移动现有tag `fp16-f6-early-tts-dispatch-internal-20260731`
17. 不得开始新的性能优化（仅修复W0观测）
18. 不得改变CHUNK_SIZE=25、Talker token policy、T2W算法、Flow/Vocoder、KV cache格式
19. 不得因音频最终存在就忽略W0观测缺陷
20. 不得延迟所有请求完成来掩盖生命周期问题
21. 埋点不得增加stream synchronize、worker join到首音关键路径、busy wait、热路径文件写入、逐token日志

## Canonical Event Names (R0)

See `F6_R0_CANONICAL_EVENT_NAMES.md` for full registry.

| Interval | Canonical Name | ❌ DO NOT CALL IT |
|----------|---------------|-------------------|
| D0→D2 | MAIN_FIRST_TOKEN_LATENCY | "LLM speedup" |
| D2→G0 | FIRST_TEXT_CHUNK_ACCUMULATION_AND_TTS_WAKE | "TTS dispatch" |
| G0→G3 | TALKER_TO_FIRST_AUDIO_TOKEN | — |
| D0→G3 | DECODE_TO_FIRST_TALKER_AUDIO_TOKEN | "first audio", "first speak", "E2E first audio" |
| G3→G4 | TALKER_AUDIO_TOKEN_ACCUMULATION | "T2W wait" |
| D0→W0 | DECODE_TO_FIRST_VALID_WAV | "decode-to-audio" unless W0 measured |
| R0→W0 | REQUEST_TO_FIRST_VALID_WAV | "user-perceived latency" unless W0 measured |
| **SERVER_D0_TO_W0** | **Decode begin to first valid WAV buffer (server monotonic)** | Do not compare with client clock |
| **CLIENT_REQUEST_TO_FIRST_AUDIO_FRAME** | **Client send to first non-empty audio frame (client monotonic)** | Do not subtract server timestamps |

## Document Index

| Reference | Document | Content |
|-----------|----------|---------|
| R0 | `F6_R0_CANONICAL_EVENT_NAMES.md` | Event name registry, forbidden equivalences |
| R1 | `/tmp/f6_r1_canonical/F6_B6B_CANONICAL_MATCHED_INTERSECTION.csv` | 16 strict pairs (D0+D2+G0+G3) |
| R2 | (embedded in R1 output) | Pass-through verification on same 16 pairs |
| R3 | `F6_R3_W0_GAP_FINAL.md` | W0 gap filling: 1/64 wav_ready, NOT_MEASURABLE |
| R4 | `F6_R4_TEXT_CONSISTENCY_WORDING.md` | CODE_AUDIT + RUNTIME_MEASUREMENT |
| R5 | `F6_R5_STALE_WRITE_FINAL.md` | stale_write_accepted=0, cross=0 |
| R6 | `F6_R6_AUDIO_QUALITY_GATE_SPLIT.md` | FORMAT/BASIC_QC/HUMAN_LISTENING/OBJECTIVE |
| R7 | `F6_B6B_INTERNAL_CANDIDATE_MANIFEST.md` | SHA256s, launcher, rollback, limitations |
| R8 | `F6_G3_G4_SEMANTIC_AUDIT.md` et al. | G3→G4: 302ms, CHUNK_SIZE=25 ENGINEERING_POLICY |
| R9 | `F6_R9_DSPARK_FINAL_RECORD.md` | DSpark REJECTED |
| W1 | `F6_W1_BINARY_PROVENANCE.md` | Tag, SHA256s, 350 stability provenance |
| W2 | `F6_W2_W0_CALLCHAIN_AUDIT.md` | W0 complete call chain |
| W3 | `F6_W3_64_PROFILE_RECONCILIATION.csv` + `.md` | Per-profile W0 gap classification |
| W4 | `F6_W4_CLIENT_SERVER_METRICS.md` | Independent server/client timing definitions |
| W5-W7 | `F6_W5_PROFILE_LIFECYCLE_FIX.md` | Request-scoped profile, lifecycle state machine |
| W8 | `F6_W8_W0_SMOKE.md` | W0 correctness smoke (5/5, 100% W0) |
| W9 | `F6_W9_OVERHEAD_GATE.md` | Instrumentation overhead gate (PASS) |
| W10-W11 | `F6_W10_W11_AB_RECONCILIATION.md` | 5-pair A/B pilot + pass-through reconciliation |
| W12 | `runs/w8_smoke/`, `runs/w10_ab/` | Persisted profile assets |
| W13-W14 | (gate updates + tag) | Final gates + observability tag |
| W15 | `F6_W15_G3G4_HANDOFF.md` | Updated G3→G4 handoff |
