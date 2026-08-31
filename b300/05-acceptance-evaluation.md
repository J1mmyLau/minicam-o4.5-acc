# B300 · acceptance evaluation — stage10 vs stage11 A/B

**问题**：stage11 训练是否真的提升了 draft 质量？比较是否公平？

**证据**（B300 机）：
- `/ssd2/minicpmo-dspark/logs/eval_stage10.log`、`eval_stage11.log`（两次评估原始日志）
- `logs/eval_compare.log`（identity 断言 + 最终对比表，:1-24）
- `eval/stage10_vs_stage11/`（comparison / summary / per-sample JSONL）
- 适配封装：`/root/b300_minicpmo_dp8/assets/eval_accept_compare.py`（只覆写 build_models）、
  `assets/compare_eval.py`（输入 identity 与指标比较）

## 评测协议

| 项 | 值 |
|---|---|
| 任务 | gsm8k:200 + humaneval:164 + mt-bench:80 + alpaca:200 = **644 samples** |
| 生成参数 | seed 980406，temperature 1.0，max_new_tokens 256，DP8（world_size 8） |
| **identity 断言** | 两 checkpoint 的**逐样本 prompt sha256 多重集相等**（同题同序，比较公平的前提） |
| 共享 | 同一 target / tokenizer / generation config / 评估器（acceptance 公式未改） |

## 结果（eval_compare.log:7-21）

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
| proposals | 32334 | 29243 | 结果非损失（见下） |

分数据集 accept_len（stage11）：gsm8k **5.30** / humaneval 4.37 / mt-bench 2.84 / alpaca 2.72。

## 读法（三条，防过度解读）

1. **提升集中在 block 后部**（@4/@5/@6 各 +0.07~0.09），@0 几乎不变——
   这是「多接受几个 token」的能力提升，不是首 token 分布改变。
2. `proposals` 下降是**结果**：接受更长，同 token 预算需要的轮次更少。
3. **口径边界（结项包原文）**：这是文本域 speculative decoding 评估，
   **不应扩展解读为多模态输入效果，也不等于已完成 speedup parity**。
   多模态 held-out 需 evaluator 支持 inputs_embeds，未做。
   实测吞吐加速在 910C 侧单独测（k=2→1.87×）。

## confidence 指标的名称映射

上游 eval 期输出 per-position `ece / auc / brier / pred_mean / target_mean`；
本表把 ECE 映射为 abs_error、`pred_mean − target_mean` 映射为 bias
（按 total_weight 加权）。公式没自创，但这层对应关系是本项目定的。
