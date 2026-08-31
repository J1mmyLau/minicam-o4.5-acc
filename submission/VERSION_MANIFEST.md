# VERSION_MANIFEST — 版本溯源清单（唯一权威）

> 每次评测 / 每次复现都以此清单为准。任何提交结果必须能回溯到本清单的一行。

## 候选冻结（2026-08-30；2026-08-31 提交前复测后 config 修正，见变更记录）

| 项 | 值 |
|---|---|
| CANDIDATE_SOURCE_COMMIT | `df45b47c3e86b47871d2a64726ff194f46766a8a`（branch `perf/tilelang-bridge`） |
| 未提交工作区 diff | 10 文件（4369+/887−）：`config-local.env`, `ggml/src/ggml-cann/tl_conv_bridge.cpp`, `tools/omni/omni-cli.cpp`, `tools/omni/omni.cpp`, `tools/omni/omni.h`, `tools/omni/token2wav/token2wav-{example,impl.h,impl,cpp}.cpp`, `tools/omni/vision.cpp`；另含未跟踪 `tools/omni/talker_rollout.py` |
| 冻结方式 | 源码以 git commit + 工作区 diff 快照（`submission/patches/`）双重固定；二进制以下列 SHA256 固定 |
| llama-omni-server SHA256 | `e4fea2680f52147f6c84718b4fd8ab1e1271fc6b5e53c92cbc88ad2ff69d35c4` |
| libomni.so SHA256 | `c31dbef10c2ca8c5faab8675f4f7d930386f5009fdd5df5da44da3466a1178ca` |
| libggml-cann.so.0 SHA256 | `c37b9230f0897f4976588664d4b8b5b4395f7fa5dc693e416dedfc958e8ef8c8` |
| libggml.so SHA256 | `304ffb2e549749334349a5a1eb5201f1d47f53ef2fff35d7c44dd3fe3f594f15` |
| libllama.so SHA256 | `b7b5feae782195bcdc2da4b53be2e52c26d4b8deb371d4528d29834197963b1c` |
| llama-omni-eval-cli SHA256 | `531fc80ca9a9ca71c8e9dfd3e8a0a91402e0cd0c209c40a7e419ec78bf8a58e1` |
| llama-omni-eval-daily-cli SHA256 | `006b71416f2e3190cee0a94f67ca51bbc780e87888deef61f9e4e59de91dc157` |
| llama-omni-tts-eval SHA256 | `ab611e9a6425a8e542cff601f6d3c94b7bc5783865765333fc34976963bb3276` |
| model SHA256 | `d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de`（MiniCPM-o-4_5-F16.gguf，未改动） |

## 环境基线

| 项 | 值 |
|---|---|
| NPU | 1× Ascend 910C（dual-die，单卡合规，`ASCEND_RT_VISIBLE_DEVICES=1`） |
| CANN | 9.1.0-beta.1 |
| TileLang AOT 核 | 仓库根 `tilelang-aot/`（相对 cwd 加载；`OMNI_TL_CONV_DIR` 等可覆盖） |
| Model | `MiniCPM-o-4_5-F16.gguf`（`-ngl 999 --device CANN0`） |
| T2W | token2wav-gguf（CANN flow-only，`OMNI_VOC_DEVICE=gpu:0`） |
| 评测 harness | 本仓库 `evaluation/`（run_eval.sh → run_eval.py，任务 = videomme / daily-omni / tts / rts） |
| 数据 | Video-MME 官方子集（parquet+视频）/ Daily-Omni（daily_omni.jsonl）/ seed-tts-eval zh 2020 项 / RTS: judge-final omni_duplex1.mp4 |

## 运行时配方（A+C，RTS/性能链路）

```text
# --- A+C 性能杠杆（仅 server/RTS 链路生效）---
OMNI_DUPLEX_MAX_SLICE=0        # 杠杆A: 仅 overview 64 vision token/帧
OMNI_TTS_FIRST_CHUNK_STEP=10   # 杠杆C: 首 TTS chunk 10 token

# --- 稳定性基线（Config D 继承）---
OMNI_CANN_FA_MAX_UBATCH=32
OMNI_T2W_DEVICE=cann-flow-only
OMNI_VOC_DEVICE=gpu:0
OMNI_T2W_PIPELINE_OVERLAP=1
GGML_CANN_WEIGHT_NZ=off

# --- TileLang 融合核（性能链路；详见 config/server.env）---
OMNI_TL_QKR=1 OMNI_TL_NORM=1 OMNI_TL_TTS=1 OMNI_TL_CONV=1
OMNI_VPM_PAR=1 OMNI_VPM_PATCHMM=1
GGML_CANN_OPERATOR_FUSION=1
GGML_CANN_ACL_GRAPH=on（MAX_NODES 扩容）

# --- RTS 专用 NFE2（launch-only）---
OMNI_T2W_N_TIMESTEPS=2
OMNI_T2W_PROMPT_CACHE=/workspace/models/token2wav-rts-nfe2/prompt_cache.gguf
```

**⚠ GM3M9G 精度隔离**：上述 perf 变量只在 server 启动命令注入；精度任务
（videomme / daily-omni / tts）经 `config/config-accuracy.env` 全量显式关闭
（`OMNI_TL_*=0`, `OMNI_VPM_*=0`, `GGML_CANN_OPERATOR_FUSION=0`,
`GGML_CANN_ACL_GRAPH=off`, `GGML_CANN_WEIGHT_NZ=off`）。两套 env 严禁混用。

## DSpark 交付资产（2026-08-31 加入包内）

| 项 | 值 |
|---|---|
| 文件 | `dspark/dspark_stage11-draft-q8mixed-C.gguf`（1,849,740,160 B = 1.85GB，达标 1.8±0.1GB） |
| SHA256 | `11a70479e4a56aed4146783ac0ca45afac5214d0d0c6cb095e27668293a40ea3` |
| 方案 | C 混合精度：blk.0/1 全 linear + blk.2.ffn_down → Q8_0（15 张量）；fc/markov/其余保 BF16；norms 保 F32 |
| 验收 | BF16 vs Q8 三 prompt acceptance 逐位一致（0.20833/0.38462/0.50000），吞吐持平 47.8–75.2 t/s |
| 溯源 | stage11-step150 训练权重 → swap 原位换字节（BF16 GGUF sha256 `0fe9051b…`）→ 方案 C 量化 |
| 定位 | 独立交付资产；Track A RTF 候选运行时不含 dspark 栈，RTF 数字与该 draft 无关（见 dspark/README.md） |

## 变更记录

- **2026-08-31（提交前复测触发）**：修复 `config-local.env` 两处回归并复测 3-run
  （0.4736/0.4978/0.4806，mean 0.4840±0.0125，与 4-run 一致）——
  ① 移除硬编码 `OMNI_T2W_N_TIMESTEPS=5`（run_eval.sh 以 `set -a` source EVAL_CONFIG，
  会覆盖 launch 注入的 NFE2 → 5 步跑 2 步 cache → Token2Wav worker init 失败 →
  CPU fallback → 全程 0 WAV）；C++ 默认即 5，移除后行为不变、launch 覆盖恢复生效。
  ② 恢复 perf 块为 ON（GM3M9G 修复期被误置 0：`OMNI_TL_*=0`/`ACL_GRAPH=off`/
  `OP_FUSION=0`，导致 tts 0.14→0.25、RTF 0.48→0.62）；精度隔离载体是
  `submission/config/config-accuracy.env`，accuracy 脚本全部指向它，不受影响。
  同步刷新 `patches/uncommitted-worktree.patch` 与 `benchmark_results/rts/raw/`。
- **2026-08-31（补）**：RTF 口径按最小统计（4-run 0.4829±0.0161，最优单次 0.4603）；
  `dspark/` 交付资产并入提交包（1.85GB q8mixed-C + scripts + 验收数据）。

## run_id 约定

```text
run_yyyymmdd_hhmmss_<tag>（tag = baseline|candidate|perf|demo|repro|smoke）
每次 run 记录：完整命令 + 完整环境 + 原始输出路径 + binary_sha + model_sha
```

## 修改规则

- 评测保护资产 0 改动：`evaluation/`、`tools/omni/omni-eval-cli.cpp`、
  `tools/omni/omni-eval-daily-cli.cpp`、`tools/omni/omni-tts-eval.cpp`、
  `tools/omni/CMakeLists.txt`、token2wav 孤立验证器 —— 与上游基线 byte-identical。
- 源码/二进制任何变化 → 重建 + 重 SHA + 更新本清单 + 重跑对应验证。
- 精度验收状态以 `benchmark_results/*/STATUS.md` 为准（四项均达标）。
