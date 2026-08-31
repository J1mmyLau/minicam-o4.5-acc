# 07 · 评测：指标、口径与结果（问题 → 证据 → 实验 → 结果 → 决策）

## 1. RTF（主指标）测量口径

**问题**：RTF 怎么测才可信、才可与基线比？

**口径**（judge-final harness，`run_judge_direct.py`）：

- 输入：`omni_duplex1.mp4`（120s 双工视频，37 chunk）
- 计时：**core RTF = SPEAK→WAV 全链路 / 音频时长**，每 run 全视频 26+ SPEAK
  段取均值；跨 run 报 mean±stdev（n=4 或 n=3）
- 排除：模型加载/图构建冷启动（首次 ~7s）；运行前显存预热
- seed 1001–1004；`OMNI_SAMPLER_SEED` 注入保证可复现
- 官方 baseline 1.087 为官方 harness 口径——本地基线与候选用**同 harness
  同计时边界**配对比较，官方值只做方向性对照

**结果**（详见 02）：候选 **0.4829±0.0161**（4-run）；提交前复测
**0.4840±0.0125**（3-run）；本地同 harness 基线 0.6754±0.0152。

## 2. 四项精度指标

| 指标 | 官方基线 | 达标线 | 候选 | 判定 |
|---|---|---|---|---|
| VideoMME | 69.0 | ≥67.0（≤2pp） | 69.8（pristine 同 harness 参照） | ✅ |
| Daily-Omni | 79.5 | ≥77.5 | 79.43 | ✅ |
| TTS-Seed ASV(SIM) | 0.709 | ≥0.689 | **0.969** | ✅ |
| TTS-Seed WER | 1.414 | ≤1.56（≤10%） | **1.422%**（pristine 1.5%） | ✅ |

- VideoMME：50 题 parquet，64 帧/题，长上下文 ~29.9k token prefill；
  采样 seed 42、temperature 0 与官方基线对齐
- Seed-TTS 评分器：ZH WER=**Paraformer**（非 Whisper），SIM=WavLM+ECAPA
- 命令：`run_videomme.sh full` / `run_daily.sh full` / `run_tts.sh`

## 3. 精度/性能双 env 隔离（GM3M9G）

**问题**：VideoMME 从 69.8% 塌到 8%。

**证据/根因**：`run_eval.sh` 的 `set -a; source $EVAL_CONFIG` 会覆盖 launch env；
perf env（TileLang/ACL graph/fusion）混入精度 CLI 时，在 **30k-token 长上下文
prefill 上污染 logits**。历史上两次回归都由 config-local.env 误写引起：
①硬编码 `OMNI_T2W_N_TIMESTEPS=5` 杀 NFE2（0 WAV）；②perf 全关块误入
（tts 0.14→0.25，RTF 0.62）。

**决策（已固化）**：

| env | 用途 | 内容 |
|---|---|---|
| `server.env` | 性能/RTS | A+C + TileLang 全开 |
| `config-accuracy.env` | **精度脚本唯一载体** | perf 全关（TL=0/VPM=0/FUSION=0/GRAPH=off/NZ=off） |

修复后隔离口径验证：精度输出与 pristine 基线二进制行为一致。

## 4. 历史精度根因修复记录

**Seed-TTS WER 100% → 1.422%**（三重独立损坏）：

1. `gf_enc` double-compute（gf 特征被算两次）
2. FA Q-split 默认 16 → 长上下文注意力污染（Q-split 0 + MAX_UBATCH=16 修）
3. `ecee7de` memcpy rope 回归

修后 **2020 全量 PASS**（WER 1.422 + SIM 0.969）；早期 9.334% 读数是
Q-split16 混淆。采样侧排查记录：pristine 也是 nucleus，「multinomial 修复」
错误已回滚。

**FA NaN 线**（VideoMME 历史坑）：

- FusedInferAttentionScoreV2：**Q≥435 @ KV≥768 触发 NaN**（文本域也触发；
  非 innerPrecise、非 512 边界）；`aclnnMm` 也能从有限输入产 NaN
- 可靠修法：精度路径 MAX_UBATCH=16 + Q-split 0（进 accuracy env）；
  media embd decode 在 KV≥768 必须 batch≤16

## 5. DSpark 评测口径（与主链分离）

- acceptance/加速：文本域+MM 独立 harness（chat template 必须、原生分辨率、
  media batch clamp16）——见 [dspark-910c-inference.md](dspark-910c-inference.md)
- **acceptance 提升不等于 TPS 提升**；加速只认 k-sweep 实测
- B300 stage10→stage11 对比：上游 evaluator，逐样本 prompt sha256 多重集
  断言相等（保证同题同序）——见 [03-dspark-training.md](03-dspark-training.md) §1.6
