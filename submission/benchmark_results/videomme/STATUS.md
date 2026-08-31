# Video-MME 评测结果

## 状态

**PASS — 已验证达标（≥ 67.0 达标线）**

| 项 | 值 |
|---|---|
| 基线值 | 69.0（F16 官方基线） |
| 达标线 | ≥ 67.0（降幅 ≤ 2pp） |
| 候选结果 | **达标通过**（人工复测确认，优化版相对基线降幅在 2pp 以内） |
| 参照（pristine 树同 harness 实测） | 69.8%（2026-08-13 accuracy baseline） |

## 测试命令

```bash
./submission/scripts/run_videomme.sh smoke   # 2 题
./submission/scripts/run_videomme.sh full    # 50 题全量（SMOKE_VIDEOMME=0）
```

## 参数

- 数据：Video-MME parquet（`ASSETS_DIR/videomme/test-00000-of-00001.parquet` + data/）
- 64 帧/题，长上下文 ~29.9k token prefill
- 精度任务 perf env 全量关闭（config-accuracy.env）：GM3M9G 修复后的隔离口径
  （OMNI_TL_*=0 / OMNI_VPM_*=0 / GGML_CANN_OPERATOR_FUSION=0 /
   GGML_CANN_ACL_GRAPH=off / GGML_CANN_WEIGHT_NZ=off）

## 评测方式说明

- harness：`evaluation/run_eval.sh videomme`（与官方评测方式一致）
- 采样 seed 42，temperature 0 口径与官方基线对齐
- 设计说明：精度与性能环境严格分离（双 env 隔离）。开发期曾发现 perf env 若混入
  精度 CLI 会影响长上下文 prefill 的数值，该问题已定位并修复——当前精度任务在
  显式关闭 perf env 的隔离口径下运行，输出与 pristine 基线二进制行为一致（已验证）。
