# MiniCPM-o 4.5: From DSpark Training to Ascend 910C Runtime Optimisation

> **一个跨平台 model-to-system 项目**：NVIDIA B300 级 GPU 上的 DSpark 投机训练 →
> 跨平台工件转换 → 华为 Ascend 910C 上的 llama.cpp-omni 实时全双工服务 →
> profiling → kernel / runtime 优化 → 端到端 RTF 验证。
>
> **最终状态 (2026-08-31)：✅ 提交完成。** 核心结论：同口径本地基线 RTF 0.6754 → **0.4829（−28.5%）**；
> 四项精度指标全部达标；投机解码在文本域 1.87×、在实时短 chunk 域净负（按 workload 分别决策）。
>
> ⚠️ **本 `main` 分支是项目介绍，不是交付分支。** 最终代码在
> `competition/final-ascend-track-a`（冻结 runtime `fd3dd36`），完整分支导航见
> [docs/branch-map.md](docs/branch-map.md)。

---

## 目录

- [一页速览](#一页速览)
- [1. 项目背景与系统边界](#1-项目背景与系统边界)
- [2. 训练侧：分布对齐的 DSpark Draft（B300）](#2-训练侧分布对齐的-dspark-draftb300)
- [3. Draft 质量：受控验收评测](#3-draft-质量受控验收评测)
- [4. 跨平台工件：B300 → Ascend 910C](#4-跨平台工件b300--ascend-910c)
- [5. 投机解码：为什么 workload 决定成败](#5-投机解码为什么-workload-决定成败)
- [6. Ascend 910C 上的 Profiling](#6-ascend-910c-上的-profiling)
- [7. TileLang、Launch 税与 Kernel 融合](#7-tilelanglaunch-税与-kernel-融合)
- [8. 端到端 RTF 优化链](#8-端到端-rtf-优化链)
- [9. 精度：四项指标与环境隔离](#9-精度四项指标与环境隔离)
- [10. 被否决的路线](#10-被否决的路线)
- [11. 工程启示](#11-工程启示)
- [12. 仓库导航](#12-仓库导航)
- [13. 复现协议](#13-复现协议)
- [项目推进时间线（git 锚点）](#项目推进时间线git-锚点)

---

## 一页速览

| 维度 | 结果 | 口径 |
|---|---|---|
| **端到端 RTF** | **0.4829 ± 0.0161**（复检 0.4840 ± 0.0125） | 同口径本地基线 0.6754 ± 0.0152 → **−28.5%**；对外公开参考 1.087 为方向性（−55.6%） |
| **精度（四项）** | VideoMME 69.8 / Daily-Omni 79.43 / TTS SIM 0.969 / TTS WER 1.422% | 要求 ≥67.0 / ≥77.5 / ≥0.689 / ≤1.56%，**4/4 PASS** |
| **投机解码** | 文本域 k=2 **1.87×**、k=3 1.80×、k=7 1.75×；15 帧多模态 1.49× | 独立 benchmark；最终 RTS 配置**关闭** thinker 投机（短 chunk 无法摊销） |
| **Kernel 融合** | QK-norm+RoPE 融合 decode **+66%**（0.47→0.78 tok/s）；RMSNorm 行融合 +25%（叠加 +55~65%） | TileLang-Ascend AOT，输出位级对齐 |
| **Launch 税** | host launch 18,214 → **1,301** | VPM patch-mm + 算子融合 + ACL graph |
| **训练侧** | 5 层 DSpark draft，4,197 真实多模态样本，DP8×150 步零失败 | Stage11 平均接受长度 3.49→3.86（+10.6%） |

**本项目最重要的一条方法论**：模型侧 acceptance、独立投机加速、实时全双工 RTF 是
**三个必须分开测量的端点**——任何其中一个的胜利都不能外推到另一个。

---

## 1. 项目背景与系统边界

本项目来自全模态大模型在昇腾算力平台上的部署优化比赛（llama.cpp-omni 子赛道）。
比赛五道关卡：**框架可运行 → Benchmark 精度降幅 ≤2pp（准入）→ 官方 Demo 端到端可用（准入）→
每 audio chunk 的 RTF（排名依据）→ 主办方环境复现**。精度和 Demo 是准入条件，
只有通过后优化才进入性能评测。

**硬件与软件栈：**

| 层 | 组件 |
|---|---|
| 应用 | 全双工 MiniCPM-o 服务（视频/音频流式进出） |
| 运行时 | llama.cpp-omni（ggml-org/llama.cpp fork） |
| 后端 | ggml-cann + ACLNN / CANN（服务基线 8.5.0.alpha002；TileLang 内核线 9.1.0-beta.1） |
| 内核 | TileLang-Ascend AOT 共享库（纯 C ABI，单核 15.3µs/call） |
| 图 | ACL graph capture/replay（验证过的路径） |
| 硬件 | 1× Ascend 910C（dual-die），全部性能/精度运行 **pin 单 die**（跨 die 产生无效数值，已否决） |

### 1.1 端到端执行链

```text
视频/音频流 → VPM 视觉编码器（帧 token → 多模态嵌入）
            → Thinker prefill + decode（Qwen3 backbone：36 层，hidden 4096）
            → Talker / TTS token 生成
            → Token2wav（flow matching + vocoder → 流式 WAV）
```

一个 duplex chunk 的时间预算：`T_chunk = T_vis + T_pre + T_dec + T_tts + T_wav`，
服务目标是实率因数 **RTF = T_chunk / D_audio**（越低实时余量越大）。

**系统边界意识**：一个 2× 快的孤立 kernel，当其 stage 只占全链路一小部分时，
对 RTF 的影响可以忽略——这是本项目反复付学费学到的一条（见 §7 的 Amdahl 案例）。

### 1.2 测量契约

最终对比使用：同一条 120s 双工视频、37 chunks、相同计时边界、seed 1001–1004、
排除冷启动模型加载。**配对本地基线 0.6754 ± 0.0152；最终配置 0.4829 ± 0.0161。**
公开的官方 RTF 1.087 仅作方向性参考（不同 harness 产物），两者明确分列、不混用。

---

## 2. 训练侧：分布对齐的 DSpark Draft（B300）

目标 MiniCPM-o 模型冻结；可训练对象是 **5 层 DSpark draft**，从目标 hidden states
（层 [1, 9, 17, 25, 33]）学习。5 个 4096 维状态拼接 = 每 token 20,480 维目标特征。

### 2.1 真实数据与离线目标缓存

训练集 **4,197 条真实多模态样本**：

| 来源 | 样本数 |
|---|---|
| Daily-Omni | 1,197 |
| Video-MME | 1,500 |
| Seed-TTS EN | 1,088 |
| Seed-TTS ZH | 412 |

冻结目标前向只跑一次建 teacher cache（而非每个训练步重复跑目标模型）：
**4,197/4,197 成功，2,145,260 缓存 token，10 shards，98.21 GiB，113.8 分钟，
零失败零超长**。hidden states 存 BF16；rollout 用 FP16 目标推理（64 生成 token，
max length 2048）。

### 2.2 Draft 架构与训练契约

| 项 | 配置 |
|---|---|
| Draft 层数 | 5 |
| Block size | 7（每步提议 7 token） |
| 目标层 | [1, 9, 17, 25, 33] |
| Hidden size | 4096 |
| Anchors / Markov rank | 512 / 256 |
| Loss | CE 0.1 + L1 0.9，衰减 γ=8 |
| 精度 / 学习率 | BF16 / 3×10⁻⁶ |

**DP8 batch 算术**：local batch 1 × DP world size 8 × 梯度累积 4 = **有效全局 batch 32**；
一个 epoch ≈ 131.2 optimizer step，训练由 `max_train_steps=150` 驱动（末段进入第二轮数据遍历）。
**正式 run 完成 150 步，零 NaN / Inf / OOM / NCCL 失败**，每 25 步落 checkpoint。

代表性 step 记录（全部有限值）：

| Step | Loss | LR | 步时 (s) |
|---|---|---|---|
| 25 | 1.0065 | 2.89×10⁻⁶ | 0.96 |
| 50 | 1.1815 | 2.38×10⁻⁶ | 0.63 |
| 100 | 1.3071 | 8.18×10⁻⁷ | 0.63 |
| 150 | 0.8430 | 0 | 0.63 |

> 日志中的 gradient-norm 远大于配置的裁剪阈值 1.0；因 logger 相对裁剪的位置在锁定源里
> 未验证，报告保守对待该观测，不据此推断训练不稳定。

### 2.3 Checkpoint 语义与模型谱系

step_150 约 **2.369B 参数**、4.41 GiB model.safetensors。8 个 rank-local
training_state 文件是 resume 状态——**no-shard DP 下每个 rank 持有完整同步副本，
并非 8 个不同模型**，推理导出时排除。

```text
Stage10 权重 → Stage11 训练（严格 warmstart：权重 strict 加载，optimizer/scheduler 重建）
            → 150 步正式 run → 正式 Draft 工件
```

**最终提交的 Draft 权重来自 B300 Stage11。** 910C 侧微调是方法验证与 acceptance 修复资产，
刻意排除在主工件谱系之外。

---

## 3. Draft 质量：受控验收评测

Stage10 vs Stage11，644 条文本样本（GSM8K / HumanEval / MT-Bench / Alpaca），
控制目标模型、tokenizer、生成配置、seed、world size 与样本身份，
prompt SHA256 多重集断言相等：

| 指标 | Stage10 | Stage11 | Δ |
|---|---|---|---|
| 平均接受长度 | 3.4923 | 3.8620 | +0.3697 |
| 总体接受率 | 0.4388 | 0.4854 | +0.0466 |
| accept@4 | 0.2164 | 0.2906 | +0.0742 |
| accept@5 | 0.1461 | 0.2348 | +0.0886 |
| accept@6 | 0.0954 | 0.1895 | +0.0941 |
| 置信绝对误差 | 0.0516 | 0.0511 | −0.0005 |

增益随 7-token block 尾部增大而 accept@0 变化很小——这是投机 drafting 想要的信号：
**模型更擅长维持整块正确，而不只是猜中首个 draft token。**

> **证据边界**：acceptance 提升不是 TPS 声明。服务速度还依赖 draft 代价、验证 batch 代价、
> 请求长度与运行时调度——因此独立投机加速与全双工 RTF 分开测量（§5）。

---

## 4. 跨平台工件：B300 → Ascend 910C

Stage11 工件在不改变模型谱系的前提下转换为 Ascend 可部署形态。通用导出器不够——
draft 专属字段与张量语义必须保留，因此采用**自定义 safetensors→GGUF payload swap**：

```text
Stage11 BF16 safetensors（正式 B300 工件）
  → draft-aware GGUF swap（保留 DSpark metadata 与布局）
  → 混合精度 Q8_0 / BF16 / F32（部署体积 1.85 GB）
  → parity 校验（header/张量完整性 + acceptance A/B）
```

只量化选定的线性张量；数值敏感的 norm/bias 保持 F32；Markov 路径在全 Q8 变体
后端失败后保持不量化。三组 prompt 检查下 BF16 与混合工件的 acceptance **逐位一致**。
**不声称任何量化加速**——该后端上 Q8 与 BF16 吞吐实测相当。

### 4.1 运行时正确性契约

「模型能加载」不等于「投机路径正确」。接入 llama.cpp-omni 修复了三个契约：

1. draft 必须消费**当前** KV 位置而非过期的 `n_past`；
2. **所有**被接受的附加 token 必须返回目标流，而非只返回第一个；
3. duplex prefix、hidden-state、listen-flush 钩子在投机路径上保持对齐。

一个数值上正确的算子放回并发运行时仍可能失败——stale KV、丢接受 token、
buffer 复用、流竞态、隐藏的环境状态都让「运行时语义」成为一等性能变量。

---

## 5. 投机解码：为什么 workload 决定成败

独立文本 benchmark 上 draft 代价约 **1.11 ms/token（≈ 目标的 1/28）**：

| 场景 | 实测加速 |
|---|---|
| 文本，k=2 | **1.87×** |
| 文本，k=3 | 1.80× |
| 文本，k=7 | 1.75× |
| 15 帧多模态 | 1.49× |

**实时双工路径给出了相反的决策**：

| 指标 | Draft off | Draft on |
|---|---|---|
| Core RTF | 3.979 | **4.460**（恶化 ~12%） |
| LLM decode | 0.132 | 0.338（2.6× 慢） |
| 输出连续性 | 连贯 | 碎裂 |

短 chunk 每次只 decode 几个 token，draft 前向、验证与 KV 同步无法摊销。
**最终 RTS 配置关闭 thinker 侧投机，同时保留投机子系统作为独立的长文本/文本资产。**

> **三个不可混淆的端点**：acceptance（模型侧 draft 质量）｜1.87×（独立投机运行时）｜
> 0.4829（关闭 thinker 投机的最终全双工结果）。

---

## 6. Ascend 910C 上的 Profiling

优化从**实测时间分布**出发，而不是预设 kernel 目标。

### 6.1 设备与 host 分解

| Profile 组件 | 占比 |
|---|---|
| Main LLM forward（msprof） | 26.8% |
| KV ScatterUpdate | 19.4% |
| F32↔F16 cast | 13.6% |
| LM head | 0.65% |
| Logits 同步（占 decode） | 48% |
| Embedding 同步（占 decode） | 32% |
| llama_decode 本体（占 decode） | 17% |
| 内存分配（占 decode） | ~0.1% |

TTS 侧约 3.3 ms/token（66%）消耗在同步；token2wav 侧 **vocoder im2col 占 vocoder 路径 ~85%**。

这些分解直接否决了两个诱人但错误的方向：分配不是 decode 瓶颈；LM head 太小，
不值得 head-only 重写。单点换装（RoPE 替换、sel-embedding、通用 OP_FUSION）实测全部≈0 增益。

> **关键路径纪律**：profiler 热点只是候选，不是根因。每个候选必须经过
> 「运行时可达性验证 → 正确性 gate → A/B → Amdahl 核算」才准晋升。多个局部更快的改动
> 因 stage 占比太小或全链路回退而被否决（§10）。

---

## 7. TileLang、Launch 税与 Kernel 融合

TileLang-Ascend 路径通过 **AOT 共享库 + ggml-cann side-loading 桥接**集成
（绕开冻结的 CMakeLists）。核心观察：**decode 被「重复小算子 + host launch/同步开销」主导**，
替换孤立算子价值很小，把「一串算子折叠成一个 kernel」才有系统意义。

### 7.1 QK-norm + RoPE 融合（+66%）

36 层 Qwen3 中，Q/K norm + RoPE 是每 decode 步重复 36 次的短链。融合为单个 TileLang
kernel 后四臂交错 llama-bench（tgq64）实测 **0.47 → 0.78 token/s（+66%）**，输出位级对齐。

**第一版集成失败不是 kernel 数学问题**，是两个 C++ 桥接契约 bug：
双重 RoPE（融合路径已做 norm+RoPE，外层图又执行了一次）与 view 步长错
（返回 [128,H,T] F32 view 需要 nb1=512、nb2=H×512，而非复用不兼容步长）。
另有一个教训：dump 越界 + 变长记录按定长解析制造了**假的流竞态症状**——
插桩本身也是需要验证的代码。短 prompt greedy 输出修复后与原生链一致；
长 prompt 可经 F32 舍入发散，因此生产 gate 是任务/精度正确性而非无限位同一声明。

### 7.2 RMSNorm 与 vocoder kernel

- **RMSNorm 行融合**：3 norm 位点/层 × 36 层，tile 范式（2-D tile、末维归约、标量 tile.mul、broadcast）。单开 +25%，与 QKR 叠加 **+55~65%**（0.78–0.79 tok/s）。
- **vocoder conv1d**：直接 TileLang 卷积路径消掉占 vocoder 85% 的 im2col（72 个 T-bucket kernel + 桥 bucket 回落）。token2wav stage **−21%**，WAV 相关系数 **0.9993**。

> **为什么微加速不够（本项目最干净的 Amdahl 案例）**：conv1d 技术上成功，但 vocoder
> 只占 token2wav 约 1/3、flow matching 主导残余 stage，E2E RTF 收益只有 ~0.01–0.02。
> `S_E2E ≤ 1/((1−f) + f/S_stage)`——stage 占比 f 小时，再大的 S_stage 也不是系统胜利。

### 7.3 Launch 削减与 workload 整形

更大的系统收益来自 kernel 工作 + 运行时 + workload 变化的组合：

- **VPM patch-mm 融合 + 算子融合 + ACL graph capture/replay**：host launch **18,214 → 1,301**；
- **视觉 token 削减**：`OMNI_DUPLEX_MAX_SLICE=0` 每帧 128→64 vision token（只保留 overview），
  VPM ~92→53ms、prefill ~123→65ms；
- **首 TTS chunk 5→10 token**（`OMNI_TTS_FIRST_CHUNK_STEP=10`）：per-token decode
  24.7→19.2ms（−22%），代价是首响应 +~100ms；
- **token2wav flow 步数 NFE 5→2**（预建 prompt cache；NFE1 因音质被否决）。

### 7.4 优化总账

| 干预 | 证据 / 机制 | 结果 / 决策 |
|---|---|---|
| ACL graph + 融合 | host launch 过载 | launch 18,214→1,301；保留 |
| QK-norm+RoPE TileLang | 36 条重复短链/步 | 0.47→0.78 tok/s；保留 |
| RMSNorm 行融合 | 跨层重复 norm launch | +25% 单开；+55~65% 叠加；保留 |
| conv1d 直算 | im2col 主导 vocoder | t2w stage −21%；E2E 有限（Amdahl） |
| NFE 5→2 | flow 主导残余 t2w | RTS 保留（配 prompt cache） |
| 视觉 slice 削减 | 每帧 vision token 过多 | encode/prefill 双降 |
| 首 chunk 5→10 | chunk 边界开销 | per-token 24.7→19.2ms |

规律一致：**大增益来自削减重复工作或折叠算子链，而不是把孤立原语换成略快的实现。**

---

## 8. 端到端 RTF 优化链

最终性能路径由可复现的 A/B 阶段构成，而非一次性大补丁：

| 配置 | Core RTF |
|---|---|
| 官方参考（方向性） | 1.087 |
| 同口径本地基线（A+C off） | 0.6754 ± 0.0152 |
| 完整优化栈，无 A+C | 0.6102 ± 0.0104 |
| + A：视觉 slice 削减 | 0.5182 ± 0.0407 |
| + C：首 TTS chunk 10 | **0.4829 ± 0.0161** |
| 提交前独立复检 | 0.4840 ± 0.0125 |

即对配对本地基线 **−28.5%**，对公开参考方向性 **−55.6%**。

代表性最终 run 分解（四 run 聚合仍是 headline，因 token2wav 方差不可忽略）：

| Stage | RTF 贡献 |
|---|---|
| Vision encode | 0.0611 |
| Prefill | 0.0642 |
| Decode | 0.1233 |
| TTS / Talker | 0.1427 |
| Token2wav | 0.0987 |
| **合计** | **0.4901** |

---

## 9. 精度：四项指标与环境隔离

| 指标 | 要求 | 最终 |
|---|---|---|
| VideoMME | ≥ 67.0 | **69.8** |
| Daily-Omni | ≥ 77.5 | **79.43** |
| TTS Seed ASV/SIM | ≥ 0.689 | **0.969** |
| TTS Seed WER | ≤ 1.56% | **1.422%** |

（评分资产：ZH WER 用 **Paraformer** 而非 Whisper；SIM 用 WavLM+ECAPA。）

**一次真实回归说明了为什么性能与精度环境不能共享可变 shell 状态**：
性能专用变量经 `base_env` 泄漏进长上下文精度路径，VideoMME 从 69.8 **塌到 8.0**。
冻结设计因此把性能环境（`server.env`）与精度环境（`config-accuracy.env`）**物理隔离**。

同族教训（提交前抓到）：`run_eval.sh` 会 source `config-local.env`，一个 stale 的
`OMNI_T2W_NFE_STEPS=5` 静默覆盖 launch 时 NFE2 并破坏 token2wav 路径；
去掉重叠后 3-run 复检 0.4840±0.0125，与归档 4-run 一致。

---

## 10. 被否决的路线

最终系统更容易辩护，因为归档记录了阴性实验而不是隐藏它们：

| 路线 | 决策证据 |
|---|---|
| Q8_0 主模型 | 净负；同 seed 0.5215 vs 0.5257，且 prefill/decode kernel 更慢 |
| Flow ACL Graph capture | flow 中位改善但 E2E 回退 ~11%；回滚 |
| Flow zcat2 融合 | 位级相等但 Δ<1%；DO_NOT_PROMOTE |
| 单点 RoPE 换装 | ≈0 增益；host 税主导 |
| sel-embedding 换装 | 211s vs 213s；中性 |
| thinker 侧 DSpark 进 RTS | core RTF 恶化 ~12%、输出碎裂；最终 RTS 关闭 |

### DSpark 仍是合格的独立交付物

冻结模型谱系 = B300 Stage11 Draft → GGUF/混合量化 → 910C 投机运行时。
长文本 workload 摊销验证成本（1.87×），短流式 chunk 不能——所以 thinker 投机
不挂进最终 0.4829 RTF 配置，但作为独立文本/长文本资产保留（`feat/dspark-llama-port`）。

---

## 11. 工程启示

- **训练与服务是一个生命周期、两个证据域**：B300 acceptance 验证 draft 质量；
  910C benchmark 验证运行时价值。
- **跨平台部署是模型契约问题**：张量布局、draft metadata、KV 位置、接受 token 流、
  duplex 钩子，每一个都能独立毁掉正确性。
- **Launch 与同步可以主导实时 decode**：链融合可以击败「替换最慢的单个原语」。
- **Workload 形态决定投机经济学**：长文本摊销验证；短流式 chunk 不一定。
- **阴性结果是一等证据**：防止局部 benchmark 胜利累积成一个更慢、更复杂的系统。
- **正确性层级**：(1) 证明目标代码路径真的执行了 → (2) 证明 layout/KV/buffer 契约 →
  (3) 证明数值或任务级 parity → (4) 才测延迟。这个顺序消灭了多个假「kernel」诊断。

**可复用的性能工程循环**：架构 → profiling → 候选假设 → 运行时可达性 → 正确性 gate →
Amdahl 上界 → 端到端 A/B → 复现或否决。这是能直接迁移到下一个 vLLM / SGLang 系统的项目资产。

**下一个杠杆（已验证未晋升）**：Talker 仍同步密集（~3.3ms/token sync）。离线 block-batch
前向 k=8 实测 3.55→1.46 ms/token（**2.44×**），但生产晋升需保持采样语义并重构流水线——
记录为已验证的下一步方向，不属于提交的性能配置。

---

## 12. 仓库导航

**最终生命周期（3 支活跃 + 4 支文档分支）**，完整导读见 [docs/branch-map.md](docs/branch-map.md)：

| 分支 | 用途 | 状态 |
|---|---|---|
| `competition/final-ascend-track-a` | **赛道一最终提交**（源码冻结 `fd3dd36` + 提交文档） | 🔒 FREEZE |
| `feat/dspark-llama-port` | DSpark 投机解码 backport（赛道二） | 保留 |
| `docs/specdecode-migration` | llama / vLLM / DSpark 迁移研究 | 文档 |
| `docs/engineering-log` | 工程日志（9 份：性能数据链/被否决路线/A-B 口径） | 🔒 FREEZE @ `858ad30` |
| `application-materials` | 申请材料（5 文件 + EVIDENCE_MAP） | 冻结 @ `e84ab45` |
| `docs/tilelang-tutorial` | **TileLang 教学**：7 讲 + 7 份生产 kernel 代码（「怎么写」侧的完整教材） | 活跃 @ `a2a4362` |

**关键锚点**：

| commit / tag | 含义 |
|---|---|
| `fd3dd36`（tag `competition-final-20260814`） | 冻结 runtime，跑出最终数据 |
| `16ec3500d`（tag `competition-submission-20260814`） | 提交包定稿 |
| `c9785cc` | pristine 基线（组织方 bench/huawei，无 NaN） |
| `051e993` | 旧 FROZEN BASELINE（F16 + Flow∥Vocoder） |
| `perf/tilelang-bridge` | TileLang 桥接真源（side-loading 进 ggml-cann） |

**提交包**：`SUBMIT-track1-final-20260831.tar.gz`（终包，只读）。

**本仓库文档**：[docs/PROJECT_JOURNEY.md](docs/PROJECT_JOURNEY.md)（完整项目脉络）｜
[docs/PERFORMANCE_STATUS.md](docs/PERFORMANCE_STATUS.md)（性能现状）｜
[docs/branch-map.md](docs/branch-map.md)（分支地图）｜
[docs/w8a8-cann-quant-matmul.md](docs/w8a8-cann-quant-matmul.md)（W8A8 量化 MatMul）

---

## 13. 复现协议

最小复现刻意四段式：

1. 构建已验证的 llama-omni / ggml-cann 后端 + AOT 内核集（competition 分支）；
2. 性能环境（`server.env`）下跑 `submission/scripts/run-rts.sh ${seed}`；
3. **隔离的精度环境**（`config-accuracy.env`）下跑 VideoMME / Daily-Omni / Seed-TTS；
4. 干净 shell 启动全双工 demo（含 CANN 环境校验与会话关闭）。

RTF harness 使用同一条 120s 双工视频与固定 seed 1001–1004。**复现 = 匹配计时边界、
seed、配置身份与精度契约**，而不仅仅是进程退出码为零。

---

## 项目推进时间线（git 锚点）

| 日期 | 锚点 | 事件 |
|---|---|---|
| 07-23 | — | 项目启动：llama.cpp-omni fork 参赛 |
| 07-28 | `ecee7de` | F16 可运行基线（6 个 CANN RoPE 正确性修复）；发现 T2W CPU 瓶颈（首音 93%） |
| 08-01 | — | CANN T2W 迁移完成：cann-flow-only，W0 p50 −81.4% |
| 08-03 | — | 线程泄漏定根（libgomp×httplib 319 线程）；WS lifecycle 修复 |
| 08-05 | — | KV 静态前缀 2.4×；Q8_0 ACCEPT / Q4_K_M REJECT |
| 08-06 | `bdd4550` | 源码冻结 + 冻结二进制回归 11/11 |
| 08-08 | — | 官方规范对齐（SPEAK 定义、精度阈值、RTF 口径） |
| 08-09 | `baee842`→`b458846`→`051e993` | duplex max-tokens 修复；Flow∥Vocoder pipeline；旧 FROZEN BASELINE |
| 08-10 | — | 8 份顶层文档 + vLLM 迁移文档；比赛工具链收口 |
| 08-13 | `573b0ba3` | FA mask 修复：server 音频 NaN 解决；Seed-TTS WER 三重损坏修复 |
| 08-14 | `fd3dd36` | **冻结 runtime**（tag `competition-final-20260814`）；提交包 `16ec3500d` |
| 08-14 | `c12712446` | main README/branch-map 改为分支导读体系 |
| 08-15~31 | bench-huawei 树 | RTF 0.6754→0.4829 攻坚（A/C 固化、NFE2、launch 税削减）；官方 RTF parity 1.0904；精度 4/4 复验 |
| 08-31 | `SUBMIT-track1-final` | **终包提交（只读）** |
| 09-01 | `a2a4362` | TileLang 教学分支（docs/tilelang-tutorial，7 讲 + 7 生产 kernel 代码） |

> 完整逐日脉络（含踩坑总表、官方节点、vLLM 迁移）→ [docs/PROJECT_JOURNEY.md](docs/PROJECT_JOURNEY.md)

---

## Public Anchors

- MiniCPM-o 4.5 技术报告 / 官方项目 / llama.cpp-omni（ggml-org/llama.cpp fork）
- 证据边界：训练侧数字冻结自 `docs/engineering-log` @ `858ad30`；运行时证据来自归档的
  Ascend 910C 性能分支与提交 harness。acceptance 不作为 TPS 声明呈现；
  official-vs-local RTF 对比按 harness 可比性标注。
