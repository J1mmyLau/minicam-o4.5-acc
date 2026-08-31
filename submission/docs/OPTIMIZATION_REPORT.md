# 优化与复现说明

## 1. 瓶颈分析（优化前 RTF 0.89 → 本轮起点 0.6754）

对 120s 双工视频逐段 wall-clock 解剖（msprof + F6_EVENT 链路埋点）：

| 阶段 | 占比 | 瓶颈细节 |
|---|---|---|
| llm_decode | ~26% | 每步 ~30µs launch 税 ×1027 次算子提交；RoPE 链 35%、RMSNorm 链 30%、KV-scatter 14% |
| tts 音频 token | ~24% | per-token sync 3.3ms（66%）+ gemv 0.8 + sample 0.4 + feed 0.5 |
| token2wav | ~17% | vocoder conv1d im2col 占 85%（351ms/chunk）；flow NFE5 主导 |
| vision encode + prefill | ~18% | 128 vision token/帧（overview+detail 双路） |

## 2. 优化方法（按上线顺序）

### 2.1 TileLang 融合核（代码级，已 commit 在 perf/tilelang-bridge）

- **QK-norm+RoPE 整段融合核**（`OMNI_TL_QKR=1`）：qwen3 36 层每步的
  Q/K-norm + RoPE 三算子串塌缩为单 TileLang 核。decode t/s +66%。
  根因修复：桥接双重 RoPE + view_3d 步长错（commit 6dbb79247）。
- **RMSNorm 行融合核**（`OMNI_TL_NORM=1`）：官方 norm_row 范式（commit 5d8044e06），
  单开 +25%，与 QKR 叠加 +55~65%。
- **vocoder conv1d im2col**（`OMNI_TL_CONV=1`）：TileLang conv1d 替换 im2col
  路径，t2w stage −21%，WAV corr 0.9993。
- **MUL+ADD broadcast 融合**（aclnnAddcmul，commit df45b47c3）：调制对位级一致塌缩。
- **TTS norm/rope 融合核**（`OMNI_TL_TTS=1`）：768 维 talker 专用核。
- AOT .so 15.3µs/call 纯 C ABI；tile-op 向量化 6.5×。

### 2.2 host 税削减

- ACL graph replay（`GGML_CANN_ACL_GRAPH=on` + MAX_NODES=4000）+ OP_FUSION +
  VPM patchmm 并行：launch 18214→1301。

### 2.3 A+C 架构级杠杆（纯 env，零代码）

- **杠杆A `OMNI_DUPLEX_MAX_SLICE=0`**：双工视觉只保留 overview 路径
  （64 token/帧，128→50%）。RTF 0.6102→0.5182。
- **杠杆C `OMNI_TTS_FIRST_CHUNK_STEP=10`**：首个 TTS chunk 10 token（默认 5），
  chunk 边界税摊薄。0.5182→0.4829（方差 0.041→0.016）。
- **NFE2 launch-only**：RTS 启动带 `OMNI_T2W_N_TIMESTEPS=2` +
  NFE2 prompt_cache.gguf（多 shape 图缓存位级 parity 已验证）。

### 2.4 已否决路线（防止重复踩坑）

- Q8_0 主模型：净负（aclnn Q8 kernel 慢，prefill +25.5%）。
- flow NFE1：音频垃圾（dt=1 过冲）。NFE3：device-bound 无增益。
- thinker 投机解码：双域 37/38% 一致率，封顶 6.5% vs 需 2.4×，数学性关闭。
- zcat2 零拼融合 / tlrope qwen3 换装 / sel-emb：零增益。

### 2.5 GM3M9G 精度塌缩修复（必读）

perf env（TL kernels / OP_FUSION / ACL_GRAPH / VPM）只在 RTS 链路做过位级验证；
经 run_eval.sh `set -a` → run_eval.py `base_env()` 泄漏进精度 CLI 后，在
videomme 64 帧/29.9k-token 长上下文 prefill 上系统性污染 logits（8% vs 基线
69.8%）。修复 = 精度任务显式关闭全部 perf env（本提交 config/ 两套 env 严格分离）。

## 3. 完整复现步骤

### 3.0 构建

```bash
cd /workspace/omni-tilelang-opt
cmake -B build -DGGML_CANN=ON && cmake --build build -j --target llama-omni-server llama-omni-eval-cli llama-omni-eval-daily-cli llama-omni-tts-eval
# TileLang AOT 核（首次）: PYTHONPATH=/workspace/tilelang-ascend <tilelang kernel gen>
# 校验 SHA256 与 submission/VERSION_MANIFEST.md 一致
```

### 3.1 性能（RTF，主指标）

```bash
./submission/scripts/run_rts.sh 1001   # 单 run；1002-1004 重复得 4-run 统计
```

### 3.2 精度（GM3M9G 修复后口径）

```bash
./submission/scripts/run_videomme.sh full   # ~7-8h
./submission/scripts/run_daily_omni.sh
./submission/scripts/run_tts_seed.sh
```

### 3.3 预期结果

- RTF：0.4829±0.0161（4-run）；SPEAK→wav 647.9ms
- 精度：四项达标（videomme ≥67 / daily ≥77.5 / ASV ≥0.689 / WER ≤1.56，
  见 benchmark_results/*/STATUS.md）

## 4. 保护资产（0 改动声明）

`evaluation/`、`tools/omni/omni-eval-cli.cpp`、`tools/omni/omni-eval-daily-cli.cpp`、
`tools/omni/omni-tts-eval.cpp`、`tools/omni/CMakeLists.txt`、token2wav 孤立验证器
与上游基线 byte-identical。工作区 diff（patches/uncommitted-worktree.patch）不含上述路径。
