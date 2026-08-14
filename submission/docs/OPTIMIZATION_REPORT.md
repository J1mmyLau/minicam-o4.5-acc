# 优化报告（提交物）

> 结构见 `docs/competition-submission/PERFORMANCE_REPORT_TEMPLATE.md`。最终落本文件。
> 候选冻结：`fd3dd36`（tag `competition-final-20260814`，Config D），见 `VERSION_MANIFEST.md`。

## 主线

```
MiniCPM-o 4.5 → Main LLM → Talker → Token2Wav → Flow → Vocoder → streaming audio
原始瓶颈：T2W CPU 设备放置 93%（decode→speak 仅 2.9%）
优化：静态前缀 KV Cache（prefill 2.4×）/ 生命周期 / CANN Flow/Vocoder（W0 −81.4%）
      / TTS KV bounds guard / 文本+SSE 接口修复 / FA NaN 修复（MAX_UBATCH=16）
```

## 精度结果（候选 + Config D，冻结基线对比）

| 基准 | 候选 | pristine 基线 | 验收 | 判定 |
|---|---|---|---|---|
| Daily-Omni | **79.43%**（950/1196） | 79.43% | ≥77.5% | **PASS** |
| VideoMME | **69.8%** | 69.8% | — | **PASS** |
| Seed-TTS ZH_WER | **1.422%**（2020/2020） | 1.5% | ≤1.56% | **PASS**（优于 pristine） |
| Seed-TTS SIM(ASV) | **0.969** | 0.97 | ≥0.689 | **PASS** |

Config D 零精度副作用（simplex Seed-TTS 保持 pristine NPU 路径）。证据：
`experiments/nightly/trackC_seedtts_full/summary_tts.json`（WER 1.422% / SIM 0.969 / 9941s）。

## 性能结果（RTF）

- 官方 SPEAK→WAV RTF = **core.rtf_aggregate 1.09–1.17（parity baseline 1.087）**。
  LISTEN-wedge 生命周期 bug 已修（`tools/omni/omni.cpp`，非受保护），n_speak 0→33，0 拒绝。
  见 `docs/F6_OFFICIAL_RTF_RESOLVED.md`。
- ⚠️ 诚实口径：RTF 可用但**无相对 baseline 1.087 的已证实加速**；Config D 的 ~18% wall 改善是
  本地配对 A/B（`docs/F6_*`），**不是** official RTF −18%。
- pristine 服务端 [bench] RTF 基线 = 1.083（official 1.087）。

## 待回填章节

- [ ] 2. 官方基线（统一评测分支数字，已到达；隐藏测试集公开后复核分母）
- [ ] 11. chunk RTF 正式结果（补 C++ 计时发射后重跑 RTS 得 rtf.core.rtf_aggregate）
- [x] 12. 精度结果（三条内部基线 PASS，见上）
- [ ] 13. Demo 稳定性（官方 Demo 接入后）
