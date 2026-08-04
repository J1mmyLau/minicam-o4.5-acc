# 实验模板（Run Manifest / Per-request 记录 / 决策记录 / 配对 A/B 清单）

> 每次实验**必须**用模板记录。模板的目的是：任何结论都能被复核（样本数、配对方式、CI95、来源路径），任何 run 都能被复现（版本、命令、环境全部 SHA 化）。
> 引用位置：执行计划「通用前置」、交接包 §6、主指南 §9.2。

---

## 1. Run Manifest（每次 run 一栏）

```markdown
## Run {run_id}

- date: {YYYY-MM-DD}
- host: {主机}
- NPU 拓扑: {如 1× Ascend 910C dual-die}
- CANN: {9.1.0-beta.1}
- driver: {版本}
- image: {镜像 tag}
- branch: {vllm-omni 分支}
- HEAD: {commit}
- deploy YAML: {文件名 + SHA}
- model / revision: {OpenBMB/MiniCPM-o-4_5 @ {revision}}
- env vars: {如 VLLM_WORKER_MULTIPROC_METHOD=spawn}
- server command: {完整命令}
- benchmark command: {完整命令}
- 二进制/SHA: {若有}
- 备注: {环境特殊性}
```

用途：比较不同 run 前先核对 manifest，防止旧进程/旧版本/旧结果污染。

---

## 2. Per-request 记录（每个实验请求一行）

```markdown
| run_id | request_id | 类型(text/audio/av) | mode(stream/non) | T0 | T1 | ... | T15 | in_len | out_len | HTTP | 字段完整 | WAV 有效 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r001 | q001 | audio | non | 0 | 2 | ... | 4700 | 120 | 800 | 200 | yes | yes |
```

- T0–T15 见主指南 §9.1；每事件带 `request_id/stage_id/worker_id/pid/device/timestamp`。
- 聚合口径：p50 / p90 / p95 / CI95；样本数 = 行数。

---

## 3. 决策记录（每个 A/B 或 Gate 一条）

```markdown
## DECISION {D-编号}

- 假设: {一句话，可证伪}
- 实验: {V3 / V4 / ... 引用执行计划阶段}
- run_id: {关联 Run Manifest}
- 样本数: {30 对 / 32 对 / ...}
- 配对方式: {strict matched: 同服务同模型同输入同采样}
- 指标: {p50/p95，如 W0 4798→894ms}
- CI95: {如 [−4220, −3732]}
- 结论: {OPTIMIZE / VERIFY_FIRST / PROFILE_FIRST / DEFER / REJECT_BY_AMDAHL / NOT_APPLICABLE / QUALITY_RISK}
- 依据: {证据文件路径}
- 回滚方法: {怎么回退}
- 日期 / by: {2026-08-04 / name}
```

---

## 4. 配对 A/B 检查清单（做 A/B 前后逐项打勾）

```text
□ 同服务实例（同一进程，端口一致，无旧进程占用）
□ 同模型权重 + 同 revision
□ 同输入（同 prompt / 同参考音频 / 同 TTS template）
□ 同采样（greedy 或固定 temp/seed；官方 benchmark 用 greedy/temp 0）
□ 同负载条件（无并发干扰、无其它 NPU 任务）
□ 配对方式 strict：A 与 B 一一对应
□ 样本数 ≥ 10 对（优化结论 ≥ 30 对）
□ 统计：p50/p95 + CI95（优化结论必须 CI95 不跨 0）
□ 结果带 run_id + 数据文件路径
□ 负结果也记录（防重复踩）
□ 内部结果 ≠ 官方结果（状态标签不混用）
```

---

## 5. 常见错误

| 错误 | 正确 |
|---|---|
| 样本 < 10 对下结论 | 至少 10 对；优化 ≥ 30 对 |
| 报"Hit"不报端到端 | 端到端 TTFT / audio TTFP 必须测 |
| 阶段收益当端到端收益 | 分开展示，明确是阶段口径 |
| 不配对直接比均值 | 配对 + CI95 |
| 旧进程结果当新版本结果 | 起服前核对 run manifest + kill 旧进程 |
| profiler 解析失败当代码问题 | 先换输出目录（本地盘），再走注入路径 |
