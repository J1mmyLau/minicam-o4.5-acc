# vLLM-Omni 比赛约束附录（子赛道 B）

> 只补充**比赛规则约束层**，不重写现有迁移主指南（`LLAMA_TO_VLLM_EXPERIENCE_MIGRATION.md`）。
> 本附录回答：vLLM 队友在选型、指标、准入、加分、交付上必须知道的事。

---

## 1. vLLM 子赛道公开评分指标（三项）

```
chunk RTF   = 每个音频 chunk 生成耗时 ÷ 该 chunk 音频时长（越低越好）
TTFT        = 请求发出 → 首个有效 text token（越低越好；起止/预处理是否计入以官方脚本为准）
TTFP        = 请求发出 → 第一段可用音频 chunk/packet（越低越好）
```

最终成绩 = RTF + TTFT + TTFP 综合（归一化/权重以官方最终评测文档为准）。

## 2. 指标 → Stage 事件映射

```
request received ──┬─→ Thinker first text token   = TTFT
                   └─→ Speak/TTS decision → Talker → Token2Wav
                                          └──→ First valid audio packet = TTFP
                                               → 每个后续音频 chunk      = chunk RTF
```

迁移 llama 的 Stage 打点经验时，**必须同时覆盖**：请求排队、Thinker Prefill、首文本 token、Talker 启动、首音频 packet。

## 3. 指标起止点（待官方确认项）

| 项 | 说明 |
|---|---|
| TTFT 起点 | 客户端发送 / 服务端接收 / prefill 完成？ |
| TTFT 终点 | 首个 text token 判定（内容非空？协议标记？） |
| TTFP 判定 | 首个完整 WAV / 首个音频帧？ |
| chunk 语义 | 服务端帧 / 固定间隔 / 语义段？ |
| 预处理是否计入 | 音频/图像 prefill 计入 TTFT？ |

> 上述定义以官方脚本为准；当前 `METRIC_CONTRACT`（official-eval/competition/）全部 provisional。
> 内部打点起止事件、raw schema、统计与误判清单见 **`VLLM_METRIC_MEASUREMENT_SPEC.md`**。

## 4. 准入（先于性能排名）

1. **精度 ≤ 2pp**：相对 vLLM-Omni 官方基线（Daily-Omni / TTS-Seed / Video-MME），不跨框架比较。
2. **Demo 可用**：vLLM-Omni 对应官方 Demo（详见"在昇腾 NPU 上部署 MiniCPM-o 4.5"文档）；只跑 Benchmark 不算。
3. 检查项同 llama：服务启动、Demo 连接、多模态输入、输出完整、音频连续、长稳。

## 5. 硬件与环境

- 单卡 910C 统一评测（不得用多卡结果当单卡成绩）。
- 镜像 `vllm-omni:v0.25.0`（Atlas A3/910C：`quay.io/ascend/vllm-omni:v0.25.0-a3`）。

## 6. 额外机会：PR 加分

优化 PR 合入 `vllm-omni` 仓库 `minicpm-challenge` 分支可能获得加分。因此候选从一开始就要满足：
- 代码风格 / 单元测试 / 回归测试通过
- commit 清晰可追溯
- PR 描述注明队伍名称
- 性能收益可独立复现（不能只依赖 llama 数字）

## 7. 最终交付内容

- 代码/配置（vLLM-Omni 相关）+ 服务/Demo/Benchmark 脚本
- 三项 Benchmark 完整结果（测试命令、参数、原始输出、结果汇总）
- 性能报告（RTF / TTFT / TTFP、环境、数据、次数、统计、前后对比、资源、异常）
- 可运行 Demo + 演示视频 + 使用说明
- 优化与复现说明（瓶颈 → 方法 → 收益 → 效果保持 → 复现步骤）

## 8. 与 llama 迁移集的衔接

| 本附录 | 迁移主指南 |
|---|---|
| 比赛规则/指标/准入/交付 | 工程经验/Stage 打点/设备放置/Prefix Cache/生命周期 |

队友顺序：先读主指南（方法论）+ 本附录（比赛规则），再按执行计划 V0→V12 动手。llama 数字仅作参考标尺，**不是 vLLM 结果**；vLLM 侧一律 `TO_AUDIT` / `TO_MEASURE_AT_RUNTIME`，官方 Gate 通过前不宣称 OFFICIAL PASS。
