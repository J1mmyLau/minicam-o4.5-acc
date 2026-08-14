# 性能现状 — MiniCPM-o 4.5 昇腾赛道（候选 `fd3dd36`）

> 更新：2026-08-14 · 环境：1× Ascend 910C（dual-die）+ CANN 9.1.0-beta.1 · 模型：MiniCPM-o-4_5-F16.gguf
> 数据源：`docs/competition-submission/RESULTS.md` + `OPTIMIZATIONS.md`（权威）；本页为**现状速览**。

**一句话结论**：精度 4/4 全 PASS（准入达标）；官方 RTF 是 **parity**（1.09–1.17 vs 基线 1.087），**没有已证实的加速**。

---

## 1. 精度（四项指标，准入线，全 PASS）

| 指标 | 候选 | 官方基线 | 验收线 | 判定 |
|---|---|---|---|---|
| Daily-Omni ↑ | **79.43%**（950/1196） | 79.5 | ≥ 77.5 | ✅ +1.93pp |
| Video-MME ↑ | **69.8%** | 69.0 | ≥ 67.0 | ✅ +2.8pp |
| Seed-TTS WER ↓ | **1.422%**（2020/2020） | 1.414 | ≤ 1.56 | ✅ |
| Seed-TTS SIM/ASV ↑ | **0.969**（2020/2020） | 0.709 | ≥ 0.689 | ✅ |

> TTS-Seed 是**两项**指标（ASV 绝对下降 ≤0.02 + WER 相对增幅 ≤10%），总指标 = 4 项（三个 Benchmark）。

## 2. 官方 SPEAK→WAV RTF（排名依据）

| 口径 | 值 |
|---|---|
| core.rtf_aggregate | **1.09 – 1.17** |
| 官方基线 | **1.087** |
| 相对基线 | **无已证实加速**（parity 区间） |

> ⚠️ **诚实口径**：RTF 只是「可用、能测出来」（LISTEN-wedge 修复后 n_speak 0→33、0 拒绝），
> 但**没有赢过基线**。谁要把这个数报成"加速了 X%"，都是错的。

## 3. 本地优化收益（真实，但**不是** official RTF）

这些是**本地配对 A/B 的 wall-clock 改善**，不能当 official RTF 写：

| 优化 | 收益 |
|---|---|
| T2W 上 CANN（`cann-flow-only`） | W0 p50 4798→894ms（**−81.4%**） |
| Flow∥Vocoder 流水线 | 601→375ms/window（**1.60×**） |
| KV Cache 静态前缀 | prefill 206→85ms（**2.4×**） |
| Config D（整体 wall） | ~**−18%** |

## 4. 稳定性

| 项 | 结果 |
|---|---|
| RTS soak | 2× 运行，**0 崩溃、0 线程泄漏** |
| 二进制可复现 | 重建 SHA 逐字节一致（PASS） |
| 已知负面 | SPEAK turn 楔死（候选级边界，非 Config D，未解、不在官方 RTS 路径） |

## 5. 定位与结论

- **正确性优先**：先修 NaN / WER=100% / 生命周期楔死，再做性能——精度 4/4 PASS 是准入前提。
- **性能定位 = parity 交付**：把 T2W 从 CPU 搬上 NPU 本地快 81%，但官方口径（SPEAK→WAV 完整链路）下
  没体现成相对基线的加速，最终是「无性能回退的 parity」，不是「性能大杀器」。
- **官方 RTF 无加速的诚实原因**：官方 harness 的计时链（Main LLM→Talker→TTS→T2W→Flow→Vocoder）
  与本地 A/B 的计时对象不同；本地 wall 改善没有映射到 official RTF 指标。

## 6. 权威数据源

- [`docs/competition-submission/RESULTS.md`](docs/competition-submission/RESULTS.md) — 精度 + RTF + 稳定性
- [`docs/competition-submission/OPTIMIZATIONS.md`](docs/competition-submission/OPTIMIZATIONS.md) — 优化清单 + 本地 A/B
- [`docs/competition-submission/OFFICIAL_GATE_STATUS.md`](docs/competition-submission/OFFICIAL_GATE_STATUS.md) — Gate 状态
- 数据可视化：`submission/performance/charts/`（accuracy / t2w_iteration / w0_breakdown / rtf_parity）
