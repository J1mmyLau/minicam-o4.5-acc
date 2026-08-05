# vLLM-Omni 比赛指标测量规范（TTFT / TTFP / chunk RTF）

> **用途**：给 vLLM-Omni 队友的唯一指标口径来源。回答四个问题：
> 1. 三项比赛指标（chunk RTF / TTFT / TTFP）到底怎么算？
> 2. 内部打点起止事件与官方脚本可能差在哪？
> 3. 每项指标的 raw 数据记什么、怎么统计、哪些情况必须判无效？
> 4. 哪些坑会让人"测出一个假指标"（误判清单）。
>
> **硬性纪律**（与主指南 §3.10 一致，不重复）：
> - 官方权重/归一化未公布前一律标注"待官方确认"；**禁止自行定权重**。
> - 内部测量 ≠ 官方成绩；官方脚本到达前不得置位任何 OFFICIAL 标签。
> - llama 数字只作参考标尺，**不是 vLLM 结果**。
> - 配套：`VLLM_COMPETITION_REQUIREMENTS.md`（比赛约束）、`LLAMA_RAW_EVIDENCE_APPENDIX.md`（llama 数字出处）。

---

## 1. 三项指标定义

| 指标 | 定义 | 单位 | 方向 | llama 子赛道 | vLLM 子赛道 |
|---|---|---|---|---|---|
| **chunk RTF** | 每个音频 chunk 的生成耗时 ÷ 该 chunk 的音频时长 | 无量纲（RTF<1 快于实时） | 越低越好 | **核心排名指标** | 排名指标 |
| **TTFT** | 请求发出 → 首个有效 text token | ms | 越低越好 | 分析指标 | 排名指标 |
| **TTFP** | 请求发出 → 第一段可用音频 chunk/packet | ms | 越低越好 | 分析指标 | 排名指标 |

> - llama 子赛道官方规则明示排名核心为**逐 chunk RTF**；TTFT/TTFP 在 llama 侧属分析指标，排名权重以官方最终文档为准。
> - vLLM 子赛道三项均为排名指标，最终成绩为三者综合（归一化/权重以官方最终评测文档为准，**本规范不预设**）。

## 2. 官方口径 vs 内部口径

| 项 | 官方口径（以官方脚本为准） | 内部口径（本规范允许） | 关系 |
|---|---|---|---|
| 数据源 | 官方 Harness 逐请求/逐 chunk 记录 | 服务日志（冻结 llama 二进制已输出 chunk RTF 行）或客户端时间戳 | 官方脚本到达前用内部口径占位，**不宣称 OFFICIAL** |
| 起始时间 | 官方脚本定义（待确认：含客户端发送/网络/预处理？） | `T0 request received`（服务端接收） | 若官方含网络与音频/图像预处理，则内部 TTFT 会偏小 |
| 结束判定 | 官方脚本定义 | 内部事件（见 §3） | 官方脚本到达后必须校准一次 |
| chunk 边界 | 官方脚本定义（服务端帧 / 固定间隔 / 语义段？） | 服务端实际 chunk（llama 为每次 T2W 落盘一个 WAV） | 边界不同则 RTF 不可直接对比 |
| 归一化/权重 | 官方最终文档 | **不预设** | 禁止自行定权重 |

> 当前状态：`/workspace/llama.cpp-omni-official-eval/competition/` 的 METRIC_CONTRACT 全部 provisional（待官方确认）。任何内部报告必须显式标注口径："内部口径（官方脚本未定）"。

## 3. 内部打点：指标起止事件（映射 T0–T15）

主指南 §9.1 的 T0–T15 事件在此映射到三项指标：

```text
T0 request received ──────────┬──→ T3 首个非空 text token         = TTFT
                              ├──→ T13 首个有效音频 chunk 完整生成 = TTFP（首个有效包）
                              └──→ 每个 chunk: T11 Flow begin → T12 Vocoder end = chunk 计算耗时
```

| 指标 | 起点 | 终点 | 说明 |
|---|---|---|---|
| TTFT | `T0` | `T3`（首个**非空** text token；空 token/占位符不计） | 若官方计 preprocessing，需加 `T0'`（请求经网络到达前） |
| TTFP | `T0` | `T13`（首段音频 chunk 完整生成且 WAV 有效，**空包/静音包不计**） | 区分"第一个数据包"与"第一个有效音频包"（误判 R29） |
| chunk RTF | 每个 chunk 的 `T11` | 同 chunk 的 `T12` | 用**生成耗时**，不是相邻 chunk 的到达间隔；`queue_wait` 单列不并入 RTF |

**chunk RTF 计算**：

```text
chunk_rtf = (T12 − T11) ÷ (sample_count ÷ sample_rate)
          = chunk 计算耗时(ms) ÷ chunk 音频时长(ms)
```

- 音频时长 = `sample_count / sample_rate`（WAV 有效前提下）。
- `T12 − T11` 不含排队等待；排队（`queue_wait`）单独记录，作为后续优化分析项，**不允许加进 RTF**（否则把调度问题混进生成效率）。

**llama 冻结二进制已内建该行日志**（无需改源码即可离线解析）：

```text
T2W线程: wav_1002.wav | 1.00s audio | 232.4ms inference | RTF=0.23 | t=1744ms | queue_wait=110.5ms | req=1 gen=1
```

> 即：`chunk_rtf = inference(ms) / audio_duration(s×1000)`。该行是**每个音频 chunk 一条**，parse 时可还原逐 chunk RTF 全序列。
> 配套解析脚本与统计口径见 `submission/scripts/analyze_chunk_rtf.py` 与 `docs/competition-submission/CHUNK_RTF_MEASUREMENT_SPEC.md`（llama 侧提交包）。

## 4. 原始数据 schema（chunk 级，必须逐 chunk 落一条）

```text
run_id            # 一次完整 run 的唯一标识
request_id        # 该 chunk 所属请求
chunk_index       # 请求内 chunk 序号（从 0/1 开始，需固定并记录）
is_first_chunk    # true/false —— 首 chunk 常含 TTS 冷启动/prefill，统计时单列
is_final_chunk    # true/false —— 尾 chunk 可能被截断，单列
chunk_compute_begin_ns   # T11
chunk_compute_end_ns     # T12
chunk_compute_ms         # T12−T11
sample_count       # WAV 样本数（SAMPLE_RATE 固定 24000 时 = 音频时长×24k）
sample_rate        # 24000（MiniCPM-o TTS WAV 采样率）
audio_duration_ms  # sample_count / sample_rate
chunk_rtf          # chunk_compute_ms / audio_duration_ms
valid_audio        # true/false（WAV 可解码、非空、非静音判定）
error              # 该 chunk 异常（空包/解码失败/超时/HTTP 错误）
server_pid / binary_sha / model_sha   # 环境指纹，防旧进程/旧版本污染
```

## 5. 统计口径

| 项 | 规定 |
|---|---|
| 样本下限 | 结论性数字（尤其排名指标）≥ 30 个有效 chunk；分析性 ≥ 10 |
| 分桶 | **首 chunk / 中间 chunk / 尾 chunk 分开统计**；混桶会因首 chunk 冷启动拉偏 p50（误判 R31） |
| 统计量 | count / mean / p50 / p90 / p95 / p99 / max；逐桶给 |
| 排除规则 | 显式排除并记录原因：空包、解码失败、客户端 HTTP 异常、静音包、超时；**排除率 >5% 时整个 run 无效** |
| 有效判定 | WAV 可解码、`sample_count>0`、非全静音、`audio_duration_ms>0` |
| 配对 | 任何 A/B 结论必须 strict matched（同服务/同模型/同输入/同采样）+ CI95 不跨 0 |
| 环境指纹 | 每 run 必须带 `server_pid / binary_sha / model_sha`，否则结论不可复核 |

## 6. 易误判清单（测出"假指标"的坑）

| # | 误判 | 正确做法 |
|---|---|---|
| M1 | 用**全请求 RTF**（总生成耗时/总音频时长）冒充**逐 chunk RTF** | 排名指标是逐 chunk；全请求口径单独标注为"端到端口径" |
| M2 | 用 **Flow 内部 RTF / Vocoder 内部 RTF** 冒充 chunk RTF | chunk RTF 含 Flow+Vocoder 整段 T2W 生成，不含排队 |
| M3 | 用 **request RTF**（客户端总耗时/总时长）冒充 chunk RTF | request 口径混入网络/排队/解码调度，不可用于排名 |
| M4 | 首/中/尾 chunk 混统计 | 三桶分开；首 chunk 冷启动显著拉偏 p50 |
| M5 | TTFP 用"第一个数据包"而非"第一个**有效**音频包" | 空包/静音包/解码失败包不计入 |
| M6 | TTFT 起点用服务端接收当"官方口径" | 标注内部口径；官方脚本到达后校准 |
| M7 | 把 queue_wait 或调度等待并入 chunk RTF | 排队时间单列，分析用，不进 RTF |
| M8 | 把 llama 冻结二进制的 RTF 行直接当成 vLLM RTF | llama 数字仅参考标尺，vLLM 必须重新测量 |
| M9 | 只测 candidate 不测官方 baseline（相对降幅无从计算） | 准入需相对官方基线降幅，必须同口径测 baseline |
| M10 | 小样本（<30 有效 chunk）下结论 | 满足样本下限才可作为结论性数字 |

## 7. 与 llama 冻结口径的对应（参考标尺，非 vLLM 结果）

| llama 侧（冻结，2026-08-05） | 值 | vLLM 侧处置 |
|---|---|---|
| 逐 chunk RTF（T2W线程 行） | 例：RTF=0.23（232.4ms/1.00s） | 重新在 vLLM Token2Wav Stage 打点测量（V3/V7） |
| 首响 decode_to_first_audio | 例：1269ms（log `🎉 首响时间`） | 重新测量 TTFP（V3/V6） |
| request_to_first_audio | 例：0ms（该行口径下起点=decode 起点） | 校准时注意 llama 该行不跨网络/排队 |
| T2W drain wav_count | 例：wav_count=12（`T2W drain: complete`） | 用于确认 chunk 完整性/丢 chunk 检测（V8） |

> llama 侧完整口径定义与统计见 `docs/competition-submission/CHUNK_RTF_MEASUREMENT_SPEC.md`（提交包）。以上行格式来自冻结二进制日志，解析脚本 `submission/scripts/analyze_chunk_rtf.py` 已可离线运行。

## 8. 报告必需字段（每个数字出现时）

```text
指标名（chunk RTF / TTFT / TTFP）
定义（含起止事件）
口径（官方 / 内部 / 校准后内部）
样本数（有效 chunk 数 / 请求数）
分桶（首/中/尾）
统计量（p50/p95/CI95）
硬件 + 配置（单卡 910C + YAML SHA）
来源路径（raw 数据文件）
二进制/model SHA（环境指纹）
内部 or 官方（OFFICIAL 仅在官方脚本结果）
```

> 缺任一字段的数字视为不可复核，禁止进入性能报告或交接材料。
