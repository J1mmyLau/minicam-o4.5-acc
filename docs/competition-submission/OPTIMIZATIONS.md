# OPTIMIZATIONS — 优化说明（权威）

> 候选 `fd3dd36` 相对 pristine 基线 `c9785cc` 的**正确性修复 + 运行时优化**清单。
> 核心原则：**正确性优先**。所有「提速」前先修 NaN / WER=100% / 生命周期楔死。

## 1. 正确性修复（决定准确率能否达标，优先级最高）

| 修复 | 问题 | 影响 |
|---|---|---|
| FA mask 语义回归回滚（`b6b6af0`） | raw -Inf→pseShift、mask=nullptr vs pristine BOOL-mask+Clamp | 长多模态 logits→NaN，文本全 `?` |
| `OMNI_CANN_FA_MAX_UBATCH=16` workaround | CANN `aclnnMm` 有限输入→NaN（Q≥435、KV≥768 触发） | 唯一可靠 workaround，+5.3% 开销 |
| TTS 三污染源修复 | gf_enc 双重计算 / FA Q-split 默认 16 / ecee7de memcpy rope | Seed-TTS WER 1.5%→1.422%（不再 100%） |
| LISTEN-wedge 生命周期修复 | 空 duplex LISTEN chunk_end 未完成 drain 记账 → active_gen 楔死 → NOT_REUSABLE | RTF 可测，n_speak 0→33，0 拒绝 |

## 2. 运行时优化（Config D，零评测器改动注入）

Config D 是**纯环境变量注入**（不改 `evaluation/` + 4 保护工具），6 变量：

```text
OMNI_T2W_DEVICE=cann-flow-only   # Token2Wav flow-matching 走 CANN
OMNI_VOC_DEVICE=gpu:0            # Vocoder 走 CANN
OMNI_T2W_PIPELINE_OVERLAP=1      # Flow ∥ Vocoder 流水线
OMNI_CANN_FA_MAX_UBATCH=16       # 长多模态 NaN 保护
GGML_CANN_WEIGHT_NZ=off
GGML_CANN_ACL_GRAPH=off
```

### 本地配对 A/B（**不是 official RTF**）

| 项 | 结果 | 性质 |
|---|---|---|
| T2W W0（cann-flow-only） | −81.4%（4798→894ms p50） | 本地 A/B |
| Flow ∥ Vocoder 流水线 | 1.60×（601→375ms/window） | 本地 A/B |
| Config D wall（E2E） | ~−18% | 本地配对 A/B |

> ⚠️ 以上是**本地配对 A/B 的 wall 改善**。official RTF 口径下候选 = parity（1.09–1.17 vs baseline 1.087），
> **无已证实加速**。详见 `RESULTS.md` §2。

## 3. 尝试过但**未采用**的优化（诚实记录）

| 项 | 结论 |
|---|---|
| W8A8 量化（QuantMatmulV5） | V5 dead-end（无 int8×int8→fp16 kernel）；V3 1.27× 但 F16 路径更稳，未默认开启 |
| Q8_0 权重量化 | CANN 量化路径 10.3% **更慢**，拒绝 |
| flow ACL graph capture | E2E 净损 +11%，冻结 OFF |
| B6b 机械提前触发 Talker | 无稳定收益，REJECT |
| DSpark / speculative decode | 尚未接线（研发分支，非参赛物） |

## 4. 优化边界声明

- 未改 `evaluation/` + 4 保护工具（`omni-eval-cli.cpp` / `omni-eval-daily-cli.cpp` /
  `omni-tts-eval.cpp` / `omni/CMakeLists.txt`），byte-identical to `c9785cc`。
- 生产源码改动仅限**非受保护**的 `tools/omni/omni.cpp` / `tools/server/server-omni.cpp`（正确性 + 计时发射）。
