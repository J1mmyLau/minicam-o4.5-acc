# Evidence Map — 申请材料数字 → 工程归档出处

> 来源分支：`docs/engineering-log` @ `858ad30`（所有路径相对该分支根）。
> 用法：往 PS / CV / 面试里写任何数字前，先在此表核对其原始出处与口径。

## A. 主成绩（RTF / 精度）

| 数字 | 口径 | 出处 |
|---|---|---|
| **RTF 1.087 → 0.4829（−55.6%）** | 官方基线为官方 harness 口径，方向性对照；候选为 judge-final 同 harness 4-run mean±stdev | `02-rts-optimization.md` §0-1；`07-evaluation.md` §1 |
| 0.4829 ± 0.0161 | 4-run（seed 1001–1004） | `02` §1 |
| 复测 0.4840 ± 0.0125 | 3-run 提交前复测 | `02` §0 |
| 本地同 harness 基线 0.6754 ± 0.0152 → −28.5% | 配对口径 | `02` §1 |
| RTF 五段分解 0.0611/0.0642/0.1233/0.1427/0.0987 | encode/prefill/decode/tts/t2w，config-verify seed1001 | `02` §2；`01-overview.md` |
| VideoMME 69.8 vs 基线 69.0（线 ≥67.0） | pristine 同 harness 参照 | `07-evaluation.md` §2 |
| Daily-Omni 79.43（线 ≥77.5） | | `07` §2 |
| WER 1.422%（pristine 1.5%，线 ≤1.56）；SIM 0.969（线 ≥0.689） | Paraformer + WavLM/ECAPA | `07` §2 |
| VideoMME 69.8→8% 塌缩事故 | perf env 泄漏，已修复 | `07` §3 |

## B. TileLang / 内核 / host 税

| 数字 | 口径 | 出处 |
|---|---|---|
| QK-norm+RoPE 融合核 decode +66%（0.47→0.78 t/s） | NPU A/B，位级一致 | `06-kernel-runtime-optimization.md` §1.1 |
| RMSNorm 行融合单开 +25%，叠加 +55~65% | | `06` §1.2 |
| conv1d im2col：t2w −21%，WAV corr 0.9993 | im2col 占 vocoder 85% | `06` §1.3；`05-profiling.md` §4 |
| launch 18214 → 1301 | patchmm + ACL graph + fusion 三连 | `06` §2；`05` §5 |
| 杠杆A：0.6102→0.5182（encode −0.038 / prefill −0.055） | vision 128→64 token/帧 | `02` §5 |
| 杠杆C：0.5182→0.4829；decode per-token 24.7→19.2ms（−22%） | 首 chunk 5→10 | `02` §6 |
| NFE 5→2（launch-only） | prompt_cache.gguf 预铸 | `06` §5 |
| 单核 AOT 15.3µs/call；tile-op 向量化差 6.5× | tilelang-ascend 装配 | `06` §1 |
| 被否决：Q8 主模型净负（prefill +25.5%/decode +7.9%）；flow graph capture E2E +11%；单算子换装全零 | | `06` §7 |
| decode 分解：48% logits 同步 + 32% emb 同步 + 17% 调用本体 | C1/C2 假设否决 | `05` §2 |
| tts per-token：sync 3.3ms(66%)+gemv 0.8+sample 0.4+feed 0.5 | ×26 token/chunk | `05` §3 |
| 块批前向 k=8 离线 2.44×（3.55→1.46 ms/tok） | 未上线，下一步 | `06` §8 |

## C. B300 训练（stage11 主线）

| 数字 | 口径 | 出处 |
|---|---|---|
| 8×B30Z（sm_103，268GiB/卡），DP8，global batch 32，150 步，bf16，lr 3e-6 | torch 2.8.0+cu128 / transformers 4.51 | `03-dspark-training.md` §1.1/1.4；`b300/03-stage11-training.md` |
| 数据 4197 = Daily-Omni 1197 + Video-MME 1500 + Seed-TTS EN 1088 + ZH 412 | 每源非零准入 | `b300/01-data.md` |
| cache 98.21 GiB / 2,145,260 tokens / 113.8 min / 成功率 100%（0 fail） | 单 GPU 生成，peak 17.54GiB | `b300/02-target-cache.md` |
| accept_len 3.4923→3.8620；overall 0.4388→0.4854；@6 0.0954→0.1895 | 644 样本 4 任务，prompt-hash 多重集断言相等 | `b300/05-acceptance-evaluation.md`；`03` §1.6 |
| warmstart ≠ exact resume；8×training_state.rank*.pt = optimizer state 非 8 模型 | 口径三钉 | `03` §0 |
| max_train_steps=150 优先于 epochs；4197/32≈131.2 步/epoch（≈1.14 epoch） | | `03` §1.4 |
| grad_norm 234–640 vs clip 1.0：条件式表述（logger 记录时点未核实） | | `03` §1.4 |

## D. 跨平台部署 / 投机

| 数字 | 口径 | 出处 |
|---|---|---|
| 量化 2.26GB→1.85GB（方案C），acceptance 三 prompt 逐位一致（0.20833/0.38462/0.50000） | Q8 与 BF16 吞吐持平 47.8–75.2 t/s | `dspark-910c-inference.md` §1 |
| k=2 → **1.87×**（k=3 1.80×，k=7 1.75×；MM 15帧 1.49×） | **独立 speculative benchmark，非 RTS 主成绩** | `dspark-910c-inference.md` §3 |
| c_draft = 1.11 ms/token（≈target 1/28）；V(batch 3..8)≈30.9ms | k-sweep 拟合 | 同上 |
| RTS 双工 A/B：RTF 3.979→4.460（+12%），decode 0.132→0.338（2.56×慢） | 净负 → 主提交不挂 draft | `dspark-910c-inference.md` §4 |
| 910C 本地微调：TF acc 74.13%→90.85%（ft3）；held-out +0.7~1.0pp | 方法论验证线，非主 artifact 血统 | `03` §2.2 |

## E. 口径红线（写材料前必读）

1. acceptance 提升 ≠ E2E speedup（两套测量，别混写）。
2. k=2 1.87× 是文本域独立 benchmark；RTS 主成绩只有 RTF −55.6%。
3. 官方基线 1.087 与本地 0.6754 是两个口径，对比时注明。
4. Draft 权重来源 = B300 stage11；910C 微调只是验证线。
5. 单 run RTF 方差 ±0.04，一切结论用 4-run 均值。
