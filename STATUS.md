# F6 项目状态 — 2026-08-10 (收口)

## 当前状态: 🟡 FROZEN — 等待官方统一测评分支

官方 organizer 确认明天上午提供统一测评分支。当前所有 Cookbook/自定义 evaluator accuracy 结果不作为最终官方成绩。

## 进度矩阵

```
FROZEN_CANDIDATE_051e993
├─ Phase A: F16 校准          ✅ COMPLETE
├─ Phase B: Q8_0 A/B          ✅ COMPLETE (Q8_0 慢于 F16)
├─ Phase C: W8A8 量化 MatMul  ✅ COMPLETE (ROUTE A: F16 主力)
├─ Phase 1: 性能优化          ✅ COMPLETE (RTF=0.452)
├─ Phase 2: 稳定性            ✅ COMPLETE (50-reuse + 100-soak)
├─ Phase 3: Demo 路径         ✅ COMPLETE (Text 30/30, Audio valid)
├─ Phase 4: 最终收口          ✅ COMPLETE (Gate 表 + 文档)
├─ Phase 5: Accuracy          🟡 FROZEN (等官方统一分支)
└─ READY                      ❌ NOT_UNTIL_OFFICIAL_ACCURACY
```

## 关键指标 (F16, 051e993)

| 指标 | 值 |
|------|-----|
| SPEAK→WAV RTF | 0.452 (LOCAL_BEST_EFFORT) |
| Prefill latency (KV hit) | 85ms p50 |
| Decode→speak latency | ~142ms (2.9%) |
| T2W latency (pipeline) | ~375ms/window |
| Session reuse | 50/50 PASS |
| Long soak | 100/100 PASS |
| Demo Text gate | 30/30 valid |
| Demo Audio gate | WAV output valid |

## 已知 Bug (P0, 未修复)

| Bug | 根因 | 修复状态 |
|-----|------|---------|
| WS 多模态 NaN | mel 预处理 160/2400 NaN | 已追踪，等官方分支验证后决定是否修 |
| Q8_0 contiguous-y | [4096,17] multi-token → CANN 算子限制 | 已复现，等官方分支验证后决定是否修 |

## 明天行动

1. 拉官方统一测评分支 → 记录 commit SHA
2. 跑 F16 accuracy (基准)
3. 跑 Q8_0 accuracy
4. 重新评估: Daily-Omni / VideoMME / TTS-Seed / NaN / Q8 contiguous-y
5. 只有官方分支上复现的 bug 才是提交阻塞项

---

> 基线: 051e993 | 分支: main | 状态: `WAIT_OFFICIAL_UNIFIED_EVAL_BRANCH`
