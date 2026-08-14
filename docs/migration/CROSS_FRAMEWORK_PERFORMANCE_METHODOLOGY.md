# 跨框架性能方法论（llama.cpp-omni ↔ vLLM-Omni）

> 目的：**框架无关**的 AI Infra 性能方法论。同一个实验，在两个框架下可比。
> 状态：方法论 + 指标口径，不依赖具体实现。

---

## 1. 核心信条

```
local stage speedup ≠ E2E speedup
```

本项目反复验证：
- Phase 7 flow ACL graph：flow p50 −20.4%，E2E +11% → 回滚。
- 单算子 W8A8 1.6×，E2E MUL_MAT 收益不传导到 wall。
- 「本地 benchmark 快」≠「SPEAK→WAV / RTF 快」。

**任何优化必须配对的 E2E A/B**，stage 级数字只能当诊断，不能当结论。

---

## 2. 指标口径（统一）

| 指标 | 定义 | 备注 |
|---|---|---|
| TTFT | 请求 → 第一个 token | 含 prefill |
| TPOT / ITL | token 间平均 / 分位时延 | decode 稳态 |
| TTFP | 请求 → 第一个音频 | Omni 特有，含 prefill + 首 chunk T2W |
| SPEAK→WAV | SPEAK 判定 → WAV 落盘 | 官方 RTF 的分子口径 |
| audio RTF | Σcompute / Σaudio | 官方 `rtf.core.rtf_aggregate` |
| throughput | token/s / req/s | 多并发点（C1/C2/C4/C8） |
| acceptance rate / accepted length | speculative 专属 | 见下 |
| HBM / CPU / NPU util | 资源 | msprof / nsys |

**必须同脚本同子集同分母**，否则 baseline/candidate 对比无效。

---

## 3. 分位 vs 均值

- 时延指标必须报 **p50 / p95 / p99**，不能只报 mean（本项目校准阶段发现 mean 被 outlier 污染）。
- 首 chunk / 尾 chunk 分开报（首 chunk 含 prefill，尾 chunk 含 drain，与稳态不同）。

---

## 4. Warmup / 冷启动

- 固定 warmup 次数，或 `warmup=0` 单独报冷启动。
- 本项目的经验：session 复用 + KV cache reuse 会让第 2 次起显著快于第 1 次，必须显式区分「冷/热」。

---

## 5. Speculative 专属

```
Spec gain ≈ saved_sequential_target_forwards − draft_forward_cost − verify_cost − scheduler/KV_overhead
```

- 高 acceptance ≠ E2E 加速（draft 成本可能吃掉收益）。
- 报 `TOKENS_PER_TARGET_FORWARD`（每 target 前向产出的 token 数）比 acceptance 更直接反映收益。
- 低 QPS 降时延 / 高并发损吞吐 —— 必须多并发点测。

---

## 6. 可比性五条

1. 同模型、同权重、同 dtype（迁移初期 F16/BF16 对齐）。
2. 同数据、同 prompt、同 seed。
3. 同指标口径（§2 表）。
4. 同 warmup/count/统计方法（分位）。
5. 资源归一（同 NPU 数、同 HBM 预算）。

---

## 7. 实验记录模板

```
run_id / framework / model / dtype / device / concurrency
warmup / count / seed
TTFT p50/p95 · TPOT p50/p95 · SPEAK→WAV p50/p95
audio RTF · throughput
acceptance (spec) · tokens_per_forward (spec)
HBM / util
异常（NaN / 溢出 / 上下文污染 / session 泄漏）
```

---

## 8. 可复用方法论清单（非 competition 专属）

- 冷/热分离 + KV 复用对时延的影响是**一等公民**，不是噪音。
- duplex/turn 边界的时延口径必须先于任何优化冻结（本项目曾因 timer 边界差异产生 +44%/+132% 的不可比数据）。
- 调度类优化（KV、pipeline overlap）比算子类优化更接近 E2E 收益 —— 但都要 E2E A/B 证明。
- 资源争用（CPU vocoder vs NPU）会抵消局部加速，必须测争用系数。
