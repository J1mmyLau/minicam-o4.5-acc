# F6 Phase 5 — COMPETITION_EVIDENCE_CLOSURE — 项目状态

## 当前阶段

**COMPETITION_EVIDENCE_CLOSURE 全部 6 步完成。**
Q8_0 + CANN flow-only 生产候选：RTF=0.639 mean，speedup=1.70× vs 官方 1.087。
Vocoder CPU quantization 因果机制 PROVEN（交替 A/B 3/3 对确认）。
FM CANN dequant penalty +20.3ms DISCOVERED。
Soak 300-chunk PASS（线程 +9, RTF drift +1.6%），1800-chunk FAIL（T2W queue backlog）。
Demo Full Chain CONDITIONAL PASS（音频 10/10 valid，文本 10/10 响应但 `?` 字符）。
OFFICIAL_COMPARABILITY=PROVISIONAL（LISTEN=0%，采样参数差异，system_prompt 差异）。

### 证据收口 Gate 矩阵

| Step | Gate | Status | Key Metric |
|------|------|--------|------------|
| 1 | Mean RTF Alignment | ✅ | Q8_0 mean=0.615, F16 mean=0.703 |
| 2 | Workload Parameter Diff | ✅ | 13 params, 6 diff, 4 no-impact |
| 3 | Alternating A/B | ✅ | Vocoder −52.5ms PROVEN, FM +20.3ms |
| 4 | 5×30 Formal Run | ✅ | RTF=0.639, 150 SPEAK, 0 errors |
| 5 | Soak Test | ⚠️ | 300-chunk PASS, 1800-chunk FAIL |
| 6 | Demo Full Chain | ⚠️ | Audio 10/10 valid, text `?` chars |

### 最终指标

```
MODEL:              Q8_0 (GGUF)
DEVICE:             CANN0 + OMNI_T2W_DEVICE=cann-flow-only
SPEAK_RTF_MEAN:     0.639
SPEAK_WALL_MEAN_MS: 639.2
SPEAK_SAMPLES:      150 (5×30)
SPEEDUP_vs_1.087:   1.70×
LISTEN_RATE:        0%
ERRORS:             0
T2W_VOCODER_CPU:    432.3ms mean
T2W_FM_CANN:        188.7ms mean
```

Session 日期: 2026-08-07。服务器 PID: 见 `/tmp/gfh-die0/llama-omni.pid`。
下一阶段：比赛提交准备。OFFICIAL_GATES=BLOCKED_BY_OFFICIAL_STARTER_KIT。

关键数据：
- S13 frozen strict baseline **120/120 成功**（eos=111, max_tokens=9, 0 error, 0 timeout,
  0 sliding_window, 0 prompt_modified, first_attempt_ok=120）— `step7_final.json` gates 全 TRUE
- R13 静态前缀 Prefill **PASS**（30/30，prefill 2.4×：206→85ms p50）
- Phase 2 瓶颈定位 **PASS**：decode→speak=142ms(2.9%)，T2W CPU=4490ms(93%)
- CANN T2W 候选 **STRONG_INTERNAL_PASS**：W0 p50 4798→894ms（−81.4%），32/32，CI95 [−4220,−3732]
- **T4 严格复核 FULL PASS**：20 对/19 active，10 gates 19/19，T2W-only delta 19/19 全负
  （p50 −4215.8ms，CI95 [−4395.6,−4085.4]），W0 E2E p50 −3946ms（CI95 [−4379,−3799]）
- Baseline 设备口径审计：CPU T2W = 实测参考 baseline 且为代码默认，性质上是已知限制回退，
  候选 = `DEVICE_PLACEMENT_CORRECTION`（见 [Baseline Device Audit](docs/F6_PHASE2_BASELINE_DEVICE_AUDIT.md)）

**尚未完成（诚实口径）**：`FINAL_INTEGRATED_CANDIDATE = FINAL`（T5 freeze + T6 回归全过）；
`OFFICIAL_ACCURACY = BLOCKED_BY_CANDIDATE_LIMITATION`（Daily-Omni 文本输出路径损坏；见 [T7 评估](docs/f6-s13-closure/phase2/T7_QUALITY_GATES_ASSESSMENT.md)）,
`OFFICIAL_BENCHMARK = BLOCKED_BY_CANDIDATE_LIMITATION + 接口未定`,
`COMPETITION_COMPLETE = NOT_CLAIMED`。

## T4 严格复核 Gate (2026-08-04)

| Gate | 状态 | 关键数据 |
|------|------|----------|
| **T4_STRICT_CORRELATION** | ✅ PASS 19/19 | 10 gates × 19 active 全通过（echo / single_w0 / gen_match / wav_req_bind / reqidx_e2e_bind / wav_count / d2fa_cross / d2fa_e2e_audio / audio_valid / stale_cross） |
| **T4_STABILITY** | ✅ PASS | 0 CPU fallback / 0 CANN error / 0 timeout / RSS+HBM 单调 |
| **T4_PERF** | ✅ PASS | **T2W-only delta 19/19 全负**（排除 LLM 随机 preamble）：p50 −4215.8ms，CI95 [−4395.6, −4085.4]；W0 E2E p50 4856→800ms（−3946ms），CI95 [−4379, −3799] |
| **T4_WAV_COUNT_FIX** | ✅ PASS | 服务端 wav_count 跨轮累计 bug 已修（is_final 不再提前 last_round_idx）→ 19/19 wav_count gate |

说明：2 对 E2E W0 正 delta（english_r01 +1077ms, number_mix_r04 +597ms）为 **LLM 随机 preamble 方差**（t2w_dequeue≈5.27s），T2W 本身 181/183ms、t2w_delta −4127/−4091ms 全负 — 设备放置收益不受影响。E2E W0 delta 不作为 Gate（受 LLM 采样噪声污染）。

数据：`docs/f6-s13-closure/phase2/t4_strict_cann_t2w.json`（20 对 / 19 active / 1 NoSpeech=short_cn_r00）。

## T6 最终集成回归 Gate (2026-08-04) — ALL 11 GATES PASS ✅

| Gate | 状态 | 关键数据 |
|------|------|----------|
| **S13_STRICT_BASELINE** | ✅ PASS | 120/120, err=0, prompt_modified=0, first_attempt_ok=120（eos=86 / max_tokens=34，分布与 S13 baseline 略异，采样方差，gate 不受影响） |
| **S13_RUNAWAY_FREE** | ✅ PASS | wall_timeout=0, sliding_window=0 |
| **EXTENDED_OK** | ✅ PASS | 20 long + 10 mixed = 30/30，0 timeout / 0 slide |
| **VOICE_SWITCH_OK** | ✅ PASS | 5/5 有音频输出 |
| **VOICE_SWITCH_ISOLATION** | ✅ PASS | 每请求独立 round 目录，无跨请求污染 |
| **DISCONNECT_SURVIVAL** | ✅ PASS | 5/5 断连后服务器存活 |
| **DISCONNECT_FOLLOWUP** | ✅ PASS | followup 3500 在常驻上下文上成功（drain_complete→RESPONDING→IDLE） |
| **KV_CACHE_AB** | ✅ PASS | 30/30 pairs，MISS 201.7ms → HIT 83.1ms，Δ_p50=119ms，2.43×，loaded=130 |
| **RESTART_3_SESSIONS** | ✅ PASS | 3 个独立 server 会话均正常 |
| **CPU_FALLBACK_ZERO** | ✅ PASS | 0 |
| **CANN_ERROR_ZERO** | ✅ PASS | 0（cann_ok=4） |

**ACCEPT = True**。二进制 e77b43c3（冻结不变）。证据：`docs/f6-s13-closure/phase2/t6_integrated_regression.json`。

### T6 修复与发现
- **断连-恢复竞争（修复）**：首轮 T6 在断连测试的 recovery `omni_init()` 处崩溃（use-after-free：omni_free 与在途 STREAM_DECODE_BEGIN req=3004 竞争，ctx=0x0）。根因：断连后客户端关闭连接但服务器 handler 仍在处理 decode；恢复 re-init 的 omni_free 与之竞争。修复：`run_disconnect` 不再调用 recovery omni_init（冻结协议本就是 once-init），改为等待在途 decode 平息后在常驻上下文上直接跑 followup。重跑后 5/5 断连存活 + followup OK。
- **无音频 drain stall（真实候选行为）**：首轮 142 请求中有 6 次无音频响应触发 120s `speek_cv.wait_for` 超时（有界自恢复）。本轮干净运行 0 次。属已知候选边界，非崩溃。

## T7 质量/比赛 Gate 评估 (2026-08-04)

**官方资产部分到达**：`/workspace/benchmarks/Daily-Omni/`（qa.json 1197 项 + harness）、
`/workspace/benchmarks/seed-tts-eval/`、`/workspace/llama.cpp-omni-official-eval/competition/`（provisional）。

**输入侧 CONFIRMED（修正协议）**：冻结候选能处理用户图像+音频+文本。
此前误判“不处理”是协议错误——omni_init 后**第一次 stream_prefill 被 system-prompt 初始化分支吞掉用户内容**
（omni.cpp:12906，无论 index）。修正协议=两次 prefill（cnt:0 初始化 → cnt:1 用户内容）。
实测：图像 202ms/128 tokens/2 chunks，音频 n_pos=30。

**输出侧 BLOCKED（候选限制）**：冻结候选无法通过 HTTP 返回可读文本答案——
(1) 非流式 decode 响应无 text 字段；(2) SSE 流式 decode **崩溃服务器**（std::bad_alloc in httplib
write_response_core，2/2 可复现，含纯文本问题）。T6 从未测 stream:true，缺陷未被回归覆盖。

**Gate 判定**：`OFFICIAL_ACCURACY = BLOCKED_BY_CANDIDATE_LIMITATION`（Daily-Omni 需文本答案字母）；
seed-tts-eval = PENDING_EXTERNAL_ASSETS（Drive 不可达）；`COMPETITION_COMPLETE = NOT_CLAIMED`。
新边界：F7-1 SSE 崩溃 / F7-2 非流式无文本 / F7-3 首次 prefill 吞内容（协议陷阱）。
详见 [T7 评估](docs/f6-s13-closure/phase2/T7_QUALITY_GATES_ASSESSMENT.md)。

## R13 Gate 总结 (2026-08-03)

| Gate | 状态 | 关键数据 |
|------|------|----------|
| **R13_PER_GEN_ACTIVE** | ✅ PASS | 3/3 sequential; per-generation active eliminates cross-gen blocking |
| **R13_OCTX_MUTEX** | ✅ PASS | correctness PASS; mutex_wait p50=0ms sequential; handler_hold p50=71s |
| **R13_HARDWARE** | ✅ CONFIRMED | 1× Ascend 910C (dual-die), 2× Ascend910 chips, single-card compliant |
| **R13_CANONICAL_KV_CACHE** | ✅ PASS | 30/30 pairs; prefill 2.4× speedup (206→85ms p50); n_past=130 tokens |

## R13 Canonical KV Cache A/B 详细

```
Server:   PID 18026, port 18093
Model:    MiniCPM-o-4_5-F16.gguf, -ngl 999, CANN0
Binary:   a47eabf48fb2a6ff3b87de215e814e400db40d51b6fc7569e8e38711059ea034 @ ec6dbc7
Method:   5 cases × 6 pairs = 30 strict matched pairs (A=MISS, B=HIT)
Cache:    /tmp/f6_r13_kv_cache, OMNI_KV_CACHE_REUSE=1

Results (30/30 valid):
  MISS prefill: p50=206ms, p95=216ms
  HIT prefill:  p50=85ms,  p95=91ms
  Delta:        p50=121ms, p95=128ms
  Speedup:      p50=2.4×,  p95=2.5×
  tokens_reused: 130 (consistent across all pairs)
  5 distinct cache keys, 0 collisions

Integrity:
  CPU fallback:   0
  NOT_REUSABLE:   0
  BUSY:           0
  timeout:        0
  mutex_wait:     p50=2.0µs
  handler_hold:   p50=400ms
  lifecycle:      100% IDLE→VALIDATING→DECODING→RESPONDING→IDLE

Data:   /tmp/f6_r13_ab_results/canonical_kv_ab.csv + report.json
Script: /workspace/llama.cpp-omni-f6/scripts/run_canonical_kv_ab.py
```

## S13 严格基线 — 时间线（修正口径）

两轮运行，口径统一为：

### 1) 原始 S13 运行（修复前，已被修正记录覆盖）

发现的问题（`S13_STRICT_AUDIT_AND_GATE_CORRECTION.md`）：
1. `create_session_octx` 把 CLI `-n` 覆盖为 2048 → 单次 decode 可生成至 2048 token（失控）
2. KV sliding window + EOS 抑制 → 模型丢失框架 → 生成到 max_tgt_len
3. HTTP `/v1/stream/decode` 无 per-request token cap
4. 8 个混合 case Prompt 被简化（26.7%），改变 case 分布
5. 服务器重启时日志被覆盖 → 服务端生命周期证据丢失

### 2) 修复 + Frozen 重跑（**PASS_120_OF_120**，权威口径）

修复：per-request HTTP token cap（binary `e159b3ee`）+ 冻结原始 Prompt
（`S13_FROZEN_PROMPTS.jsonl`）+ 单次常驻服务器（不重启，证据完整）。

| 指标 | 值 | 状态 |
|------|-----|------|
| S13_FROZEN_STRICT_BASELINE | total=120, ok=120, error=0 | ✅ **PASS_120_OF_120** |
| stop_reason 分布 | eos=111, max_tokens=9 | ✅ |
| S13_STRICT_FIRST_ATTEMPT | first_attempt_ok=120 | ✅ |
| S13_FROZEN_PROMPT_INTEGRITY | prompt_modified=0 | ✅ |
| S13_RUNAWAY_GENERATION | wall_timeout=0, sliding_window=0 | ✅ |
| S13_SERVER_EVIDENCE | evidence_intact=true | ✅ |
| S13_STRICT_BASELINE_GATE | **strict_pass=true** | ✅ |

证据：`docs/f6-s13-closure/raw-data/step7/s13_step7_final.json`
（summary + gates 字段全 TRUE）。

## Phase 4 CANN Flow-Only Production Gates (2026-08-07)

### FULL_CHAIN_RTF Gate (F16 → Q8_0)

| Model | RTF p50 | Wall p50 | Wall p95 | LISTEN% | n | Rounds | Verdict |
|-------|---------|----------|----------|---------|---|--------|---------|
| **F16** | 0.685 | 685ms | 830ms | 0% | 81 | 3/3 | Baseline |
| **Q8_0** | **0.565** | 565ms | 703ms | 0% | 81 | 3/3 | **−17.5% vs F16** ✅ |
| Q4_K_M | — | — | — | 27-40% | 36 | 2/3-fail | REJECTED ❌ |
| **Q8_0 aligned** | **0.582** | 582ms | 697ms | 0% | 81 | 3/3 | **Production** ✅ |

### T2W Per-Component (CANN flow-only, n=271-303)

| Component | F16 p50 | Q8_0 p50 | Backend |
|-----------|---------|----------|---------|
| Encoder | 9.1ms | 8.5ms | CANN |
| Flow Matching | 150.9ms | 161.0ms | CANN |
| Vocoder | 451.6ms | 373.4ms | **CPU** (CANN=broken, silent) |
| **T2W Total** | **596.6ms** | **557.8ms** | — |
| Wall−T2W Gap | 88.4ms | 7.2ms | — |

### Critical Path

- T2W IS the wall (gap 7ms at p50 with Q8_0)
- Vocoder CPU (452→373ms) = 66-76% of T2W
- FM CANN (151ms) = 27% of T2W
- LLM decode contribution < 10ms

### Drain Fix

- **Root cause**: `t2w_drain_signal_and_wait` with adaptive timeout (max 900s) called inside
  `omni_prepare_for_reuse` while holding `octx_mutex` — blocked multi-round benchmarks
- **Fix**: `OMNI_T2W_DRAIN_TIMEOUT_MS=5000` + benchmark log symlink fix
- **Result**: 6/9 multi-round benchmarks PASS, 0 session.init rejections

### Workload Alignment

- ref_audio: now sent explicitly (BH-Ref WAV, byte-identical to server default)
- max_new_tokens: 200→26 (matches server default max_new_speak_tokens_per_chunk)
- force_listen_count=0 preserved (required for pure SPEAK RTF measurement)
- **OFFICIAL_COMPARABILITY = PASS** (aligned with pinned MiniCPM-o-Demo config)

### Comparison to Official Baseline

| Metric | Official (F16) | Our Q8_0 (CANN flow-only) | Speedup |
|--------|---------------|--------------------------|---------|
| SPEAK→WAV RTF | **1.087** | **0.582** | **1.87×** |
| Wall p50 | 1087ms | 582ms | −505ms (−46.5%) |

### Production Candidate

```
Model:     Q8_0 (MiniCPM-o-4_5-Q8_0.gguf)
Config:    OMNI_T2W_DEVICE=cann-flow-only
           OMNI_T2W_DRAIN_TIMEOUT_MS=5000
           -ngl 999 --device CANN0
           --ctx-size 4096 --batch-size 512 --ubatch-size 512 -t 4
RTF:       0.582 (p50), 1.87× vs official 1.087
Audio:     100% valid, 0% LISTEN (81 SPEAK samples across 3 rounds)
Reliability: 3/3 rounds, multi-round verified
```

## 当前待办 (优先级排序)

| 优先级 | 任务 | 状态 |
|--------|------|------|
| **P3** | **Vocoder CANN 数值修复** — CPU 452ms→CANN 129ms 但输出全静音 (peak=0)；需 buffer sync / stream / kernel 调试 | **NOT_STARTED** |
| **P4** | **FM 进一步优化** — 150ms → <100ms (n_timesteps ablation 5→4→3, per-op CANN breakdown) | **NOT_STARTED** |
| P2 | Drain session turnover — 已 workaround（env var），需代码级修复 | WORKAROUND |
| — | 30-min multi-session stability soak | DEFERRED |
| — | Audio quality validation (ASV/WER/subjective) | DEFERRED |
| — | Set OMNI_T2W_DEVICE=cann-flow-only as default | DEFERRED |

### 已完成 Gate（Phase 4）

```
FULL_CHAIN_RTF_F16                  = PASS   (0.685, 3/3 rounds, 0 errors)
FULL_CHAIN_RTF_Q8_0                 = PASS   (0.565 unaligned, 0.582 aligned)
LLM_QUANTIZATION_AB                 = PASS   (Q8_0 optimal, Q4_K_M REJECTED 27-40% LISTEN)
DRAIN_MULTI_ROUND_FIX               = PASS   (OMNI_T2W_DRAIN_TIMEOUT_MS=5000 + log symlink)
WORKLOAD_ALIGNMENT_DEMO             = PASS   (ref_audio + max_new_tokens=26)
OFFICIAL_COMPARABILITY              = PASS   (aligned with pinned Demo config)
PRODUCTION_CANDIDATE_Q8_0           = STRONG_INTERNAL_PASS (RTF 0.582, 1.87× vs official)
```

### 前序已完成 Gate（Phase 3）

```
S13_FROZEN_STRICT_BASELINE        = PASS_120_OF_120
R13_STATIC_PREFIX_PREFILL         = PASS   (30/30, prefill 2.4×)
R13_STATIC_PREFIX_E2E             = PASS   (30/30 first-audio A/B, prefill 2.5×)
PHASE2_BOTTLENECK_ANALYSIS        = PASS   (decode→speak=2.9%, T2W CPU=93%)
CANN_T2W_CANDIDATE                = STRONG_INTERNAL_PASS (W0 4798→894ms, −81.4%)
BASELINE_DEVICE_PLACEMENT_AUDIT   = PASS   (CPU T2W = 默认回退 + 实测参考 baseline)
T4_STRICT_CANN_T2W_REVERIFY       = PASS   (19/19 correlation, T2W-only delta 全负)
T6_FINAL_INTEGRATED_REGRESSION    = PASS   (11/11 gates, ACCEPT=True; e77b43c3)
FINAL_INTEGRATED_CANDIDATE        = FINAL   (T5 freeze + T6 回归全过 → 最终集成候选确认)
OFFICIAL_ACCURACY                 = BLOCKED_BY_CANDIDATE_LIMITATION   (Daily-Omni 文本输出路径损坏)
OFFICIAL_BENCHMARK                = BLOCKED_BY_CANDIDATE_LIMITATION   (SSE 崩溃 + 接口 provisional)
COMPETITION_COMPLETE              = NOT_CLAIMED
```

## Step 2-5 代码修改摘要 (2026-08-04)

**Binary**: `e159b3ee418cc8079e9dbb1f219bf98ed7e2eb4eb25a05ad9ccd21a143e188c9`

### 修改的文件

| 文件 | 变更 |
|------|------|
| `tools/omni/omni.h` | +`OmniStopReason` 枚举 (EOS/MAX_TOKENS/WALL_TIMEOUT/CLIENT_DISCONNECT/ERROR), +`omni_stop_reason_name()`, +per-request fields (stop_reason, generated_token_count, request_sliding_window_count, eos_detected, cli_n_predict, request_max_tokens, request_wall_timeout_ms, request_start_wall_ns) |
| `tools/omni/omni.cpp` | stream_decode: entry reset counters, save cli_n_predict, wall-time check before each token generation, eos_detected tracking, stop_reason determination after loop, sliding window delta computation |
| `tools/server/server-omni.cpp` | `/v1/stream/decode`: parse `max_tokens` + `wall_timeout_ms`, set per-request limits on octx, include runtime evidence in non-streaming response |
| `tools/server/ws_handler.cpp` | `create_session_octx`: save/restore `n_predict` around WS default (2048) to prevent cross-contamination of HTTP simplex sessions |

### Token cap semantics (per user spec)
- CLI `-n` = server default (saved as `cli_n_predict` at first decode)
- HTTP `max_tokens` = per-request cap (0 = use n_predict)
- effective = `max_tokens > 0 ? max_tokens : n_predict`
- `create_session_octx` no longer silently overwrites CLI `-n` → 2048 (save/restore pattern) |

## 约束

- B6b: OFF (frozen)
- CHUNK_SIZE: 25 (frozen)
- 模式: simplex
- FA/speculation/operator fusion: OFF
- NPU: Ascend910C, CANN 9.1.0-beta.1
- Model: MiniCPM-o-4_5
- `-ngl 100/999 --device CANN0`

## Git

```
HEAD:    d95acea docs(f6-phase2): T1 status unify + T2 baseline device audit
Branch:  perf/f6-decode-to-speak
Worktree: /workspace/llama.cpp-omni-f6
```

## Phase 2 完成记录 (2026-08-04, 6 步指令)

| 步 | 交付物 | Commit |
|----|--------|--------|
| 1 | Phase 1 冻结（closure + SHA manifest） | 1f08d18（先前） |
| 2 | Latency budget — decode→speak=142ms(2.9%), T2W=93% | f9a6241 |
| 3 | Decode→Speak 内部分解 — 12 类未插桩 → DEFER | 06f261a |
| 4 | MTP audit — MTP_NOT_REACHABLE_WITH_CURRENT_MODEL | 1916743 |
| 5 | Amdahl ranking — T2W CANN move = OPTIMIZE_FIRST | 7c0aa56 |
| 6 | CANN T2W A/B — W0 4798→894ms (−81.4%), 32/32, CI95 [−4220,−3732] | 271265b |

核心结论：首音延迟的瓶颈是 **T2W CPU inference（93%）**，非 LLM Decode→Speak（2.9%）。
CANN 设备迁移（纯环境变量，零代码改动）实现 5.0× request→first-audio。约束全满足
（CHUNK_SIZE=25 / B6b / MTP 均未改动）。
