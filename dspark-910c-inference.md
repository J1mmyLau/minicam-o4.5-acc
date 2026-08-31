# DSpark：910C 推理闭环（量化 → 接入 → 投机 A/B → RTS 判定）

> 训练侧见 [03-dspark-training.md](03-dspark-training.md)。本文是 910C 上
> 把 Draft artifact 变成可用推理资产、并给出投机解码判定 的完整链路：
>
> ```
> Draft artifact（B300 step_150 / 910C ft3）
> → GGUF/量化(1.85GB) → llama.cpp-omni 接入 → speculative decoding
> → runtime A/B（加速实测）→ RTS 双工 A/B（净负判定）→ E2E RTF
> ```

## 1. 量化（2.26GB → 1.85GB，方案 C）

**问题**：draft 体积需压到 1.8GB ± 0.1GB，且 acceptance 零损失。

**产物**：

| 文件 | 大小 | SHA256（前 16） |
|---|---|---|
| `dspark_stage11-draft-q8mixed-C.gguf` | **1,849,740,160 B（1.85GB）** | `11a70479e4a56aed…` |
| `dspark_stage11-draft.gguf`（BF16 参考） | 2,258,684,800 B | `0fe9051b6499f9de…` |

**方案 C 混合量化**（`scripts/quant_mixed_stage11_C.py`）：

- **Q8_0（15 张量）**：blk.0/blk.1 全部 7 个 linear + blk.2.ffn_down
- **保持 BF16**：blk.2–4 其余 linear、fc（20480→4096 条件主干）
- **保持 F32**：norms/biases
- **markov_w1/w2 不量化**：全 Q8 触发 `aclnn_mul` NZ-offset 段错误（实测否决）

Q8_0 严格遵循 ggml 语义：**roundf（half-away-from-zero，非 rint）**、scale `d`
存 fp16 RNE；量化器与 `llama-quantize` 在 stage10 控制组上做过**位级对拍**。

**验证（910C，F16 target）**：

| 项 | 结果 |
|---|---|
| BF16 vs Q8 acceptance | **三 prompt 逐位一致**：0.20833（10/48，mean 1.62）/ 0.38462（50/130，2.14）/ 0.50000（15/30，2.50） |
| 吞吐 | 47.8–75.2 t/s（Q8 与 BF16 持平） |
| 保真三重自证 | ①tensor 表/header 与 stage8 模板字节全等 ②4 张量 payload safetensors round-trip max_err=0 ③量化前后 acceptance 逐位一致 |

**转换链复现**：

```bash
# safetensors → BF16 GGUF：以 stage8 GGUF 为模板「原位换 payload」
# ⚠ 勿用 convert_*.py 全新写（丢 dspark 专有字段）
python3 scripts/swap_stage11_weights.py <model.safetensors> <outBF16.gguf>
python3 scripts/quant_mixed_stage11_C.py <outBF16.gguf> <outQ8.gguf>
```

布局要点：torch (out,in) 连续内存 = ggml mul_mat ne=(K,N) 原生布局，**不转置**；
校验比 numel 不比 shape 元组。

## 2. llama.cpp-omni 接入

**问题→决策**：上游 DSpark = DFlash 之上（非独立 arch）；converter 仅支持 Qwen3，
MiniCPM-o 走 `minicpmo` 路径需自写转换——词表手术（markov_w1/w2 切 151748 +
tokenizer 换血 + mask 151669 保留，`slice_draft_vocab.py`；MiniCPM-o 主干 =
arch qwen3、词表前缀 0–151668 同表）。

工程坑（全部实测撞过）：

- 双 die 必须 pin `ASCEND_RT_VISIBLE_DEVICES`
- **必须编 `llama-server` target**，否则 so 不更新
- 正确用法只有 `llama-server -md … --spec-type draft-dspark`；
  `llama-cli -p` 走内嵌 server + bad_alloc；`llama-speculative` example
  不填 20480 维条件张量，数字无效

**乱码三根因修**（spec-on 输出乱码 → 修后 KV 错误 12+ → 0）：

1. `dp.n_past` 用 `pos_last` 而非 `n_past` → KV 冲突
2. 多接受 token 只返回 `ids[0]` 其余静默丢弃 → 对齐上游 spec-simple
3. duplex 三漏：`eval_prefix` 漏门闩 / `eval_tokens_with_hidden` 缺钩子 /
   listen-flush 回卷不对齐

修后 duplex 26 步 first-pos accept 38%。

## 3. 投机加速实测（文本域，910C，ft3 checkpoint）

**问题**：draft 划不划算？早期按 draft≈target/6 推的「17% acceptance 盈亏线」对不对？

**实验**：k-sweep 三点拟合（text 域 46 token，贪心，三 k 输出逐字节一致 ✓）：

- **c_draft = 1.11 ms/token**（CANN 图捕获后，≈ target 的 1/28）
- V(batch 3..8) ≈ 30.9ms（verify batch 近似免费）

| 场景 | 加速 |
|---|---|
| **k=2** | **1.87×** |
| k=3 | 1.80× |
| k=7 | 1.75× |
| MM 15帧 | 48.1 vs 32.3 t/s ≈ **1.49×** |

**决策**：生产最优 k=2~3（acceptance 19% 时 k 大反而略慢）；
**「17% 盈亏线」被实测推翻**——真实盈亏由 c_draft/V(batch) 决定。

## 4. RTS 双工 A/B：净负，坐实关闭（2026-08-31，stage11-q8 draft）

**问题**：文本域净正 ≠ RTS 双工净正——双工每 chunk 只解码 5-9 token，
draft 前向+验证 batch 摊不平，且 chunk 间 KV 同步有税。

**实验装置（可复用）**：omni-tilelang-opt 的 judge-final 客户端跨树评 dspark：

```bash
python run_judge_direct.py \
  --llamacpp-root /workspace/llama-cpp-upstream-dspark --gpu 0
OMNI_SERVER_BIN=./scripts/dspark_rts_server_ab.sh   # wrapper 注入 draft
```

**⚠ 开关是 env 不是 CLI**：dspark 树双工投机走 `OMNI_SPEC_DRAFT=<gguf>`
（默认 off，n_max=3/n_min=0）。`-md/--spec-type draft-dspark` 会被 arg 解析
接受但 **omni_init 完全不消费**——传了等于没传（判别法：server 日志找
`=== omni_init: loading DSpark draft model`）。

**结果**（同视频 120s 全程，同树同 binary；两树绝对值不可比，只看相对量）：

| 项 | A 无 draft | B draft on |
|---|---|---|
| core RTF | 3.979 | **4.460（+12%）** |
| llm_decode | 0.132 | **0.338（2.56× 慢）** |
| SPEAK 文本 | 连贯成句 | 碎裂（segs 减半） |

**决策**：

- RTS 主提交**不挂 draft**（净负且伤输出质量，与数学结论一致：decode 占
  RTF 13% → 增益封顶 6.5%，需 2.4× 才到 0.45）
- DSpark 交付定位 = **量化模型资产 + 文本域投机（k=2 1.87×）**
- RTF≤0.45 只能靠 Talker 侧（见 [02-rts-optimization.md](02-rts-optimization.md) §9）

两树无公共祖先（bench-huawei=June 基 / upstream-dspark=Aug 孤儿 squash +
dflash 全套），禁止 cherry-pick 互搬（dflash 依赖 Aug 内存系统
ctx_other/mem_other 跨上下文 KV）。
