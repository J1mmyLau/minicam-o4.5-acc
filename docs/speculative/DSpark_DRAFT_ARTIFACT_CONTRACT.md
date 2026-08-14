# DSpark Draft Artifact 契约（teammate 训练产物接入合同）

> 目的：在写任何 runtime 代码之前，先把「队友训好的 draft 到底是什么、能否直接转上游 DSpark GGUF」钉死。
> 状态：**队友 checkpoint 当前不在本机**（已全盘搜索 `/workspace /data /mnt /root`，无 DSpark/draft 产物）。
> 因此本文件是**契约模板 + 已填的 target 侧事实**，draft 侧字段留 `NOT_AVAILABLE`，待队友提供后回填。

---

## 1. Draft 侧字段（待队友回填）

```text
DRAFT_FORMAT           = NOT_AVAILABLE   # HF / safetensors / custom?
TARGET_MODEL           = MiniCPM-o-4_5   # 主 LLM（Thinker）? 还是 Talker?
TARGET_COMMIT/BASE     = NOT_AVAILABLE   # 训练时挂载的 base model / commit
TOKENIZER_MATCH        = NOT_AVAILABLE   # 与 target tokenizer 是否一致（必须一致，否则 draft logits 维度错）
VOCAB_SIZE             = NOT_AVAILABLE   # 期望 == 151748（target）
HIDDEN_SIZE            = NOT_AVAILABLE   # 期望 == 4096（target），或 draft 自己的小 hidden
BLOCK_SIZE / GAMMA     = NOT_AVAILABLE   # dflash.block_size，训练时定死的 γ
MARKOV_RANK            = NOT_AVAILABLE   # markov W1/W2 的 rank r
MASK_TOKEN_ID          = NOT_AVAILABLE   # draft 输出里的 MASK 语义
CONFIDENCE_HEAD        = NOT_AVAILABLE   # 有无 confidence proj 头
WEIGHT_NAMES           = NOT_AVAILABLE   # safetensors 里的键名清单
TRAINING_FRAMEWORK     = NOT_AVAILABLE   # SGLang / DeepSpec / custom
```

## 2. Target 侧事实（本机已核实）

| 字段 | 值 | 来源 |
|---|---|---|
| model_type | `minicpmo`（MiniCPM-o 4.5） | `config.json` |
| vocab_size | **151748** | `config.json` |
| hidden_size | **4096** | `config.json` |
| num_hidden_layers | **36** | `config.json` |
| num_attention_heads | **32** | `config.json` |
| num_key_value_heads | **8** | `config.json` |
| intermediate_size | **12288** | `config.json` |
| max_position_embeddings | **40960** | `config.json` |
| tie_word_embeddings | **False** | `config.json` |
| GGUF (F16) | `/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf` (16.4 GB) | 磁盘 |

> 主 LLM 是 Qwen 系（4096/36L/32h/8kv），与 `f6-cross-stage-npu-profile` 的 profiler 观测一致。

## 3. 核心问题

```
Can teammate draft → convert directly to upstream DSpark GGUF?
```

在 draft 侧字段回填前无法判定。判定的充分条件（三条都要）：

1. `TOKENIZER_MATCH = YES` 且 `VOCAB_SIZE == 151748`（否则 draft 的 token head 维度错，不可直接接）。
2. draft 权重可映射到上游 DSpark 的 4 类张量：`dspark_markov_w1`、`dspark_markov_w2`、`dspark_conf_proj`、DFlash backbone（`dflash.block_size` 元数据）。
3. `BLOCK_SIZE/GAMMA` 与运行时 `--spec-draft-n-max` 一致（训练定死 γ，运行时不能超过）。

> **禁止** 在映射文档写清楚之前静默 reshape / rename 权重。

## 4. GGUF 转换计划（若 llama.cpp 路径需要 GGUF）

上游 `convert_hf_to_gguf.py` 对 DSpark 的支持（待从上游 diff 确认）。预期 HF→GGUF 张量映射：

```
HF tensor                          →  GGUF tensor
draft.markov.w1  [rank, hidden]    →  dspark_markov_w1
draft.markov.w2  [vocab, rank]     →  dspark_markov_w2
draft.conf.proj  [1, hidden]       →  dspark_conf_proj
draft.backbone.* (DFlash)          →  blk.*.attn_q/w/k/v/o + ffn（复用 target 命名空间）
metadata: block_size                →  dflash.block_size
```

**必过 Gate**（在任何 speculate 集成之前）：

```
HF_DRAFT_OUTPUT  ≈  GGUF_DRAFT_OUTPUT
```

在固定 hidden-state / token 输入上，两套输出的 logits 逐位一致（容差按 F16 数值）。

## 5. 若不能直接转上游 DSpark GGUF

写一个独立 converter 计划（不是 runtime 里硬塞），明确：

1. 权重命名重映射表（HF key → GGUF key，逐条）。
2. 形状 reshape 依据（哪些是 [in,out] vs [out,in] 转置）。
3. 元数据注入（block_size / gamma / rank / mask_token_id）。
4. 数值校验脚本（HF vs GGUF 前向对比）。

---

## 6. 队友需提供的最小信息（阻塞解除条件）

- draft checkpoint 路径（或 tar/safetensors）+ 训练框架（SGLang/DeepSpec/custom）。
- `config.json`（draft 结构：hidden/layers/heads/vocab/block_size/markov_rank）。
- 训练时挂载的 base model + commit。
- 一个固定输入的 golden 输出（用于 GGUF 转换校验）。

**在拿到这些之前，`TEAMMATE_DRAFT_COMPATIBILITY = NOT_AVAILABLE`，DSpark runtime 集成停在 backport + 架构层。**
