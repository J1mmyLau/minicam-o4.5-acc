# perf/exp005-v3b-persistent-worker — Async Vocoder Pipeline

> 实验分支：persistent worker 模式下的异步 vocoder pipeline 优化。
> 将 vocoder 推理与下一个 encoder+flow 计算 overlap，隐藏 vocoder 延迟。

## 分支目的

探索 persistent worker 架构下，vocoder 与其他 pipeline stage 的 overlap 优化空间。
核心思路：vocoder 推理（CPU/CANN）与下一个 chunk 的 encoder+flow 计算并行执行。

## 实验方法

- Async vocoder pipeline：vocoder 推理异步化，与 encoder+flow overlap
- Persistent worker 生命周期管理
- Per-chunk pipeline stage 时间分解

## 状态

实验阶段。核心 overlap 收益需要在稳定 worker 生命周期基础上测量。
该优化的有效性能取决于 vocoder 延迟占总 pipeline 的比例（当前 CANN GPU vocoder 已大幅降低）。

## 与前后分支的关系

```
fix/tts-thread-lifecycle            ← 稳定性修复
perf/exp005-v3b-persistent-worker    ← 本分支：async vocoder    [← YOU ARE HERE]
perf/f6-decode-to-speak             ← 主性能优化（吸收了本分支的结论）
release/final-integration           ← 最终集成
```

## 详细推进记录

完整的时间线和每阶段累积进展见 [主分支 README（推进全记录）](../../main/README.md)。

---

> 分支标签：`EXPERIMENTAL` | 状态：`EXPLORATORY`
