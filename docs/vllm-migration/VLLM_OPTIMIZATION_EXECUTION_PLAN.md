# vLLM-Omni 优化执行计划（V0–V12）

> 每个阶段 16 字段：背景 / 目标 / 为什么现在做 / 前置条件 / 操作步骤 / 命令入口 / 源码审计入口 / 采集字段 / 实验矩阵 / 通过标准 / 失败标准 / 自动停止条件 / 产物 / 决策树 / 资源占用 / 预计时间。
> llama 数字仅作假设；命令以 vLLM 现有文档为准。

---

## 通用前置（所有阶段共用）

- **Run Manifest**：每次 run 记录 `run_id / date / host / NPU / CANN / driver / image / branch / HEAD / model / model revision / deploy config / deploy SHA / env vars / server command / benchmark command`（模板见 `VLLM_TEAM_HANDOFF.md` §6）。
- **指标 schema**：见 `LLAMA_RAW_EVIDENCE_APPENDIX.md` §0 与 T0–T15 事件（主指南 §9）。
- **纪律**：单因素优化；内部结果 ≠ 官方结果；vLLM 未核实一律 `TO_AUDIT`。

---

## V0 — 环境与版本冻结

- **背景**：无冻结基线则一切优化无法归因（llama 一路踩过"旧 Server 占端口/旧结果继承"）。
- **目标**：复现最小可运行环境，全版本 SHA 固化。
- **为什么现在做**：所有后续阶段的比较基准。
- **前置条件**：镜像/驱动/CANN 就绪；NPU 可见。
- **操作步骤**：装镜像 → checkout `minicpm-challenge` → 起 serve → 冒烟。
- **命令入口**：vLLM-Omni 部署文档（`v0.25.0-a3` 镜像；`VLLM_WORKER_MULTIPROC_METHOD=spawn`）。
- **源码审计入口**：`vllm_omni/deploy/*.yaml`。
- **采集字段**：镜像 tag / 分支 HEAD / deploy SHA / 模型 revision / torch/torch_npu/vLLM/CANN/driver / NPU 数量。
- **实验矩阵**：—（无实验）。
- **通过标准**：serve 启动成功，三类请求各 1 次冒烟通过。
- **失败标准**：启动失败或请求失败 → 记录最小复现。
- **自动停止条件**：环境无法在当前硬件复现 → 回退到文档指定版本。
- **产物**：`freeze.txt` + 启动命令 + 日志 + SHA 清单。
- **决策树**：启动成功→V1；启动失败→核对镜像/分支/环境变量。
- **资源占用**：单卡全量加载（数 GB HBM）。
- **预计时间**：半天。

---

## V1 — 官方接口冒烟（text / audio / 多模态）

- **背景**：llama 的 T7 教训——接口字段缺陷直接阻塞官方准确率（非流式无 text、SSE 崩溃）。
- **目标**：三类请求各冒烟通过，响应字段完整。
- **为什么现在做**：先验接口再谈优化。
- **前置条件**：V0 冻结完成。
- **操作步骤**：文本 → 文本+音频（`modalities:["text","audio"]`+`use_tts_template:true`）→ Daily-Omni（`--interleave-mm-strings --daily-omni-pack-mode minicpm-interleave`）；streaming 与 non-streaming 各测。
- **命令入口**：`/v1/chat/completions`；`vllm bench serve --omni`（若已有）。
- **源码审计入口**：chat 响应构造、streaming 实现。
- **采集字段**：HTTP status / 响应字段（text+audio）/ WAV 有效性 / 输出长度。
- **实验矩阵**：3 请求类型 × 2 模式 × 3 次。
- **通过标准**：全部字段完整，无 500/hang/crash。
- **失败标准**：任一字段缺省或崩溃 → 记录为接口缺陷。
- **自动停止条件**：接口缺陷阻断 → 停止该方向，先修接口。
- **产物**：冒烟脚本 + 三份请求/响应样例。
- **决策树**：字段完整→V2；缺 text/audio→查 output processor；崩溃→查 streaming。
- **资源占用**：低（少量请求）。
- **预计时间**：半天。

---

## V2 — 单卡 Baseline

- **背景**：比赛单卡约束，需冻结单卡基线。
- **目标**：三类基线指标（§8.2），p50/p95 稳定。
- **为什么现在做**：所有优化的对照基准。
- **前置条件**：V1 通过。
- **操作步骤**：单卡 YAML 起服 → 三类请求各 ≥10 次 → 记录指标分布。
- **命令入口**：`minicpmo_4_5.yaml`（单卡）+ 请求脚本。
- **源码审计入口**：deploy YAML 的 Stage 布局。
- **采集字段**：文本：TTFT/TPOT/E2E/token；TTS：TTFT/audio TTFP/RTF/音频长度/WAV 有效；AV：packing 参数。
- **实验矩阵**：3 类 × 10 次。
- **通过标准**：p50/p95 稳定，无异常；音频全部有效。
- **失败标准**：指标抖动 >50% 或空音/500 → 记录。
- **自动停止条件**：—（可重试）。
- **产物**：`baseline.json` + 冻结 YAML + 启动命令。
- **决策树**：稳定→V3；不稳定→查设备放置/Stage 布局。
- **资源占用**：单卡持续加载。
- **预计时间**：1 天。

---

## V3 — Stage 级端到端打点（★最核心）

- **背景**：llama 靠打点推翻"decode 是瓶颈"（decode→speak 2.9%，T2W 93%）。
- **目标**：T0–T15 事件全链路，输出"占比 + Amdahl 排序"。
- **为什么现在做**：决定后续所有优化方向；不做打点 = 盲优化。
- **前置条件**：V2 基线。
- **操作步骤**：①在每 Stage 首尾埋 monotonic 时间戳（事件见主指南 §9.1）；②事件带 `request_id/stage_id/worker_id/pid/device`；③跑 ≥10 次 TTS 请求；④算各段 p50/p90/p95、占比、Amdahl 上限。
- **命令入口**：请求脚本 + 可选 torch_npu profiler（msprof）。
- **源码审计入口**：每 Stage 的执行入口/出口；日志点。
- **采集字段**：T0–T15 全事件 + queue wait + device + in/out len。
- **实验矩阵**：10 次 × 同请求；必要时分长/短文本。
- **通过标准**：占比表可复现；若单段 >50% 则锁定第一候选。
- **失败标准**：打点无法产出（llama 教训：输出目录文件系统问题 → 换盘；验收 kernel_details 列数）。
- **自动停止条件**：profiler 3 次失败 → 换目录/换方案。
- **产物**：`stage_timeline.json` + 占比表 + Amdahl 排序。
- **决策树**：T2W/Flow/Vocoder 占比高→V4 设备放置；Thinker prefill 高→V5 Prefix Cache；queue wait 高→V8 调度参数。
- **资源占用**：中（打点开销 <1% 需验证）。
- **预计时间**：1–2 天。

---

## V4 — 设备放置审计（★最核心）

- **背景**：llama T2W CPU→NPU 收益最大（W0 −81.4%）。
- **目标**：确认 Thinker/Talker/audio tokenizer/Flow/Vocoder/multimodal processor 各自设备 + host-device copy 位置。
- **为什么现在做**：V3 若显示语音链占比高，设备放置是第一候选。
- **前置条件**：V3 打点。
- **操作步骤**：①逐 Stage 打 device 字段；②对 T10–T13 查 tensor.device；③用进程/Stage 配置交叉确认；④msprof 采集算子归属；⑤找 host-device copy（输入在 CPU 分配、每 step `.to('npu')`、输出搬回）。
- **命令入口**：日志 + `npu-smi` + msprof。
- **源码审计入口**：Token2Wav / `step_audio2_core` / Flow/Vocoder 实现。
- **采集字段**：每 Stage 设备、copy 次数/字节、`npu-smi` 利用率、CPU 占比。
- **实验矩阵**：3 类请求 × 各 5 次。
- **通过标准**：明确整条语音链真实设备；区分"算子在 CPU"与"控制线程在 CPU"。
- **失败标准**：无法从日志/配置确认 → 标记 TO_AUDIT 并继续。
- **自动停止条件**：—。
- **产物**：`device_placement.md`。
- **决策树**：Flow/Vocoder 在 CPU→V8 迁 NPU（先算子支持审计）；已在 NPU 仍慢→查同步/shape/host copy；占首音 <5%→REJECT_BY_AMDAHL。
- **资源占用**：中（profiling）。
- **预计时间**：1 天。

---

## V5 — Prefix Cache A/B（★最核心）

- **背景**：llama prefill 2.4×，但**该数字不能直接迁移**。
- **目标**：验证固定 system prompt / 参考音频 / TTS template / 多模态 embedding 是否真正复用。
- **为什么现在做**：V3 若 prefill 占比高，这是第一候选。
- **前置条件**：V3；先回答 Cache Key 组成。
- **操作步骤**：①确认开启与缓存粒度；②构造 MISS/HIT（清 KV vs 同前缀）；③≥30 组 strict matched；④配对统计（p50/CI95）；⑤检查 false HIT/collision。
- **命令入口**：请求脚本（A/B 两分支）。
- **源码审计入口**：Prefix Caching 实现 + Cache Key。
- **采集字段**：reused blocks/tokens / prefill latency / TTFT / audio TTFP / E2E / 输出有效性 / false HIT / timeout / HBM。
- **实验矩阵**：30 对 ×（同服务同模型同输入同采样）。
- **通过标准**：HIT vs MISS 端到端（TTFT/audio TTFP）显著（CI95 不跨 0）。
- **失败标准**：端到端无改善 → 审计 Cache Key 覆盖（很可能只缓存 thinker 文本 KV）。
- **自动停止条件**：false HIT 或 collision 率 >0 → 停止并修复 key 语义。
- **产物**：`prefix_cache_ab.json` + 结论。
- **决策树**：端到端改善→OPTIMIZE；仅 prefill 改善→评估摊销；无改善→检查 key 覆盖。
- **资源占用**：中。
- **预计时间**：1–2 天。

---

## V6 — 连续请求 / 取消 / 断连 / 长 TTS（生命周期）

- **背景**：llama 生命周期踩坑最多（跨请求污染、出队≠完成、断连竞争）。
- **目标**：验证跨请求状态隔离 + 断连/取消无 orphan work + 无 KV/queue leak。
- **为什么现在做**：稳定性是比赛现场最容易炸的（用户原话）。
- **前置条件**：V2 基线。
- **操作步骤**：20× text-only + 20× text+audio + 5× 断连 + 5× 取消 + 5× 长 TTS；逐项记录失败清单；监控 HBM/RSS。
- **命令入口**：请求脚本（含断连/取消注入）。
- **源码审计入口**：request identity 贯穿、abort/cancel 路径、Stage 完成语义。
- **采集字段**：hang/500/crash/orphan future/KV block leak/Stage queue leak/跨请求输出/HBM+RSS 增长。
- **实验矩阵**：见操作步骤。
- **通过标准**：全部场景通过；断连/取消后 1 请求内恢复。
- **失败标准**：任一场景失败 → 记录最小复现 + 归因层级。
- **自动停止条件**：发现跨请求污染 → 立即停，先修身份绑定。
- **产物**：`lifecycle.json` + 失败样本。
- **决策树**：HTTP 错误→serving；旧输出混入→request identity；HBM 涨→leak；queue 空但未结束→active/future bookkeeping。
- **资源占用**：中。
- **预计时间**：1–2 天。

---

## V7 — 长 TTS 与 KV 容量（Memory Slot 提前测）

- **背景**：llama 在 `tts_n_past_accumulated=4096` 处 memory-slot。
- **目标**：提前测 Talker/Token2Wav 独立 context 上限。
- **为什么现在做**：长 TTS 是比赛现场另一个高爆点。
- **前置条件**：V6。
- **操作步骤**：长文本→长 TTS；分 Stage 监控 context usage；区分 Thinker/Talker/Token2Wav/block manager 满。
- **命令入口**：长 TTS 请求 + 监控脚本。
- **源码审计入口**：每 Stage max_num_batched_tokens / max_num_seqs / buffer 上限。
- **采集字段**：各 Stage context usage、KV blocks free+used、累计音频 token、HTTP 结果。
- **实验矩阵**：不同长度文本 × 多次。
- **通过标准**：长 TTS 优雅截断或明确报错，不 500/崩溃/污染。
- **失败标准**：memory-slot 类错误 → 诊断矩阵定位层级。
- **自动停止条件**：出现跨请求污染 → 停。
- **产物**：`tts_long_ctx.json` + 诊断矩阵。
- **决策树**：Talker KV 满→调 max_num_* 或截断策略；Token2Wav buffer 满→背压；block manager 满→容量。
- **资源占用**：中。
- **预计时间**：1 天。

---

## V8 — 第一候选优化

- **背景**：V3/V4/V5 已锁定第一瓶颈。
- **目标**：单因素优化落地 + A/B 证明。
- **为什么现在做**：现在才有足够依据动手。
- **前置条件**：V3–V5 结论。
- **操作步骤**：改一个变量 → 冻结其余 → 前后同口径 A/B。
- **命令入口**：改动对应配置/代码。
- **源码审计入口**：目标 Stage。
- **采集字段**：前后 p50/p95/占比。
- **实验矩阵**：≥10 对 matched。
- **通过标准**：端到端真实改善且稳定；无质量/稳定性回归。
- **失败标准**：不在关键路径 → 回滚（llama B6b 教训）。
- **自动停止条件**：A/B 无改善 → 回滚换候选。
- **产物**：优化 diff + A/B 数据。
- **决策树**：改善→保留并回归；无改善→回滚，按 Amdahl 选下一候选。
- **资源占用**：—。
- **预计时间**：2–3 天。

---

## V9 — Seed-TTS

- **背景**：官方 TTS 质量链路。
- **目标**：WER/RTF 达标，无空音。
- **为什么现在做**：官方指标之一。
- **前置条件**：V1–V2。
- **操作步骤**：`vllm bench serve --omni`（Seed-TTS 数据）；请求必须带 `use_tts_template:true`。
- **命令入口**：bench 命令（vLLM 文档）。
- **源码审计入口**：—（bench 层）。
- **采集字段**：audio_ttfp / audio_rtf / WER / 逐条 WER / 失败率 / 空音频率 / 输出音频长度 / 长文本与参考音频长度分桶 / p50/p95。
- **实验矩阵**：全量 Seed-TTS 集。
- **通过标准**：WER 与 RTF 达基线；无空音。
- **失败标准**：请求未进 TTS 路径 → 检查 template 开关。
- **自动停止条件**：空音率 >X% → 停查合成路径。
- **产物**：`seed_tts_report.json` + 失败样本。
- **决策树**：WER 高→查合成/Talker；空音→查设备/数据；RTF 高→V8 设备放置。
- **资源占用**：中。
- **预计时间**：1–2 天。

---

## V10 — Daily-Omni

- **背景**：官方准确率链路。
- **目标**：packing 正确 → 文本答案 → 判分可复现。
- **为什么现在做**：官方质量 Gate。
- **前置条件**：V1；媒体资产与 allowlist 就绪。
- **操作步骤**：先验 packing（image/audio token 数）→ 跑 benchmark（`--interleave-mm-strings --daily-omni-pack-mode minicpm-interleave`，关闭 TTS，greedy/temp 0）。
- **命令入口**：Daily-Omni benchmark 命令（vLLM 文档）。
- **源码审计入口**：processor / packing。
- **采集字段**：准确率 / 每项分数 / packing 日志 / HTTP 失败分母。
- **实验矩阵**：全量 QA。
- **通过标准**：分数可复现；packing 正确。
- **失败标准**：packing 错误 → 假低精度（llama 教训：曾误判模型不支持）。
- **自动停止条件**：packing 或媒体路径错误 → 先修协议。
- **产物**：`daily_omni_report.json`。
- **决策树**：先查 packing → interleave → media path → frame/audio 数量 → prompt → 采样 → 解析器；最后才怀疑模型。
- **资源占用**：中。
- **预计时间**：1–2 天。

---

## V11 — Duplex 实验（独立线）

- **背景**：全双工为 experimental 路径。
- **目标**：单会话全双工最小闭环；不破坏 simplex。
- **为什么现在做**：与主线并行验证。
- **前置条件**：simplex 候选稳定。
- **操作步骤**：duplex YAML 起服 → 单会话 → speak/listen → barge-in → 断线恢复 → 重复 response.done → Stage 崩溃清理。
- **命令入口**：`/v1/realtime?duplex=1` 或 `/v1/duplex`。
- **源码审计入口**：duplex session 实现。
- **采集字段**：会话 TTL / disconnect grace / replay TTL / pending turn / 音频顺序。
- **实验矩阵**：单会话全流程。
- **通过标准**：全流程可用；simplex 回归通过。
- **失败标准**：影响 simplex → 立即回退。
- **自动停止条件**：污染 simplex 候选 → 停 duplex。
- **产物**：`duplex_findings.md`。
- **决策树**：可并行；任何 simplex 破坏 → 回退。
- **资源占用**：额外卡/时段。
- **预计时间**：1 周内穿插。

---

## V12 — 最终回归与冻结

- **背景**：比赛候选需完整回归。
- **目标**：全基线 + 稳定性全集 + 官方链路回归通过。
- **为什么现在做**：收口。
- **前置条件**：V8 候选 + V9/V10。
- **操作步骤**：跑 V2/V6/V7 全集 + Seed-TTS + Daily-Omni；记录状态判定。
- **命令入口**：全部既有脚本。
- **源码审计入口**：—。
- **采集字段**：全部指标。
- **实验矩阵**：全集。
- **通过标准**：稳定、无回归、官方 Harness 可跑通。
- **失败标准**：任一未过 → 回对应阶段。
- **自动停止条件**：—。
- **产物**：最终候选 YAML + 一键脚本 + 报告 + 口径文档（见 `VLLM_TEAM_HANDOFF.md`）。
- **决策树**：全过→冻结 + 口径分离；未过→定位到阶段。
- **资源占用**：全量。
- **预计时间**：2–3 天。

---

## 并行/跳过规则

- V3 与 V4 同一轮完成（打点同时记 device）。
- 若 V3 证明瓶颈在 KV 复用，先 V5 再 V4。
- V11（duplex）可并行，但不得改动 simplex 候选路径。
