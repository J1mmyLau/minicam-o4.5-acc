# TileLang 优化分支 (perf/tilelang-bridge)

基于统一测评分支 `bench/huawei` (c9785cc) 的全部优化迁移，**冻结文件零改动**：
`evaluation/`、`tools/omni/omni-eval-cli.cpp`、`tools/omni/omni-eval-daily-cli.cpp`、
`tools/omni/omni-tts-eval.cpp`、`tools/omni/CMakeLists.txt` 均与主办方分支逐字节一致。

## 优化清单

| # | 优化 | 开关 | 位置 | 状态 |
|---|---|---|---|---|
| 1 | vocoder conv1d: im2col → TileLang AOT 直算 | `OMNI_TL_CONV=1` | `ggml/src/ggml-cann/tl_conv_bridge.*` + `token2wav-impl.cpp` 三处调用点 | ✅ 官方 server RTF 0.370→0.296 (−20%)；harness envelope 0.187–0.224 |
| 2 | flow CFM 零拼融合（scale+concat 3-op → 1 CUSTOM） | `OMNI_TL_LAYOUT=1` | `ggml/src/ggml-cann/tl_layout_bridge.*` | ⚪ 输出位相等，RTF Δ<1%（噪声内，DO_NOT_PROMOTE） |
| 3 | qwen3 decode RoPE: ggml_rope_ext → TileLang AOT | `OMNI_TL_ROPE=1` | `src/models/qwen3.cpp` | ⚪ 已接线已跑通；当前 decode 每步 ~2.1s 被 host 路径主导，rope 占 0.05%，无可见增益 |
| 4 | FA NaN 修复（BOOL mask + Clamp / Q-chunking） | 默认生效 | `ggml-cann.cpp` 血统 | ✅ |
| 5 | cond_cat 提出循环 + tree-concat O(N²)→O(N log N) | 默认生效 | `token2wav-impl.cpp` | ✅ |
| 6 | CANN host 侧 ADD+RMS_NORM 融合 | `GGML_CANN_OPERATOR_FUSION=1` | `ggml-cann.cpp`（血统自带） | 🔄 A/B 进行中 |

## AOT kernels

`tilelang-aot/` 内 60 个预编译 `.so`（conv 29 / tlnorm / tlrope H32·H8 × T1..8 × F16·F32）。
桥默认在 `<repo>/tilelang-aot` 找（cwd=仓库根），可用 `OMNI_TL_CONV_DIR` / `OMNI_TL_ROPE_DIR` 覆盖。

## 构建

```bash
source /usr/local/Ascend/cann/set_env.sh
cmake -S . -B build -DGGML_CANN=ON -DSOC_TYPE=ascend910c -DCMAKE_BUILD_TYPE=Release -DUSE_ACL_GRAPH=OFF
cmake --build build --target token2wav-example -j8
```

桥文件放在 `ggml/src/ggml-cann/`（该目录 `file(GLOB *.cpp)` 自动编译），
因此**不需要**改 `tools/omni/CMakeLists.txt`。

## 验证

```bash
export OMNI_T2W_MODEL_DIR=<token2wav-gguf 目录> OMNI_T2W_DEVICE=gpu OMNI_VOC_DEVICE=gpu:0
OMNI_TL_CONV=1 OMNI_TL_LN=0 OMNI_TL_ROPE=0 OMNI_T2W_PROFILE=1 \
OMNI_T2W_REPEAT=12 OMNI_T2W_OUT_WAV=/tmp/x.wav ./build/bin/token2wav-example
```

迁移认证（2026-08-16, 910C die-0）：conv-off/on 输出与源树 rep=12 **位相等**
（`0cac7480…` / `72a068c2…`），conv 增益 −16% 复现（绝对 RTF 受同 die 残留进程干扰）。

## 已知教训

- CUSTOM 回调内**禁止**对当前 compute 流 `aclrtSynchronizeStream`（自同步 → segfault）；
  需要设备侧数据移动时用 stream-ordered 异步原语（见 `tl_layout_bridge.cpp`）。
- host 预计算权重/表缓存按**根张量指针+签名**索引，防止 galloc 地址复用竞态（见 conv 桥 `rewrite_w`）。
- decode 当前每 token ~2.1s（llama-bench fa=1 Q6_K），瓶颈在 host 侧 launch 税
  （~1027 个 aclnn 微算子 ×30µs）+ embeddings D2H，非单个算子；单算子融合在该量级下不可见。
