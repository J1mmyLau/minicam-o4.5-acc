# F6 — Track A：Seed-TTS WER=100% 根因解析与修复

Date: 2026-08-13 · Base commit: `a77d6a8` (`fix/cann-fa-nan-ubatch16`) + 4 文件补丁（见下）
Directive: 【BYPASS — LONG-RUN FINALIZATION QUEUE】Track A

## 结论

Seed-TTS WER=100%（候选 `a77d6a8` vs 干净基线 `c9785cc`）= **三个相互独立的污染源**，
全部定位并修复。修复后 8 样本 smoke 复现 pristine：**WER=1.732% · SIM(ASV)=0.978**。

| 污染源 | commit / 位置 | 现象 | 修复 |
|---|---|---|---|
| 1. gf_enc 双重计算 | `6f134c7`（token2wav-impl.cpp） | flow/voco 条件张量被第二张图二次 compute | 用 `OMNI_T2W_ENC_TIMING` 门控 gf_enc compute（默认 OFF） |
| 2. FA Q-split 默认 16 | `aclnn_ops.cpp` `ggml_cann_flash_attn_ext` | 主 LLM prefill Q≈91-128 恒被拆 → 提前 EOS + 复读 | 源码默认 `16 → 0`（OFF） |
| 3. ecee7de memcpy 非-neox rope | `ecee7de`（aclnn_ops.cpp） | TTS-LLM 音频码条件被逐位置 D2D memcpy 破坏（commit 自承 "PENDING numerical alignment"） | 恢复 pristine c9785cc Step 6：非-neox 用 `aclnn_repeat_interleave(dim=3, n=2)`，neox 用 `aclnn_repeat{1,1,1,2}` |

三个污染源彼此掩蔽，需全部修复才回到 pristine（此前单修任一仅部分恢复：1→仍有截断、
2→WER 12%、3→WER 97%）。

## Config D 统一兼容性（关键新结论）

`OMNI_CANN_FA_MAX_UBATCH=16`（长多模态 NaN 保护）+ Q-split 源码默认 0 + rope 修复 →
Seed-TTS **WER=1.732% = pristine**（`trackA_ub16_clean`，2026-08-13 实测）。

旧矩阵里 "MAX_UBATCH=16 → 9.334%" 是 **被当时的 Q-split 默认 16 混淆** 的假象。Q-split
源码默认改为 0 后，`MAX_UBATCH=16` 对 Seed-TTS 无副作用。⇒ **Config D 可作为全精度任务
统一配置**（长多模态 + Seed-TTS 共用），无需任务级分叉。

## Simplex 路径恢复 pristine NPU 行为

`omni.cpp` `omni_init` 恢复 simplex（Seed-TTS eval）使用 `token2wav_device`（NPU），
与 pristine c9785cc 一致（WER 1.7%）。CANN flow/vocoder 的 cross-thread stream 所有权
问题仅影响 duplex worker 路径，同步 simplex 路径无此问题。

## 源码补丁（相对 `a77d6a8`，未提交）

```
ggml/src/ggml-cann/aclnn_ops.cpp        # rope 修复 + Q-split 默认 16→0
tools/omni/omni.cpp                     # simplex→NPU revert + OMNI_TTS_NGL + pipeline drain
tools/omni/token2wav/token2wav-impl.cpp # gf_enc 门控 OMNI_T2W_ENC_TIMING
tools/server/server-omni.cpp            # SSE duplex drain（RTS SPEAK=0 修复，非 Seed-TTS）
```

完整补丁：`experiments/nightly/trackA_fixes.patch`（296 行）。二进制 `llama-omni-tts-eval`
已重建并验证（smoke WER 1.732%）。

## 验证

| 运行 | 配置 | WER | SIM |
|---|---|---|---|
| pristine（native CANN FA） | — | 1.732% | 0.967 |
| 候选（Q-split 0 + rope 修复） | `trackA_rope_fix` | 1.732% | 0.967 |
| 候选（Config D：MAX_UBATCH=16 + Q-split 0 + rope） | `trackA_ub16_clean` | 1.732% | 0.978 |

EOS 序列 147… vs pristine 162… = CANN fused-attention 数值差异（可接受，WER 一致）；
`OMNI_CANN_FA_BYPASS=1` 给 bit-exact pristine EOS 但 CPU 慢，不作为候选。

## 目标基线（pristine c9785cc 全量 2020，已冻结）

| Metric | Value | Acceptance |
|---|---|---|
| ZH_WER | 1.5% | ≤ 1.56% |
| SIM_ASV | 0.97 | ≥ 0.689 |
| 完成度 | 2020/2020 | — |

候选全量 2020 复跑（`experiments/nightly/trackC_seedtts_full`，Config D，2 NPU）**完成**：

| Metric | Candidate（Config D） | Pristine（冻结） | Acceptance | Verdict |
|---|---|---|---|---|
| ZH_WER | **1.422%** | 1.5% | ≤ 1.56% | **PASS**（优于 pristine） |
| SIM_ASV | **0.969** | 0.97 | ≥ 0.689 | **PASS**（≈ pristine） |
| 完成度 | 2020/2020 · 0 NaN/error | 2020/2020 | — | PASS |

用时 9941s（~2.76h）。WER_BELOW50=1.395%（2019/2020，ratio 0.9995）。

## 二进制一致性（Track F）

4 个可执行文件均**动态链接** `libomni.so` + `libggml-cann.so`，故 rope 修复 / Q-split / simplex
revert / gf_enc 门控在运行时自动生效，无需重建 server / eval-cli / eval-daily-cli（唯一 baked-in
的 server-omni.cpp Fix 2 已在 17:29 server 构建中）。最终候选共享库 SHA256（2026-08-13 23:17）：

| 产物 | SHA256（前 16） |
|---|---|
| libomni.so | b600ce5277be4eeb |
| libggml-cann.so.0 | c083aeea9aa57632 |
| libggml.so.0 | f79467d9ea9ccf26 |
| libllama.so.0 | cf5a0aaf2a68243a |
| llama-omni-tts-eval | 0208071b329bb0c4 |
| llama-omni-server | c330dc5aec2a334c |
