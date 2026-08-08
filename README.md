# release/final-integration — Final Integration Release

> 最终集成发布分支。包含所有优化和修复的累积结果，以及 TTS CPU workaround
> 和比赛提交准备。

## 分支目的

将所有分支的修复和优化集成到单一发布版本中，准备比赛提交。

## 包含内容

### 所有累积修复

- ✅ CANN RoPE 正确性修复（F-003）
- ✅ `cann-flow-only` 平台支撑
- ✅ WS Session 生命周期修复
- ✅ 线程泄漏修复（libgomp OpenMP）
- ✅ Drain timeout 修复
- ✅ Per-generation active 计数
- ✅ TTS KV bounds guard

### 所有累积优化

- ✅ CANN T2W 迁移（−81.4% 首音延迟）
- ✅ Static Prefix KV Cache（2.4× prefill 加速）
- ✅ Q8_0 LLM 量化（+17.5% RTF 改善）
- ✅ 非流式 text 输出修复
- ✅ SSE crash 修复
- ✅ 多模态 prefill 协议修正

### TTS CPU Workaround

此分支包含 `tts_gpu_layers=0` workaround（TTS on CPU），用于 CANN 多设备算子注册
不完整的环境。这是 **F-003 规避方案**而非性能选择：
- 如果 RoPE fix 已生效（ecee7de+），应使用 `tts_gpu_layers=99`（GPU TTS）
- 如果 RoPE fix 未生效（6a7718e 及之前），需要此 workaround 但会损失 TTS 音频质量

### 比赛提交

- 提交骨架（30 份文件在 `submission/`）
- 官方 Gate 矩阵（`docs/competition-submission/OFFICIAL_GATE_MATRIX.md`）
- Demo Gate 检查表（`submission/demo/DEMO_GATE_CHECKLIST.md`）
- 提交检查表（`docs/competition-submission/SUBMISSION_CHECKLIST.md`）
- vLLM 迁移文档（10 份在 `docs/vllm-migration/`）

## 官方 Gate 状态

```
FINAL_INTERNAL                       = PASS
REPRODUCIBLE_BINARY                  = PASS
OFFICIAL_GATES                       = BLOCKED_BY_OFFICIAL_STARTER_KIT
COMPETITION_COMPLETE                 = NOT_CLAIMED
```

## 与前后分支的关系

```
eval/official-baseline              ← 基线
ecee7de (CANN RoPE fix)            ← GPU TTS 可用
fix/tts-thread-lifecycle            ← 稳定性修复
perf/f6-decode-to-speak             ← 性能优化
release/final-integration            ← 本分支：最终集成    [← YOU ARE HERE]
```

## 详细推进记录

完整的时间线和每阶段累积进展见 [主分支 README（推进全记录）](../../main/README.md)。

---

> 分支标签：`RELEASE_CANDIDATE` | 状态：`FROZEN_FOR_COMPETITION`
