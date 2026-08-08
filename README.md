# eval/official-baseline — Official Evaluation Baseline

> 官方评测基线分支。基于上游 `llama.cpp-omni` commit `6a7718e`，
> 按比赛环境要求完成 F16 模型的初始部署和基准测量。

## 分支目的

建立 F16 全模态模型在 Ascend 910C 上的可运行基线，确认初始性能水平，
作为后续所有优化的比较参照点。

## 包含内容

- 官方 8 步评测序列计划（test/eval）
- 初始 RTF 基准测量
- F-003 CANN RoPE bug (`aclnnRepeatInterleave` crash) 的发现和记录
- T2W CPU 瓶颈的首次确认（4261ms，占总 wall clock 的 99%）

## 关键发现

1. **CANN RoPE 崩溃**：`tts_gpu_layers=99` 在 TTS prefill 阶段 SIGABRT，
   根因是 `aclnnRepeatInterleave` 在 `ggml_cann_rope` 中的错误。
   临时 workaround：`tts_gpu_layers=0`（TTS on CPU）。

2. **T2W CPU 瓶颈**：Flow Matching + Vocoder 全在 CPU，
   T2W 耗时 4261ms 占总耗时 99%。

3. **F16 on CPU TTS = broken**：`tts_gpu_layers=0` workaround 导致
   F16 TTS embedding zero-norm，音频质量归零。

## 与后续分支的关系

```
eval/official-baseline (6a7718e)   ← 本分支：基线
        ↓
ecee7de (CANN RoPE fix)            ← 修复 RoPE crash，GPU TTS 可用
        ↓
fix/tts-thread-lifecycle           ← WS 生命周期修复
        ↓
perf/f6-decode-to-speak            ← 性能优化
        ↓
release/final-integration          ← 最终集成
```

## 详细推进记录

完整的时间线和每阶段累积进展见 [主分支 README（推进全记录）](../../main/README.md)。

---

> 分支标签：`BASELINE_REFERENCE` | 状态：`FROZEN`
