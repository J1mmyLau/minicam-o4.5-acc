# B300 training_evidence — 索引（INDEX）

> 本目录是 **8×B300 stage11 训练主线的结项证据整理**。原文全部在 B300 训练机上，
> 数字以原始文件为准，本目录只做结构化转录（带 file:line 引用）。
> 910C 推理证据**单独归档**（见上级目录），本目录不含 910C parity/speedup 结论。

## 总链路

```
真实数据集下载/解压 → 四来源 JSONL → MiniCPM target rollout cache
→ Stage10 weight warmstart → Stage11 B300 DP8 训练 150 optimizer steps
→ step_150 checkpoint → Stage10/Stage11 acceptance 对比 → 推理文件导出
```

## 本目录结构（对应 PROJECT OVERVIEW 的 B300 支）

| 文档 | 对应节点 |
|---|---|
| [01-data.md](01-data.md) | **data**（三套真实数据集 → 4197 行 JSONL） |
| [02-target-cache.md](02-target-cache.md) | **target cache**（hidden-state cache 生成 + manifest + 读回验证） |
| [03-stage11-training.md](03-stage11-training.md) | **Stage11 training**（配置/DP8/门禁/日志） |
| [04-checkpoint.md](04-checkpoint.md) | **checkpoint**（step_150 内容/校验/导出） |
| [05-acceptance-evaluation.md](05-acceptance-evaluation.md) | **acceptance evaluation**（644 样本 A/B + 边界） |

## 结论（TRAINING_SUMMARY 原文口径）

stage11 在与 stage10 相同输入、target、tokenizer、生成参数和 DP8 评测条件下：

- **avg_accept_length: 3.4923 → 3.8620（+0.3697）**
- **overall_accept_rate: 0.4388 → 0.4854（+0.0466）**
- `STAGE11_IMPROVES_ACCEPTANCE = True`

**边界**：该结论仅覆盖本次 644 条**文本域**评测；不是多模态任务质量结论，
也不是端到端 wall-clock speedup 结论。原始证据：`/ssd2/minicpmo-dspark/logs/eval_compare.log`。

## D0–D9 证据索引（B300 机原始路径）

| Gate | 证据 |
|---|---|
| D0–D3 环境/框架/模型契约 | `/root/b300_minicpmo_dp8/run.sh`（containerd/ctr 启动器、8 GPU、/ssd2 挂载）；`/root/b300_minicpmo_dp8/scripts/pipeline.sh`（D0–D9 主流程与 gate）；`run_d4_d8.sh`（串行 controller + marker 失败闭环）；`/ssd2/minicpmo-dspark/logs/d6_full_cache.log:9-54`（环境预检、DeepSpec import、固定 commit）；`contract_gate_stage10.log`（stage10 strict contract）；`state/pip-constraints.txt`、`pip-check.txt`、`deepspec_commit` |
| D4 真实数据/JSONL | `logs/d4_jsonl.log`；`logs/build_dtriad_jsonl.log`（正式构建及来源计数）；正式 JSONL：`datasets/jsonl/dtriad_train.jsonl`（只引用不复制）；`state/jsonl.complete` |
| D4a–D6 cache | `logs/d4a_cache32.log`（32 行端到端 cache gate）；`logs/prepare_cache_minicpmo_dtriad3_media_fp16.log`；`logs/d6_full_cache.log`（4197 条进度与最终统计）；`cache/minicpmo_dtriad3_media_fp16/manifest.json`；`state/d4a.complete`、`d6.complete` |
| D5–D8 训练/checkpoint | `/root/b300_minicpmo_dp8/assets/dspark_minicpmo_stage11_b300_dp8.py:21-49`（配置入口）；`step_150/train_config.py:52-67`（实际训练配置）；`step_150/config.json:168-225`（Draft 架构）；`logs/d5_dp8_smoke.log`；`logs/d7_train150.log` / `train_stage11_b300_dp8_full.log`；`logs/report_full.log:4-164`（逐 step）；`logs/d8_verify.log` / `verify_final.log`；`state/final_step`（FINAL_STEP=150）；`state/torch_compile_fallback`（=false） |
| D9 评估 | `/root/b300_minicpmo_dp8/assets/eval_accept_compare.py`（适配封装）；`assets/compare_eval.py`（输入 identity 与指标比较）；`logs/eval_stage10.log`、`eval_stage11.log`；`logs/eval_compare.log`；`eval/stage10_vs_stage11/`（comparison/summary/per-sample JSONL） |
| 导出/校验 | `/root/submission/`（推理文件本地副本，不含 optimizer state）；`assets/push_stage11_to_hf.py`（只允许推理文件的上传清单）；`/root/dspark-minicpmo-4_5-stage11-step150.tar.gz`（3,782,289,212 B，sha256 `1db577531f1e5c3b2e2e457cfbdf06dc9cab0748f5cd8f8e78eae062e4972cae`） |

## 大文件边界

- cache 原目录（只引用）：`/ssd2/minicpmo-dspark/cache/minicpmo_dtriad3_media_fp16`
- checkpoint 原目录（只引用）：
  `/ssd2/minicpmo-dspark/home/checkpoints/deepspec/dspark_block7_minicpmo_4_5_multimodal_dtriad_stage11_b300_dp8/step_150`
- **8 份 optimizer state 保留在 checkpoint 原目录，不进入本证据包**

## 复核顺序（接手者按此走）

1. 读本 INDEX 确认每个事实的原始来源
2. 核对 `state/final_step`、`cache/.../manifest.json`、最终 `train_config.py`
3. 阅读 `d4_jsonl.log` → `d6_full_cache.log` → `report_full.log` → `d8_verify.log`
4. 阅读 `eval_compare.log`，确认输入 identity 与 acceptance 对比
5. 对 `/root/submission` 或 tarball 执行 checksum 与 safetensors 加载验证
