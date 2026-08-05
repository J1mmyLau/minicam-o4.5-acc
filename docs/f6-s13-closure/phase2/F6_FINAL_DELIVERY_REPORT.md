# F6 Phase 3 — 最终交付报告（问题→Profiling→定位→优化→收益→验证）

**日期**: 2026-08-04（更新：源码冻结完成 — bdd4550 + REPRODUCIBLE_BINARY=PASS + T6 冻结二进制重跑 11/11 PASS）
**项目**: llama.cpp-omni-f6 — MiniCPM-o-4_5 全模态（视觉+音频+文本+TTS）omni server，1× Ascend 910C (dual-die)
**候选源码**: 冻结 commit `bdd4550`（P0 text/media + T9/T11 server 修复，F6DIAG 已移除）；候选二进制 SHA 已固化：libomni `c4b16937` / server `db258375`（两次干净重建逐字节一致）
**链路状态**: 官方输入→模型→文本答案 = **PILOT_PASS（服务器链）**；判分受模型 whisper 编码上限限制（见 §6/§7）；**POST_T11_SOURCE_FREEZE=PASS，POST_T11_FINAL_CANDIDATE=FINAL_INTERNAL**

---

## 1. 一句话结论

把比赛（Daily-Omni 类）官方评测链在 Ascend 910C 上跑通所需的**性能、接口、生命周期**
三个层面的工程问题全部闭环：性能层面 CANN T2W 设备放置让首音延迟 −81.4%、静态前缀 KV
Cache 让 prefill 提速 2.4×；接口层面修复了"非流式 decode 无文本、SSE 流式崩溃服务器"
两个文本输出缺陷，使官方 Harness 能从模型拿到文本答案；输入层面修复了三个 P0（媒体请求的
问题文本被丢弃、media_type=2 缺身份句、image+audio 格式混用 think-loop），媒体+问题文本能
正确同送进上下文；生命周期层面修复了纯文本常驻会话第二次请求被拒绝的守卫 bug。T6 回归
**11/11 PASS**；Daily-Omni 内部 pilot 服务器链 **6/6 PASS**（0 HTTP500 / 0 crash / 常驻上下文
复用 / SSE+DONE）。模型侧受 whisper 音频编码上限（~24-26s）限制：Daily-Omni 29.5s 音频输出
"?"×256，属模型训练分布边界而非服务器缺陷（已文档化）。**官方 Gate 在官方 Harness 通过前
一律不宣称 PASS。**

---

## 2. 问题（Problem）— 官方链在哪一段断了

| # | 现象 | 影响 |
|---|------|------|
| P1 | 全模态 pipeline 中 T2W（文本→语音）占用 CPU，W0（首个语音 token）延迟高 | 端到端首响应 4.8s+，用户体验差 |
| P2 | 每请求对同一静态系统前缀重复 prefill（KV MISS） | prefill 210ms → 占请求延迟大头 |
| P3 | 服务器上下文生命周期 bug：纯文本会话第二次 decode 被 `drain_gen < request_gen` 守卫拒绝 / 上下文卡在 ACTIVE | 常驻多轮会话无法运行 |
| P4 | SSE 流式 decode 崩溃服务器（std::bad_alloc, 2/2 可复现） | 唯一可能的文本输出路径不可用 |
| P5 | 非流式 decode 响应无 `text` 字段 | 官方 Harness 无法提取答案字母 |
| P6 | 首次 prefill 被 system-prompt 初始化吞掉用户内容 | 输入协议陷阱，需两次 prefill 修正协议 |
| P7 | 有媒体时问题文本（user_text）被丢弃（分支1/分支2 未写） | 模型只看到媒体 token，无法作答（输出 "?"×256） |
| P8 | media_type=2 的 omni_assistant_prompt 缺「面壁小钢炮」身份句 | media_type=2 纯音频退化（空转/WS，不回答） |
| P9 | 分支1 image+audio 用单工 audio 包裹混 duplex 视觉标签 | 模型 think-loop（`<think>\n` 空循环，输出全空） |

→ P4+P5 组合曾使冻结候选无法通过 HTTP 返回可读文本答案，**官方准确率 Gate 一度 BLOCKED**（T9 已修）；P7/P8/P9 由 Daily-Omni pilot 定位并修复。

---

## 3. Profiling（测量，不猜）

| 阶段 | 工具 | 结论 | 证据 |
|------|------|------|------|
| Phase 1 prefill | 请求级计时 A/B | 静态前缀 MISS→HIT prefill p50 210→86ms | R13 A/B 30 对 |
| Phase 2 bottleneck | 全链路 stage 计时 | decode→speak 仅占 2.9%；**T2W CPU 占 93%** | `F6_PHASE2_STEP3_DECODE_SPEAK_BREAKDOWN.md` |
| Phase 2 Amdahl | 阶段收益排序 | T2W 是最优解（最高 Amdahl 上限） | `F6_PHASE2_STEP5_AMDAHL_RANKING.md` |
| T7 接口 | 实测（媒体+纯文本） | SSE `stream:true` 崩溃 2/2；非流式无 text | `T7_QUALITY_GATES_ASSESSMENT.md` §3 |

---

## 4. 定位（Root cause）

| 问题 | 根因 |
|------|------|
| T2W 在 CPU | 设备放置默认回退 CPU（`OMNI_T2W_DEVICE` 未设），CANN flow 侧可跑 |
| prefill 慢 | 每请求重建同一系统前缀，KV cache 未跨请求复用 |
| 纯文本会话第二次被拒 | `drain_complete_generation` 仅在 T2W drain（use_tts 专用）前进；`context_state` 只在 drain 中置 REUSABLE → use_tts=False 永远卡 ACTIVE |
| SSE 崩溃 | httplib chunked provider 回调内创建 decode worker + 写完 `[DONE]` 后 `return true` 未 `sink.done()` → `while(data_available)` 反复回调 → 第二次并发 `stream_decode` → text_queue 字符串损坏 → `std::bad_alloc`（addr2line 定位） |
| 首次 prefill 吞内容 | `system_prompt_initialized=false` 时首次 `stream_prefill` 无条件进入系统提示初始化分支（协议设计，API 陷阱） |
| user_text 丢弃（P7） | 分支1/分支2 构建媒体 token 后从不 evaluate `embeds->user_text`，仅纯文本分支3 写入 |
| media_type=2 退化（P8） | `omni_init` 非双工分支的 `omni_assistant_prompt` 与 audio 版本不一致（缺身份句），影响媒体预填充格式 |
| image+audio think-loop（P9） | 分支1 将音频用 `<|audio_start|>/<|audio_end|>` 单工包裹，而视觉用 duplex 标签；模型原生视频 QA 格式为媒体后直接跟音频 embedding |
| 29.5s 音频→"?" | **模型 whisper 音频编码上限 ~24-26s**（threshold.json 实测），超出后编码退化，与服务器/接口无关 |

---

## 5. 优化（Optimizations）— 全部仅改配置或 server 层，libomni 冻结

| 优化 | 改动 | 约束 |
|------|------|------|
| CANN T2W 设备放置 | 环境变量 `OMNI_T2W_DEVICE=cann-flow-only`（envy 切换） | 不改代码、不改权重 |
| 静态前缀 KV Cache 复用 | 系统前缀持久化 + 指纹校验（Phase 1） | simplex, use_tts=True |
| HTTP token cap + runaway 防护 | server 层每请求限流 | 防生成失控 |
| 生命周期：drain 由 CV 通知 + 每代 active + octx_mutex | server/omni 层 | 消除轮询与竞态 |
| **T9 文本输出** | ① 非流式 decode 后 drain text_queue → `text` 字段；② SSE handler 重构（worker 每请求一次 + `sink.done()` + releaser join）；③ 非 TTS decode 后 `drain_complete_generation=request_generation` + `context_state=REUSABLE` | server 层 |
| **P0 媒体输入**（pilot 定位） | ① 分支1/分支2 媒体后补写 `\n`+user_text（问题文本入上下文，n_past 113→665）；② media_type=2 omni_assistant_prompt 补身份句（对齐 audio）；③ 分支1 移除音频单工包裹（改裸音频 embedding，贴合模型原生视频 QA 格式） | omni.cpp（源码冻结 commit bdd4550） |
| **T11 TTS KV guard** | `eval_tokens_tts` + `prefill_with_emb_tts` 在 llama_decode 前查 `n_past+batch>n_ctx` → 优雅截断，绝不打满 TTS KV cache | omni.cpp |

---

## 6. 收益（Gains）

| 指标 | 前 | 后 | 变化 |
|------|-----|-----|------|
| 静态前缀 prefill p50 | 210 ms | 85–86 ms | **2.4–2.5×** |
| W0（首语音）p50 | 4798 ms | 894 ms | **−81.4%**（CANN T2W A/B 32/32, CI95 [−4220,−3732]） |
| T2W-only delta（严格复核） | — | 19/19 全负 | p50 −4215.8ms, CI95 [−4395.6,−4085.4] |
| request→W0 E2E p50 | 4.69 s | 4.59 s | −120ms（R13 E2E） |
| SSE 文本输出 | 崩溃（std::bad_alloc） | 干净 `[DONE]` | 崩溃根治 |
| 非流式 decode | 无 text | 返回完整文本 | 官方判分可用 |
| 纯文本常驻会话 | 第二次请求被拒 | 连续多轮复用 | 生命周期修复 |
| 媒体+问题文本同送 | 问题文本被丢弃（"?"×256） | 文本进入上下文，模型作答 | P0（n_past 113→665） |
| image+audio 生成 | think-loop 空循环 | 确定性作答 | P0 格式修复 |
| Daily-Omni pilot 服务器链 | 29.5s 音频 → "?"×256（模型 whisper 上限 ~24-26s） | 3s 音频 7/9 可提取字母；服务器链 6/6 门全过 | **模型能力边界，非服务器缺陷** |

---

## 7. 验证（Verification）

| Gate | 判定 | 数据 |
|------|------|------|
| S13_FROZEN_STRICT_BASELINE | PASS_120_OF_120 | err=0, runaway=0, prompt_modified=0 |
| R13_STATIC_PREFIX_PREFILL / E2E | PASS（30/30 + 30/30） | prefill 2.4×/2.5×, W0 E2E −120ms |
| PHASE2_BOTTLENECK_ANALYSIS | PASS | decode→speak=2.9%, T2W CPU=93% |
| CANN_T2W_CANDIDATE | STRONG_INTERNAL_PASS | W0 −81.4% |
| T4_STRICT_CANN_T2W_REVERIFY | PASS（19/19） | T2W-only delta 全负 |
| T6_FINAL_INTEGRATED_REGRESSION | **11/11 PASS**（re-run #2，binary db258375/c075c535） | S13 120 + Extended 30 + Voice 5 + Disconnect 5 + KV A/B 30（27 valid，3 对按预声明 A_ERR/B_ERR 排除，机制 30/30）+ 3 重启；0 CPU fallback / 0 CANN error |
| T6 冻结二进制重跑 | **11/11 PASS**（re-run #3，冻结 binary db258375/c4b16937，meta.binary_sha=db258375） | S13 120/120 + Extended 30/30 + Voice 5/5 + Disconnect 5/5 + **KV A/B 30（valid 28；2 对 C2-R2/C5-R3 按预声明 A_ERR 排除，机制 30/30；MISS 202.8→HIT 82.0ms Δ121.2 2.47×）** + Smoke 5/5 + 3 重启；cpu_fallback=0 / cann_error=0；POST_T11_SOURCE_FREEZE=PASS, FINAL_CANDIDATE=FINAL_INTERNAL |
| R13 canonical vs 冻结 T6 KV 结论 | **两条独立结论** | R13 canonical = 30/30 strict matched pairs（正式机制证明，MISS 206→85ms 2.4×）；Frozen-binary T6 集成 KV check = 28/30 valid（集成回归重复确认，MISS 202.8→82.0ms 2.47×）。方法同源、结论一致，独立归档，不混同 |
| T9 媒体协议 | PASS | text=748/1088 两轮常驻复用；SSE 干净 [DONE] |
| T13 TTS KV guard 边界 | **PASS** | guard=39 prefill_with_emb_tts，10/10 项，memslot=0/http500=0/崩溃=0 |
| Daily-Omni pilot（服务器链） | **PASS（6/6）** | 非流式 text ✅ · SSE+[DONE] ✅ · 常驻上下文第2次 ✅（text_len=853）· 0 HTTP500 · 0 crash · 0 stale-cross · F6_REQSTATE 11 周期无错 · server healthy；证据 `daily_omni_pilot/PILOT_REPORT.md` |
| Daily-Omni 模型输出 | **能力受限（文档化）** | 官方 29.5s 音频 > whisper 编码上限 ~24-26s → "?"×256（threshold.json）；3s 音频 7/9 可提取字母（2/7 正确） |
| P0 媒体输入 | **FIXED（pilot 验证）** | user_text / 身份句 / 格式三修复，image+audio 确定性作答 |
| OFFICIAL_ACCURACY / BENCHMARK | **NOT_CLAIMED**（诚实口径） | 官方 Harness 到达前不宣称；源码冻结 commit bdd4550 后重跑 T6 复核 |

---

## 8. 待回填项（不伪造）

- [x] T6 重跑 11/11 结果 — PASS（server db258375 / libomni c075c535）
- [x] Daily-Omni pilot — 服务器链 6/6 PASS；模型输出受 whisper 上限限制（29.5s→"?"，文档化）
- [x] P0 三修复（user_text / 身份句 / image+audio 格式）+ F6DIAG 移除 — 源码冻结 commit bdd4550
- [x] 干净重建 → 新候选 SHA 固化 → REPRODUCIBLE_BINARY（构建两次比对）— PASS：libomni `c4b16937` / server `db258375`（同目录两次干净重建逐字节一致）
- [x] T6 在冻结源码重建二进制上重跑（user_text 修复触及 media_type=1 音频路径）— PASS：11/11 GATES, ACCEPT=True, binary_sha=db258375
- [ ] 最终口径更新 — 接口/文本路径解阻塞（READY）；官方 Harness 到达前不宣称 OFFICIAL_BENCHMARK_PASS / COMPETITION_COMPLETE

---

## 9. 交付物索引

| 交付物 | 路径 |
|--------|------|
| Phase 2 各步骤 | `docs/F6_PHASE2_STEP{2,3,5,6}_*.md` |
| T5 冻结 | `docs/F6_PHASE3_T5_FINAL_INTEGRATED_CANDIDATE.md` |
| T6 回归 | `docs/f6-s13-closure/phase2/T6_INTEGRATED_REGRESSION_REPORT.md` + `t6_integrated_regression.json` |
| T6 KV A/B 27/30 | `docs/f6-s13-closure/phase2/t6_kv_ab_27of30.md` |
| T13 边界 | `docs/f6-s13-closure/phase2/tts_boundary/tts_boundary_20260804_170049.json` |
| T10 pilot | `docs/f6-s13-closure/phase2/daily_omni_pilot/PILOT_REPORT.md`（含 pilot_single*.json / threshold.json / isolate*） |
| T7 质量 Gate | `docs/f6-s13-closure/phase2/T7_QUALITY_GATES_ASSESSMENT.md` |
| T8 最终口径 | `docs/f6-s13-closure/phase2/F6_PHASE3_FINAL_FRAMING.md` |
| 证据归档 | `docs/f6-s13-closure/phase2/t7_evidence/` |
| 任务状态 | `docs/tracking/TASKS.md` / `AUDIT.md` / `STATUS.md` |
