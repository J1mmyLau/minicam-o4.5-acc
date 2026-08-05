# Official Asset Inventory — Sub-track A (llama.cpp-omni)

> 官方评测规范已发布 (2026-08-05)，全量数据集 Baseline 和评测资产已提供。
> 本文档记录官方提供的内容和 Candidate 执行状态。

---

## 官方已提供的内容

### 评测规范

| 项目 | 状态 | 来源 |
|------|------|------|
| 评测规范文档 | `AVAILABLE` | https://www.feishu.cn/docx/U41vdXMmQo7tv3xW2p9c9uEanKe |
| 子赛道 A 环境定义 | `AVAILABLE` | Ascend 910C / CANN 9.1.0-beta1 / F16 / 单并发 |
| 评测流程 | `AVAILABLE` | Framework→Accuracy→Demo→RTF→Reproduction |

### 官方全量数据集 Baseline (F16)

这些是主办方在 Ascend 910C、F16、官方完整评测集上跑出的正式 Baseline，不是示例值：

| Benchmark | 基线值 | 准入阈值 |
|-----------|--------|---------|
| VideoMME | 69.0 | ≥ 67.0 |
| Daily-Omni | 79.5 | ≥ 77.5 |
| TTS-Seed ASV | 0.709 | ≥ 0.689 |
| TTS-Seed WER | 1.414 | ≤ 1.56 |

### 性能 Baseline

| 指标 | 基线值 | 说明 |
|------|--------|------|
| SPEAK→WAV 完整链路 RTF | 1.087 | 排名依据 |
| 全部 chunk 平均 RTF | 0.618 | 仅供参考 |

### Demo

| 项目 | 状态 | 备注 |
|------|------|------|
| MiniCPM-o-Demo 仓库 | `AVAILABLE` | https://github.com/OpenBMB/MiniCPM-o-Demo |
| Demo 本地固定版本 | `CLONED` | ba7fa9c, 422 files |

### Benchmark 执行资产

| 项目 | 状态 |
|------|------|
| Daily-Omni 数据集 + 脚本 + 评分器 | `AVAILABLE` (官方提供) |
| VideoMME 数据集 + 脚本 + 评分器 | `AVAILABLE` (官方提供) |
| TTS-Seed 测试集 + ASV/WER 脚本 | `AVAILABLE` (官方提供) |
| RTF Harness (SPEAK 状态识别 + 计时) | `AVAILABLE` (官方提供) |

---

## Candidate 执行状态

官方资产已齐备，以下是 Candidate 尚未执行的项目：

| Gate | 状态 | 下一步 |
|------|------|--------|
| G2 Daily-Omni | `NOT_RUN` | 在官方全量数据集上运行 Candidate |
| G3 TTS-Seed | `NOT_RUN` | 同上 |
| G4 Video-MME | `NOT_RUN` | 同上 |
| G5 Demo D1-D12 | `NOT_RUN` | 接入官方 Demo 并完成端到端验证 |
| G6 SPEAK→WAV RTF | `NOT_RUN` | 使用官方 RTF harness 测量 Candidate RTF |
| G7 Reproduction | `NOT_RUN` | G2-G6 通过后执行 clean-room 复现 |

---

## 说明

- 官方给出的数值（69.0/79.5/0.709/1.414/1.087）是正式全量数据集 Baseline
- **不需要**先自己重跑 Baseline 才知道准入阈值
- 建议在跑 Candidate 的同时做一次本机 Baseline 复现，用于环境校验和 A/B 报告
- Candidate 结果必须与官方 Baseline 同口径比较
