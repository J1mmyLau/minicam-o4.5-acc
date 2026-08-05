# RTF Parser Audit — Official SPEAK→WAV Comparability

> 审计对象: `submission/scripts/analyze_chunk_rtf.py`
> 审计日期: 2026-08-05
> 官方指标: SPEAK 生成阶段的 SPEAK→WAV 完整链路 RTF (baseline: 1.087)

---

## 审计结论

| 维度 | 当前值 | 官方要求 | 可比? |
|------|--------|---------|-------|
| 计时链 | Flow + Vocoder (T2W 线程) | Main LLM → Talker → TTS → T2W → Flow → Vocoder | ❌ |
| 计时起点 | T2W 线程内部 | SPEAK 生成阶段开始 | ❌ |
| 计时终点 | WAV 文件写入 | WAV chunk 可用 | ⚠️ 接近但不完全对齐 |
| 阶段分类 | 无 (仅按 chunk 位置: first/middle/final) | LISTEN / SPEAK_GENERATION / SPEAK_TAIL | ❌ |
| RTF 分子 | `infer_ms` (T2W 线程日志行) | SPEAK→WAV 完整链路耗时 | ❌ |
| RTF 分母 | `audio_duration_ms` (从 sample count 推算) | audio chunk duration (官方口径) | ⚠️ 需确认 |
| 聚合方式 | mean/p50/p90/p95/p99/max | 官方未完全说明 | ⚠️ |
| 排除规则 | INTERNAL_VALIDATION_POLICY (10 项) | 官方未说明 | ⚠️ |

**OFFICIAL_COMPARABILITY = NO**

---

## 详细分析

### 1. 计时链范围

当前 parser 解析的日志行:
```
T2W线程: wav_1002.wav | 1.00s audio | 232.4ms inference | RTF=0.23 | t=1744ms | queue_wait=110.5ms | req=1 gen=1
```

`inference` = T2W 线程内部的 Flow+Vocoder 计算时间。
**不包含**: Main LLM (SPEAK 阶段)、Talker、TTS token 生成、T2W queue 等待、同步开销。

### 2. 阶段分类

当前分组: `first_chunk` / `middle_chunk` / `final_chunk` (按 chunk 在请求内的位置顺序)。

**不区分**: LISTEN / SPEAK_GENERATION / SPEAK_TAIL。

first_chunk 可能对应 LISTEN 或 SPEAK 生成，middle_chunk 无法判断是否在 SPEAK 生成阶段内。
SPEAK 尾部 chunk 会被错误地归入 middle/final。

### 3. 与官方 1.087 的关系

官方 1.087 = SPEAK→WAV 完整链路 RTF（平均每 chunk 1087.3ms，F16，单并发）。

当前 parser 输出的 RTF（典型值 ~0.23-0.28）仅覆盖 T2W 内部，**与官方 1.087 完全不同的测量对象**。

parser 的 0.23 = Flow+Vocoder 耗时 / audio 时长
官方的 1.087 = 完整 SPEAK→WAV 链路耗时 / audio 时长

**两者不能直接比较，不能写成 "优化到 0.23 vs baseline 1.087"。**

---

## 最小修复方案

### 在不修改冻结源码的前提下:

1. **SPEAK 状态识别**: 需在服务器日志中增加运行时标记 (SPEAK_START / SPEAK_END / WAV_EMIT)，在 parser 侧据此分类
2. **完整链路计时**: 需记录 SPEAK 阶段开始到 WAV 可用的 wall-clock 时间
3. **Parser 升级**: 增加 `speak_state` 字段，按 SPEAK_GENERATION 过滤汇总

### 如果现有日志不足以识别 SPEAK 状态:

```
SPEAK_STATE_CLASSIFICATION = BLOCKED_BY_RUNTIME_MARKERS
```

最小需要新增的日志事件:
- `SPEAK_GENERATION_BEGIN req=N gen=N t=XXXms` — LLM 进入 SPEAK 生成
- `SPEAK_GENERATION_END req=N gen=N t=XXXms` — LLM 结束，进入尾部
- 每行 WAV chunk 增加 `speak_state=LISTEN|SPEAK_GENERATION|SPEAK_TAIL`

在验证性能影响前，不得修改冻结源码 bdd4550。

---

## 当前 parser 的可用输出

虽然不能与官方 1.087 比较，当前 parser 仍可用于:
- 内部 T2W 阶段一致性检查 (baseline vs candidate A/B)
- valid_audio 判定和排除原因统计
- chunk 时间序列排序和单调性验证
- drain 完整性验证

所有输出已标记 `VALIDATION_POLICY=INTERNAL_VALIDATION_POLICY`。

---

## 下一步

1. 等待官方 RTF harness / Starter Kit 提供 SPEAK 阶段识别方法
2. 或在不影响性能的前提下，通过 harness 侧记录 SPEAK 状态事件
3. 升级 parser 支持三状态分类和完整链路 RTF 计算
