# 02 · 对话 / RTS 推理优化全史（带数据）

主指标：**core RTF = SPEAK→WAV 全链路耗时 / 音频时长**。
数据口径：judge-final harness（`run_judge_direct.py`），同视频
`omni_duplex1.mp4`（120s 双工，37 chunk），seed 1001–1004，跨 run 报 mean±stdev。

## 0. 总成绩链

```
官方基线                1.087   (官方 harness 口径，方向性对照)
本地同harness基线        0.6754 ± 0.0152   (A+C 关闭，4-run)
Round1 早期             0.89 → 0.73        (见 §1 稳定性三修)
Phase0 复测基线          0.6102 ± 0.0104   (全优化栈、无 A+C)
+ 杠杆A vision slice0    0.5182 ± 0.0407   (−0.092)
+ 杠杆C 首 chunk 10 tok  0.4829 ± 0.0161   (−0.035)   ← 提交配方
提交前复测(2026-08-31)   0.4840 ± 0.0125   (3-run，可复现确认)
```

**相对本地基线 −28.5%；相对官方基线 −55.6%。**

---

## 1. Round 1：稳定性三修（0.89 → 0.73）

| 问题 | 根因 | 修法 | 收益 |
|---|---|---|---|
| eval 客户端默认杀 capture | `run_eval.py` 默认关 capture | 显式 on | 解锁测量 |
| ubatch 配置反直觉 | ubatch 64 反而慢 | `OMNI_CANN_FA_MAX_UBATCH=32` 甜点 | decode 明显 |
| fence-view bug 静默杀 capture | view 在 fence 前被消费 | 修 fence 顺序 | capture 生效 |

这一轮确立 talker 4.9 ms/token = **带宽地板**（单 die HBM 带宽决定），
单算子级微调动不了它——后续所有大收益都来自「整段融合」与「少做功」。

## 2. host 税三连（launch 削减）

decode 每步 1027 次算子 launch，每次 ~30µs 的 host 端税主导。
三项叠加（位级一致验证后合入）：

- VPM `patchmm` 融合
- `GGML_CANN_ACL_GRAPH=on` + `MAX_NODES=4000`（ACL graph capture/replay）
- `GGML_CANN_OPERATOR_FUSION=1`

**launch 次数 18214 → 1301**。这为后面 TileLang 整段融合铺路。

## 3. TileLang 融合核（decode 主增益）

自建 `tilelang-ascend`（910C 后端，TVM 补丁 6 处 + AOT .so 纯 C ABI，
单核 15.3µs/call），通过 perf/tilelang-bridge 桥接进 ggml-cann。

### 3.1 QK-norm + RoPE 整段融合核（commit `6dbb79247`）

decode 每步 36 层 × (q/k norm + rope) 三算子串 → 单核。

- **decode 吞吐 +66%（0.47 → 0.78 t/s）**
- 调试血泪：初版桥接**双重 RoPE + `view_3d` 步长错**，TileLang 无辜；
  dump 越界 + 变长记录定长解析制造了流竞态幻影
- 附带发现：**「launch 税墙不可动」的单算子结论被推翻**——整段融合能动

### 3.2 RMSNorm 行融合核（commit `5d8044e06`）

3 个 norm 位点/层 × 36 层。单开 +25%，**与 3.1 叠加 +55~65%（0.78–0.79 t/s）**，
RTS RTF 1.18→1.09（当时口径）。
坑：M<2 时官方 tiling 崩；1-D copy 进 2-D tile 是垃圾。

### 3.3 vocoder conv1d im2col（t2w −21%）

vocoder 里 **im2col 占 85%**（351ms/chunk）。TileLang conv1d 核替换：

- **t2w stage −21%**；E2E −0.01~0.02（vocoder 只占 t2w ~1/3，flow NFE 主导）
- **WAV 相关系数 0.9993**（音频质量保持）
- 真根因教训：初版崩 = cast 流竞态 + galloc 地址复用（非 conv 语义），
  修复 = 根 F32 回溯重排缓存；host 读图节点必须 `SynchronizeStream`

### 3.4 被否决的核（记录防重试）

| 核 | 结果 |
|---|---|
| flow 零拼融合 zcat2 | 空结果（位相等，Δ<1%）DO_NOT_PROMOTE |
| decode RoPE 单换装 | 0 增益（rope 占 0.05%，host 税主导） |
| sel-emb 换装 | 211s vs 213s，零 |
| Q8_0 主模型（杠杆B） | **净负**：同 seed 0.5215 vs 0.5257，prefill +25.5%/decode +7.9%（aclnn Q8 kernel 慢） |

## 4. NFE2：flow 步数 5 → 2（launch-only）

token2mel 流匹配默认 NFE=5。RTS 链路降到 2 步 + 预铸 `prompt_cache.gguf`
（GGUF 手术：est cache ne[2]=n_ts×16 slots step-major，ne[3]=batch CFG=2）。

- **launch-only**：`OMNI_T2W_N_TIMESTEPS=2` + `OMNI_T2W_PROMPT_CACHE=<path>`，
  不改 config 默认（Seed-TTS 精度任务仍走 NFE5）
- 多 shape 图缓存位级 parity 已验证 ⚠️ 命中必须按 entry 重传常量
- 姊妹实验 NFE1 铸成但音频垃圾（dt=1 过冲）→ 否决；NFE2 为最终形态

## 5. 杠杆A：`OMNI_DUPLEX_MAX_SLICE=0`（0.6102 → 0.5182）

**机制**：双工每帧 144 prefill token 中 128 是 vision（overview 64 + slice 64）。
设 slice=0 后 `vision_image_preprocess` 走早退分支 → **仅 overview 64 token/帧**。

4-run A/B（seed 1001–1004，其余栈不变）：

| 段 | 基线 | slice0 | Δ |
|---|---|---|---|
| core RTF | 0.6102±0.0104 | **0.5182±0.0407** | **−0.092** |
| vision encode | 0.0984 | 0.0604 | −0.038 |
| llm_prefill | 0.1200 | 0.0654 | −0.055 |

log 直测：VPM 92→53ms、prefill 123→65ms。
质量粗验证：SPEAK 文本语义正常（楼层应答）、WAV 时长/RMS 正常。

## 6. 杠杆C：`OMNI_TTS_FIRST_CHUNK_STEP=10`（0.5182 → 0.4829）

**机制**：首 TTS chunk 默认只产 5 个 LLM token 却照付一次 chunk 边界成本
（TTS queue push + `</unit>` eval + is_first_duplex_chunk 路径）。提到 10 摊薄。

| 段 | step5 | step10 | Δ |
|---|---|---|---|
| core RTF | 0.5182±0.0407 | **0.4829±0.0161** | **−0.035** |
| llm_decode | 0.1476 | 0.1299 | −0.018 |
| decode per-token | 24.7 ms | **19.2 ms** | **−22%** |
| 方差 | 0.0407 | 0.0161 | 收敛 |

LISTEN/SPEAK per-token 同步下降 → 证明是边界税不是 TTS 影子。
trade-off：首响延迟 +~100ms（B6b 原本为首响设 5）。

## 7. 最终配方（全部 launch-only env）

```
# scripts/server.env 原件
OMNI_DUPLEX_MAX_SLICE=0          # 杠杆A
OMNI_TTS_FIRST_CHUNK_STEP=10     # 杠杆C
OMNI_CANN_FA_MAX_UBATCH=32
OMNI_T2W_DEVICE=cann-flow-only
OMNI_VOC_DEVICE=gpu:0
OMNI_T2W_PIPELINE_OVERLAP=1
OMNI_TL_QKR=1  OMNI_TL_NORM=1  OMNI_TL_TTS=1  OMNI_TL_CONV=1
OMNI_VPM_PAR=1  OMNI_VPM_PATCHMM=1
GGML_CANN_OPERATOR_FUSION=1
GGML_CANN_ACL_GRAPH=on  GGML_CANN_ACL_GRAPH_MAX_NODES=4000
# RTS 启动额外：
OMNI_T2W_N_TIMESTEPS=2
OMNI_T2W_PROMPT_CACHE=/workspace/models/token2wav-rts-nfe2/prompt_cache.gguf
```

复现：`./submission/scripts/run_rts.sh <seed>`（4-run 原始产物
`benchmark_results/rts/raw/rts_final_s100{1..4}_metrics_rts.json`）。

## 8. 提交前复测与 config 回归事故（2026-08-31）

提交前 3-run 复测触发两处 **config 覆盖回归**（`run_eval.sh` 的
`set -a; source $EVAL_CONFIG` 会覆盖 launch env）：

1. `config-local.env` 曾硬编码 `OMNI_T2W_N_TIMESTEPS=5` → 杀 launch 注入的
   NFE2 → token2wav worker init 失败 → CPU fallback → 0 WAV
2. GM3M9G 修复期误把 perf 全关块写进 config-local.env → tts 0.14→0.25、RTF 0.62

两处修复后复测 **0.4840±0.0125**（3-run），与存档 4-run 一致 → 配方可复现。
**教训固化：精度隔离唯一载体 = `config-accuracy.env`，config-local.env 不放任何
与 launch 注入同名的变量。**

## 9. 到 0.40 还差什么（定位已完成，未进本提交）

剩余主战场 decode 0.130 + tts 0.141 + t2w 0.086 = 0.357：

- **Talker 侧批量 feed 摊薄**（离线已验证）：tts per-token 分解
  sync 3.3ms(66%)+gemv 0.8+sample 0.4+feed 0.5；块批前向 k=8 实测
  **2.44×（3.55→1.46 ms/tok）**，tts 0.143→~0.07 路线；需改采样语义+流水形态
- **Talker 投机（#41）**：rollout 捕获闭环+CPU-MLP draft 已建成，
  draft 预算 ≤0.3ms/步可达；数据量是瓶颈（1651 步离线评估 top-1 9.2% 真实命中率）
- thinker 域投机（DSpark）数学封顶 6.5% vs 需 2.4× → 关闭（见 05）
