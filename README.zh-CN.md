<div align="center">

<img src="docs/assets/logo.svg" width="170" alt="项目 logo —— 昇腾 NPU 芯片与实时语音波形">

# MiniCPM-o 4.5

### 从 DSpark 训练到 Ascend 910C 运行时优化

*一个横跨 NVIDIA B300 级 GPU 与华为昇腾 910C 的跨平台 model-to-system 项目。*

[English](README.md) · **简体中文**

[![core RTF](https://img.shields.io/badge/core_RTF-0.4829-blue)]()
[![vs baseline](https://img.shields.io/badge/vs_paired_local_baseline-28.5%25_faster-brightgreen)]()
[![accuracy](https://img.shields.io/badge/accuracy_benchmarks-4_of_4_PASS-success)]()
[![spec decode](https://img.shields.io/badge/speculative_decoding-1.87x_text-blueviolet)]()
[![kernel](https://img.shields.io/badge/TileLang_fusion-+66%25_decode-orange)]()
[![platform](https://img.shields.io/badge/platform-Ascend_910C-informational)]()
[![runtime](https://img.shields.io/badge/runtime-llama.cpp--omni-important)]()
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**状态：已提交（2026-08-31）。** 同口径核心 RTF **0.6754 → 0.4829** ·
四项精度门全部达标 · 投机解码作为独立文本域资产保留。

> ⚠️ 本 `main` 分支是**项目介绍**，不是交付分支。
> 最终代码在 `competition/final-ascend-track-a`（冻结 runtime `fd3dd36`）——
> 见[仓库导航](#-仓库导航)。

**第一次来？** 📊 [结果榜](#结果榜) · 🗺️ [仓库导航](#-仓库导航) · 📅 [时间线](#-带-git-锚点的时间线)

</div>

---

## 全项目最重要的一条

> **模型侧 acceptance、独立投机加速、实时双工性能是三个独立的端点——必须分开测量。**
> 任何一个上面的胜利都不能外推到另一个。本项目的所有数字都带着这条边界汇报，每次都是。

---

## 项目全生命周期一图流

```text
┌───────────────────────────  B300 · 训练  ───────────────────────────────┐
│                                                                         │
│   4,197 条真实多模态样本 ──────▶ 冻结目标前向                            │
│   (Daily-Omni · Video-MME · Seed-TTS)        │                          │
│                                              ▼                          │
│                        hidden-state 缓存 — 98.21 GiB · 215 万 token     │
│                                              │                          │
│                                              ▼                          │
│                    DP8 DSpark draft 训练 — 150 步，零失败                │
└──────────────────────────────────────────────┬──────────────────────────┘
                                               ▼
                          Stage11 checkpoint ──▶ 受控 acceptance 评测
                                               │
┌──────────────────────────  Ascend 910C · 服务  ─────────────────────────┐
│                                                                         │
│   GGUF 换血 + 混合精度 (1.85 GB) ──▶ llama.cpp-omni 全双工服务           │
│                          │                          │                   │
│                          ▼                          ▼                   │
│                 msprof / host profiling ──▶ kernel 与 runtime 优化       │
│                          └───────────┬──────────────┘                   │
│                                      ▼                                  │
│                    端到端 RTF 验证 ──▶ 0.4829                           │
└─────────────────────────────────────────────────────────────────────────┘
```

## 结果榜

| 维度 | 结果 | 口径 |
|---|:---:|---|
| **端到端 RTF** | **0.4829 ± 0.0161**（复检 0.4840 ± 0.0125） | 配对本地基线 0.6754 ± 0.0152 → **−28.5 %**；公开 1.087 仅方向性（−55.6 %） |
| **精度（4 项）** | VideoMME **69.8** · Daily-Omni **79.43** · TTS SIM **0.969** · TTS WER **1.422 %** | 要求 ≥67.0 / ≥77.5 / ≥0.689 / ≤1.56 %——**4/4 达标** |
| **投机解码** | 文本 k=2 **1.87×** · k=3 1.80× · k=7 1.75× · 15 帧多模态 1.49× | 独立 benchmark；最终 RTS 配置**关闭**（短 chunk 摊不动） |
| **Kernel 融合** | QK-norm+RoPE decode **+66 %**（0.47→0.78 tok/s）· RMSNorm +25 %（叠加 +55~65 %） | TileLang-Ascend AOT，输出位级一致 |
| **Launch 税** | host launch **18,214 → 1,301** | VPM patch-mm + 算子融合 + ACL graph |
| **训练** | 5 层 DSpark draft · 4,197 样本 · DP8 × 150 步零 NaN/OOM/NCCL | 接受长度 3.49 → 3.86（+10.6 %） |

---

## 目录

1. [目标与系统边界](#1--目标与系统边界)
2. [训练侧：B300 上的 DSpark draft](#2--训练侧b300-上的-dspark-draft)
3. [Draft 质量：受控 acceptance](#3--draft-质量受控-acceptance)
4. [跨平台工件：B300 → 910C](#4--跨平台工件b300--910c)
5. [投机解码与 workload 经济学](#5--投机解码与-workload-经济学)
6. [Ascend 910C 上的 profiling](#6-ascend-910c-上的-profiling)
7. [TileLang、launch 税与 kernel 融合](#7-tilelanglaunch-税与-kernel-融合)
8. [RTF 优化链](#8-rtf-优化链)
9. [精度与环境隔离](#9--精度与环境隔离)
10. [被否决的路线](#10--被否决的路线)
11. [工程启示](#11--工程启示)
12. [仓库导航](#-仓库导航)
13. [复现协议](#13--复现协议)
14. [带 git 锚点的时间线](#-带-git-锚点的时间线)

---

## 1 · 目标与系统边界

本项目来自全模态大模型在昇腾算力平台上的部署优化比赛（**llama.cpp-omni 子赛道**），
五道关卡依次为：

```text
框架与环境可运行
        ↓
Benchmark 精度降幅 ≤ 2 pp            ── 准入条件
        ↓
官方 Demo 端到端可用                 ── 准入条件
        ↓
每个 audio chunk 的 RTF              ── 排名依据
        ↓
主办方环境复现
```

精度与 Demo 可用性是**准入条件**——两道都过了，优化才进入性能评测。

**软硬件栈：**

| 层 | 组件 |
|---|---|
| 应用 | 全双工 MiniCPM-o 服务（视频/音频流式进、语音流式出） |
| 运行时 | llama.cpp-omni（ggml-org/llama.cpp fork） |
| 后端 | ggml-cann + ACLNN / CANN（服务基线 8.5.0.alpha002；TileLang 内核线 9.1.0-beta.1） |
| 内核 | TileLang-Ascend AOT 共享库（纯 C ABI，单核 15.3 µs/call） |
| 图 | ACL graph capture/replay（验证过的路径） |
| 硬件 | 1× Ascend 910C（dual-die）——**所有性能/精度运行 pin 单 die**（跨 die 数值无效，已否决） |

### Chunk 流水线

```text
视频 / 音频流
   └─▶ VPM 视觉编码器 ──▶ Thinker prefill + decode ──▶ Talker / TTS token ──▶ token2wav ──▶ WAV
          T_vis                     T_pre   T_dec               T_tts               T_wav
```

一个 duplex chunk 的代价是 `T_chunk = T_vis + T_pre + T_dec + T_tts + T_wav`，服务目标为

```text
RTF = T_chunk / D_audio          （越低 = 实时余量越大）
```

**系统边界意识**：当一个 stage 只占全链路一小部分时，2× 快的孤立 kernel 对 RTF 的影响
可以忽略——这条学费本项目真交过（见 §7 的 Amdahl 案例）。

### 测量契约

最终对比使用：**同一条 120 s 双工视频、37 chunks、相同计时边界、seed 1001–1004、
排除冷启动加载**。配对本地基线 0.6754 ± 0.0152；最终配置 0.4829 ± 0.0161。
公开官方 RTF 1.087 **仅作方向性参考**——它产自不同的 harness；两组数字永远分列，不混用。

---

## 2 · 训练侧：B300 上的 DSpark draft

目标 MiniCPM-o 模型**冻结**。可训练对象是 **5 层 DSpark draft**，从目标层
`[1, 9, 17, 25, 33]` 的 hidden states 学习；5 个 4096 维状态拼接 =
**每 token 20,480 维目标特征**。

### 真实数据、离线目标缓存

| 来源 | 样本数 |
|---|---:|
| Daily-Omni | 1,197 |
| Video-MME | 1,500 |
| Seed-TTS EN | 1,088 |
| Seed-TTS ZH | 412 |
| **合计** | **4,197** |

冻结目标前向**只跑一次**建 teacher 缓存（而不是每个训练步重复跑目标模型）：

> 4,197/4,197 成功 · 2,145,260 缓存 token · 10 shards · **98.21 GiB** · 113.8 分钟 ·
> 零失败、零超长。hidden states 存 BF16；rollout 用 FP16 目标推理
> （64 生成 token，max length 2048）。

### 架构与训练契约

| 项 | 配置 |
|---|---|
| Draft 层数 | 5 |
| Block size | 每步提议 7 token |
| 目标层 | [1, 9, 17, 25, 33] |
| Hidden size | 4096 |
| Anchors / Markov rank | 512 / 256 |
| Loss | CE 0.1 + L1 0.9，衰减 γ = 8 |
| 精度 / 学习率 | BF16 / 3×10⁻⁶ |

**DP8 batch 算术**——local batch 1 × DP world size 8 × 梯度累积 4 =
**有效全局 batch 32**；一个 epoch ≈ 131.2 个 optimizer step，训练由
`max_train_steps=150` 驱动（末段进入第二轮数据遍历）。
正式 run 完成 **150 步，零 NaN / Inf / OOM / NCCL 失败**，每 25 步落 checkpoint。

<details><summary><b>代表性 step 记录</b>（全部为有限值）</summary>

| Step | Loss | LR | 步时 (s) |
|---:|---:|---:|---:|
| 25 | 1.0065 | 2.89×10⁻⁶ | 0.96 |
| 50 | 1.1815 | 2.38×10⁻⁶ | 0.63 |
| 75 | 1.1186 | 1.62×10⁻⁶ | 0.62 |
| 100 | 1.3071 | 8.18×10⁻⁷ | 0.63 |
| 125 | 1.3391 | 2.21×10⁻⁷ | 0.63 |
| 150 | 0.8430 | 0 | 0.63 |

日志中的 gradient-norm 远大于配置的裁剪阈值 1.0；由于 logger 相对裁剪的位置未在
锁定源里验证，该观测保守对待，不据此推断训练不稳定。

</details>

### Checkpoint 语义与模型谱系

`step_150` 约 **23.69 亿参数**（4.41 GiB `model.safetensors`）。8 个 rank-local
`training_state.rank*.pt` 是 **resume 状态、不是 8 个不同模型**——no-shard 数据并行下
每个 rank 持有完整同步副本，这些文件在推理导出时排除。

```text
Stage10 权重 ──严格 warmstart──▶ Stage11 训练（optimizer/scheduler 重建）
                              ──▶ 150 步正式 run ──▶ 正式 Draft 工件
```

**最终提交的 Draft 权重来自 B300 Stage11。** 910C 侧微调是方法验证与
acceptance 修复资产，刻意排除在主工件谱系之外。

---

## 3 · Draft 质量：受控 acceptance

Stage10 vs Stage11，**644 条文本样本**（GSM8K / HumanEval / MT-Bench / Alpaca），
控制目标模型、tokenizer、生成配置、seed、world size 与样本身份，
prompt SHA256 多重集断言相等：

| 指标 | Stage10 | Stage11 | Δ |
|---|---:|---:|---:|
| 平均接受长度 | 3.4923 | **3.8620** | +0.3697 |
| 总体接受率 | 0.4388 | **0.4854** | +0.0466 |
| accept@4 | 0.2164 | **0.2906** | +0.0742 |
| accept@5 | 0.1461 | **0.2348** | +0.0886 |
| accept@6 | 0.0954 | **0.1895** | +0.0941 |
| 置信绝对误差 | 0.0516 | 0.0511 | −0.0005 |

增益随 7-token block 尾部增大而 accept@0 几乎不动——这正是投机 drafting 想要的信号：
**模型变得更擅长维持一整块正确，而不只是猜中第一个 draft token。**

> **证据边界。** Acceptance 提升不是 TPS 声明。服务速度还取决于 draft 代价、验证
> batch 代价、请求长度与运行时调度——因此独立投机加速与全双工 RTF 分开测量（§5）。

---

## 4 · 跨平台工件：B300 → 910C

Stage11 工件在**不改变模型谱系**的前提下转换为 Ascend 可部署形态。通用导出器不够——
draft 专属字段与张量语义必须保留——因此走**自定义 safetensors→GGUF payload swap**：

```text
Stage11 BF16 safetensors            （正式 B300 工件）
   └─▶ draft-aware GGUF swap        （保留 DSpark metadata 与布局）
        └─▶ 混合 Q8_0 / BF16 / F32  （部署体积 1.85 GB）
             └─▶ parity 校验        （header/张量完整性 + acceptance A/B）
```

只量化选定的线性张量；数值敏感的 norm/bias 保持 F32；Markov 路径在全 Q8 后端失败后
保持不量化。三组 prompt 检查下，BF16 与混合工件的 acceptance **逐位一致**。
**不声称任何量化加速**——该后端上 Q8 与 BF16 吞吐实测相当。

### 运行时正确性契约

*「模型能加载」≠「投机路径正确」。* 接入共修复三个契约：

1. draft 必须消费**当前** KV 位置，而非过期的 `n_past`；
2. **所有**被接受的附加 token 必须返回目标流，而非只返回第一个；
3. duplex prefix、hidden-state 与 listen-flush 钩子在投机路径上保持对齐。

数值正确的算子放回并发运行时仍可能失败——stale KV、丢接受 token、buffer 复用、
流竞态与隐藏环境状态，让**运行时语义成为一等性能变量**。

---

## 5 · 投机解码与 workload 经济学

独立文本 benchmark 上，实测 draft 代价 ≈ **1.11 ms/token——约为目标的 1/28**：

| 场景 | 实测加速 |
|---|:---:|
| 文本，k=2 | **1.87×** |
| 文本，k=3 | 1.80× |
| 文本，k=7 | 1.75× |
| 15 帧多模态 | 1.49× |

**实时双工路径给出了相反的决策：**

| 指标 | Draft off | Draft on |
|---|---:|---:|
| Core RTF | 3.979 | **4.460**（恶化 ≈ 12 %） |
| LLM decode | 0.132 | 0.338（慢 2.6×） |
| 输出连续性 | 连贯 | 碎裂 |

短 chunk 每次只 decode 几个 token——draft 前向、验证与 KV 同步摊不动。
**最终 RTS 配置关闭 thinker 侧投机，同时把投机子系统保留为独立的长文本/文本资产。**

> **三个不可混淆的端点**
> ① acceptance——模型侧 draft 质量 ② 1.87×——独立投机运行时
> ③ 0.4829——关闭 thinker 投机的最终全双工结果。

---

## 6 · Ascend 910C 上的 profiling

优化从**实测时间分布**出发，而不是预设 kernel 目标。

| Profile 组件 | 占比 |
|---|---:|
| Main LLM forward（msprof） | 26.8 % |
| KV ScatterUpdate | 19.4 % |
| F32↔F16 cast | 13.6 % |
| LM head | 0.65 % |
| Logits 同步（占 decode） | 48 % |
| Embedding 同步（占 decode） | 32 % |
| llama_decode 本体（占 decode） | 17 % |
| 内存分配（占 decode） | ~0.1 % |

TTS 侧：≈ 3.3 ms/token（66 %）消耗在同步。Token2wav 侧：
**vocoder im2col ≈ vocoder 路径的 85 %**。

这些分解否决了两个诱人但错误的方向：分配不是 decode 瓶颈；LM head 太小，
不值得 head-only 重写。单点换装（RoPE 替换、sel-embedding、通用 OP_FUSION）
实测全部 ≈ 0 增益。

> **关键路径纪律。** Profiler 热点只是*候选*，不是根因。每个候选必须经过
> **运行时可达性 → 正确性 gate → 受控 A/B → Amdahl 核算**才准晋升。多个局部更快的
> 改动因 stage 占比太小、或全链路回退而被否决（§10）。

---

## 7 · TileLang、launch 税与 kernel 融合

TileLang-Ascend 路径通过 **AOT 共享库 + ggml-cann side-loading 桥接**集成
（绕开冻结的 CMakeLists）。核心观察：**decode 被「重复小算子 + host launch/同步开销」
主导**——替换孤立算子价值很小；把*一串算子折叠成一个 kernel* 才能跨过这堵墙。

### 7.1 QK-norm + RoPE 融合 —— +66 %

36 层 Qwen3 中，Q/K norm + RoPE 是每个 decode 步重复 36 次的短链。融合为单个
TileLang kernel 后，四臂交错 llama-bench（tgq64）实测 **0.47 → 0.78 token/s（+66 %）**，
输出位级一致。

**第一版集成的失败不是 kernel 数学问题**——是两个 C++ 桥接契约 bug：

- **双重 RoPE**——融合路径已做 norm+RoPE，外层图又执行了一次；
- **view 步长错**——返回的 `[128,H,T]` F32 view 要求 `nb1 = 128×4 = 512`、
  `nb2 = H×512`，而不是复用不兼容的步长。

再补一课：dump 越界 + 变长记录按定长解析，制造了**假的流竞态症状**——
插桩本身也是需要验证的代码。修复后短 prompt greedy 输出与原生链一致；
长 prompt 会经 F32 舍入发散，因此生产 gate 是任务/精度正确性，
而非无限定的全局位同一声明。

### 7.2 RMSNorm 与 vocoder kernel

- **RMSNorm 行融合**——3 个 norm 位点/层 × 36 层，tile 范式（2-D tile、末维归约、
  标量 tile-multiply、broadcast）。单开 **+25 %**，与 QKR 叠加 **+55~65 %**
  （0.78–0.79 tok/s）。
- **Vocoder conv1d**——直接 TileLang 卷积路径，消掉占 vocoder 85 % 的 im2col
  （72 个 T-bucket kernel + 桥接 bucket 回落）。Token2wav stage **−21 %**，
  WAV 相关系数 **0.9993**。

> **为什么微加速不够——本项目最干净的 Amdahl 案例。** conv1d 技术上成功，但
> vocoder 只占 token2wav 约 ⅓、flow matching 主导残余 stage，E2E RTF 只改善
> ~0.01–0.02：`S_E2E ≤ 1 / ((1−f) + f/S_stage)`——`f` 小时，再大的 `S_stage`
> 也不是系统胜利。

### 7.3 Launch 削减与 workload 整形

更大的系统收益来自 kernel 工作 + 运行时 + workload 变化的组合：

- **VPM patch-mm 融合 + 算子融合 + ACL graph capture/replay** → host launch
  **18,214 → 1,301**；
- **视觉 token 削减**——`OMNI_DUPLEX_MAX_SLICE=0` 把每帧 vision token 128 → 64
  （只留 overview）：VPM ≈ 92→53 ms、prefill ≈ 123→65 ms；
- **首 TTS chunk 5 → 10 token**（`OMNI_TTS_FIRST_CHUNK_STEP=10`）：per-token decode
  24.7 → 19.2 ms（−22 %），代价是首响应 ≈ +100 ms；
- **token2wav flow 步数 NFE 5 → 2**（预建 prompt cache；NFE1 因音质否决）。

### 7.4 优化总账

| 干预 | 证据 / 机制 | 结果 / 决策 |
|---|---|---|
| ACL graph + 融合 | host launch 过载 | launch 18,214→1,301；**保留** |
| QK-norm+RoPE TileLang | 每步 36 条重复短链 | 0.47→0.78 tok/s；**保留** |
| RMSNorm 行融合 | 跨层重复 norm launch | 单开 +25 %、叠加 +55~65 %；**保留** |
| conv1d 直算 | im2col 主导 vocoder | t2w stage −21 %；E2E 有限（Amdahl） |
| NFE 5→2 | flow 主导残余 t2w | RTS **保留**（配 prompt cache） |
| 视觉 slice 削减 | 每帧 vision token 过多 | encode 与 prefill 双降 |
| 首 chunk 5→10 | chunk 边界开销 | per-token 24.7→19.2 ms |

规律一致：**大增益来自削减重复工作或折叠算子链——不是把孤立原语换成略快的实现。**

---

## 8 · RTF 优化链

由可复现的 A/B 阶段构成，而非一次性大补丁：

| 配置 | Core RTF |
|---|---:|
| 官方参考*（方向性）* | 1.087 |
| 同口径本地基线（A+C off） | 0.6754 ± 0.0152 |
| 完整优化栈，无 A+C | 0.6102 ± 0.0104 |
| + A：视觉 slice 削减 | 0.5182 ± 0.0407 |
| + C：首 TTS chunk 10 | **0.4829 ± 0.0161** |
| 提交前独立复检 | 0.4840 ± 0.0125 |

即对配对本地基线 **−28.5 %**，对公开参考方向性 **−55.6 %**。

<details><summary><b>代表性最终 stage 分解</b>（headline 仍是 4-run 聚合——token2wav 方差不可忽略）</summary>

| Stage | RTF 贡献 |
|---|---:|
| Vision encode | 0.0611 |
| Prefill | 0.0642 |
| Decode | 0.1233 |
| TTS / Talker | 0.1427 |
| Token2wav | 0.0987 |
| **合计** | **0.4901** |

</details>

---

## 9 · 精度与环境隔离

| 指标 | 要求 | 最终 |
|---|---:|---:|
| VideoMME | ≥ 67.0 | **69.8** |
| Daily-Omni | ≥ 77.5 | **79.43** |
| TTS Seed ASV/SIM | ≥ 0.689 | **0.969** |
| TTS Seed WER | ≤ 1.56 % | **1.422 %** |

*（评分资产：中文 WER 用 **Paraformer** 而非 Whisper；SIM 用 WavLM+ECAPA。）*

> **一次真实回归教会我们：性能与精度环境不能共享可变 shell 状态。**
> 性能专用变量经 `base_env` 泄漏进长上下文精度路径，VideoMME 从 69.8 塌到 **8.0**。
> 冻结设计因此把 `server.env`（性能）与 `config-accuracy.env`（精度）**物理隔离**。

同族教训（提交前抓到）：`run_eval.sh` 会 source `config-local.env`，一个 stale 的
`OMNI_T2W_NFE_STEPS=5` 静默覆盖 launch 时 NFE2、破坏目标 token2wav 路径。
去掉重叠后 3-run 复检 0.4840 ± 0.0125，与归档 4-run 一致。

---

## 10 · 被否决的路线

最终系统更容易辩护，因为归档记录了阴性实验而不是隐藏它们：

| 路线 | 决策证据 |
|---|---|
| Q8_0 主模型 | 净负；同 seed 0.5215 vs 0.5257，prefill/decode kernel 更慢 |
| Flow ACL Graph capture | flow 中位改善但 E2E 回退 ≈ 11 %；回滚 |
| Flow zcat2 融合 | 位级相等但 Δ < 1 %；DO_NOT_PROMOTE |
| 单点 RoPE 换装 | ≈ 0 增益；host 税主导 |
| sel-embedding 换装 | 211 s vs 213 s；中性 |
| thinker 侧 DSpark 进 RTS | core RTF 恶化 ≈ 12 %、输出碎裂；最终 RTS 关闭 |

### DSpark 仍是合格的独立交付物

冻结谱系 = `B300 Stage11 Draft → GGUF/混合量化 → 910C 投机运行时`。
长文本摊得动验证成本（1.87×）；短流式 chunk 摊不动——所以 thinker 投机**不**挂进
最终 0.4829 RTF 配置，但作为独立文本/长文本资产保留（`feat/dspark-llama-port`）。

---

## 11 · 工程启示

- **训练与服务是一个生命周期、两个证据域。** B300 acceptance 验证 draft 质量；
  910C benchmark 验证运行时价值。
- **跨平台部署是模型契约问题。** 张量布局、draft metadata、KV 位置、接受 token 流、
  duplex 钩子——每一个都能独立毁掉正确性。
- **Launch 与同步可以主导实时 decode。** 链融合可以击败「替换最慢的单个原语」。
- **Workload 形态决定投机经济学。** 长文本摊销验证；短流式 chunk 不一定。
- **阴性结果是一等证据。** 防止局部 benchmark 胜利累积成一个更慢、更复杂的系统。
- **正确性层级：** ① 证明目标代码路径真的执行了 → ② 证明 layout/KV/buffer 契约 →
  ③ 证明数值或任务级 parity → ④ 才测延迟。这个顺序消灭了多个假「kernel」诊断。

> **可复用的性能工程循环**
> `架构 → profiling → 候选假设 → 运行时可达性 → 正确性 gate → Amdahl 上界 →
> 端到端 A/B → 复现或否决`——能直接迁移到下一个 vLLM / SGLang 系统的资产。

> **下一个杠杆：已验证、未晋升。** Talker 仍同步密集（~3.3 ms/token sync）。
> 离线 block-batch 前向 k=8 实测 3.55 → 1.46 ms/token（**2.44×**），但生产晋升需要
> 保持采样语义并重构流水线——记录为已验证的下一步方向，不属于提交配置。

---

## 🗺️ 仓库导航

**最终生命周期：3 支活跃 + 4 支文档分支。** 完整导读：
[docs/branch-map.md](docs/branch-map.md)

| 分支 | 用途 | 状态 |
|---|---|---|
| `competition/final-ascend-track-a` | **赛道一最终提交**（冻结 runtime `fd3dd36` + 提交文档） | 🔒 FREEZE |
| `feat/dspark-llama-port` | DSpark 投机解码 backport（赛道二） | 保留 |
| `docs/specdecode-migration` | llama / vLLM / DSpark 迁移研究 | 文档 |
| `docs/engineering-log` | 工程日志——9 个模块：性能数据链、被否决路线、A/B 口径 | 🔒 FREEZE @ `858ad30` |
| `application-materials` | 申请材料（5 文件 + EVIDENCE_MAP） | 冻结 @ `e84ab45` |
| `docs/tilelang-tutorial` | **TileLang 教学**——7 讲 + 7 份生产 kernel（「怎么写」侧配套教材） | 活跃 @ `a2a4362` |

**关键锚点：**

| Commit / tag | 含义 |
|---|---|
| `fd3dd36`（tag `competition-final-20260814`） | 跑出最终数字的冻结 runtime |
| `16ec3500d`（tag `competition-submission-20260814`） | 提交包定稿 |
| `c9785cc` | pristine 基线（组织方 bench/huawei，无 NaN） |
| `051e993` | 旧 FROZEN BASELINE（F16 + Flow∥Vocoder） |
| `perf/tilelang-bridge` | TileLang 桥接真源（side-load 进 ggml-cann） |

**提交包**：`SUBMIT-track1-final-20260831.tar.gz`（终包，只读）。

**本分支文档：**
[PROJECT_JOURNEY](docs/PROJECT_JOURNEY.md) ·
[PERFORMANCE_STATUS](docs/PERFORMANCE_STATUS.md) ·
[branch-map](docs/branch-map.md) ·
[W8A8 量化 MatMul](docs/w8a8-cann-quant-matmul.md)

---

## 13 · 复现协议

刻意四段式：

1. 构建已验证的 llama-omni / ggml-cann 后端 + AOT 内核集（competition 分支）；
2. 在**性能**环境（`server.env`）下跑 `submission/scripts/run-rts.sh ${seed}`；
3. 在**隔离的精度**环境（`config-accuracy.env`）下跑 VideoMME / Daily-Omni / Seed-TTS；
4. 从干净 shell 启动全双工 demo（CANN 环境校验 + 会话关闭）。

RTF harness 使用同一条 120 s 双工视频与固定 seed 1001–1004。
**复现 = 匹配计时边界、seed、配置身份与精度契约——不仅仅是退出码为零。**

<details><summary><b>🚀 本地启动整套服务（本分支）</b></summary>

```bash
# 构建
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON
cmake --build . --target llama-omni-server -j$(nproc)

# 启动全双工服务 —— 必须 pin 单 die（跨 die 执行产生无效数值）
ASCEND_RT_VISIBLE_DEVICES=0 \
OMNI_T2W_PIPELINE_OVERLAP=1 OMNI_T2W_DEVICE=cann-flow-only \
OMNI_DUPLEX_MAX_SLICE=0 OMNI_TTS_FIRST_CHUNK_STEP=10 \
./bin/llama-omni-server \
  -m /path/to/MiniCPM-o-4_5-F16.gguf \
  --host 127.0.0.1 --port 18094 -ngl 999 --device CANN0 \
  --ctx-size 4096 --batch-size 512 --ubatch-size 512 -t 4
```

| 变量 | 作用 |
|---|---|
| `ASCEND_RT_VISIBLE_DEVICES=0` | pin 单 die——dual-die 910C 上**必需** |
| `OMNI_DUPLEX_MAX_SLICE=0` | 杠杆 **A**：每帧 vision token 128→64 |
| `OMNI_TTS_FIRST_CHUNK_STEP=10` | 杠杆 **C**：首 TTS chunk 5→10 token |
| `OMNI_T2W_PIPELINE_OVERLAP=1` | Flow ∥ Vocoder 流水线并行 |
| `OMNI_T2W_DEVICE=cann-flow-only` | flow matching 上 NPU |
| `OMNI_T2W_DRAIN_TIMEOUT_MS=5000` | T2W drain 超时（ms） |
| `OMNI_NAN_DIAG=1` / `OMNI_T2W_QUEUE_DIAG=1` / `OMNI_ENCODING_DIAG=1` | 零开销诊断 |
| `GGML_CANN_W8A8=1` | W8A8 量化 MatMul（opt-in，非默认） |
| `OMNI_KV_CACHE_REUSE=1` | 静态前缀 KV 复用 |

> 产出提交数字 0.4829 的**精确冻结环境集**随 competition 分支的提交包存放
> （`server.env` / `config-local.env`）；精度运行使用物理隔离的
> `config-accuracy.env`（§9）。

</details>

---

## 📅 带 git 锚点的时间线

| 日期 | 锚点 | 事件 |
|---|---|---|
| 07-23 | — | 项目启动：以 llama.cpp-omni fork 参赛 |
| 07-28 | `ecee7de` | F16 可运行基线（6 个 CANN RoPE 正确性修复）；发现 T2W-CPU 瓶颈（占首音 93 %） |
| 08-01 | — | CANN T2W 迁移完成：cann-flow-only，W0 p50 −81.4 % |
| 08-03 | — | 线程泄漏定根（libgomp × httplib，319 线程）；WS lifecycle 修复 |
| 08-05 | — | 静态前缀 KV 2.4×；Q8_0 ACCEPT / Q4_K_M REJECT |
| 08-06 | `bdd4550` | 源码冻结 + 冻结二进制回归 11/11 |
| 08-08 | — | 官方规范对齐（SPEAK 定义、精度阈值、RTF 口径） |
| 08-09 | `baee842`→`b458846`→`051e993` | duplex max-tokens 修复；Flow∥Vocoder pipeline；旧 FROZEN BASELINE |
| 08-10 | — | 8 份顶层文档 + vLLM 迁移文档；比赛工具链收口 |
| 08-13 | `573b0ba3` | FA mask 修复解决 server 音频 NaN；Seed-TTS 三重损坏修复 |
| 08-14 | `fd3dd36` | **冻结 runtime**（tag `competition-final-20260814`）；提交包 `16ec3500d` |
| 08-14 | `c12712446` | main README / branch-map 改为分支导读体系 |
| 08-15→31 | bench-huawei 树 | RTF 0.6754→0.4829 攻坚（A/C 固化、NFE2、launch 税削减）；官方 RTF parity 1.0904；精度复验 4/4 |
| 08-31 | `SUBMIT-track1-final` | **终包提交（只读）** |
| 09-01 | `a2a4362` | TileLang 教学分支（`docs/tilelang-tutorial`，7 讲 + 7 生产 kernel） |

> 完整逐日脉络（踩坑总表、官方节点、vLLM 迁移）→
> [docs/PROJECT_JOURNEY.md](docs/PROJECT_JOURNEY.md)

---

## 公开锚点与证据边界

- MiniCPM-o 4.5 技术报告 · 官方项目 · llama.cpp-omni（ggml-org/llama.cpp fork）
- **证据边界**：训练侧数字冻结自 `docs/engineering-log` @ `858ad30`；运行时证据来自
  归档的 Ascend 910C 性能分支与提交 harness。Acceptance 从不作为 TPS 声明呈现；
  official-vs-local RTF 对比按 harness 可比性标注。

<div align="center">

---

[English](README.md) · **简体中文**

</div>
