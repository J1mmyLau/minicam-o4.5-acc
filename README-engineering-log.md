# MiniCPM-o 4.5 · Ascend 910C 实时语音对话 — 工程全记录

> 本分支是纯文档分支：把整个项目做过的事按模块拆开，每个模块一个 md，
> 带实测数据、机制说明和必要脚本。代码/产物本体在 `main` 与
> `submission/minimal-repro` 分支。

## 一句话

在**单张华为 Ascend 910C** 上把 MiniCPM-o 4.5 的**全双工实时语音对话**
（视频/音频输入 → 流式语音回复）从官方基线 **RTF 1.087 压到 0.4829（−55.6%）**，
四项精度指标全部在容差内；同时独立交付一条 **DSpark 投机解码**线：

```
DSpark：8×B300 正式训练主线 + 910C 本地微调验证 + 910C 推理部署闭环
```

（**最终提交 Draft 权重来源 = B300 stage11**；910C 微调是方法论验证与
acceptance 修复资产，不进入主 artifact 血统。）

## PROJECT OVERVIEW（两条 evidence 支，全项目顶层结构）

```
PROJECT OVERVIEW
│
├── B300 training_evidence（权重从这来 → b300/ 目录逐节点整理）
│   ├── data                     → b300/01-data.md           四源 4197 行 JSONL
│   ├── target cache             → b300/02-target-cache.md   98.21GiB hidden cache + manifest
│   ├── Stage11 training         → b300/03-stage11-training.md  DP8 ×150 步
│   ├── checkpoint               → b300/04-checkpoint.md     step_150 + 导出/校验
│   └── acceptance evaluation    → b300/05-acceptance-evaluation.md  3.49→3.86
│        （综述：03-dspark-training.md）
│
└── 910C inference_evidence（推理侧全部工作）
    ├── artifact conversion / quantization  → dspark-910c-inference.md §1   1.85GB 方案C
    ├── llama.cpp-omni                      → 04-architecture.md            双树/五段链路
    ├── CANN / TileLang                     → 04 §1 + 06 §1                 桥接/装配
    ├── profiling                           → 05-profiling.md               各段归因
    ├── runtime + kernel optimization       → 06-kernel-runtime-optimization.md + 02（E2E 数据链）
    ├── speculative integration             → dspark-910c-inference.md §2-4  接入/k=2 1.87×/RTS 净负
    └── E2E RTF                             → 02 §0-7（0.4829）+ 07-evaluation.md（口径）
```

**一句话链路**：

```
B300：数据/cache → Draft training → checkpoint → acceptance evaluation → Draft artifact
910C：Draft artifact → GGUF/量化 → llama.cpp-omni 接入 → speculative decoding
      → runtime A/B → E2E RTF（RTS 判定：thinker 域投机净负，主提交不挂 draft）
```

## 成绩速览

| 指标 | 官方基线 | 达标线 | 本提交 | 状态 |
|---|---|---|---|---|
| **RTF（SPEAK→WAV 全链路）** | 1.087 | — | **0.4829 ± 0.0161**（4-run）| **−55.6%** |
| 同 harness 本地基线 | 0.6754 | — | 0.4829 | **−28.5%** |
| VideoMME | 69.0 | ≥67.0 | 69.8（pristine 同 harness 实测） | ✅ |
| Daily-Omni | 79.5 | ≥77.5 | 79.43 | ✅ |
| TTS-Seed ASV(SIM) | 0.709 | ≥0.689 | 0.969 | ✅ |
| TTS-Seed WER | 1.414 | ≤1.56 | 1.422%（pristine 1.5%） | ✅ |
| DSpark 文本域投机加速 | — | — | **1.87×**（k=2，910C 实测） | 独立交付 |

## 模块导航

| 文档 | 内容 | 关键数据 |
|---|---|---|
| [01-overview.md](01-overview.md) | 项目背景、链路架构、两条主链如何串起来 | RTF 分解 5 段 |
| [02-rts-optimization.md](02-rts-optimization.md) | **对话/RTS 推理优化 E2E 全史**：逐杠杆数据链、最终配方、复测事故 | 1.087→0.4829 |
| [03-dspark-training.md](03-dspark-training.md) | **DSpark 训练**：B300 主线（数据/超参/DP8/step150/acceptance A/B）+ 910C 本地微调 | accept_len 3.49→3.86 |
| [b300/](b300/README.md) | **B300 training_evidence 逐节点整理**（data/cache/training/checkpoint/eval 五篇 + D0–D9 证据索引，带 file:line 引用） | cache manifest 逐字段 |
| [dspark-910c-inference.md](dspark-910c-inference.md) | **DSpark 910C 推理闭环**：量化 1.85GB → 接入 → 投机 A/B → RTS 净负判定 | k=2 1.87× / RTS +12% |
| [04-architecture.md](04-architecture.md) | 系统架构：硬件、五段链路、两棵代码树、模型资产、线程模型 | — |
| [05-profiling.md](05-profiling.md) | 各段归因：msprof / decode 分解 / tts per-token / im2col / launch 税 | sync 66% |
| [06-kernel-runtime-optimization.md](06-kernel-runtime-optimization.md) | 内核层细节：TileLang 四核、host 税三连、NFE2、**被否决路线全表** | QKR +66% |
| [07-evaluation.md](07-evaluation.md) | 评测口径：RTF 测量协议、四项精度、双 env 隔离（GM3M9G） | WER 1.422% |
| [08-reproduction.md](08-reproduction.md) | 复现四步、Demo+EZ1002、提交资产与版本指纹、GitHub 分支 | sha256 |
| [09-lessons-learned.md](09-lessons-learned.md) | 踩坑清单 25+ 条（环境/测量/模型/内核，接手必读） | — |

## scripts/ 目录（随文档保留的可执行原件）

| 脚本 | 用途 |
|---|---|
| `run_rts.sh` + `server.env` | RTF 性能评测一键复现（A+C 配方 launch-only 注入） |
| `run_demo.sh` | 交互双工 Demo（含 CANN EZ1002 硬校验修复） |
| `config-accuracy.env` | 精度任务专用 env（perf 全关，隔离口径） |
| `dspark_rts_server_ab.sh` | DSpark RTS 双工 A/B 注入 wrapper（OMNI_SPEC_DRAFT） |
| `train_config.py` | **B300 stage11 训练配置原件**（8×B30Z，4197 样本） |
| `train_ascend.py` | **910C 本地微调训练器**（torch-npu 复刻 dflash 图） |
| `swap_stage11_weights.py` | safetensors → GGUF 原位换字节转换器 |
| `quant_mixed_stage11_C.py` | 1.85GB 混合量化器（方案 C） |

## 环境指纹

- **推理机**：1× Ascend 910C（dual-die，pin 单 die），CANN 9.1.0-beta.1，ggml-cann
- **推理树**：`perf/tilelang-bridge` @ `df45b47c3` + 工作区 diff（见 08）
- **训练机（stage11 主线）**：单机 8× NVIDIA B30Z（sm_103，268 GiB/卡），torch 2.8.0+cu128
- **训练机（910C 微调）**：同一张 910C，torch-npu 2.12 + tilelang-ascend
- **模型**：MiniCPM-o-4_5-F16.gguf（target）+ dspark_stage11-draft-q8mixed-C.gguf（draft）
