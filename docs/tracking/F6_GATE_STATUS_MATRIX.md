# F6 Gate Status Matrix

**Updated:** 2026-08-01 (Phase 3: G0→T2W Dequeue decomposition)
**Branch:** `perf/f6-decode-to-speak`
**HEAD:** `f4133d0` (P0-P6 documentation + B6b rejection)
**Tag:** `fp16-f6-early-tts-dispatch-internal-20260731` at `00a2755` (PRESERVED)

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
| B6B_STATUS | Current status | **EXPERIMENTAL_KNOB / DEFAULT_OFF** | Env var `OMNI_TTS_FIRST_CHUNK_STEP=5`; DO_NOT_ENABLE_FOR_PRODUCTION |
| B6B_DEFAULT_ENABLEMENT | Production default | **OFF** | TRUE_E2E gate REJECTED: no significant FP16+CANN E2E gain |
| B6B_D2_TO_G0 | D2→G0 scheduling gap | **BIMODAL/NOT_SIGNIFICANT_MEDIAN** | FP16: 120 pairs, median Δ=0ms (CI95 [0,0]); BUT bimodal: 72% pairs=0ms, 23% OFF ~221ms, 18% ON ~98ms. B6b reduces gap 2.3x WHEN gap exists. C3 audit: `F6_C3_D2G0_ZERO_GAP_AUDIT.md` |
| B6B_D0_TO_D2 | Main LLM unchanged | **NO_OBSERVED_DIFFERENCE_AT_CURRENT_RESOLUTION** | FP16: 120 pairs, p50 Δ=0ms, 59% delta=0, 41% delta=±1-2ms. Integer-ms resolution. C2 audit: `F6_C2_D0D2_CI_ZERO_AUDIT.md` |
| B6B_D0_TO_G3 | D0→G3 pass-through | **NOT_MEASURABLE** | FP16 profiles lack talker_first_audio_token (G3); 115/120 pairs excluded |
| B6B_D0_TO_W0 | D0→W0 matched A/B | **DIRECTIONAL/NOT_SIGNIFICANT** | FP16: 120 pairs, median Δ=-17.5ms, win_rate=52.5% (<95% threshold) |
| B6B_R0_TO_W0 | R0→W0 matched A/B | **DIRECTIONAL/NOT_SIGNIFICANT** | Client: 120 pairs, median Δ=-2.3ms, win_rate=53.3% (<95% threshold) |
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
| B6B_INTERNAL_CANDIDATE | **FROZEN** | Tag at `00a2755`; B6b REJECTED |
| MAIN_LLM_FIRST_TOKEN_LATENCY (D0→D2) | **NO_OBSERVED_DIFFERENCE_AT_CURRENT_RESOLUTION** | C2: 120 pairs, p50 Δ=0ms, 59% delta=0, 41% delta=±1-2ms (ms quantization) |
| FIRST_TEXT_CHUNK_ACCUMULATION_AND_TTS_WAKE (D2→G0) | **BIMODAL** | C3: 72% pairs=0ms, 23% OFF~221ms, 18% ON~98ms; B6b 2.3× reduction when gap exists |
| DECODE_TO_FIRST_TALKER_AUDIO_TOKEN (D0→G3) | **NOT_MEASURABLE** | FP16 profiles lack G3 (5/120 present); requires P9 instrumentation |
| SCHEDULING_GAIN_PASSES_THROUGH_TO_D0→G3 | **NOT_MEASURABLE** | G3 absent from 115/120 FP16 profiles |
| DECODE_TO_FIRST_VALID_WAV (D0→W0) | **INCONCLUSIVE_WIDE_CI** | FP16: 120 pairs, median Δ=-17.5ms, CI95=[-44,+10.5]ms crosses zero |
| REQUEST_TO_FIRST_VALID_WAV (R0→W0) | **REJECT_BELOW_THRESHOLD** | Client: 120 pairs, median Δ=-2.3ms < 5ms engineering threshold |
| W0_EVENT_OBSERVABILITY | **FIXED** | W0 wav_ready present in 120/120 FP16 profiles (100%) |
| TRUE_END_TO_END_FIRST_AUDIO | **REJECT_NO_MEANINGFUL_GAIN** | Combined: INCONCLUSIVE + BELOW_THRESHOLD → REJECT |
| DSPARK | **REJECTED_BY_CURRENT_BOTTLENECK_EVIDENCE** | decode compute < 15% of D0→W0 |
| NEXT_BOTTLENECK | **G0→T2W_DEQUEUE_UNDECOMPOSED_REGION** (~621ms, 67.4% of D0→W0) | C4: Cannot decompose without G3/G4; Flow+Vocoder=267ms (residual=0ms at ms res) |
| CHUNK_SIZE_25 | **ENGINEERING_POLICY_FROZEN** | Phase 3: observe only, do not modify |

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
| W10_FP16_TRUE_E2E_120_PAIR | True B6b E2E matched A/B on FP16 (120 pairs) | ✅ **COMPLETE** (60 blocks, 120 pairs, D0→W0 median Δ=-17.5ms, win_rate=52.5%) |
| W11_PROFILE_CONSISTENCY | Pass-through profile timestamp consistency | ✅ PASS (Δ=0ms, same clock, same atomic) |
| W11_B6B_GAIN_TO_FIRST_WAV | B6b measured gain to first valid WAV | **DIRECTIONAL/NOT_SIGNIFICANT** (D0→W0 median Δ=-17.5ms, 52.5% win; Client median Δ=-2.3ms, 53.3% win) |
| W12 | Persist blind listening assets | ✅ PASS |
| W13 | Update final gates | ✅ PASS |
| W14 | Create observability fix tag | ✅ PASS (`fp16-f6-w0-observability-20260731` @ `31cba8d`) |
| W15 | G3→G4 next-bottleneck handoff | ✅ PASS |

### X-Stage Status (X0-X11 Execution Audit — 2026-08-01)

| Step | Description | Status | Artifact |
|------|-------------|--------|----------|
| X0 | Safe termination of invalid Q4 run | COMPLETE | `/tmp/f6_w10_ab/INVALID_RUN_MANIFEST.md` |
| X1 | Gate state correction | COMPLETE | Updated tracking docs |
| X2 | Harness analyzer fix + unit tests | COMPLETE | 8/8 tests pass; commit `c1979df` |
| X3 | Restore frozen FP16 config | COMPLETE | Model SHA256 verified; CANN env configured |
| X4 | 78 WAV / CPU anomaly diagnosis | COMPLETE | Root cause: missing CANN env → CPU T2W fallback |
| X5 | 2-block FP16 pilot | COMPLETE | 8/8 W0 present, 0 errors |
| X6 | Pilot sanity check | COMPLETE | All durations valid |
| X7 | 60-block FP16 formal run | COMPLETE | 120 pairs, 0 errors, ~84 min |
| X8 | Monitoring methodology | EMBEDDED_IN_RUNNER | progress.csv with fsync per block; no sleep 600 polling |
| X9 | Mid-run quality gates | EMBEDDED_IN_RUNNER | 4/10/30-block checks: W0=100%, crash=0, CANN_error=0; no auto-stop triggered |
| X10 | Canonical statistics | COMPLETE | `F6_B6B_FP16_CANONICAL_120_PAIRS.csv` |
| X11 | Gate decision | COMPLETE | `REJECT_NO_MEANINGFUL_GAIN` |

**X8-X9 Note:** No independent artifacts beyond `progress.csv` and run log. Quality checks were embedded in the harness (per-block progress writes, W0 presence tracking, error counters). All quality gates passed at 4/10/30-block milestones — W0 presence was 100%, no crashes, no CANN errors, no auto-stop triggered.

### TRUE_E2E Gates (FINAL — FP16 120-pair complete 2026-07-31)

| Gate | Description | Status |
|------|-------------|--------|
| TRUE_D0_TO_W0_Q4_AB | D0→W0 matched A/B on Q4_K_M (96 profiles) | **INVALID_FOR_FP16_GATE** (diagnostic only; see `/tmp/f6_w10_ab/INVALID_RUN_MANIFEST.md`) |
| TRUE_CLIENT_FIRST_AUDIO_Q4_AB | Client request→first audio frame on Q4_K_M | **INVALID_FOR_FP16_GATE** (same run; wrong model/args/env) |
| TRUE_D0_TO_W0_FP16_AB | D0→W0 matched A/B on FP16 (120 pairs) | **COMPLETE** (median Δ=-17.5ms, win_rate=52.5% — not significant) |
| TRUE_CLIENT_FIRST_AUDIO_FP16_AB | Client request→first audio frame on FP16 | **COMPLETE** (median Δ=-2.3ms, win_rate=53.3% — not significant) |
| B6B_TRUE_E2E_GATE | D0→W0 AND client first audio both significantly improved on FP16 | **REJECT_NO_MEANINGFUL_GAIN** (D0→W0 CI95 [-44,+10.5] crosses zero; Client median -2.3ms < 5ms threshold; win rates 52.5%/53.3%) |

### Known Incorrect Claims Retracted

| Claim | Previous | Corrected |
|-------|----------|-----------|
| "All W0-W15 gates resolved" | 31cba8d commit message | W8/30+, W9/matched, W11/gain, TRUE E2E still PENDING |
| "120-pair requires multi-decode architecture" | W10-W11 doc, W15 doc | Sequential server restart (same binary, different env, ABBA order) is sufficient |
| "E2E overhead gate PASS" (without matched pairs) | W9 doc | Micro overhead PASS; matched E2E overhead (F6_TIMING=0 vs summary) PENDING |

## NEXT_BOTTLENECK (Corrected — 2026-08-01)

```
B6B_TRUE_E2E_FP16_GATE = REJECT_NO_MEANINGFUL_GAIN
B6B_FEATURE_STATUS     = EXPERIMENTAL_KNOB / DEFAULT_OFF
B6B_PRODUCTION_RECOMMENDATION = DO_NOT_ENABLE

FP16+CANN latency budget (C1-C3 corrected):
  D0→D2 (main LLM):        28ms median (3.0%)
    → NO_OBSERVED_DIFFERENCE_AT_CURRENT_RESOLUTION (ms quantization)
  D2→G0 (TTS scheduling):   BIMODAL
    → Mode 1 (72%): 0ms — TTS worker already waiting
    → Mode 2 (23% OFF): ~221ms — TTS idle wake latency
    → Mode 2 (18% ON):  ~98ms — B6b reduces idle wake by ~55%
  G0→t2w_dequeue:          ~621ms (67.4%) — UNDECOMPOSED REGION
    → G3 (talker_first_audio_token) NOT INSTRUMENTED
    → G4 (t2w_submit) NOT INSTRUMENTED
  T2W dequeue→WAV:         267ms (29.0%)
    → Flow: 135ms (p50) — GLOBAL atomic (g_e2e_flow_start_ns)
    → Vocoder: 122ms (p50) — GLOBAL atomic (g_e2e_vocoder_start_ns)
    → Residual: 0ms at ms resolution (Flow+Vocoder == T2W→WAV)

NEXT_BOTTLENECK = G0→t2w_dequeue ≈ 621ms (Talker compute + token accumulation + queue)
  → P9 prerequisite: Add Talker per-step instrumentation (T5-T7, A0-A1)
  → C5 prerequisite: Fix Flow/Vocoder global atomics → request-scoped
  → CHUNK_SIZE=25 = ENGINEERING_POLICY (FROZEN)
```

## Phase 3 Gates (2026-08-01) — N0-N6 FROZEN

### N-Gates: Instrumentation Fixes (ALL FROZEN)

| Gate | Description | Status | Commit | Evidence |
|------|-------------|--------|--------|----------|
| N0 | Corrected state tracking | PASS | `ce53b18` | `F6_PHASE3_CORRECTED_STATE_N0.md` |
| N1 | Binary provenance recorded | PASS | `ce53b18` | `F6_C7_C8_CLI_SMOKE_PROVENANCE.md` |
| N2 | Event schema fix (Q1→Q2) | PASS | `2150274` | enum comment fixed |
| N3 | Q-semantics confirmed | PASS | `2150274` | Q0/Q1/Q2 assigned |
| N4 | 4 global ptrs removed | PASS | `de9290e` | C8ProfileScope RAII |
| N5 | thread_local context | PASS | `de9290e` | exception-safe, nesting-safe |
| N6 | Ring buffer race closed | CLOSED | `0f9be2f` | generation guard + finalize + 3 rejection counters |
| N7 | Schema V5 + docs | PASS | `ce53b18` | `F6_EVENT_SCHEMA_V5_FINAL.md` |
| N8 | Server async 5-request smoke | **PENDING** | — | Requires S5 RelWithDebInfo build |
| N9 | Overlap/late-drain smoke | **PENDING** | — | Requires N8 |

### C-Gates: Correctness + Overhead (BLOCKED on S5)

| Gate | Description | Status | Depends On |
|------|-------------|--------|------------|
| C0 | Checkpoint + state save | **COMPLETE** | — |
| C1 | Canonical raw data audit | **COMPLETE** | `F6_PHASE3_INPUT_DATA_AUDIT.md` |
| C2 | D0→D2 CI=[0,0] audit | **COMPLETE** | `F6_C2_D0D2_CI_ZERO_AUDIT.md` (ROUNDING_ARTIFACT) |
| C3 | D2→G0 zero-gap audit | **COMPLETE** | `F6_C3_D2G0_ZERO_GAP_AUDIT.md` (BIMODAL) |
| C4 | Event contract V4 | **COMPLETE** | `F6_EVENT_CONTRACT_V4.md` |
| C5 | Global fallback removal plan | **COMPLETE** | `F6_C5_GLOBAL_FALLBACK_AUDIT.md` |
| C6 | Request profile lifecycle state machine | **COMPLETE** | `F6_C6_PROFILE_LIFECYCLE_STATE_MACHINE.md` |
| C7 | Talker per-step instrumentation (P9) | **COMPILED+CLI_SMOKED** | `0f9be2f`; CLI smoke: Talker summary present |
| C8 | Flow/Vocoder fine-grained events | **IMPLEMENTED** (N5 thread_local) | `de9290e`; CLI smoke: per-stage present, 0 stale |
| C9 | Instrumentation correctness gate | **NOT_READY** | N8 server async smoke |
| C10 | Instrumentation overhead gate | **NOT_READY** | S5 RelWithDebInfo build |
| C11-C18 | Phase 3 baseline | **PENDING** | C9+C10 |

NEXT PHASE (P7-P15):
  P7:  Rebuild latency budget from valid FP16 data → CONFIRMED: G0→W0 dominates
  P8:  Re-audit G3/G4 event semantics
  P9:  Add Talker per-step low-overhead instrumentation
  P10: 120-request G3→G4 baseline
  P11: Compute/wait decomposition
  P12: Backend reachability + msprof
  P13: Amdahl candidate ranking
  P14: Execute first candidate
  P15: Regression + final state
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
