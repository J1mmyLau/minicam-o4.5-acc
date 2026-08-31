# B300 · Stage11 training — DP8 ×150 步

**问题**：从 stage10 warmstart 出发，在多模态 rollout 域上继续训练 draft。

**证据**（B300 机）：
- 配置入口：`/root/b300_minicpmo_dp8/assets/dspark_minicpmo_stage11_b300_dp8.py:21-49`
- **实际生效配置（以 checkpoint 自带为准）**：`step_150/train_config.py:52-67`
- 训练日志：`logs/d7_train150.log` / `train_stage11_b300_dp8_full.log`；
  逐 step 记录 `logs/report_full.log:4-164`
- smoke：`logs/d5_dp8_smoke.log` / `train_stage11_b300_dp8_smoke.log`
- 完成验证：`logs/d8_verify.log` / `verify_final.log`；
  `state/final_step`（**FINAL_STEP=150**）；`state/torch_compile_fallback`（**false**）

## warmstart（口径：不是 exact resume）

- stage11 从 stage10 Draft 权重 warmstart，**无 optimizer/scheduler 状态继承**，
  新建 optimizer 与 scheduler（`RESUME_SEMANTICS = WEIGHT_WARMSTART`）
- stage10 strict contract 独立过 gate：`logs/contract_gate_stage10.log`

## 训练配置（train_config.py:52-67）

```text
DP8（local batch 1 × 8 ranks × grad_accum 4 = global batch 32）
bf16   no_shard（纯 DP）   lr 3.0e-6   warmup_ratio 0.05
weight_decay 0.0   max_grad_norm 1.0   seed 42
max_train_steps 150   checkpointing every 25 steps
torch_compile true（fallback=false，实测未回退）
loss = ce 0.1 + l1 0.9（gamma 8.0）+ confidence_head 0.5
```

**停止条件与 epoch 的关系**：实际停止由 `max_train_steps=150` 驱动（优先于
num_train_epochs）。按 4197 samples / global batch 32 估算一个 epoch ≈ 131.2
steps，即**约 step 132 后进入第二个 epoch**——不是严格的「一轮数据训练」。

8 GPU 由启动器固定：`/root/b300_minicpmo_dp8/run.sh:84-95`（containerd/ctr，
data_root=/ssd2/minicpmo-dspark = 容器内 /pool/hdd/minicpmo-dspark，preflight free=3174GiB）。

## 框架钉死与补丁（进入训练前的准入）

- DeepSpec commit `ae6712019fb3880cedab918fb683d076e3cf15d6`（`state/deepspec_commit`）
- 对 transformers 4.51.0 做 **DEEP_IMPORT 全量检查 PASS**（17 个模块 ok，
  且验证 gemma4 guard **fails closed**——即守卫真在拦截，日志 `d6_full_cache.log`）
- 幂等补丁 marker（重复运行显示 already applied）：
  gemma4 guard（7 文件）、GradientCheckpointingLayer shim（2 文件）、base_trainer patch

## 逐步训练记录（report_full.log）

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

全部 metric 有限，无 NaN/Inf/OOM/NCCL 错误。同级目录另有 step_25/50/75/100/125。

**grad_norm 口径**：日志值约 234–640，显著高于 max_grad_norm=1.0。
**若**该字段对应 `clip_grad_norm_()` 返回的 pre-clipping norm（DeepSpec logger
的记录时点未在源码中核实），则这些 step 均触发了 gradient clipping。
由于 acceptance 最终改善，本项目未进一步修改该训练超参。

**无效历史记录**：早期 5-step 运行保留在 `logs/invalid_5step_record.txt`，
**不作为正式训练证据**；正式完成以 `state/final_step` + D8 独立检查为准。

## D8 完成验证

`model.safetensors` 可读、全 float tensor 有限；FINAL_STEP gate 独立重推 = 150；
校验对象是显式声明的 `step_150`，而非按 mtime 猜。
