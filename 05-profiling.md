# 05 · Profiling：各段归因（问题 → 证据 → 实验 → 结果 → 决策）

> 方法论先行：**对照必须归一化模型加载**（冷热缓存 160s vs 7s 会假扮 40% 增益）；
> A/B 同 seed 同视频同 harness；单 run 方差 ±0.04，结论看 4-run 均值。

## 1. 跨段 msprof（10-chunk 硬件时间线）

**问题**：RTF 时间都花在哪类算子上？

| 算子类 | 占比 | 备注 |
|---|---|---|
| MAIN_LLM（thinker 前向） | 26.8% | |
| **KV-ScatterUpdate** | **19.4%** | 新发现热点 |
| **Cast F32↔F16** | **13.6%** | 新发现热点 |
| lm_head | 0.65% | 「lm_head 翻倍」假设 REFUTED |

**决策**：攻 decode 全链（launch 税 + norm/rope 链）而非单算子；
KV-scatter 与 cast 列为候选（后被 TileLang 整段融合路线吸收）。

## 2. llm_decode 分解（0.357）

**问题**：decode 0.357 里 malloc/attn 各占多少？（C1=malloc、C2=attn 两假设）

**结果**：**C1、C2 均 REFUTED**——malloc ~0.1%，大头是同步等待：

| 成分 | 占比 |
|---|---|
| logits 同步 | **48%**（bimodal，prefill 混计） |
| embeddings 同步 | **32%** |
| llama_decode 调用本体 | 17% |
| sample | 1% |

**决策**：decode 的墙在 host-device 同步与 launch 税，不在算子 FLOPs
→ 走整段融合 + graph capture 路线。

## 3. tts（talker）per-token 分解（0.138-0.143）

**问题**：talker 4.9ms/token 的构成？

| 成分 | per-token | 占比 |
|---|---|---|
| **同步等待** | **3.3 ms** | **66%** |
| gemv（head_code） | 0.8 ms | 16% |
| sample | 0.4 ms | 8% |
| feed（emb_code 回填） | 0.5 ms | 10% |

（×26 token/chunk）

**决策**：单 token 优化填不平缺口；**批量 feed 摊薄 sync** 是正解——
离线块批前向 k=8 实测 2.44×（3.55→1.46 ms/tok），是 0.40 的最现实杠杆。
launch 塌缩假设已否决（ACL graph REPLAY=272/CAPTURE=2 已生效）。

## 4. token2wav 分解

**问题**：t2w 里 flow 与 vocoder 谁主导？

- **vocoder im2col 占 85%**（351ms/chunk）→ TileLang conv1d 替换（06 §3）
- 修后 vocoder 只占 t2w ~1/3，**flow NFE 主导** → NFE2 路线（06 §5）
- flow 零拼融合（zcat2）位相等 Δ<1% → 空结果，DO_NOT_PROMOTE

## 5. host 侧 launch 税

- decode 每步 **~1027 次算子 launch × ~30µs** host 税
- 修复后 launch 次数 **18214 → 1301**（06 §2）
- **教训链**：单算子换装（rope/OP_FUSION/sel-emb）实测全零；**整段融合**
  （qknorm+rope×36 层）实测 +66%——「墙不可动」的结论错在量级，不在方向。

## 6. WER/SIM 工具链（评测侧 profile 资产）

ZH WER=Paraformer（**不是** Whisper）；SIM=WavLM+ECAPA；数据集+ONNX
token2wav 在 appendix。 scorer 加载 PASS（Paraformer 9.2s "All keys matched"，
SIM/ECAPA 44.9s）。

## 7. VPM 侧

- 杠杆A 前 VPM 92ms/chunk、每帧 144 prefill token（128 vision）
- slice0 后 VPM ~53ms、prefill 123→65ms（数据见 02 §5）
- VPM 图构建本身 build_alloc 仅 2.4ms（vs compute 103ms）→ 图缓存收益可忽略
