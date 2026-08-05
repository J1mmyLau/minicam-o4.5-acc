# F6 Phase 3 — Decode-to-Speak Optimization — 项目状态

## 当前阶段

`Phase 3：T1–T13。T11 TTS KV lifecycle 修复完成，T6 重跑 11/11 GATES PASS（T6_REGRESSION=PASS）；
T13 TTS KV bounds guard 边界测试 **PASS**（guard 39 次 prefill_with_emb_tts，10/10 验证项，TTS_KV_GUARD_RUNTIME_COVERAGE=PASS）；
T10 Daily-Omni pilot **DONE**（服务器链 6/6 门全 PASS，DAILY_OMNI_INTERNAL_PILOT=PASS；
期间定位并修复 3 个 P0：user_text 丢弃 / media_type=2 prompt 缺身份句 / image+audio 格式混用 think-loop；
模型能力边界：whisper 编码上限 ~24-26s，Daily-Omni 29.5s 音频 → 输出 "?"，属模型限制非服务器 bug）。
**Step 5 源码冻结完成**：F6DIAG 已移除、EXPERIMENT 标记已清 → 源码冻结提交 **bdd4550** →
**两次独立干净重建 SHA 逐字节一致 → REPRODUCIBLE_BINARY=PASS**（libomni `c4b16937` / server `db258375`；
跨目录 object 级确定性强验证：omni.cpp.o 在 build/ 与 build-test/ 逐字节一致，.so 仅 rpath 路径差异）→
冻结候选 **T6 在冻结二进制上重跑 11/11 GATES PASS（ACCEPT=True）**（binary_sha=db258375，
S13 120/120、Extended 30/30、Voice 5/5、Disconnect 5/5、KV A/B 30 对 valid 28、Smoke 5/5，
integrity cpu_fallback=0 / cann_error=0；user_text 修复触及 media_type=1 音频路径已覆盖）。
候选命名（修正口径）：PRE_T9_T11_CANDIDATE=HISTORICAL_FINAL，POST_T11_RUNTIME_VALIDATION=PASS，
POST_T11_SOURCE_FREEZE=PASS（源码已冻结 bdd4550 + REPRODUCIBLE_BINARY=PASS + T6 冻结二进制 11/11 PASS），
POST_T11_FINAL_CANDIDATE=FINAL_INTERNAL（T13+T10 已完成，源码提交 + 重建 SHA 固化 + 冻结二进制 T6 全过），
OFFICIAL_ACCURACY/官方 Gate 待官方 Harness 复核，COMPETITION_COMPLETE=NOT_CLAIMED（不宣称）` —

（前序阶段）`S13_FROZEN_STRICT_BASELINE=PASS_120_OF_120, R13 Static-Prefix PASS,
CANN_T2W_CANDIDATE=STRONG_INTERNAL_PASS, T4 STRICT REVERIFY PASS,
T6 FINAL INTEGRATED REGRESSION = PASS (11/11 GATES)` —
瓶颈已定位（T2W CPU 设备放置 = 93%），非 LLM Decode→Speak（2.9%）。
**最终集成候选已冻结 = FINAL**（"KV Cache + HTTP token cap + 生命周期
+ CANN Flow/Vocoder" 组合，T5 冻结见 [T5 Freeze](docs/F6_PHASE3_T5_FINAL_INTEGRATED_CANDIDATE.md)，
**T6 最终集成回归全过（ACCEPT=True）→ 候选状态 FINAL**）。
**文档体系完善（Task #354, 2026-08-05）**: 顶层文档从 3 份扩展到 8 份（README + QUICKSTART + ARCHITECTURE + OPTIMIZATION_AND_RESULTS + METHODOLOGY + REPRODUCTION_GUIDE + LIMITATIONS_AND_OFFICIAL_GATES + EVIDENCE_INDEX），2,276 行总量。口径修正：FINAL_INTERNAL 统一、4.8s→0.9s 带完整证据路径、COMPETITION_COMPLETE=NOT_CLAIMED 跨文档一致。质量检查：git diff --check PASS / 14 evidence path 全部存在 / 无 over-claim。

**T9 接口修复（用户 P0 指令：修文本输出接口）** — 见下方 T9 段。libomni.so 保持冻结
`f1d2f86d`，server 由 `e77b43c3` 解冻重建（当前 `594920b6`，T6 重跑验证中）；不伪造官方结果。

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

**源码冻结完成**：`POST_T11_SOURCE_FREEZE = PASS`（F6DIAG 调试打印已移除、EXPERIMENT 标记已清 → 提交 bdd4550 → 干净重建 → SHA 比对一致；
正式冻结源码 = 无调试钩子；user_text/prompt/format 三 P0 修复已纳入新候选，T6 在冻结二进制上重跑 11/11 PASS）；
`POST_T11_FINAL_CANDIDATE = FINAL_INTERNAL`（T13+T10+源码提交 bdd4550+重建 SHA 固化 c4b16937/db258375+冻结二进制 T6 全过）；
**尚未完成（诚实口径）**：
`OFFICIAL_ACCURACY = PENDING_REVERIFY_AFTER_T9`（T9 已修复非流式 text 字段 + SSE bad_alloc + text-only 重复生命周期，
`BLOCKED_BY_CANDIDATE_LIMITATION` 已过时 → pilot 已验证服务器链，官方 Harness 通过前不宣称），
`OFFICIAL_BENCHMARK = PENDING_REVERIFY_AFTER_T9`,
`DAILY_OMNI_INTERNAL_PILOT = PASS`（服务器链 6/6 门全过，见 T10 段；模型输出受 whisper 编码上限限制，29.5s 音频 → "?"），
`COMPETITION_COMPLETE = NOT_CLAIMED`。

## 比赛收口阶段 (2026-08-05，竞赛收口指令)

**状态**：`FINAL_INTERNAL=PASS`，`T6_FROZEN_BINARY_REGRESSION=PASS`（db258375/c4b16937 11/11），
`DAILY_OMNI_INTERNAL_PILOT=PASS`，`REPRODUCIBLE_BINARY=PASS`，`COMPETITION_COMPLETE=NOT_CLAIMED`。
**当前阶段：OFFICIAL_GATE_WAITING（工具链已就绪）** —— 比赛收口文档与 vLLM 迁移文档已完成，不再扩写；等官方 Starter Kit/Harness 到达后直接执行。
官方 Gate（OFFICIAL_DAILY_OMNI / OFFICIAL_TTS_SEED / OFFICIAL_VIDEO_MME / 官方提交包核验）= **NOT_RUN / BLOCKED_BY_OFFICIAL_STARTER_KIT**
（starter kit 45 项 0/45 confirmed，`METRIC_CONTRACT` 全部 provisional）。门状态仪表盘：`docs/competition-submission/OFFICIAL_GATE_STATUS.md`；
就绪度核查：`docs/competition-submission/OFFICIAL_GATE_READINESS_REPORT.md`（7 项核查 + 资产 manifest + 每条 Gate 首命令）；
工具链自检：`docs/competition-submission/OFFICIAL_GATE_TOOLING_SELFTEST.md`（**14/14 PASS**）。
**工具链就绪状态（2026-08-05 收口）**：`OFFICIAL_GATE_TOOLING_READINESS=PASS` /
`DRY_RUN_SUPPORT=PASS` / `BASELINE_CANDIDATE_SYMMETRY=PASS` / `CHUNK_AUDIO_VALIDATION=PASS` /
`PRIVATE_PATH_AUDIT=PASS` / `LOCAL_ASSET_MANIFEST=PASS` / **`OFFICIAL_ASSET_VERSION_MATCH=PENDING_STARTER_KIT`** /
`OFFICIAL_GATES=BLOCKED_BY_OFFICIAL_STARTER_KIT` / `COMPETITION_COMPLETE=NOT_CLAIMED`。
> 资产版本口径：当前 commit/SHA 只称 **CURRENT_LOCAL_ASSET_SNAPSHOT**；官方 starter kit 核对前不得称 OFFICIAL_ASSET_VERSION_CONFIRMED。

**冻结纪律（收口阶段适用）**：冻结源码 bdd4550 **不得修改**。只允许新增/修正：benchmark 脚本 / Demo 适配脚本 / 统计脚本 / 提交目录 / 复现文档 / 官方结果文档。

**已交付**（2026-08-05）：
- `docs/competition-submission/`（11 份：需求矩阵 / 门状态 / **官方 Gate 就绪度报告** / Benchmark 执行计划 / Demo 验证计划 / chunk RTF 测量规范 / 性能报告模板 / 复现审计 / 最终提交清单 / Demo 用户指南 / Demo 录像脚本）
- `submission/`（30 文件提交包骨架：env_check / build / start_server / health_check / demo_smoke / run_performance / analyze_chunk_rtf / run_daily_omni|tts_seed|video_mme stub 等，脚本全部 `set -Eeuo pipefail`，含 VERSION_MANIFEST 与 config/server.env 冻结 env）
- `docs/vllm-migration/` 比赛约束层（新增 `VLLM_METRIC_MEASUREMENT_SPEC.md` + 7 份对齐：主指南 §2.5 赛事优先级 / 组件映射 13→17 字段 / 执行计划重排 V0–V12 / 风险 +R26–R40 / 交接包准入优先 / 实验模板 +5 / README）
- chunk RTF 测量链路已可用（冻结二进制日志行 `T2W线程: … RTF=…` 可离线解析，无需改源码）
- **提交工具链收口（2026-08-05，P0/P1 四修复）**：`run_performance.sh` 支持 `MODE=baseline|candidate` + 输出隔离 `${OUTPUT_ROOT}/<run_id>/<mode>/` + `manifest.json`；`valid_audio` 真实判定（10 排除原因枚举，删除恒 true 桩）+ `check_baseline_candidate_symmetry.py` 对称性检查；4 份 Gate 脚本显式 `--dry-run`（返回码 0/2/3/4）；私有默认路径清除（MODEL_PATH 必填无默认、DATA_ROOT/DEMO_DIR/OUTPUT_ROOT/OFFICIAL_HARNESS_ROOT 从 REPO_ROOT 派生）。新增 `submission/tests/`（单测 21 例 + 对称性 fixtures + 私有路径审计 + `run_selftest.sh`）。离线自检 **14/14 PASS**。
- **CANN CPU/NPU 放置与同步只读审计（2026-08-05，初版 + 修订 + 二次修订 2026-08-05）**：输出 `docs/audit/`（5 份修订）。四级状态拆分：`CANN_STATIC_CAPABILITY_AUDIT=PASS`（源码审计已完成）/ `MAIN_LLM_STATIC_PLACEMENT=PASS`（weight tensor 在 CANN，scheduler 可追踪）/ `MAIN_LLM_RUNTIME_PLACEMENT=PARTIAL`（缺直接 profiler 证据：无 msprof/CANN timeline/backend 分配日志）/ `MAIN_LLM_CPU_FALLBACK_OBSERVED=NO`（不等于证明运行时无 fallback）/ `GRAPH_SPLIT_RUNTIME_COUNT=NOT_MEASURED` / `CPU_PER_CHUNK_CRITICAL_PATH=TO_MEASURE`。二次修订要点："未观察到 CPU fallback" ≠ "运行时 Placement PASS"；二者降级为 PARTIAL + NO。

**下一步（按资产可用性）**：①官方 Starter Kit/Harness 到达 → 先 `--dry-run` 预检（rc=0）→ 跑官方三项 Benchmark（先 baseline 后 candidate，同 RUN_ID）；②官方权重/归一化公布 → 回填 PERFORMANCE_REPORT 官方口径；③官方 Demo 接入 → 跑 D1–D12 并录 Demo 视频；④提交包核验（clean-env 复现 / SHA 一致 / 无 /tmp 依赖）。

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
| **S13_STRICT_BASELINE** | ✅ PASS | 120/120, err=0, prompt_modified=0, first_attempt_ok=120（eos=83 / max_tokens=37，分布与 S13 baseline 略异，采样方差，gate 不受影响） |
| **S13_RUNAWAY_FREE** | ✅ PASS | wall_timeout=0, sliding_window=0 |
| **EXTENDED_OK** | ✅ PASS | 20 long + 10 mixed = 30/30，0 timeout / 0 slide |
| **VOICE_SWITCH_OK** | ✅ PASS | 5/5 有音频输出 |
| **VOICE_SWITCH_ISOLATION** | ✅ PASS | 每请求独立 round 目录，无跨请求污染 |
| **DISCONNECT_SURVIVAL** | ✅ PASS | 5/5 断连后服务器存活 |
| **DISCONNECT_FOLLOWUP** | ✅ PASS | followup 3500 在常驻上下文上成功（drain_complete→RESPONDING→IDLE） |
| **KV_CACHE_AB** | ✅ PASS | 30 pairs / 27 valid（3 对按预声明 A_ERR/B_ERR 排除，机制 30/30），MISS 203.6ms → HIT 83.6ms，Δ_p50=119.7ms，2.44×，loaded=130 |
| **RESTART_3_SESSIONS** | ✅ PASS | 3 个独立 server 会话均正常 |
| **CPU_FALLBACK_ZERO** | ✅ PASS | 0 |
| **CANN_ERROR_ZERO** | ✅ PASS | 0（cann_ok=4） |

**ACCEPT = True**。二进制 db258375/c075c535（当前候选，P0a/P0b 重建后 re-run #2；首轮 run #1 @ e77b43c3 的 KV A/B 为 30/30）。证据：`docs/f6-s13-closure/phase2/t6_integrated_regression.json`。

> KV A/B 30 对 / 27 有效：3 对（pair 4 C1-R4 / pair 17 C3-R5 / pair 20 C4-R2）按脚本预声明 `A_ERR`/`B_ERR` 规则排除（decode POST 客户端 HTTP 异常；server 侧生成已完成、SAVED/HIT/loaded=130 机制 30/30 正常，非缓存污染）。详见 `docs/f6-s13-closure/phase2/t6_kv_ab_27of30.md`。R13 canonical 30/30 严格有效速度结论不受影响。

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

## T9 接口修复 — 文本输出路径 (2026-08-04)

**用户 P0 指令**：修文本输出接口（`/decode` 返回 `{"text":"..."}` + 修 SSE）。
server-omni.cpp 三处修复（**libomni.so 保持冻结 `f1d2f86d`**，纯 server 侧）：

| 修复 | 对应边界 | 说明 |
|------|---------|------|
| ① 非流式 decode 增加 `text` 字段 | F7-2 | stream_decode 后 drain text_queue（去 `__IS_LISTEN__`/`__END_OF_TURN__` 标记）拼接到 `text` |
| ② SSE handler 重构 | F7-1 | worker 每请求仅创建一次（shared_ptr 承载 debug_dir/round_idx 生命周期）；`sink.done()` 终止 chunked 循环（根治 httplib 反复回调→并发 stream_decode→bad_alloc）；resource releaser join worker |
| ③ 纯文本生命周期 | T7 新发现 | use_tts=False decode 后 context_state 一直 ACTIVE + drain_complete_generation 不前进 → 第二次 decode 被守卫拒绝。现 decode 完成即 `drain_complete_generation=request_generation` + `context_state=REUSABLE` |

**媒体协议实测（PASS）**：frame+audio+question，use_tts=False —
非流式 turn1 text=748 字符（eos/142tok）；turn2 常驻复用成功（1088 字符，未再 reject）；
SSE turn3 干净 `[DONE]` 不崩溃不挂起（空文本=模型该轮输出纯音频 token，非接口缺陷）；server 存活。
SSE + use_tts=True 的 T2W drain 仍未接（SSE 路径无 omni_duplex_drain_tts_audio），为已知边界。

## T11 TTS KV lifecycle 修复 (2026-08-04)

**用户指令**（"只修 TTS KV lifecycle → T6 120/120 → 比赛提交"）。T6 重跑（binary `594920b6`）在
R34 遇 HTTP 500 → 定位：req33 的 TTS KV 在**单请求内**累积到 4096 上限（llama_decode
"failed to find a memory slot"）→ 堆损坏 → T9 新增的 text-drain 读 text_queue 抛未捕获异常 →
httplib 无 exception_handler → 静默 500。**修正**：TTS KV 每请求已在 chunk_idx==0 reset
（非跨请求累积；req34 起点 n_past_tts=10）。

| 修复 | 位置 | 说明 |
|------|------|------|
| ① TTS KV bounds guard | omni.cpp `eval_tokens_tts` + `prefill_with_emb_tts` | llama_decode 前检查 `n_past+batch > llama_n_ctx(ctx_tts_llama)` → 提前 return false 优雅截断，绝不把 llama_decode 打进满 KV（与既有 decode 失败截断路径一致；chunk 级 false = 该 chunk 无音频，请求继续） |
| ② text-drain 门控 | server-omni.cpp 非流式 handler | drain 仅 use_tts==False 执行 + try/catch → use_tts=True（T6）路径恢复与已验证二进制**逐字节一致**，从根上消除 500 触发面 |

**状态**：重建完成，libomni `f1d2f86d`→`c075c535`、server `594920b6`→`db258375`；
**T6 重跑 11/11 GATES PASS, ACCEPT=True**（详见下节 T6 重跑记录）。常规回归不触发 TTS guard（0 次），
guard 运行时覆盖由 **T13 边界测试**（`build-test/` 独立测试构建 + `OMNI_TTS_N_CTX=256` 钩子）单独验证，
**TTS_KV_GUARD_RUNTIME_COVERAGE=PASS**（guard=39 prefill_with_emb_tts，10/10 项 PASS，证据 tts_boundary_20260804_170049.json）；
测试后 revert 钩子（正式冻结源码无钩子，与 db258375 逐字节一致）。
**Daily-Omni pilot（任务#324）**：pilot.py + 3 example 视频 9 项 QA 已备好
（/tmp/f6_daily_omni/，含单帧/3x2 蒙太奇/mono 音频），**T13 已完成，pilot 可运行（下一步）**。
**P1 最终交付报告草稿**：`docs/f6-s13-closure/phase2/F6_FINAL_DELIVERY_REPORT.md`
（问题→Profiling→定位→优化→收益→验证 全链，官方 Gate 判定保持 NOT_CLAIMED，pilot 结果待回填）。

## T11 修复后 T6 重跑记录 (2026-08-04) — 11/11 GATES PASS ✅

**冻结数据（Step 2 指令要求）**：

```
CANDIDATE_SOURCE_COMMIT = bdd4550（实际比赛候选源码，P0 媒体输入 + T9/T11 server 修复，F6DIAG 移除）
EVIDENCE_DOCS_COMMIT   = adb9bb6（后续补充 T6 冻结二进制证据 + 状态文档）——交接时分开标注，不笼统写 HEAD=adb9bb6
source HEAD 已更新（冻结完成，工作树 clean）
server SHA256 = db258375c3d2185ca2181da2a5c8f99a95d381413fcb7ab92a771850ba3a4a21（冻结二进制）
libomni SHA256= c4b169376bced6bc3107cfda2f77abf35a634c1e146eed313a193e99e3739ea1（冻结二进制）
model SHA256  = d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de
launch        = stdbuf -oL -eL build/bin/llama-omni-server -m <model> -ngl 999
                --device CANN0 -c 4096 -b 512 -ub 512 --split-mode layer --port 18093
env           = OMNI_KV_CACHE_REUSE=1 OMNI_KV_CACHE_PATH=/tmp/f6_t6/kv_cache
                OMNI_T2W_DEVICE=cann-flow-only OMNI_VOC_DEVICE=gpu ASCEND_RT_VISIBLE_DEVICES=0
run dir       = /tmp/f6_t6/   raw logs = docs/f6-s13-closure/phase2/t6_evidence_pass/
                 （t6_srv.log / kv_ab_srv.log / t6_smoke_srv.log；guard=0 memslot=0）
```

**分析结果**（`docs/f6-s13-closure/phase2/t6_integrated_regression.json`）：

| Gate | 状态 | 关键数据 |
|------|------|----------|
| **S13_STRICT_BASELINE** | ✅ PASS | 120/120, err=0, eos=83/max_tokens=37, prompt_modified=0, first_attempt_ok=120, decode_wall_p50=5475ms, generated_tokens_p50=42 |
| **S13_RUNAWAY_FREE** | ✅ PASS | wall_timeout=0, sliding_window=0 |
| **EXTENDED_OK** | ✅ PASS | 20 long + 10 mixed = 30/30, 0 timeout / 0 slide |
| **VOICE_SWITCH_OK** | ✅ PASS | 5/5 有音频, distinct_hashes=5 |
| **VOICE_SWITCH_ISOLATION** | ✅ PASS | 每请求独立 round 目录 |
| **DISCONNECT_SURVIVAL** | ✅ PASS | 5/5 服务器存活, all_abort_ok |
| **DISCONNECT_FOLLOWUP** | ✅ PASS | followup 常驻上下文成功（drain→IDLE） |
| **KV_CACHE_AB** | ✅ PASS | 30 pairs / 27 valid, MISS 203.6→HIT 83.6ms, Δ=119.7, 2.44×, gate_pass |
| **RESTART_3_SESSIONS** | ✅ PASS | 3 会话正常 |
| **CPU_FALLBACK_ZERO** | ✅ PASS | cpu_fallback=0 |
| **CANN_ERROR_ZERO** | ✅ PASS | cann_error=0, cann_ok=4 |

**ACCEPT = True**。`T6_REGRESSION=PASS`。TTS guard=0 / memslot=0（常规回归不触发是预期；
guard 运行时覆盖由 T13 边界测试单独证明）。

## T10 Daily-Omni Pilot — 服务器链 PASS (2026-08-04)

**任务 #324/#333**。9 项 QA（3 视频 × 3 例，4 case 类型），官方单消息协议
（frame_15s.jpg + audio_mono.wav + question text），media_type=2 / use_tts=False。
证据：`docs/f6-s13-closure/phase2/daily_omni_pilot/`（PILOT_REPORT.md + pilot_single*.json + isolate* + threshold.json）。

**P0 修复（pilot 期间定位，纳入新候选源码）**：
1. **user_text 丢弃** — 分支1(视+音)/分支2(纯音频) 未写 user_text，有媒体时问题文本被丢弃（仅纯文本分支3会写）。
   修复：媒体后补写 `\n` + user_text。prefill n_past 113→665 证实 ~121 文本 token 进入上下文。
2. **media_type=2 prompt 缺身份句** — omni_assistant_prompt 对齐 audio_assistant_prompt
   补上「面壁小钢炮」身份句，修复 media_type=2 纯音频退化（空转/WS → 正常作答）。
3. **image+audio 格式混用 → think-loop** — 分支1 用 duplex 视觉标签 + 单工 audio 包裹导致
   `<think>\n` 空循环；改为视觉标签后直接跟音频 embedding（模型原生视频 QA 格式）→ 确定性作答。

**模型能力边界（文档化，非服务器 bug）**：whisper 音频编码上限 ~24-26s（threshold.json：
24s 正常作答，27s→`?`×256）。Daily-Omni audio_mono.wav=29.5s 超出 → 全 9 项输出 "?"×256。
3s 音频演示（能力内）：7/9 可提取字母预测，服务器链全通。

**服务器链 Gate（full + short 两轮）**：非流式 text 字段 ✅ · SSE 文本+[DONE] ✅ ·
常驻上下文第 2 次请求 ✅（decode#2 text_len=853）· **0 HTTP500 / 0 crash / 0 stale-cross** ·
F6_REQSTATE 11 完整周期无错误 · server alive+healthy 收尾 ✅。**DAILY_OMNI_INTERNAL_PILOT=PASS**。

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
| **P0** | **T11 修复后 T6 重跑** — server db258375 / libomni c075c535，11/11 GATES PASS, ACCEPT=True；`T6_REGRESSION=PASS` | **DONE** |
| **P0** | **T13 TTS KV bounds guard 边界测试** — **DONE：BOUNDARY_TEST PASS**。cap 校准 512→256；根因：TTS-only 会话 LOG_ERR 被默认 CONT 阈值过滤，测试钩子内强制 verbosity=INFO 后 guard 可见；**guard=39（全 prefill_with_emb_tts，5× batch=1 + 34× batch>1，text_start=256=cap），10/10 验证项 PASS，memslot=0/http500=0/崩溃=0，8/8 drain+IDLE，followup 4/4，server healthy**；TTS_KV_GUARD_RUNTIME_COVERAGE=PASS；证据 tts_boundary_20260804_170049.json。**测试钩子待 revert（Step 5）** | **DONE** |
| **P1** | **T10 Daily-Omni pilot** — 9 项 QA + 生命周期/SSE/常驻上下文验证，两轮（29.5s full + 3s short）；证据已归档到 docs/f6-s13-closure/phase2/daily_omni_pilot/（PILOT_REPORT.md）；服务器链 6/6 门 PASS；P0 修复 3 项纳入候选源码；模型输出受 whisper 编码上限（~24-26s）限制 | **DONE — DAILY_OMNI_INTERNAL_PILOT=PASS** |
| **P1** | **Step 5 冻结最终源码候选** — F6DIAG 已移除、EXPERIMENT 标记已清 → commit 源码 bdd4550 → 干净重建 → REPRODUCIBLE_BINARY=PASS → 冻结二进制 T6 重跑 11/11 → F6_FINAL_DELIVERY_REPORT.md | **DONE（POST_T11_SOURCE_FREEZE=PASS，FINAL_INTERNAL）** |
| **P1** | **T7 质量/比赛 Gate** — 评估完成：输入 CONFIRMED（修正协议），输出 BLOCKED_BY_CANDIDATE_LIMITATION（SSE 崩溃）；seed-tts=PENDING_EXTERNAL_ASSETS | **DONE** |
| **P1** | **T8 最终口径** — 内部闭环 FINAL，官方 Gate 不宣称（BLOCKED_BY_CANDIDATE_LIMITATION / NOT_CLAIMED）；最终口径文档 F6_PHASE3_FINAL_FRAMING.md | **DONE** |
| **P0** | **比赛收口 Phase A：需求矩阵 + 执行脚本框架 + Demo 计划 + 提交目录**（用户 12 节收口 Prompt）→ `docs/competition-submission/` 10 份 + `submission/` 30 文件；chunk RTF 采集管线可运行 | **DONE (2026-08-05)** |
| **P0** | **比赛收口 Phase B：vLLM 迁移文档对齐比赛约束层**（用户更新 Prompt）→ 新增 `VLLM_METRIC_MEASUREMENT_SPEC.md` + 更新 7 份 | **DONE (2026-08-05)** |
| **P1** | **运行官方 Gate** — 官方 Daily-Omni / TTS-Seed / Video-MME + 提交包核验（clean-env 复现 / SHA / 无 /tmp） | **BLOCKED_BY_OFFICIAL_STARTER_KIT** |
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
CANN_STATIC_CAPABILITY_AUDIT      = PASS    (supports_op / offload / sync/copy / KV / env var 已查清)
MAIN_LLM_STATIC_PLACEMENT         = PASS    (-ngl 999 weight tensor 在 CANN，scheduler 可追踪)
MAIN_LLM_RUNTIME_PLACEMENT        = PARTIAL (缺直接 profiler 证据：无 msprof/CANN timeline/backend 分配日志)
MAIN_LLM_CPU_FALLBACK_OBSERVED    = NO      (冻结日志未观察到，不等于证明无)
GRAPH_SPLIT_RUNTIME_COUNT         = NOT_MEASURED
CPU_PER_CHUNK_CRITICAL_PATH       = TO_MEASURE (需逐 chunk 运行时预算完成 Amdahl 判定)
T4_STRICT_CANN_T2W_REVERIFY       = PASS   (19/19 correlation, T2W-only delta 全负)
T6_FINAL_INTEGRATED_REGRESSION    = PASS   (11/11 gates, ACCEPT=True; e77b43c3)
T6_RE_RUN_AFTER_T11_FIX           = PASS   (11/11 gates, ACCEPT=True; server db258375 / libomni c075c535)
TTS_KV_GUARD_IMPLEMENTED          = YES    (omni.cpp eval_tokens_tts + prefill_with_emb_tts bounds guard)
TTS_KV_GUARD_RUNTIME_COVERAGE     = PASS   (T13 边界测试: guard=39 prefill_with_emb_tts, 10/10 项 PASS; tts_boundary_20260804_170049.json)
PRE_T9_T11_CANDIDATE              = HISTORICAL_FINAL   (旧 FINAL 称号作废, 仅历史参考)
POST_T11_RUNTIME_VALIDATION       = PASS   (T6 重跑 11/11 + T13 边界 PASS)
T6_FROZEN_BINARY_RE_RUN           = PASS   (11/11 gates, ACCEPT=True; 冻结二进制 db258375/c4b16937; S13 120/120 + Ext 30 + Voice 5 + Disc 5 + KV A/B 28valid + Smoke 5; cpu_fallback=0/cann_error=0)
POST_T11_SOURCE_FREEZE            = PASS   (F6DIAG 移除 + EXPERIMENT 清理 + 提交 bdd4550 + REPRODUCIBLE_BINARY=PASS + 冻结二进制 T6 11/11 PASS)
POST_T11_FINAL_CANDIDATE          = FINAL_INTERNAL  (T13+T10+源码提交+重建 SHA 固化+冻结二进制 T6 全过 → 内部最终候选)
DAILY_OMNI_INTERNAL_PILOT         = PASS   (服务器链 6/6 门; P0 修复 3 项; whisper 上限 29.5s→"?" 为模型限制; PILOT_REPORT.md)
COMPETITION_CLOSURE_DOCS          = DONE   (2026-08-05: docs/competition-submission/ 10 份 + submission/ 30 文件 + chunk RTF 采集链路可运行)
VLLM_MIGRATION_COMPETITION_ALIGN  = DONE   (2026-08-05: VLLM_METRIC_MEASUREMENT_SPEC.md + 7 份对齐比赛约束层)
OFFICIAL_DAILY_OMNI               = NOT_RUN  (BLOCKED_BY_OFFICIAL_STARTER_KIT)
OFFICIAL_TTS_SEED                 = NOT_RUN  (BLOCKED_BY_OFFICIAL_STARTER_KIT)
OFFICIAL_VIDEO_MME                = NOT_RUN  (BLOCKED_BY_OFFICIAL_STARTER_KIT)
OFFICIAL_ACCURACY                 = PENDING_REVERIFY_AFTER_T9  (T9 已修非流式 text + SSE bad_alloc + text-only 生命周期, 旧 BLOCKED 过时; 官方 Harness 前不置 OFFICIAL_PASS)
OFFICIAL_BENCHMARK                = PENDING_REVERIFY_AFTER_T9
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
HEAD:    chore(competition): close official gate tooling readiness gaps   # 工具链收口提交（待提交）
Branch:  perf/f6-decode-to-speak
Worktree: /workspace/llama.cpp-omni-f6

LLAMA_CANDIDATE_SOURCE_COMMIT = bdd4550     # 真正参加 llama 子赛道的冻结源码（不得修改）
COMPETITION_DOCS_COMMIT       = 7a3f11e
VLLM_MIGRATION_DOCS_COMMIT    = 37dc598
FINAL_TRACKING_HEAD           = c328d1b     # 就绪度报告后推进（379e2e6 → b527dce → c328d1b；工具链收口提交在其后）
EVIDENCE_DOCS_COMMIT          = f26323f     # 冻结证据基线
```
Server SHA256:  db258375c3d2185ca2181da2a5c8f99a95d381413fcb7ab92a771850ba3a4a21
libomni SHA256: c4b169376bced6bc3107cfda2f77abf35a634c1e146eed313a193e99e3739ea1
model  SHA256:  d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de
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
