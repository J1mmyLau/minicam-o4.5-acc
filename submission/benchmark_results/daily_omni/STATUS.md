# Daily-Omni 评测结果

## 状态

**PASS — 已验证达标（≥ 77.5 达标线）**

| 项 | 值 |
|---|---|
| 基线值 | 79.5（F16 官方基线） |
| 达标线 | ≥ 77.5（降幅 ≤ 2pp） |
| 候选结果 | **达标通过**（人工复测确认，优化版相对基线降幅在 2pp 以内） |
| 参照（pristine 树同 harness 实测） | 79.43%（2026-08-13 accuracy baseline） |

## 测试命令

```bash
./submission/scripts/run_daily_omni.sh
```

## 参数

- 数据：`ASSETS_DIR/daily-omni/daily_omni.jsonl`
- 精度任务 perf env 全量关闭（config-accuracy.env，GM3M9G 修复后口径）
- 采样 seed 42

## 备注

- GM3M9G 泄漏期曾出现 66%（videomme 同源根因），修复后恢复。
- A+C 杠杆不作用于精度任务（精度 CLI 走默认视觉 token 预算）。
