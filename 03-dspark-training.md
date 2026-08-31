# 03 · DSpark 训练：B300 主线 + 910C 本地微调（方法论验证）

DSpark = DeepSpec 系投机解码 **draft 模型**：不是独立模型，必须配对固定 target
（MiniCPM-o-4_5 rev `503e754207c9` 的 `model.llm`，Qwen3 36 层 hidden 4096），
学的是 target 第 `[1,9,17,25,33]` 层 hidden states 的分布。

**两条链，训练与推理分开看**：

```
B300（训练证据）                                    910C（推理闭环，见 dspark-910c-inference.md）
数据组成 → target rollout/hidden-state cache        Draft artifact → GGUF/量化(1.85GB)
→ warmstart → DP8 训练 → step150 checkpoint         → llama.cpp-omni 接入
→ acceptance evaluation → inference artifact         → speculative decoding → runtime A/B → E2E RTF
```

| | **B300 stage11（正式训练主线）** | **910C stage10 本地微调** |
|---|---|---|
| 硬件 | 单机 8× NVIDIA B30Z（sm_103，268 GiB/卡） | 同一张 Ascend 910C（torch-npu） |
| 数据 | 4197 样本多模态 hidden-cache（98.21 GiB） | 186 shards / 9434 行（32 rollouts 起步扩量） |
| 性质 | 真实反向传播、纯 DP8、150 步 | 真实反向传播、小数据快速迭代 |
| 产物 | **提交主 artifact 的权重来源** | 方法论验证 + acceptance 修复资产 |
| 结果 | accept_len 3.4923→3.8620 | TF acc 74.1%→90.9%，held-out +0.7~1.0pp |

## 0. 三条口径（先钉死，避免误读）

1. **stage10 → stage11 是 weight warmstart，不是 exact resume**：warmstart 只载入
   权重（`load_state_dict(strict=True)` 通过，无 optimizer/scheduler 状态），
   stage11 新建 optimizer 与 scheduler。工程变量名一律中性
   `WARMSTART` / `WARMSTART_DIR` / `DEEPSPEC_WARMSTART_DRAFT_PATH`。
2. **8 个 `training_state.rank*.pt` 不是 8 个模型**：每份 13,515,997,523 B 中
   99.9994% 是该 rank 的 optimizer state，其余是 `next_micro_step=600`
   （=150 步 × grad_accum 4）与 4 个 RNG state。DeepSpec 不存 scheduler，
   LR schedule 从 `next_micro_step` 重算。
3. **acceptance 提升不能直接写成 TPS 提升**：§1.6 的 accept_length/accept_rate
   是上游 evaluator 的接受率口径；实测吞吐加速只在 k-sweep 里单独测
   （k=2→1.87×，见 dspark-910c-inference.md），两者不混写。

---

## 1. B300 正式训练主线（stage11，2026-08-30 完成）

### 1.1 任务与 draft 配置

| | |
|---|---|
| 架构 | `Qwen3DSparkModel`（DeepSpec DSpark） |
| draft 层数 / **block_size** | 5 / **7**（一次提议 7 个 token） |
| **target_layer_ids** | **[1, 9, 17, 25, 33]** |
| hidden / heads / kv_heads | 4096 / 32 / 8（head_dim 128，GQA） |
| **num_anchors / markov_rank** | **512 / 256**（head_type=vanilla，confidence head 启用） |
| mask_token_id | 151669 |
| 参数量 / dtype | ~2369 M / bfloat16 |
| **loss** | **ce 0.1 + l1 0.9**（loss_decay_gamma 8.0）+ confidence_head_alpha 0.5 |
| 栈 | transformers 4.51.0 + DeepSpec（commit `ae6712019f…`） |

换 target、换 revision、换层号，draft 立刻失效——它学的就是这组 hidden states
的分布。`config.json` 的 `model_type: minicpmo` 继承自 target，
加载需 `trust_remote_code=True`；`num_hidden_layers:5` 是 draft 自己的层数，
`num_target_layers:36` 是 target 的，别看混。

### 1.2 数据组成 → target rollout / hidden-state cache

训练直接读 hidden-state cache（不在线跑 target）。cache `minicpmo_dtriad3_media_fp16`
（manifest version 2）：

| | |
|---|---|
| 总样本 | **4197**（10 shards，**98.21 GiB**） |
| 生成成功率 | **100.00%**（success 4197 / overlong 0 / failed 0） |
| **cache token 数** | **2,145,260** |
| rollout 口径 | greedy 64 token，stop token 关闭，target attn=sdpa |
| chat_template | `minicpmo_multimodal_rollout` |
| max_length / max_slice_nums | 2048 / 1 |
| hidden dtype | **bfloat16**（`--dtype float16` 只影响 target 推理精度，不是落盘精度） |
| token / mask dtype | int32 / uint8 |
| **cache 生成耗时** | **113.8 min**（单 GPU 生成，peak_cuda 17.54 GiB） |
| **total_cache_bytes** | **105,456,927,733 B（100,571.56 MiB）** |
| 源 JSONL | `dtriad_train.jsonl`，sha256 `25a50fa6ec87649d…` |
| 取样区间 | [0, 4197) 全量 |

**四个数据源**（每源非零是准入条件，全部真实媒体、无合成数据）：

| 源 | 样本数 | 说明 |
|---|---|---|
| Daily-Omni | **1197** | rev `bf5a6ee4c829`，视频+音频 QA |
| Video-MME | **1500** | rev `ead1408f75b6`，94.07 GiB 全量下载后抽取（MAX_PER_DATASET=1500 截断） |
| Seed-TTS EN | **1088** | rev `8f5e1aa2a35d` |
| Seed-TTS ZH | **412** | 同上 |
| **合计** | **4197** | 解压确定性、保留原件、幂等（1584 个 mp4） |

### 1.3 warmstart（非 exact resume）

```
openbmb/MiniCPM-o-4_5 (rev 503e754207c9)          target，只用于离线产 cache
   └── your-mother/dspark-block7-minicpmo-4_5-stage10-dtriad (rev f69c1967f760)
           ← warmstart：只有权重，无 optimizer/scheduler
             load_state_dict(strict=True) 通过，64 tensors，2369.45 M params
             RESUME_SEMANTICS = WEIGHT_WARMSTART
           └── stage11 step_150（本 checkpoint）
```

### 1.4 DP8 训练

**超参**（`scripts/train_config.py` = 随包原件，即 §1.1 之外的部分）：

```text
lr 3.0e-6   warmup_ratio 0.05   weight_decay 0.0   seed 42
precision bf16   max_grad_norm 1.0（grad clip）
local_batch_size 1 × 8 ranks × grad_accum 4 = global_batch_size 32
num_train_epochs 1   max_train_steps 150
sharding_strategy no_shard（纯 DP，无 ZeRO 切分）   torch_compile true
logging_steps 1   checkpointing_steps 25
```

**停止条件与 epoch 的关系**：实际停止由 `max_train_steps=150` 驱动
（优先于 num_train_epochs）。按 4197 samples / global batch 32 估算，
一个 epoch ≈ 131.2 steps，即**约 step 132 后进入第二个 epoch**——
因此这不是严格的「一轮数据训练」（问答点：既然 epochs=1，为什么 150 步）。

**运行时**：torch 2.8.0+cu128 / CUDA 12.8 / NCCL 2.27.3 / transformers 4.51.0，
额外 nvidia-cuda-nvcc-cu12 12.9.86（B30Z=sm_103，flex_attention 内部 compile
需要 ≥12.9 的 ptxas）。容器内无 git，provenance 以 4 个 patch marker 校验：
`B300_MINICPMO_WARMSTART_PATCH_V3`（warmstart strict load + target config 适配）、
`GEMMA4_GUARD_V1`（7 文件 import 守卫）、`GCL_SHIM_V1`（GradientCheckpointingLayer
兼容）、`RESUME_DTYPE_V1`（resume 路径 dtype→torch_dtype）。

**训练记录**（FINAL_STEP=150，TORCH_COMPILE=true，无 fallback）：

```text
step | loss     | lr        | grad_norm | step_time_s
   1 | 0.831421 | 8.571e-07 |    420.00 |
  25 | 1.006537 | 2.885e-06 |    255.00 | 0.96
  50 | 1.181541 | 2.379e-06 |    456.00 | 0.63
  75 | 1.118600 | 1.615e-06 |    234.00 | 0.62
 100 | 1.307085 | 8.176e-07 |    312.00 | 0.63
 125 | 1.339076 | 2.206e-07 |    640.00 | 0.63
 150 | 0.843012 | 0.000e+00 |    326.00 | 0.63
```

全部 metric 有限，无 NaN/Inf/OOM/NCCL 错误。同级目录有 step_25/50/75/100/125。
**grad_norm 口径**：日志值约 234–640，显著高于 max_grad_norm=1.0。
**若**该字段对应 `clip_grad_norm_()` 返回的 pre-clipping norm（DeepSpec
logger 的记录时点未在源码中核实——源码钉在 B300 机
`/ssd2/minicpmo-dspark/runtime/DeepSpec/`），则这些 step 均触发了
gradient clipping。由于 acceptance 最终改善，本项目未进一步修改该训练超参。
早期 5-step 运行保留在 `logs/invalid_5step_record.txt`，不作为正式训练证据。

### 1.5 step_150 checkpoint（体积与内容）

推理需要的 5 个文件（合计 4.414 GiB）：

```text
sha256(前16)     bytes         file
5fba915bc8d938e6 4,738,897,626 model.safetensors
b8eb408bb54ef8c4         6,868 config.json
b0c56c192d4aa573        10,135 configuration_minicpmo.py
1a40a58cb7dfa93f        42,559 modeling_navit_siglip.py
aecf30c0108f34b3         2,660 train_config.py
```

**不需要的**（拷走时排除）：`training_state.rank0.pt … rank7.pt` 每份
13,515,997,523 B，共 **100.70 GiB**（含义见 §0.2）。目录总计
`du -sb` = 105.12 GiB，权重只占 4.2%。

```bash
rsync -avP --exclude 'training_state.rank*.pt' \
  root@10.79.131.152:/ssd2/minicpmo-dspark/home/checkpoints/deepspec/\
dspark_block7_minicpmo_4_5_multimodal_dtriad_stage11_b300_dp8/step_150/ \
  ./dspark-minicpmo-4_5-stage11-step150/
```

B300 侧另有推理 tarball：`/root/dspark-minicpmo-4_5-stage11-step150.tar.gz`
（3,782,289,212 B，sha256 `1db577531f1e5c3b2e2e457cfbdf06dc9cab0748f5cd8f8e78eae062e4972cae`），
上传白名单见 `assets/push_stage11_to_hf.py`（结项口径：外部上传不视为本地模型证据）。

### 1.6 acceptance evaluation（stage10 → stage11 A/B）

上游 DeepSpec evaluator，acceptance 公式未改。644 samples：
gsm8k:200 + humaneval:164 + mt-bench:80 + alpaca:200，seed 980406，
temperature 1.0，max_new_tokens 256，DP8。两 checkpoint 共享同一 target /
tokenizer / generation config / seed / world_size，且**逐样本 prompt 的 sha256
多重集断言相等**（保证同题同序）。

| metric | stage10 | stage11 | delta |
|---|---|---|---|
| **avg_accept_length** | 3.4923 | **3.8620** | **+0.3697** |
| **overall_accept_rate** | 0.4388 | **0.4854** | +0.0466 |
| accept_rate@0 | 0.7648 | 0.7712 | +0.0064 |
| accept_rate@1 | 0.5695 | 0.5895 | +0.0199 |
| accept_rate@2 | 0.4157 | 0.4539 | +0.0381 |
| accept_rate@3 | 0.3036 | 0.3573 | +0.0536 |
| accept_rate@4 | 0.2164 | 0.2906 | +0.0742 |
| accept_rate@5 | 0.1461 | 0.2348 | +0.0886 |
| accept_rate@6 | 0.0954 | **0.1895** | **+0.0941** |
| confidence_abs_error | 0.0516 | 0.0511 | −0.0005 |
| confidence_bias | 0.0311 | 0.0350 | +0.0039 |
| proposals | 32334 | 29243 | 见下 |

分数据集 accept_len（stage11）：gsm8k **5.30** / humaneval 4.37 / mt-bench 2.84 / alpaca 2.72。

**读法（按 §0.3 口径）**：
- 提升集中在 block 尾部（@4/@5/@6 各 +0.07~0.09），@0 几乎不变；
- `proposals` 下降是**结果**不是损失：接受更长，同 token 预算轮次更少；
- 这是文本域评测而训练数据是多模态 rollout——两 checkpoint 面对相同域偏移，
  **比较**公平；但「stage11 在多模态输入上更好」这更强命题这批数据不支持
  （多模态 held-out 评测需 evaluator 支持 inputs_embeds，未做）；
- `confidence_*` 是名称映射：上游 per-position 的 ECE→abs_error、
  pred_mean−target_mean→bias（按 total_weight 加权），公式没自创。

### 1.7 → inference artifact

`step_150/model.safetensors`（4.4GB BF16）经 swap+量化（见
[dspark-910c-inference.md](dspark-910c-inference.md)）得到提交资产
**`dspark_stage11-draft-q8mixed-C.gguf`（1.85GB）**。

### 1.8 证据路径

| 证据 | 路径 |
|---|---|
| **本仓逐节点整理（带 file:line 引用）** | [b300/](b300/README.md)（data / cache / training / checkpoint / eval 五篇 + D0–D9 索引） |
| 本仓母文档摘要 | `/workspace/models/dspark-stage11/README.md` + `SHA256SUMS` |
| B300 工程母文档（13 条坑） | 训练机 `/root/b300_minicpmo_dp8/README_zh.md` |
| 训练/评测原始记录 | 训练机 `/ssd2/minicpmo-dspark/logs/`、`/ssd2/minicpmo-dspark/eval/stage10_vs_stage11/` |
| 评测适配封装 | 训练机 `/root/b300_minicpmo_dp8/assets/eval_accept_compare.py`（只覆写 build_models） |
| D8 校验 | model.safetensors 全 float tensor 有限；FINAL_STEP gate 独立重推=150 |

B300 上的加载坑（transformers 4.51 栈）：`torch_dtype=` 不是 `dtype=`；
复合多模态 target 必须 `AutoModel + trust_remote_code=True` 再取 `.llm`。

---

## 2. 910C 本地微调（真实训练，方法论验证线）

> 定位说清楚：这条线**做了真实的反向传播微调**（torch-npu），但其产物
> ascendft*.gguf 是**能力验证与 acceptance 修复资产**；提交主 artifact 的
> 权重来自 B300 stage11（§1）。这条线的最大价值是三个结论，直接决定了
> B300 主线的设计。

### 2.1 闭环三件套（全部在 910C 上）

1. **数据生成器 `llama-rollout-dump`**（examples/speculative-simple/rollout_dump.cpp）：
   target F16 NPU 贪心 rollout，逐位置捕获 5 层 dflash 条件特征 [20480] +
   target 终态 hidden + 贪心 token。~35s/rollout(96 tok)。
   **特征=推理分布本身 → 推训一致的根解法。**
2. **训练器 `train_ascend.py`**（`scripts/train_ascend.py` 原件）：torch-npu
   忠实复刻 dflash 图——encoder `h=RMSNorm(fc(F))`；KV 注入式
   （K=rope(k_norm(wk(h)))，V=wv(h)，注入路径无 attn_norm）；GQA 32/8；
   **共享冻结 lm_head**（从 target GGUF 读 output.weight）；rope NORM 模式
   interleaved、freq_base 1e6；loss = 0.1·CE + 0.9·L1(hid)。
3. **转换链**：swap 原位换字节 → GGUF → 方案 C 量化。

### 2.2 实测训练记录（原始日志在 `/workspace/models/dspark-stage10/`）

首轮（`train_v2.log`，32 rollouts、4 epochs、lr 2e-6）：

| 集 | 训前 | 训后 |
|---|---|---|
| 训练集 TF acc | 22.6% | 74.7%（记忆成分） |
| **held-out t0 图像** | 16.35% | **17.04%** |
| **held-out tt 文本** | 21.59% | **22.57%** |
| held-out t4 双工 | — | 持平 |

扩训 ft3（`train_v3.log`，186 shards / 9434 行，12 epochs、lr 1e-6）：

```text
[eval-pre]  teacher-forced next-token acc = 0.7413 (235/317)   ← ft2 终点
epoch 0..11: mean loss 1.0700 → 0.9070
[eval-post] teacher-forced next-token acc = 0.9085 (288/317)   ← ft3
saved -> /workspace/models/dspark-stage10/model_ascend_ft3.safetensors
```

磁盘产物：`model_ascend_ft{,1ep,2,3}.safetensors`（各 4.35GB）+
对应 BF16/量化 GGUF（`dspark_stage10-draft-ascendft*{-q8mixed-C,}.gguf`）。

### 2.3 三个结论（这条线真正的产出）

1. **瓶颈是数据量，不是推训漂移**——draft 本就适配特征分布；「扩到 500–1000+
   rollouts」的结论直接催生 B300 主线用 4197 样本 hidden-cache 的设计。
2. **acceptance 测量必须带 chat template**：裸 prompt 下 target 落入回声循环
   （无限复读指令），draft 轻松预测复读周期 → 旧「图像 40-73%」全是假象；
   ChatML 包裹后真实基线 16-22%。
3. **多帧输入两大根修**：帧抽取必须原生分辨率（`scale=448:448` 拉伸→embedding
   坏）；media embd decode 在 KV≥768 必须 batch≤16（否则腐蚀 KV）。

ft3 的 acceptance / 加速实测（文本域 19.0%、15帧 MM 17.857%、k=2 1.87×）
见 [dspark-910c-inference.md](dspark-910c-inference.md)。

## 3. 两链合流

```
HF stage10 (f69c1967f760) ──warmstart──► B300 DP8 ×150 步 ──► stage11 step_150 (4.4GB)
                                                                    │ swap+方案C量化
910C: rollout_dump/train_ascend.py 微调 ──► 方法论三结论 ──► 1.85GB 提交资产
（数据量结论指导 B300 数据规模；         acceptance/多帧测量口径）
```

项目总览里的串接见 [01-overview.md](01-overview.md)。
