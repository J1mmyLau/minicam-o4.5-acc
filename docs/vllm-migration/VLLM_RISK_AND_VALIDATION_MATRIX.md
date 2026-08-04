# vLLM-Omni：llama 经验证据矩阵 + 风险清单 + 候选决策

> 证据矩阵回答：**每条 llama 经验来自哪份证据、在 vLLM 中如何验证、优先级多少**。
> 未附证据的内容一律标 **UNPROVEN**。vLLM 侧未核实标 **TO_AUDIT**。
> 全部 llama 实测数字（含 CI95、配对数量、来源路径）见 **`LLAMA_RAW_EVIDENCE_APPENDIX.md`**。
> 风险矩阵 9 字段：触发条件 / 最早可观测信号 / 典型日志 / 错误归因 / 确认方法 / 缓解措施 / 根治措施 / 回归用例 / 状态 owner。

---

## 1. llama 经验证据矩阵（16 条）

列：`# 经验 | 原始问题 | 测量证据 | 最终结论 | 可迁移程度 | vLLM 对应 | vLLM 验证方式 | 风险 | 优先级`

| # | llama 经验 | 原始问题 | 测量证据（文档/raw/源码） | 最终结论 | 可迁移 | vLLM 对应 | vLLM 验证方式 | 风险 | 优先级 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 静态前缀 KV Cache | prefill 每请求重复 | `F6_PHASE3_STEP9_STATIC_PREFIX_REPORT.md`、`R13` A/B（30/30，206→85ms，2.4× / 210→86ms 2.5×） | 固定前缀可复用 | 高（机制通用） | vLLM Prefix Caching | V5 A/B：reused tokens + TTFT/audio TTFP | 只覆盖 thinker 文本 KV | P1 |
| 2 | Persistent Server 连续请求 | 每请求重建前缀 | R13 Canonical（30/30 全过）；`F6_C6_*` | 常驻上下文可用 | 高 | vLLM serving 常驻 + KV cache | V6 连续 20/20 | 生命周期回归 | P1 |
| 3 | request generation 绑定 | 全局布尔量跨请求污染 | `F6_R5_STALE_WRITE_FINAL.md`、`F6_C6_*` | 状态必须绑定请求身份 | 高（方法论） | request_id/sequence_id | V6：回调是否写已复用 state | 隔离不彻底 | P1 |
| 4 | queue empty ≠ task complete | 队列空误判完成 | `F6_PHASE3_R7_DRAIN_AUDIT.md` | 出队≠完成 | 高（教训） | Stage channel/future | V6：response 后查 orphan work | 高（隐蔽） | P1 |
| 5 | dequeue ≠ Flow/Vocoder processed | 后台仍在执行 | R7 happens-before proof；T4 证据 | 完成语义需精确 | 高（教训） | Token2Wav task | V3/V6 打点 | 音频延迟被低估 | P1 |
| 6 | per-generation queued/active | 旧请求唤醒新请求 | `F6_C6/C7`、R13（active==0\|>N） | 按代隔离 | 中（范式参考） | stage request identity | V6 | vLLM 已有等价机制？ | P2 |
| 7 | T2W CPU 设备放置 | W0 高 | `F6_PHASE2_STEP6_CANN_T2W_AB.md`（32/32，4798→894ms，−81.4%）；STEP3（T2W 93%） | 设备放置收益最大 | 高（假设） | Token2Wav 设备布局 | V4 设备审计 + V8 优化 | 单卡 vs 多卡混淆 | **P0** |
| 8 | LLM Decode-to-Speak Amdahl | 误以为 decode 是瓶颈 | `F6_PHASE2_STEP3`（2.9%）、`STEP5`（Amdahl 排序） | 必须先测占比 | 高（方法论） | Stage 打点 | V3 Stage profiler | 过早优化 decode | **P0** |
| 9 | B6b 负结果 | 提前 5 token 触发 TTS 无收益 | `F6_PHASE2_STEP6`（B6b verified 无稳定收益） | 不在关键路径的优化无效 | 高（教训） | Decode-to-Speak 提前触发 | PROFILE_FIRST 后再考虑 | 机械迁移 | P2 |
| 10 | CANN Flow/Vocoder | CPU→NPU | `F6_PHASE2_STEP6`、`BASELINE_DEVICE_AUDIT` | 语音链跑 NPU | 高（假设） | Token2Wav/Flow/Vocoder device | V4/V8 | host-device copy | P1 |
| 11 | SSE/non-stream 文本输出 | 无 text + SSE 崩溃 | `T7_QUALITY_GATES_ASSESSMENT.md`、`T9`（server-omni.cpp） | 接口缺陷阻塞准确率 | 中（接口层教训） | OpenAI streaming + chat 字段 | V1 冒烟两路径 | 字段缺省 | P1 |
| 12 | 多模态输入协议错误 | 首次 prefill 吞内容 | `docs/tracking/F6_PHASE3_INPUT_DATA_AUDIT.md`、`STEP9` 输入协议章 | 先验证 packing | 高（教训） | processor 输出/packing | V1/V10 | 假低精度 | P1 |
| 13 | TTS context / memory slot | `tts_n_past_accumulated=4096` | `t6_evidence_f9/`、`omni.cpp eval_tokens_tts` guard | Talker 有独立上限 | 高（教训） | Talker/Token2Wav context | V7 长 TTS | 归因主模型 KV | P1 |
| 14 | 端口旧进程/测试污染 | 旧进程占用端口 | AUDIT 多轮（端口残留） | 测试前清理 | 中（操作） | 端口/进程管理 | 冒烟前检查 | 低 | P3 |
| 15 | 故障注入 | 断连崩溃 | `T6`（Disconnect 5/5 修复）、T5 freeze | 注入测试必须做 | 高（方法论） | abort/cancel/restart | V6 | orphan work | P2 |
| 16 | 官方质量 Gate 诚实口径 | 区分内部/官方 | `T7/T8`（OFFICIAL_*=NOT_CLAIMED） | 不伪造官方结果 | 高（纪律） | 全部官方判定 | 状态分离 | 口径失真 | P0 |

> **证据路径基准**：`docs/` 均在 llama.cpp-omni-f6 仓库内；commit chain 见 `docs/tracking/F6_PHASE3_HANDOFF.md`（HEAD 参考：T5 freeze `b043257`；Phase 3 handoff `549be69`）；raw 数据：`docs/f6-s13-closure/phase2/t6_integrated_regression.json`、`R13` A/B JSON、`t4_strict_cann_t2w.json` 等。

---

## 2. 重点风险矩阵（25 条 × 9 字段）

> 状态 owner 命名：`V3/V4/…`（执行计划阶段）或 `官方资产/队友`。风险 1–16 源自 llama 实测教训；17–25 为 vLLM 侧特有风险（TO_AUDIT）。

### R1 — llama 静态前缀收益数字被当成 vLLM 收益

- **触发条件**：拿到 vLLM reused tokens / prefill 改善后直接引用 llama 2.4×/58.7%。
- **最早可观测信号**：报告中出现"≈2.4×"但 vLLM 未测。
- **典型日志**：`reused_tokens > 0`（来源：block allocator 统计）。
- **错误归因**：把"命中缓存"当"端到端收益"。
- **确认方法**：V5 端到端 TTFT / audio TTFP A/B（CI95 不跨 0）。
- **缓解措施**：凡引 llama 数字必须加注"llama 侧，未迁移"。
- **根治措施**：口径文档强制要求 vLLM 数字来源。
- **回归用例**：prefix_cache_ab.json 每次优化后重跑。
- **状态 owner**：V5。

### R2 — llama T2W 93% 被当作 vLLM 瓶颈

- **触发条件**：跳过 V3 直接优化 Token2Wav。
- **最早可观测信号**：尚未有 vLLM Stage 占比表。
- **典型日志**：—（无打点数据）。
- **错误归因**：假设设备放置是 vLLM 首音大头。
- **确认方法**：V3 端到端打点 + Amdahl 排序。
- **缓解措施**：V3 完成前禁止 V8 优化动作。
- **根治措施**：把"先打点"写进执行纪律。
- **回归用例**：stage_timeline.json 复跑。
- **状态 owner**：V3。

### R3 — vLLM Prefix Cache 只覆盖 thinker 文本 KV

- **触发条件**：V5 HIT 但端到端无改善。
- **最早可观测信号**：prefill 降但 audio TTFP 不变。
- **典型日志**：reused_tokens 增长、TTFT 下降、audio TTFP 持平。
- **错误归因**：误判"前缀复用无效"（实际是覆盖范围问题）。
- **确认方法**：审计 Cache Key 组成（含 multimodal embedding / reference audio / TTS template）。
- **缓解措施**：先验证 key 覆盖再下结论。
- **根治措施**：需要缓存多模态前缀 → 评估 APC 扩展或等价机制。
- **回归用例**：V5 30 对 A/B。
- **状态 owner**：V5 / TO_AUDIT。

### R4 — Token2Wav / Talker 有独立容量上限（memory-slot 类）

- **触发条件**：长 TTS 或长参考音频。
- **最早可观测信号**：上下文近满（Talker KV / Token2Wav buffer）。
- **典型日志**：`failed to find a memory slot` 类 / buffer overflow。
- **错误归因**：错误归因主模型 KV 或 block manager。
- **确认方法**：V7 分 Stage 监控 context usage。
- **缓解措施**：长 TTS 提前压测 + 截断/背压策略。
- **根治措施**：调 max_num_batched_tokens / max_num_seqs / output cap；明确各 Stage 上限文档。
- **回归用例**：V7 长 TTS 全集。
- **状态 owner**：V7。

### R5 — request 完成 ≠ 所有 Stage 完成

- **触发条件**：异步 Stage（Token2Wav）仍在处理而主响应已返回。
- **最早可观测信号**：response 后仍有日志/CPU/HBM 活动。
- **典型日志**：response.done 之后仍有 Flow/Vocoder 时间戳。
- **错误归因**：把"响应返回"当"处理完成"。
- **确认方法**：V6 response 后查 orphan work / 残留 future。
- **缓解措施**：完成语义打点；响应结束前 drain。
- **根治措施**：Stage 完成以最慢消费者为准。
- **回归用例**：V6 断连/取消 5/5。
- **状态 owner**：V6。

### R6 — cancellation 留 orphan task / future

- **触发条件**：client 断连或取消请求。
- **最早可观测信号**：取消后日志仍持续输出、worker 未退出。
- **典型日志**：cancel 后出现原 request 的 token/音频。
- **错误归因**：以为 abort 即终止全部下游。
- **确认方法**：V6 注入断连，检查残留任务计数。
- **缓解措施**：abort 路径显式取消下游 Stage。
- **根治措施**：request identity 贯穿 + 各 Stage 监听 cancel。
- **回归用例**：V6 Disconnect 场景。
- **状态 owner**：V6。

### R7 — queue empty ≠ worker inactive

- **触发条件**：监控脚本只看 queue depth。
- **最早可观测信号**：queue 空但 Stage 仍在跑（CPU/HBM 高）。
- **典型日志**：channel 空、但 Token2Wav 时间戳持续。
- **错误归因**：误判空闲。
- **确认方法**：V3 同时打 active work 与 queue depth。
- **缓解措施**：完成语义同时看 active worker 与 queue。
- **根治措施**：暴露 per-Stage active/inactive 状态。
- **回归用例**：V6 长稳。
- **状态 owner**：V3 / V6。

### R8 — 多卡诊断结果当成单卡比赛成绩

- **触发条件**：优化实验跑在 2/3 GPU YAML，比赛单卡。
- **最早可观测信号**：报告中含多卡数值而无单卡复验。
- **典型日志**：YAML 文件名含 `_2gpu/_3gpu`。
- **错误归因**：把 stage 分散收益当单卡收益。
- **确认方法**：任何收益必须单卡 YAML 复验。
- **缓解措施**：比赛口径一律单卡。
- **根治措施**：口径文档强制单卡基线。
- **回归用例**：V2/V12 单卡全集。
- **状态 owner**：队友。

### R9 — Daily-Omni packing 错误导致假低精度

- **触发条件**：interleave/pack 顺序错误，模型"答不出来"。
- **最早可观测信号**：同类请求准确率显著低于文档。
- **典型日志**：media token 计数与模型预期不符。
- **错误归因**：误判"模型不支持"（llama 曾如此）。
- **确认方法**：V1/V10 先验 processor 输出 + packing token 数。
- **缓解措施**：基准脚本固定 `--daily-omni-pack-mode minicpm-interleave`。
- **根治措施**：协议验证脚本化。
- **回归用例**：V10 全量 QA。
- **状态 owner**：V10。

### R10 — Duplex 实验阻塞 Simplex 主线

- **触发条件**：并行开发 duplex 改到共享路径。
- **最早可观测信号**：simplex 请求回归（与 duplex 改动同 PR）。
- **典型日志**：simplex 请求失败/变慢。
- **错误归因**：把 duplex 缺陷当主线缺陷。
- **确认方法**：simplex 回归集在 duplex 改动后重跑。
- **缓解措施**：duplex 独立线、独立 YAML、独立提交。
- **根治措施**：V11 定义"不得改动 simplex 候选路径"。
- **回归用例**：V2 基线回归。
- **状态 owner**：V11。

### R11 — 静默 HTTP 500 / 异常吞掉

- **触发条件**：handler 异常未接住，客户端只见 500。
- **最早可观测信号**：HTTP 500 但服务端无 traceback。
- **典型日志**：`write_response_core` 500 分支，无 exception 日志。
- **错误归因**：误判请求本身失败（实为服务端缺陷）。
- **确认方法**：V1 冒烟 + 错误路径注入。
- **缓解措施**：异常 handler 记录 traceback + request_id。
- **根治措施**：异常 → 结构化错误响应。
- **回归用例**：V1/V6。
- **状态 owner**：V1。

### R12 — 接口字段缺省（text/audio 缺字段）

- **触发条件**：非流式无 text、或 audio 字段为空。
- **最早可观测信号**：响应 choices 缺 content / audio 空数组。
- **典型日志**：response 字段 schema 不完整。
- **错误归因**：误判模型能力。
- **确认方法**：V1 校验响应字段完整性。
- **缓解措施**：冒烟断言字段存在。
- **根治措施**：output processor 补齐字段。
- **回归用例**：V1 冒烟。
- **状态 owner**：V1。

### R13 — 流式崩溃 / SSE 处理不当

- **触发条件**：streaming 请求、流结束资源未回收。
- **最早可观测信号**：第二次流式请求失败或服务崩溃。
- **典型日志**：generator 未终结 / `[DONE]` 后仍写。
- **错误归因**：误判为模型问题。
- **确认方法**：V1 streaming 多次循环。
- **缓解措施**：流结束后显式 terminate + join。
- **根治措施**：provider 终结语义正确。
- **回归用例**：V1/V6。
- **状态 owner**：V1。

### R14 — 旧进程 / 端口 / 测试污染

- **触发条件**：多个 server 实例共存。
- **最早可观测信号**：请求打到旧实例，结果异常。
- **典型日志**：端口冲突 / 版本不符。
- **错误归因**：误判新版本回归。
- **确认方法**：run manifest 记录 pid + 端口 + SHA。
- **缓解措施**：起服前 kill 旧进程。
- **根治措施**：一键脚本自清理。
- **回归用例**：V0/V12。
- **状态 owner**：V0。

### R15 — HBM / RSS 单调增长（KV 或队列 leak）

- **触发条件**：长稳运行（数百请求）。
- **最早可观测信号**：HBM/RSS 随请求数线性上升。
- **典型日志**：block 计数增长、free 不回收。
- **错误归因**：误判为正常缓存。
- **确认方法**：V6 长稳后观察内存基线。
- **缓解措施**：定期快照 + 重启窗口。
- **根治措施**：block/队列回收审计。
- **回归用例**：V6 20/20 长稳。
- **状态 owner**：V6。

### R16 — 单卡显存不够引发的二次分配/换页

- **触发条件**：长文本 + 长 TTS 同时峰值。
- **最早可观测信号**：峰值 HBM 逼近上限、TTFT 异常抖动。
- **典型日志**：OOM 重试、host fallback。
- **错误归因**：误判算子慢。
- **确认方法**：V2/V7 峰值 HBM 采集。
- **缓解措施**：调 max_num_seqs / batch。
- **根治措施**：容量规划表。
- **回归用例**：V7 长 TTS。
- **状态 owner**：V7。

### R17 — device 放置与文档不符（Flow/Vocoder 实际在 CPU）

- **触发条件**：配置声明的设备与实际算子设备不一致。
- **最早可观测信号**：`npu-smi` 利用率低 + CPU 高。
- **典型日志**：算子落在 CPU 设备。
- **错误归因**：误以为已跑 NPU。
- **确认方法**：V4 逐 Stage tensor.device + msprof 算子归属。
- **缓解措施**：device_placement 文档逐项核实。
- **根治措施**：显式 device 绑定。
- **回归用例**：V4 复验。
- **状态 owner**：V4。

### R18 — host-device copy 主导首音

- **触发条件**：音频/多模态输入在 CPU 分配、逐 step `.to('npu')`。
- **最早可观测信号**：audio TTFP 高但算子本身不慢。
- **典型日志**：copy 时间占比高（profiler）。
- **错误归因**：误判为算子慢。
- **确认方法**：V4 msprof 统计 copy 耗时/字节。
- **缓解措施**：输入提前放 NPU / 复用 buffer。
- **根治措施**：消除关键路径 copy。
- **回归用例**：V4/V8 A/B。
- **状态 owner**：V4。

### R19 — 批次/容量配置不合理（max_num_seqs / max_num_batched_tokens）

- **触发条件**：并发或长请求下吞吐/时延异常。
- **最早可观测信号**：queue wait 长、长请求被分批打散。
- **典型日志**：request 被拆到多个 step。
- **错误归因**：误判为解码慢。
- **确认方法**：V3 queue wait 打点 + 配置审计。
- **缓解措施**：调参 A/B。
- **根治措施**：按负载形态定容量。
- **回归用例**：V3/V8。
- **状态 owner**：V3。

### R20 — 长请求 E2E p95 严重拖尾（llama 121.6s 教训）

- **触发条件**：长文本长 TTS 混合负载。
- **最早可观测信号**：p95 远超 p50 数量级。
- **典型日志**：个别请求超长耗时。
- **错误归因**：误判为常态。
- **确认方法**：V2 记录 p50/p95 分布。
- **缓解措施**：超时/截断策略。
- **根治措施**：长 TTS 分块 + 背压。
- **回归用例**：V2/V7。
- **状态 owner**：V7。

### R21 — 参考音频/多模态资产缺失导致假失败

- **触发条件**：官方 benchmark 需要的媒体资产未就绪。
- **最早可观测信号**：请求失败率异常、字段缺省。
- **典型日志**：media load 失败。
- **错误归因**：误判模型不支持。
- **确认方法**：核对 allowlist + 资产路径。
- **缓解措施**：V1 先跑最小媒体样例。
- **根治措施**：资产清单 + 加载检查脚本。
- **回归用例**：V1/V10。
- **状态 owner**：官方资产。

### R22 — TTS 模板开关未透传（请求未进 TTS 路径）

- **触发条件**：请求缺 `use_tts_template:true` / modalities 缺 audio。
- **最早可观测信号**：请求无 audio 输出。
- **典型日志**：响应无 audio 字段。
- **错误归因**：误判合成失败。
- **确认方法**：V1 请求参数核对。
- **缓解措施**：冒烟脚本固定参数。
- **根治措施**：协议校验。
- **回归用例**：V1。
- **状态 owner**：V1。

### R23 — 并发/锁竞争（mutex / GIL 类型）

- **触发条件**：多 Stage 并行访问共享状态。
- **最早可观测信号**：queue wait / 锁等待 p50 异常。
- **典型日志**：lock 等待时间高。
- **错误归因**：误判为 GPU 慢。
- **确认方法**：V3 打点锁等待（llama 曾 mutex_wait p50=0ms，作对照）。
- **缓解措施**：无锁队列 / 分片。
- **根治措施**：状态分区。
- **回归用例**：V3/V6。
- **状态 owner**：V3。

### R24 — profiler 产物解析失败 / 数据不可用

- **触发条件**：V3 采集。
- **最早可观测信号**：`run failed`、无 CSV、trace_view 截断。
- **典型日志**：`run failed` 计数 > 0。
- **错误归因**：误判为代码/权限问题（实际多为输出目录文件系统）。
- **确认方法**：把失败 raw 数据换盘重解析。
- **缓解措施**：输出目录放本地盘。
- **根治措施**：验收脚本（kernel_details 47 列 + JSON 合法）。
- **回归用例**：V3 每次采集后验收。
- **状态 owner**：V3。

### R25 — 官方 Gate 口径混用（内部结果当官方 PASS）

- **触发条件**：官方 Harness/资产未定时宣称 PASS。
- **最早可观测信号**：报告出现 OFFICIAL_BENCHMARK_PASS 而官方未跑。
- **典型日志**：状态标签混用。
- **错误归因**：把内部质量当官方成绩。
- **确认方法**：状态分离清单核对（见 Handoff §7）。
- **缓解措施**：状态字面量强制。
- **根治措施**：官方 Gate 仅在官方 Harness 通过后置位。
- **回归用例**：每次报告前核对。
- **状态 owner**：队友。

---

## 3. 优化候选决策清单（decision 只能从以下选）

按 llama Amdahl 经验排序；**不得因 llama 成功直接标 vLLM 为 PASS**。

| 候选 | decision（建议） | 依据 |
|---|---|---|
| 端到端 Stage 打点 | **PROFILE_FIRST**（V3，最先做） | §3.2 推翻 decode 假设 |
| Flow/Vocoder/Token2Wav 设备放置 | **VERIFY_FIRST**（V4/V8） | §3.3 最大收益假设 |
| Prefix Caching（含多模态/TTS 前缀） | **VERIFY_FIRST**（V5） | §3.1 |
| multimodal embedding 缓存 | **TO_AUDIT**（先审计 Cache Key） | §10.1 |
| Thinker/Talker Stage 布局 | **EXPERIMENT**（单卡先冻结，多卡仅诊断） | §13 |
| Stage queue wait / max_num_batched_tokens / max_num_seqs | **PROFILE_FIRST**（V3 数据后定） | V3 |
| PIECEWISE graph / 算子融合 | **DEFER**（需先证明 Stage 占比） | Amdahl |
| workspace 复用 | **DEFER** | Amdahl |
| host-device copy 消除 | **PROFILE_FIRST**（V4 量化后） | §3.3 |
| 输出序列化 | **PROFILE_FIRST**（V3 量化后） | V3 |
| Decode-to-Speak 提前触发 | **REJECT_BY_AMDAHL（默认）**，仅当 profiling 证明占比够大才 **EXPERIMENT** | §3.2 / B6b 负结果 |
| 全双工 | **NOT_APPLICABLE**（独立实验线，不阻塞主线） | §17 |
| 修改 thinker decode 以降低 TTFT | **QUALITY_RISK**（可能不是瓶颈） | §3.2 |

---

## 4. 未核实即 UNPROVEN / TO_AUDIT 汇总

```text
UNPROVEN：本文中任何未附 llama 证据路径的结论
TO_AUDIT：vLLM 侧全部源码级结论（组件名/函数/字段/Schema）
          └ 需队友在 vllm-omni 仓库与 vLLM 主仓库核对后转 CONFIRMED 或修正
```

> 一旦 TO_AUDIT 项核实，请在本文件对应行追加 `→ CONFIRMED (date, by)` 并附 commit 引用。
