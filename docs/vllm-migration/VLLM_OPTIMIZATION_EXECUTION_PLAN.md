# vLLM-Omni 优化执行计划（V0–V12，比赛口径版）

> 每个阶段 16 字段：背景 / 目标 / 为什么现在做 / 前置条件 / 操作步骤 / 命令入口 / 源码审计入口 / 采集字段 / 实验矩阵 / 通过标准 / 失败标准 / 自动停止条件 / 产物 / 决策树 / 资源占用 / 预计时间。
> llama 数字仅作假设；命令以 vLLM 现有文档为准。
> **2026-08-05 重排**：对齐比赛规则——排名指标为 chunk RTF（llama 子赛道）/ TTFT+TTFP+chunk RTF（vLLM 子赛道）；准入=精度相对官方基线 ≤2pp + Demo 可用，先于性能排名。顺序改为 V0 规则冻结 → V1 官方接口冒烟 → V2 三指标 Baseline → V3 三指标 Stage 打点 → V4 设备放置 → V5 Prefix Cache TTFT A/B → V6 TTFP 优化 → V7 chunk RTF 优化 → V8 生命周期长稳 → V9 Daily-Omni → V10 TTS-Seed → V11 Video-MME + Demo → V12 冻结。**Duplex 移入附加实验（DEFER），不得阻塞 Simplex 主线。**

---

## 通用前置（所有阶段共用）

- **Run Manifest**：每次 run 记录 `run_id / date / host / NPU / CANN / driver / image / branch / HEAD / model / model revision / deploy config / deploy SHA / env vars / server command / benchmark command`（模板见 `VLLM_TEAM_HANDOFF.md` §6）。
- **指标口径**：TTFT / TTFP / chunk RTF 的定义、起止事件、raw schema、统计与误判清单见 **`VLLM_METRIC_MEASUREMENT_SPEC.md`**；比赛规则见 **`VLLM_COMPETITION_REQUIREMENTS.md`**。官方权重/归一化未定 → 一律"待官方确认"，**不预设**。
- **纪律**：单因素优化；内部结果 ≠ 官方结果；vLLM 未核实一律 `TO_AUDIT`；任何性能结论必须附 `server_pid / binary_sha / model_sha`。

---

## V0 — 赛事规则冻结

- **背景**：官方 METRIC_CONTRACT 全部 provisional（待确认），且无冻结基线则一切优化无法归因（llama 一路踩过"旧 Server 占端口/旧结果继承"）。
- **目标**：复现最小可运行环境 + 全版本 SHA 固化 + 比赛口径冻结清单（规则/指标/起止点/权重/准入）。
- **为什么现在做**：所有后续阶段的比较基准；官方规则未冻结前任何指标结论都不可申报为官方口径。
- **前置条件**：镜像/驱动/CANN 就绪；NPU 可见；官方 Starter Kit（未到则记录 BLOCKED_BY_OFFICIAL_STARTER_KIT）。
- **操作步骤**：①核对比赛规则与 Starter Kit（评分指标/起止点/权重/准入/Demo/提交格式）→ 输出 `rule_freeze.md`；②装镜像 → checkout `minicpm-challenge` → 起 serve → 冒烟；③输出 `freeze.txt`。
- **命令入口**：vLLM-Omni 部署文档（`v0.25.0-a3` 镜像；`VLLM_WORKER_MULTIPROC_METHOD=spawn`）。
- **源码审计入口**：`vllm_omni/deploy/*.yaml`。
- **采集字段**：镜像 tag / 分支 HEAD / deploy SHA / 模型 revision / torch/torch_npu/vLLM/CANN/driver / NPU 数量 / 官方规则版本 + METRIC_CONTRACT 状态。
- **实验矩阵**：—（无实验）。
- **通过标准**：serve 启动成功，三类请求各 1 次冒烟通过；`rule_freeze.md` 记录齐全（未知项显式标"待官方确认"）。
- **失败标准**：启动失败或规则缺失 → 记录最小复现 + 阻塞项。
- **自动停止条件**：官方 Starter Kit 缺失 → 标 BLOCKED_BY_OFFICIAL_STARTER_KIT，用内部口径占位但**不申报**。
- **产物**：`freeze.txt` + `rule_freeze.md` + 启动命令 + 日志 + SHA 清单。
- **决策树**：启动成功→V1；官方规则到→填口径清单；未到→BLOCKED_BY_OFFICIAL_STARTER_KIT。
- **资源占用**：单卡全量加载（数 GB HBM）。
- **预计时间**：半天。

---

## V1 — 官方接口冒烟（text / audio / 多模态，官方格式）

- **背景**：llama 的 T7 教训——接口字段缺陷直接阻塞官方准确率（非流式无 text、SSE 崩溃），且 packing/参数错误会造成"假低精度"卡准入。
- **目标**：三类请求按**官方格式**冒烟通过，响应字段完整（streaming 与 non-streaming 各测）。
- **为什么现在做**：先验接口再谈优化；接口是准入精度的前提。
- **前置条件**：V0 冻结完成。
- **操作步骤**：文本 → 文本+音频（`modalities:["text","audio"]`+`use_tts_template:true`）→ Daily-Omni（`--interleave-mm-strings --daily-omni-pack-mode minicpm-interleave`）；streaming 与 non-streaming 各测；断言 text 与 audio 字段完整。
- **命令入口**：`/v1/chat/completions`；`vllm bench serve --omni`（若已有）。
- **源码审计入口**：chat 响应构造、streaming 实现。
- **采集字段**：HTTP status / 响应字段（text+audio）/ WAV 有效性 / 输出长度。
- **实验矩阵**：3 请求类型 × 2 模式 × 3 次。
- **通过标准**：全部字段完整，无 500/hang/crash；packing 参数与官方脚本一致。
- **失败标准**：任一字段缺省或崩溃 → 记录为接口缺陷。
- **自动停止条件**：接口缺陷阻断 → 停止该方向，先修接口。
- **产物**：冒烟脚本 + 三份请求/响应样例 + 字段断言结果。
- **决策树**：字段完整→V2；缺 text/audio→查 output processor；崩溃→查 streaming；packing 错→先修协议。
- **资源占用**：低（少量请求）。
- **预计时间**：半天。

---

## V2 — 三指标 Baseline（TTFT / TTFP / chunk RTF）

- **背景**：比赛排名指标（vLLM 子赛道三项 / llama 子赛道 chunk RTF），需冻结单卡基线。
- **目标**：三类基线指标（TTFT / TTFP / chunk RTF）p50/p95 稳定；**chunk RTF 必须逐 chunk 采集**（见指标规范 §4–§5）。
- **为什么现在做**：所有优化的对照基准；排名指标没有基线 = 无归因。
- **前置条件**：V1 通过。
- **操作步骤**：单卡 YAML 起服 → 三类请求各 ≥10 次 → 记录 TTFT/TTFP 分布 + 逐 chunk RTF 全序列（首/中/尾分桶）。
- **命令入口**：`minicpmo_4_5.yaml`（单卡）+ 请求脚本。
- **源码审计入口**：deploy YAML 的 Stage 布局。
- **采集字段**：文本：TTFT/TPOT/E2E/token；TTS：TTFT/audio TTFP/逐 chunk RTF/音频长度/WAV 有效；AV：packing 参数。
- **实验矩阵**：3 类 × 10 次。
- **通过标准**：p50/p95 稳定，无异常；音频全部有效；chunk RTF 排除率 ≤5%。
- **失败标准**：指标抖动 >50% 或空音/500 → 记录；chunk RTF 排除率 >5% → 整个 run 无效。
- **自动停止条件**：—（可重试）。
- **产物**：`baseline.json` + `chunk_rtf_baseline.csv`（逐 chunk）+ 冻结 YAML + 启动命令。
- **决策树**：稳定→V3；不稳定→查设备放置/Stage 布局。
- **资源占用**：单卡持续加载。
- **预计时间**：1 天。

---

## V3 — 三指标 Stage 打点（★最核心）

- **背景**：llama 靠打点推翻"decode 是瓶颈"（decode→speak 2.9%，T2W 93%）。排名指标是三比赛指标，打点必须能**还原逐 chunk** 口径。
- **目标**：T0–T15 事件全链路，输出"逐 chunk 占比 + Amdahl 排序"，覆盖 TTFT / TTFP / chunk RTF 三段。
- **为什么现在做**：决定后续所有优化方向；不做打点 = 盲优化。
- **前置条件**：V2 基线。
- **操作步骤**：①在每 Stage 首尾埋 monotonic 时间戳（事件见主指南 §9.1 + 指标规范 §3）；②事件带 `request_id/stage_id/worker_id/pid/device`；③跑 ≥10 次 TTS 请求；④按 chunk 计算各段 p50/p90/p95、占比、Amdahl 上限；⑤TTFT/TTFP/chunk RTF 各还原一条时间线。
- **命令入口**：请求脚本 + 可选 torch_npu profiler（msprof）。
- **源码审计入口**：每 Stage 的执行入口/出口；日志点。
- **采集字段**：T0–T15 全事件 + queue wait（单列）+ device + in/out len。
- **实验矩阵**：10 次 × 同请求；必要时分长/短文本。
- **通过标准**：占比表可复现；若单段 >50% 则锁定第一候选；三项指标均可从时间线还原。
- **失败标准**：打点无法产出（llama 教训：输出目录文件系统问题 → 换盘；验收 kernel_details 列数）。
- **自动停止条件**：profiler 3 次失败 → 换目录/换方案。
- **产物**：`stage_timeline.json` + 占比表 + Amdahl 排序 + 三指标时间线。
- **决策树**：TTFP 中 Token2Wav/Flow/Vocoder 占比高→V4 设备放置；TTFT 中 prefill 高→V5 Prefix Cache；chunk RTF 中 compute 高→V7；queue wait 高→V6/V8 调度参数。
- **资源占用**：中（打点开销 <1% 需验证）。
- **预计时间**：1–2 天。

---

## V4 — 设备放置审计（★最核心）

- **背景**：llama T2W CPU→NPU 收益最大（W0 −81.4%）；TTFP/chunk RTF 直接受 Token2Wav 设备影响。
- **目标**：确认 Thinker/Talker/audio tokenizer/Flow/Vocoder/multimodal processor 各自设备 + host-device copy 位置。
- **为什么现在做**：V3 若显示语音链（TTFP 后段 / chunk RTF compute）占比高，设备放置是第一候选。
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
- **决策树**：Flow/Vocoder 在 CPU→V6/V7 迁 NPU（先算子支持审计）；已在 NPU 仍慢→查同步/shape/host copy；占首音 <5%→REJECT_BY_AMDAHL。
- **资源占用**：中（profiling）。
- **预计时间**：1 天。

---

## V5 — Prefix Cache TTFT A/B

- **背景**：llama prefill 2.4×，但**该数字不能直接迁移**；TTFT 排名口径下 prefill 是直接成分。
- **目标**：验证固定 system prompt / 参考音频 / TTS template / 多模态 embedding 是否真正复用，且**端到端 TTFT/audio TTFP 下降**。
- **为什么现在做**：V3 若 TTFT 中 prefill 占比高，这是第一候选。
- **前置条件**：V3；先回答 Cache Key 组成。
- **操作步骤**：①确认开启与缓存粒度；②构造 MISS/HIT（清 KV vs 同前缀）；③≥30 组 strict matched；④配对统计（TTFT/audio TTFP p50/CI95）；⑤检查 false HIT/collision；⑥端到端校验（不只看 prefill）。
- **命令入口**：请求脚本（A/B 两分支）。
- **源码审计入口**：Prefix Caching 实现 + Cache Key。
- **采集字段**：reused blocks/tokens / prefill latency / TTFT / audio TTFP / E2E / 输出有效性 / false HIT / timeout / HBM。
- **实验矩阵**：30 对 ×（同服务同模型同输入同采样）。
- **通过标准**：HIT vs MISS 端到端（TTFT/audio TTFP）显著（CI95 不跨 0）。
- **失败标准**：端到端无改善 → 审计 Cache Key 覆盖（很可能只缓存 thinker 文本 KV）。
- **自动停止条件**：false HIT 或 collision 率 >0 → 停止并修复 key 语义。
- **产物**：`prefix_cache_ab.json` + 结论。
- **决策树**：端到端改善→OPTIMIZE 并回归 V8；仅 prefill 改善→评估摊销；无改善→检查 key 覆盖。
- **资源占用**：中。
- **预计时间**：1–2 天。

---

## V6 — TTFP 优化

- **背景**：TTFP = 请求 → 首段**有效**音频包；vLLM 子赛道排名指标之一。
- **目标**：用 V3 打点定位 TTFP 各段占比（请求排队 / Thinker prefill / 首 text token / speak 决策 / Talker 首 token / Token2Wav 首 chunk），对主导段单因素优化。
- **为什么现在做**：V3 已给出 TTFP 分段时间线；只有先分桶才能知道改哪段。
- **前置条件**：V3 打点（TTFP 分段占比）。
- **操作步骤**：①按 TTFP 分段占比排序；②对第一主导段做单因素 A/B（≥10 对 strict）；③检查首 chunk 是否"有效"（空包/静音包不计，见指标规范 M5）。
- **命令入口**：改动对应配置/代码 + 请求脚本。
- **源码审计入口**：主导段对应 Stage。
- **采集字段**：TTFP 全序列、各段耗时、首 chunk 有效性、E2E。
- **实验矩阵**：≥10 对 matched。
- **通过标准**：TTFP 端到端真实改善且稳定；无精度/稳定性回归。
- **失败标准**：不在关键路径 → 回滚（llama B6b 教训）。
- **自动停止条件**：A/B 无改善 → 回滚换候选。
- **产物**：优化 diff + TTFP A/B 数据。
- **决策树**：首 text token 慢→V5 Prefix Cache；speak 决策慢→查策略；Talker 首 token 慢→查设备/调度；Token2Wav 首 chunk 慢→V4 设备 / V7。
- **资源占用**：—。
- **预计时间**：2–3 天。

---

## V7 — chunk RTF 优化

- **背景**：chunk RTF = 每个音频 chunk 生成耗时 ÷ 音频时长；**llama 子赛道核心排名指标**，vLLM 子赛道亦排名。
- **目标**：逐 chunk RTF 下降；首/中/尾分桶各自统计（首 chunk 常含冷启动）。
- **为什么现在做**：V3 打点给出 chunk compute 占比；TTFP 优化后这是下一个排名杠杆。
- **前置条件**：V3 打点（chunk 级 compute 占比）。
- **操作步骤**：①按 chunk compute 占比排序（Flow / Vocoder / 内部 copy / 同步）；②单因素 A/B（≥30 有效 chunk，CI95 不跨 0）；③首/中/尾分桶确认无回归。
- **命令入口**：改动对应配置/代码 + 请求脚本。
- **源码审计入口**：Token2Wav / Flow / Vocoder 实现。
- **采集字段**：逐 chunk compute_ms / audio_duration_ms / chunk_rtf / queue_wait（单列）/ WAV 有效。
- **实验矩阵**：≥30 对 matched。
- **通过标准**：chunk RTF p50 真实改善且稳定；排除率 ≤5%；无精度/稳定性回归。
- **失败标准**：不在关键路径 → 回滚；把 queue_wait 或内部 RTF 混入（误判 M7/M2）。
- **自动停止条件**：A/B 无改善 → 回滚换候选。
- **产物**：优化 diff + chunk RTF A/B 数据。
- **决策树**：Flow/Vocoder 设备慢→V4；backlog→调度/背压；首 chunk 冷启动→预热策略。
- **资源占用**：—。
- **预计时间**：2–3 天。

---

## V8 — 生命周期长稳（连续 / 取消 / 断连 / 长 TTS / 长稳）

- **背景**：llama 生命周期踩坑最多（跨请求污染、出队≠完成、断连竞争、memory-slot）。长稳是官方 Harness 与 Demo 能跑通的前提，前置到精度基准之前。
- **目标**：验证跨请求状态隔离 + 断连/取消无 orphan work + 无 KV/queue leak + 长 TTS 无 memory-slot + 长稳 ≥100 请求无漂移。
- **为什么现在做**：Benchmark 与 Demo 都是连续请求；长稳崩 = 一切指标不可测。
- **前置条件**：V2 基线。
- **操作步骤**：20× text-only + 20× text+audio + 5× 断连 + 5× 取消 + 5× 长 TTS + ≥100 请求长稳；逐项记录失败清单；监控 HBM/RSS。
- **命令入口**：请求脚本（含断连/取消注入）+ 长稳脚本。
- **源码审计入口**：request identity 贯穿、abort/cancel 路径、Stage 完成语义、每 Stage max_num_batched_tokens / max_num_seqs。
- **采集字段**：hang/500/crash/orphan future/KV block leak/Stage queue leak/跨请求输出/HBM+RSS 增长/chunk 完整性（丢 chunk）。
- **实验矩阵**：见操作步骤。
- **通过标准**：全部场景通过；断连/取消后 1 请求内恢复；长稳下指标 p50 漂移 <10%。
- **失败标准**：任一场景失败 → 记录最小复现 + 归因层级。
- **自动停止条件**：发现跨请求污染 → 立即停，先修身份绑定。
- **产物**：`lifecycle.json` + 失败样本。
- **决策树**：HTTP 错误→serving；旧输出混入→request identity；HBM 涨→leak；queue 空但未结束→active/future bookkeeping；memory-slot→分 Stage 定位。
- **资源占用**：中。
- **预计时间**：1–2 天。

---

## V9 — Daily-Omni（准入精度第 1 链）

- **背景**：官方准确率链路；**准入门槛 = 相对官方基线降幅 ≤2pp**，先于性能排名。
- **目标**：packing 正确 → 文本答案 → 判分可复现。
- **为什么现在做**：精度是能否上榜的硬门槛；放主线靠前以便尽早发现协议/接口问题。
- **前置条件**：V1；媒体资产与 allowlist 就绪（官方 Starter Kit）。
- **操作步骤**：先验 packing（image/audio token 数）→ 跑 benchmark（`--interleave-mm-strings --daily-omni-pack-mode minicpm-interleave`，关闭 TTS，greedy/temp 0）→ 与**官方基线**同口径对比降幅。
- **命令入口**：Daily-Omni benchmark 命令（vLLM 文档）。
- **源码审计入口**：processor / packing。
- **采集字段**：准确率 / 每项分数 / packing 日志 / HTTP 失败分母 / **官方基线分数（必须同口径测）**。
- **实验矩阵**：全量 QA。
- **通过标准**：分数可复现；相对官方基线降幅 ≤2pp；packing 正确。
- **失败标准**：packing 错误 → 假低精度（llama 教训：曾误判模型不支持）；只测 candidate 未测 baseline（风险 R27）。
- **自动停止条件**：packing 或媒体路径错误 → 先修协议。
- **产物**：`daily_omni_report.json` + `accuracy_comparison.md`（candidate vs baseline）。
- **决策树**：先查 packing → interleave → media path → frame/audio 数量 → prompt → 采样 → 解析器；最后才怀疑模型；降幅超 2pp → 回退最近一次优化并重测。
- **资源占用**：中。
- **预计时间**：1–2 天。

---

## V10 — TTS-Seed（准入精度第 2 链 + WER/RTF）

- **背景**：官方 TTS 质量链路；准入精度与 Demo 质量的直接成分。
- **目标**：WER/RTF 达标，无空音；相对官方基线同口径。
- **为什么现在做**：精度准入三项基准之一；空音直接破坏 Demo。
- **前置条件**：V1–V2。
- **操作步骤**：`vllm bench serve --omni`（Seed-TTS 数据）；请求必须带 `use_tts_template:true`；输出音频逐条校验有效性。
- **命令入口**：bench 命令（vLLM 文档）。
- **源码审计入口**：—（bench 层）。
- **采集字段**：audio_ttfp / audio_rtf / WER / 逐条 WER / 失败率 / 空音频率 / 输出音频长度 / 长文本与参考音频长度分桶 / p50/p95 / **官方基线同口径值**。
- **实验矩阵**：全量 Seed-TTS 集。
- **通过标准**：WER 与 RTF 达基线；相对官方基线降幅 ≤2pp（若有官方数字）；无空音。
- **失败标准**：请求未进 TTS 路径 → 检查 template 开关；空音 → 查合成路径/设备。
- **自动停止条件**：空音率 >X% → 停查合成路径。
- **产物**：`seed_tts_report.json` + 失败样本。
- **决策树**：WER 高→查合成/Talker；空音→查设备/数据；RTF 高→V7 chunk RTF 优化。
- **资源占用**：中。
- **预计时间**：1–2 天。

---

## V11 — Video-MME + Demo（准入精度第 3 链 + Demo 可用）

- **背景**：官方三项 Benchmark 之一（Video-MME）+ **准入第二门槛 Demo 可用**。
- **目标**：Video-MME 精度达标；官方 Demo 可启动、可交互、音频连续。
- **为什么现在做**：准入 = 精度 ≤2pp **且** Demo 可用；只跑 Benchmark 不算。
- **前置条件**：V8 长稳通过（Demo 是连续交互）；V9/V10 精度链路已通。
- **操作步骤**：①Video-MME benchmark（官方脚本 + 视频资产）；②Demo 启动 → 连接 → 纯文本 → 单图 → 单音频 → 视频 → 语音对话 → 多轮 → 连续语音 → 长稳 → 断连恢复 → 错误恢复（逐项记录，见 `docs/competition-submission/DEMO_VALIDATION_PLAN.md` 的 D1–D12）。
- **命令入口**：Video-MME benchmark 命令 + Demo 启动脚本（官方 Demo）。
- **源码审计入口**：—（bench/Demo 层）。
- **采集字段**：Video-MME 分数 / 失败率；Demo 每用例通过/失败 + 录像。
- **实验矩阵**：Video-MME 全量 + Demo D1–D12。
- **通过标准**：Video-MME 相对官方基线降幅 ≤2pp；Demo 全用例通过、音频连续无卡死。
- **失败标准**：Benchmark 过但 Demo 不可用（风险 R32）→ 单独记录。
- **自动停止条件**：—。
- **产物**：`video_mme_report.json` + `demo_validation.md` + Demo 视频。
- **决策树**：Demo 失败→查接口/生命周期（回 V1/V8）；Video-MME 低→查 packing/媒体路径。
- **资源占用**：中（Demo 常驻）。
- **预计时间**：2 天。

---

## V12 — 最终回归与冻结

- **背景**：比赛候选需完整回归 + 官方提交包。
- **目标**：全基线 + 稳定性全集 + 三基准精度 + Demo + 官方链路回归通过，口径分离。
- **为什么现在做**：收口。
- **前置条件**：V6–V11 通过。
- **操作步骤**：跑 V2/V5/V8 全集 + Daily-Omni + TTS-Seed + Video-MME + Demo 录像；逐项记录状态判定；产出一键复现脚本与提交包。
- **命令入口**：全部既有脚本。
- **源码审计入口**：—。
- **采集字段**：全部指标 + 状态判定。
- **实验矩阵**：全集。
- **通过标准**：稳定、无回归、官方 Harness 可跑通；内部/OFFICIAL 标签严格分离。
- **失败标准**：任一未过 → 回对应阶段。
- **自动停止条件**：—。
- **产物**：最终候选 YAML + 一键脚本 + 报告 + 口径文档 + 提交包（见 `VLLM_TEAM_HANDOFF.md` §9）。
- **决策树**：全过→冻结 + 口径分离；未过→定位到阶段。
- **资源占用**：全量。
- **预计时间**：2–3 天。

---

## 附加实验 — Duplex（DEFER，不阻塞 Simplex 主线）

> **2026-08-05 变更**：Duplex 从主线 V11 移出。比赛规则未明确计入 Duplex；即使计入，也以 Simplex 主线候选完整性为第一优先级。

- **背景**：全双工为 experimental 路径。
- **目标**：单会话全双工最小闭环；**不破坏 simplex**。
- **为什么现在做**：与主线并行验证，但任何时候不得优先于主线。
- **前置条件**：Simplex 候选稳定（V8 通过）。
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
- **预计时间**：1 周内穿插，不占主线 deadline。

---

## 并行/跳过规则

- V3 与 V4 同一轮完成（打点同时记 device）。
- 若 V3 证明 TTFT 中 prefill 主导，先 V5 再 V4。
- V6（TTFP）与 V7（chunk RTF）共用 V3/V4 结论；若 TTFP 已达标，直接进入 V7。
- V8（长稳）是 V9–V11 前置（精度基准与 Demo 的前提），**不可跳过**。
- Duplex 可并行，但不得改动 simplex 候选路径，且不占用主线 deadline。
