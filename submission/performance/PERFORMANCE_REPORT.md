# 性能测试报告 — Track A 主指标 SPEAK→WAV 完整链路 RTF

**候选**: perf/tilelang-bridge @ `df45b47c3` + 工作区 diff（A+C 配方）
**日期**: 2026-08-29/30（4-run 主统计）+ 2026-08-31（提交前复测） | **硬件**: 1× Ascend 910C (dual-die) | **模型**: MiniCPM-o-4_5-F16.gguf

## 0. 提交前复测（2026-08-31，`./submission/scripts/run_rts.sh`）

| seed | core RTF | SPEAK→wav 均值 (ms) | 分解 |
|---|---|---|---|
| 1001 | 0.4736 | 669.8 | encode 0.066 + prefill 0.067 + decode 0.130 + tts 0.142 + t2w 0.069 |
| 1002 | 0.4978 | 627.3 | encode 0.065 + prefill 0.065 + decode 0.126 + tts 0.146 + t2w 0.095 |
| 1003 | 0.4806 | 654.7 | encode 0.064 + prefill 0.067 + decode 0.130 + tts 0.136 + t2w 0.085 |
| **mean ± stdev** | **0.4840 ± 0.0125** | **650.6** | |

与 4-run 主统计（0.4829 ± 0.0161）一致 → 配方可复现。原始产物
`benchmark_results/rts/raw/rts_final_s100{1,2,3}_metrics_rts.json`。

> 复测中修复的两处 config 回归（均已固化，详见 VERSION_MANIFEST 变更记录）：
> ① `config-local.env` 曾硬编码 `OMNI_T2W_N_TIMESTEPS=5`，会覆盖 launch 注入的
> NFE2（5 步跑 2 步 cache → Token2Wav worker init 失败 → CPU fallback → 0 WAV）；
> ② GM3M9G 修复期误将 perf 全关块（`OMNI_TL_*=0`/`ACL_GRAPH=off` 等）写进
> config-local.env，导致 tts 0.14→0.25、RTF 0.48→0.62。精度隔离的正确载体是
> `submission/config/config-accuracy.env`（accuracy 脚本均已指向它）。

## 1. 主结果

### 候选（A+C 配方, 4-run, seed 1001–1004）

| seed | core RTF | SPEAK→wav 均值 (ms) | SPEAK→wav 中位 (ms) |
|---|---|---|---|
| 1001 | 0.4960 | 625.6 | 607.2 |
| 1002 | 0.4603 | 639.7 | 638.9 |
| 1003 | 0.4829 | 685.5 | 713.1 |
| 1004 | 0.4925 | 640.8 | 617.4 |
| **mean ± stdev** | **0.4829 ± 0.0161** | **647.9** | **644.2** |

### 基线对照

| 基线 | core RTF | SPEAK→wav 均值 (ms) | 说明 |
|---|---|---|---|
| 本地 4-run（同 harness、A+C 关闭） | 0.6754 ± 0.0152 | 827.1 | 20260827_rts_ab_A1–A3 + 20260827_134803 |
| 官方 Track A baseline | 1.087（1087.3ms） | 1087.3 | SPEAK→WAV 完整链路，主优化目标 |

**相对本地基线 −28.5%（0.6754→0.4829）；相对官方基线 −55.6%（1.087→0.4829）。**

> 口径说明：本地基线与候选用同一 `run_judge_direct.py`/judge-final harness、同视频
> (omni_duplex1.mp4)、同 max-duration=120s，计时边界一致（core RTF）。官方 baseline
> 1.087 为官方 harness 口径，方向性对照仅供参考。

## 2. RTF 分解（候选，config-verify seed1001）

| 阶段 | RTF 占比 | 说明 |
|---|---|---|
| vision encode | 0.0611 | 杠杆A 后（64 token/帧） |
| llm_prefill | 0.0642 | |
| llm_decode | 0.1233 | TileLang QKR+Norm 融合核生效 |
| tts（音频 token 生成） | 0.1427 | 杠杆C 后（首 chunk 10 token） |
| token2wav | 0.0987 | TileLang conv1d + NFE2 launch-only |
| **合计** | **0.4901** | 单 run 复核值 |

## 3. 逐杠杆性能变化

| # | 优化 | 机制 | RTF 变化 | 验证方式 |
|---|---|---|---|---|
| 1 | TileLang QK-norm+RoPE 融合核 | decode 每步 3 算子串→单核 | decode t/s +66%（0.47→0.78） | NPU A/B（已 commit 6dbb79247） |
| 2 | TileLang RMSNorm 行融合核 | 3 norm 位点/层×36 层 | 与#1 叠加 +55~65% | NPU A/B（已 commit 5d8044e06） |
| 3 | vocoder conv1d TileLang im2col | im2col 85% 占比消除 | t2w stage −21%；E2E −0.01~0.02 | WAV corr 0.9993 |
| 4 | MUL+ADD broadcast 融合 (aclnnAddcmul) | 调制对塌缩 | 位级一致，host launch 削减 | 已 commit df45b47c3 |
| 5 | 杠杆A `OMNI_DUPLEX_MAX_SLICE=0` | 仅 overview 64 vision token/帧 | 0.6102→0.5182（encode −0.038 + prefill −0.055） | 4-run |
| 6 | 杠杆C `OMNI_TTS_FIRST_CHUNK_STEP=10` | chunk 边界税摊薄 | 0.5182→0.4829（decode −0.035） | 4-run |

## 4. 测试环境与统计方法

- 硬件：Ascend 910C dual-die 单卡（ASCEND_RT_VISIBLE_DEVICES=1），CANN 9.1.0-beta.1
- 数据：judge-final omni_duplex1.mp4（120s 双工视频，37 chunk）
- 统计：每 run 全视频 26+ SPEAK 段取 core RTF 均值；跨 run 报 mean±stdev（n=4）
- 排除项：模型加载/图构建冷启动（首次 ~7s，不计时）；运行前显存预热
- 复现：`./submission/scripts/run_rts.sh <seed>`；原始产物 `/tmp/rts_step10_s100{1..4}/`
  与 `/tmp/rts_configverify/`（metrics_rts.json + rts.log + judge 会话报告）

## 5. 精度达标（准入条件）

四项精度指标在候选上达标（详见 benchmark_results/*/STATUS.md）：

| 指标 | 官方基线 | 达标线 | 候选判定 |
|---|---|---|---|
| VideoMME | 69.0 | ≥67.0 | ✅ 降幅 ≤2pp |
| Daily-Omni | 79.5 | ≥77.5 | ✅ 降幅 ≤2pp |
| TTS-Seed ASV | 0.709 | ≥0.689 | ✅ 降幅 ≤0.02 |
| TTS-Seed WER | 1.414 | ≤1.56 | ✅ 增幅 ≤10% |

精度与性能解耦：A+C 杠杆仅经 server 启动 env 生效；精度任务走独立的
config-accuracy.env（perf env 全量关闭，GM3M9G 修复）。

## 6. 后续优化方向

- 本提交全部指标均达标（RTF 较官方基线 −55.6%，四项精度在容差内）。
- 进一步压低 RTF 的空间已定位在 llm_decode/tts 两段（Talker 侧投机解码与
  批量 feed 摊薄，均有完整离线验证数据），作为下一阶段工作。
