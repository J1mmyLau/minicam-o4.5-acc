# Official Evaluation Specification — llama.cpp-omni (Sub-track A)

> 来源: [官方评测规范](https://www.feishu.cn/docx/U41vdXMmQo7tv3xW2p9c9uEanKe)
> 发布日期: 2026-08-05
> 适用子赛道: A (llama.cpp-omni)

---

## 1. 测试环境

| 参数 | 值 |
|------|-----|
| 硬件 | Ascend 910C 单卡 |
| 运行环境 | CANN 9.1.0-beta1 |
| 权重精度 | F16 |
| 并发 | 1 |
| 框架 | llama.cpp-omni |

---

## 2. 精度准入阈值（四项必须全部满足）

| Benchmark | 官方基线 | 准入阈值 | 判定规则 |
|-----------|---------|---------|---------|
| VideoMME | 69.0 | **≥ 67.0** | 绝对下降 ≤ 2pp |
| Daily-Omni | 79.5 | **≥ 77.5** | 绝对下降 ≤ 2pp |
| TTS-Seed ASV | 0.709 | **≥ 0.689** | 绝对下降 ≤ 0.02 |
| TTS-Seed WER | 1.414 | **≤ 1.56** | 相对增幅 ≤ 10% |

> ⚠️ TTS-Seed 使用两套不同规则: ASV = 绝对下降 ≤ 0.02, WER = 相对增幅 ≤ 10%。
> 不得再使用统一的 "≤2pp" 描述 TTS-Seed。

多精度基线对照（F16 为正式精度）:

| 权重精度 | VideoMME | Daily-Omni | TTS-Seed ASV ↑ | TTS-Seed WER ↓ |
|----------|---------|-----------|----------------|---------------|
| F16 | 69.0 | 79.5 | 0.709 | 1.414 |
| Q8_0 | 68.9 | 79.6 | 0.708 | 1.387 |
| Q4_0 | 67.6 | 79.9 | 0.707 | 1.387 |

---

## 3. 性能指标 — SPEAK→WAV RTF

### 全双工推理三阶段

| 阶段 | 运行模块 | 是否计入排名 |
|------|---------|------------|
| **LISTEN** | VPM + APM + LLM, 不运行 TTS/T2W | ❌ 不计入 |
| **SPEAK 生成** | VPM + APM + LLM + TTS + T2W (全部) | ✅ **主要排名指标** |
| **SPEAK 尾部** | 仅 TTS/T2W (LLM 已结束) | ❌ 不计入 |

### 官方基线 (F16, 单并发)

| 指标 | 基线值 | 用途 |
|------|--------|------|
| 全部 chunk 平均 RTF | 0.618 | 仅供参考, 不用于排名 |
| **SPEAK→WAV 完整链路 RTF** | **1.087** | **排名依据** |
| SPEAK→WAV 平均耗时 | 1087.3 ms/chunk | 官方附带统计 |

### RTF 定义

```
RTF = audio_chunk_generation_latency / audio_chunk_duration
```

SPEAK→WAV 完整链路 = Main LLM (SPEAK 阶段) → Talker → TTS → T2W queue → Flow → Vocoder → WAV。
不是仅 Flow+Vocoder，不是仅 T2W 线程。

### 关键约束

- 不同用例 LISTEN/SPEAK 比例不同，**全部 chunk 平均 RTF 不可直接对比**
- 必须按 SPEAK 生成阶段 chunk 单独统计
- LISTEN 和 SPEAK 尾部 chunk 必须排除

---

## 4. Demo 准入

子赛道 A 官方 Demo: [MiniCPM-o-Demo](https://github.com/OpenBMB/MiniCPM-o-Demo)

检查内容:
- 模型服务正常启动，Demo 正常连接推理服务
- 音频、视频和文本输入正常处理，模型输出完整
- 流式语音输出连续，无明显卡顿、中断或异常退出
- 能够完成官方指定完整交互流程，连续运行保持稳定

> 仅能运行 Benchmark 但无法正常接入 Demo 的方案，不满足准入条件。

---

## 5. 评测流程

```
G1 框架与环境检查
        ↓
G2-G4 三项 Benchmark 精度准入
        ↓
G5 官方 Demo 可用性准入
        ↓
G6 SPEAK→WAV RTF 性能排名
        ↓
G7 官方环境工程复现
        ↓
G8 最终提交审查
```

---

## 6. 最终提交内容

| 类别 | 内容 |
|------|------|
| 完整代码与配置 | 推理适配与性能优化代码、框架配置、服务启动脚本、Benchmark 执行脚本、Demo 启动脚本、依赖与环境配置 |
| Benchmark 评测结果 | VideoMME、Daily-Omni、TTS-Seed 三项完整结果 (含命令、参数、原始输出、汇总) |
| 性能测试报告 | RTF 结果、测试环境、测试数据、统计方式、优化前后对比 |
| 可运行 Demo | 演示视频、使用说明、启动与访问方式 |
| 优化与复现说明 | 瓶颈分析、优化方法、性能变化、完整复现步骤 |

---

## 7. 子赛道 B 参考 (vLLM-Omni)

| 指标 | 基线值 |
|------|--------|
| TTFT | 333.27 ms |
| TTFP | 986.47 ms |
| RTF | 0.4423 |

> TTFT/TTFP 是 vLLM-Omni 子赛道指标，**不适用于本仓库 (llama.cpp-omni)**。

---

## 8. 参考链接

| 资源 | 链接 |
|------|------|
| 官方规范 | https://www.feishu.cn/docx/U41vdXMmQo7tv3xW2p9c9uEanKe |
| 框架仓库 | https://github.com/ggml-org/llama.cpp-omni |
| 模型 | MiniCPM-o 4.5 (ModelScope) |
| Demo | https://github.com/OpenBMB/MiniCPM-o-Demo |
| 算力申请 | HiDevLab |
