# 实验模板（Run Manifest / Per-request / 决策 / A/B + 5 个比赛模板）

> 每次实验**必须**用模板记录。模板的目的是：任何结论都能被复核（样本数、配对方式、CI95、来源路径），任何 run 都能被复现（版本、命令、环境全部 SHA 化）。
> 引用位置：执行计划「通用前置」、交接包 §6、主指南 §9.2。
> **比赛模板**（§6–§10，2026-08-05 新增）：Metric Manifest / Benchmark Accuracy Comparison / Demo Validation Record / Per-chunk RTF Record / Official Gate Record。指标口径见 `VLLM_METRIC_MEASUREMENT_SPEC.md`。

---

## 1. Run Manifest（每次 run 一栏）

```markdown
## Run {run_id}

- date: {YYYY-MM-DD}
- host: {主机}
- NPU 拓扑: {如 1× Ascend 910C dual-die}
- CANN: {9.1.0-beta.1}
- driver: {版本}
- image: {镜像 tag}
- branch: {vllm-omni 分支}
- HEAD: {commit}
- deploy YAML: {文件名 + SHA}
- model / revision: {OpenBMB/MiniCPM-o-4_5 @ {revision}}
- env vars: {如 VLLM_WORKER_MULTIPROC_METHOD=spawn}
- server command: {完整命令}
- benchmark command: {完整命令}
- 二进制/SHA: {若有}
- 备注: {环境特殊性}
```

用途：比较不同 run 前先核对 manifest，防止旧进程/旧版本/旧结果污染。

---

## 2. Per-request 记录（每个实验请求一行）

```markdown
| run_id | request_id | 类型(text/audio/av) | mode(stream/non) | T0 | T1 | ... | T15 | in_len | out_len | HTTP | 字段完整 | WAV 有效 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r001 | q001 | audio | non | 0 | 2 | ... | 4700 | 120 | 800 | 200 | yes | yes |
```

- T0–T15 见主指南 §9.1；每事件带 `request_id/stage_id/worker_id/pid/device/timestamp`。
- 聚合口径：p50 / p90 / p95 / CI95；样本数 = 行数。

---

## 3. 决策记录（每个 A/B 或 Gate 一条）

```markdown
## DECISION {D-编号}

- 假设: {一句话，可证伪}
- 实验: {V3 / V4 / ... 引用执行计划阶段}
- run_id: {关联 Run Manifest}
- 样本数: {30 对 / 32 对 / ...}
- 配对方式: {strict matched: 同服务同模型同输入同采样}
- 指标: {p50/p95，如 W0 4798→894ms}
- CI95: {如 [−4220, −3732]}
- 结论: {OPTIMIZE / VERIFY_FIRST / PROFILE_FIRST / DEFER / REJECT_BY_AMDAHL / NOT_APPLICABLE / QUALITY_RISK}
- 依据: {证据文件路径}
- 回滚方法: {怎么回退}
- 日期 / by: {2026-08-04 / name}
```

---

## 4. 配对 A/B 检查清单（做 A/B 前后逐项打勾）

```text
□ 同服务实例（同一进程，端口一致，无旧进程占用）
□ 同模型权重 + 同 revision
□ 同输入（同 prompt / 同参考音频 / 同 TTS template）
□ 同采样（greedy 或固定 temp/seed；官方 benchmark 用 greedy/temp 0）
□ 同负载条件（无并发干扰、无其它 NPU 任务）
□ 配对方式 strict：A 与 B 一一对应
□ 样本数 ≥ 10 对（优化结论 ≥ 30 对）
□ 统计：p50/p95 + CI95（优化结论必须 CI95 不跨 0）
□ 结果带 run_id + 数据文件路径
□ 负结果也记录（防重复踩）
□ 内部结果 ≠ 官方结果（状态标签不混用）
```

---

## 5. 常见错误

| 错误 | 正确 |
|---|---|
| 样本 < 10 对下结论 | 至少 10 对；优化 ≥ 30 对 |
| 报"Hit"不报端到端 | 端到端 TTFT / audio TTFP 必须测 |
| 阶段收益当端到端收益 | 分开展示，明确是阶段口径 |
| 不配对直接比均值 | 配对 + CI95 |
| 旧进程结果当新版本结果 | 起服前核对 run manifest + kill 旧进程 |
| profiler 解析失败当代码问题 | 先换输出目录（本地盘），再走注入路径 |
| 用 request RTF / 内部 RTF 当 chunk RTF | 逐 chunk 采集（指标规范 §4；M1/M2/M3） |
| 只报 candidate 不报官方基线 | 同口径测 baseline（模板 §7；R27） |
| 权重/归一化未知自行加权 | 只报单项分布，权重"待官方确认"（R39） |
| 首/中/尾 chunk 混统计 | 分桶统计（指标规范 §5；R31） |
| 内部 pilot 当官方 Gate | 官方脚本结果才置 OFFICIAL（模板 §10；R38） |

---

## 6. Metric Manifest（指标清单 — 每个 run 的指标口径声明）

> 任何含比赛指标的结论，先开一张 Metric Manifest，防止口径漂移。

```markdown
## Metric Manifest {run_id}

- 指标: {TTFT / TTFP / chunk RTF}
- 定义: {逐指标起止事件，见 VLLM_METRIC_MEASUREMENT_SPEC.md §3}
- 口径: {官方 / 内部 / 校准后内部}
- 官方脚本状态: {已到 / 未到 —— 未到则禁止任何 OFFICIAL 标签}
- 权重/归一化: {官方文档引用；未公布则"待官方确认"，不自行定}
- chunk 语义: {服务端帧 / 固定间隔 / 语义段 —— 官方脚本未定则记录候选}
- 排除规则: {空包 / 解码失败 / 静音 / 超时的定义}
- 统计量: {count/mean/p50/p90/p95/p99/max；首/中/尾分桶}
- 环境指纹: {server_pid / binary_sha / model_sha}
```

---

## 7. Benchmark Accuracy Comparison（基准精度对比 — 准入用）

> 准入 = 相对官方基线降幅 ≤2pp；candidate 与 baseline **必须同口径同框**（R27）。

```markdown
## ACCURACY COMPARISON {A-编号}

- 基准: {Daily-Omni / TTS-Seed / Video-MME}
- candidate run_id: {…}
- baseline run_id: {官方基线同口径跑分 —— 未测则 R27 风险}
- 数据/资产版本: {qa.json 版本 + SHA / allowlist / reference audio 版本}
- 配置: {单卡 YAML SHA / greedy temp0 / 官方参数}
- candidate 分数: {逐项 + 汇总}
- baseline 分数: {逐项 + 汇总}
- 降幅 (candidate − baseline): {数值 / %；禁止跨框架比较}
- 阈值判定: {|降幅| ≤ 2pp → PASS；> 2pp → FAIL + 回退最近一次优化并重测}
- 失败分母: {HTTP 失败 / 空音 / packing 错误计数}
- 口径标注: {内部 or 官方}
- 日期 / by: {…}
```

---

## 8. Demo Validation Record（Demo 验证记录 — 准入第二门槛）

> 对应 `docs/competition-submission/DEMO_VALIDATION_PLAN.md` 的 D1–D12。Benchmark 过但 Demo 不可用 = 准入失败（R32）。

```markdown
## DEMO VALIDATION {D-编号}

- 用例: {D1 冷启动 / D2 Demo 连接 / D3 纯文本 / D4 单图 / D5 单音频 / D6 视频视听 / D7 文本+语音 / D8 多轮 / D9 中长输入 / D10 10min 长稳 / D11 断连重连 / D12 错误恢复}
- 通过/失败: {PASS / FAIL + 失败现象}
- 音频连续: {是/否 —— 是否卡死/断音}
- 录像: {文件路径 / 时间点}
- 复现命令: {启动 + 交互步骤}
- 备注: {与 benchmark 的差异（如 Demo 走 streaming）}
- 日期 / by: {…}
```

---

## 9. Per-chunk RTF Record（逐 chunk RTF 记录 — 排名核心）

> 每 chunk 一条；首/中/尾分桶 × count/mean/p50/p90/p95/p99/max；排除率 ≤5%。
> llama 侧可直接离线解析冻结二进制日志行（`T2W线程: wav_… | …s audio | …ms inference | RTF=…`，见 `submission/scripts/analyze_chunk_rtf.py`）；vLLM 侧用 V3 打点等价事件。

```markdown
| run_id | request_id | chunk_index | is_first | is_final | compute_ms | sample_count | sample_rate | audio_duration_ms | chunk_rtf | queue_wait_ms | valid_audio | error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r001 | q001 | 1 | true | false | 232.4 | 24000 | 24000 | 1000.0 | 0.2324 | 110.5 | yes | - |
```

> 禁止用 request RTF / Flow 内部 RTF / Vocoder 内部 RTF 冒充 chunk RTF（指标规范 M1/M2/M3）。

---

## 10. Official Gate Record（官方 Gate 记录 — 状态判定）

> 每个官方 Gate 一条；**禁止用内部 pilot 顶替**（R38）。OFFICIAL_* 仅在官方脚本结果时置位。

```markdown
## OFFICIAL GATE {G-编号}

- Gate: {准入精度 / 准入 Demo / 排名指标 / 工程复现}
- 官方脚本: {名称 + 版本 + SHA}
- 官方 run_id: {…}
- 内部 run_id（预跑占位）: {… —— 仅内部口径，不置 OFFICIAL}
- 判定: {NOT_RUN / PASS / FAIL / BLOCKED_BY_OFFICIAL_STARTER_KIT}
- 关键数据: {数值 + 口径标注}
- 证据路径: {raw 数据 / 日志 / 报告}
- 状态标签: {INTERNAL_* / OFFICIAL_* 严格分离}
- 复核: {由谁 / 日期}
```
