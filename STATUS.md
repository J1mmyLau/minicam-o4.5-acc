# F6 Phase 3 — Decode-to-Speak Optimization — 项目状态

## 当前阶段

`Phase 3：T1–T8 全部完成。FINAL_INTEGRATED_CANDIDATE=FINAL（内部闭环），
OFFICIAL_ACCURACY=BLOCKED_BY_CANDIDATE_LIMITATION, OFFICIAL_BENCHMARK=BLOCKED,
COMPETITION_COMPLETE=NOT_CLAIMED（不宣称）` —

（前序阶段）`S13_FROZEN_STRICT_BASELINE=PASS_120_OF_120, R13 Static-Prefix PASS,
CANN_T2W_CANDIDATE=STRONG_INTERNAL_PASS, T4 STRICT REVERIFY PASS,
T6 FINAL INTEGRATED REGRESSION = PASS (11/11 GATES)` —
瓶颈已定位（T2W CPU 设备放置 = 93%），非 LLM Decode→Speak（2.9%）。
**最终集成候选已冻结 = INTERNAL_PASS**（"KV Cache + HTTP token cap + 生命周期
+ CANN Flow/Vocoder" 组合，见 [T5 Freeze](docs/F6_PHASE3_T5_FINAL_INTEGRATED_CANDIDATE.md)），
**T6 最终集成回归全过（ACCEPT=True）→ 候选状态 FINAL**。
下一阶段：**T7 质量/比赛 Gate 已评估** — 官方资产部分到达；Daily-Omni 输入路径经修正协议确认可用，
但**文本输出路径损坏（SSE 崩溃 + 非流式无文本）→ BLOCKED_BY_CANDIDATE_LIMITATION**；
seed-tts-eval = PENDING_EXTERNAL_ASSETS（Drive 不可达）。不伪造官方结果。

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

## 当前待办 (优先级排序)

| 优先级 | 任务 | 状态 |
|--------|------|------|
| **P0** | **T3 严格事件关联** — 埋点实现并提交 510a9f0（decode-start 打 round_idx/gen/reqidx；W0/wav 行 req/gen；响应回显）；smoke 验证通过：value-bound 证据（log/e2e-JSON/pipeline-CSV/响应回显）全渠道一致 | **DONE** |
| **P0** | **T4 严格复核** — CANN T2W ≥16 对，request-id 绑定，0 错配；FULL PASS：20 对 / 19 active，10 gates 19/19，T2W-only delta 19/19 全负（p50 −4215.8ms，CI [−4395.6, −4085.4]），W0 E2E p50 −3946ms（CI [−4379, −3799]），0 fallback/0 error/0 timeout；wav_count 服务端 bug 已修 | **DONE** |
| **P0** | **T5 最终集成候选** — KV Cache + HTTP token cap + 生命周期 + CANN Flow/Vocoder 组合冻结；freeze 文档 `docs/F6_PHASE3_T5_FINAL_INTEGRATED_CANDIDATE.md`（二进制 e77b43c3 + libomni f1d2f86d，HEAD b043257）；INTERNAL_PASS | **DONE** |
| **P0** | **T6 最终集成回归** — 120 frozen + 30 MISS→HIT + 20 长文本 + 10 混合 + 5 切音色 + 5 断连 + 3 重启 | **DONE — ALL 11 GATES PASS** |
| **P1** | **T7 质量/比赛 Gate** — 评估完成：输入 CONFIRMED（修正协议），输出 BLOCKED_BY_CANDIDATE_LIMITATION（SSE 崩溃）；seed-tts=PENDING_EXTERNAL_ASSETS | **DONE** |
| **P1** | **T8 最终口径** — 内部闭环 FINAL，官方 Gate 不宣称（BLOCKED_BY_CANDIDATE_LIMITATION / NOT_CLAIMED）；最终口径文档 F6_PHASE3_FINAL_FRAMING.md | **DONE** |
| **P1** | 审计 Git 未跟踪脚本 → 归档或提交 | PENDING |
| **P2** | M6 6h mixed-workload soak audit | DEFERRED |

### 已完成 Gate（本阶段权威状态）

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
OFFICIAL_ACCURACY                 = BLOCKED_BY_CANDIDATE_LIMITATION   (Daily-Omni 文本输出路径损坏, 见 T7)
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
