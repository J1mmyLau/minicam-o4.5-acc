# 01 · 项目总览

## 比赛任务（Track 1 / 子赛道 A）

在指定 NPU（Ascend 910C）上部署 MiniCPM-o 4.5（GGUF / llama.cpp-omni 推理框架），
优化**实时语音对话（RTS）**的主指标：

> **RTF = SPEAK→WAV 完整链路耗时 / 音频时长**（官方基线 **1.087**）

同时四项精度指标需在容差内（VideoMME ≥67.0 / Daily-Omni ≥77.5 /
TTS-Seed ASV ≥0.689 / WER ≤1.56）。

## 三条工作链（怎么串起来的）

**① RTF 推理优化链（910C，主提交）**——架构见 [04](04-architecture.md)，
归因见 [05](05-profiling.md)，内核细节见 [06](06-kernel-runtime-optimization.md)，
E2E 数据链见 [02](02-rts-optimization.md)：

```
稳定性三修(0.89→0.73) → host税三连(launch 18214→1301) → TileLang 四核
→ NFE2 → 杠杆A+C → 0.4829±0.0161（复测 0.4840±0.0125 确认可复现）
```

**② DSpark B300 训练主线**（权重从这来，见 [03](03-dspark-training.md)）：

```
数据组成(Daily-Omni 1197 + VideoMME 1500 + Seed-TTS 1500 = 4197 样本)
→ target rollout / hidden-state cache(98.21GiB, 2,145,260 tokens)
→ warmstart(非 exact resume) → DP8 训练(150 步) → step_150 checkpoint
→ acceptance evaluation(accept_len 3.4923→3.8620) → inference artifact(4.4GB)
```

**③ DSpark 910C 推理闭环**（artifact 变成可用资产，见
[dspark-910c-inference.md](dspark-910c-inference.md)）：

```
Draft artifact → GGUF/量化(1.85GB 方案C, acceptance 逐位一致)
→ llama.cpp-omni 接入(乱码三修) → speculative decoding(k=2 实测 1.87×)
→ runtime A/B → RTS 双工 A/B(净负判定) → E2E RTF(主提交不挂 draft)
```

②③ 分工：**B300 = 训练证据，910C = 推理验证**。910C 侧另有一条小规模
本地微调线（真实反向传播，TF acc 74.1%→90.9%），其「瓶颈是数据量」的结论
直接决定了 B300 主线 4197 样本的数据规模设计（[03](03-dspark-training.md) §2）。

## 推理链路与 RTF 分解

全双工会话中每个 chunk 走五段，最终候选的 RTF 分解（config-verify seed1001）：

| 阶段 | RTF 占比 | 说明 |
|---|---|---|
| vision encode（VPM） | 0.0611 | 杠杆A 后 64 token/帧 |
| llm_prefill | 0.0642 | |
| llm_decode（thinker） | 0.1233 | TileLang QKR+Norm 融合核生效 |
| tts（talker 音频 token 生成） | 0.1427 | 杠杆C 后首 chunk 10 token |
| token2wav（flow+vocoder） | 0.0987 | TileLang conv1d + NFE2 |
| **合计** | **0.4901** | 单 run 复核值；4-run 统计 0.4829±0.0161 |

## 两条交付线的关系（工程事实）

```
线 1（主提交，RTF）                 线 2（独立交付，DSpark 投机解码）
llama.cpp-omni @ bench-huawei 树    llama-cpp-upstream-dspark 树
  │ 无损 runtime/内核优化              │ draft 模型资产 + 训练 + 量化
  │ TileLang 融合核 + A+C 杠杆         │ 8×B300 训练（stage11）
  │ RTF 1.087 → 0.4829                │ 文本域 k=2 1.87×；量化 1.85GB
  └ 四项精度达标                       └ RTS 双工实测净负 → 不挂
```

两条线**相互独立、互不依赖**：RTS 主提交不挂 draft（双工路径实测净负）；
DSpark 以量化模型资产 + 文本域投机收益独立交付。两棵代码树无公共祖先
（bench-huawei=June 基+CANN 修复；upstream-dspark=Aug 孤儿 squash+dflash
全套），不能 cherry-pick 互搬。

## 时间线摘要

| 日期 | 里程碑 |
|---|---|
| 08 月上旬 | 稳定性/生命周期攻坚：WS 会话 50/50、线程泄漏根因（cgroup PID 耗尽）、FA NaN 定位（Q≥435@KV≥768） |
| 08-13 | 精度基线冻结：Daily 79.43% + VideoMME 69.8% PASS；Seed-TTS WER 100% 三重根因修复 → 1.422% PASS |
| 08 中旬 | TileLang-ascend 910C 装配；vocoder conv1d im2col（t2w −21%）；RTF 0.89→0.73 |
| 08-25 | DSpark 910C 训练闭环（推训一致）；stage10 量化 1.85GB |
| 08-27~28 | DSpark acceptance 全域达标（ft3 91% TF / 文本 19% / MM 17.9%）；多帧两大根修 |
| 08-29 | RTF Phase1：杠杆A+C 落地 0.6102→0.4829 |
| 08-30 | **8×B300 stage11 150 步训练完成**（accept_len 3.49→3.86）；量化+接入+对拍 |
| 08-31 | 提交包冻结；DSpark RTS A/B 净负坐实；Demo EZ1002 修复；文档分支（本分支） |

## 硬件一句话

910C 是 dual-die 单卡：必须 `ASCEND_RT_VISIBLE_DEVICES` pin 到一个 die（0 或 1），
精度与性能任务都用单 die 跑，跨 die 会拿到垃圾数值。
