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

## 官方 smoke 自测（已通过, 2026-08-16）

四任务一次过的关键环境（完整见 `config-local.env.example`，通过 `EVAL_CONFIG` 加载，
**不改动** `evaluation/`）：

```bash
EVAL_CONFIG=$PWD/config-local.env ./evaluation/run_all.sh --smoke 2 --no-build
```

| 任务 | 结果 | 关键旋钮 |
|---|---|---|
| Video-MME | OK | `OMNI_CANN_FA_MAX_UBATCH=16`（aclnnMm NaN 唯一可靠 workaround，缺它大 prefill 挂死） |
| Daily-Omni | OK (smoke 2/2) | — |
| Seed-TTS | OK (WER 4.5%) | — |
| RTS | OK (RTF 1.1461, SPEAK→wav 1123ms) | `OMNI_T2W_DEVICE=cann-flow-only` + `OMNI_VOC_DEVICE=gpu:0` + `OMNI_T2W_PIPELINE_OVERLAP=1`（缺它们 SPEAK=0 → 无 t2w 事件 → RTF 不可用） |

注意：系统 python3 读 parquet 会 core dump（环境问题），`EVAL_PYTHON` 必须指向可用 venv。

## 行级 RMSNorm 融合 (OMNI_TL_NORM=1) — ✅ norm_row +25% decode

`examples/normalization/rms_norm.py` 官方范式重写（2-D tile + `tile.fill` 累加器 +
`reduce_sum(dim=-1)` + 标量 `tile.mul` + `tile.broadcast`，零标量大循环）。
`norm_row` 接管 qwen3 每层 3 个 no-res norm 位点（attn_norm/ffn_norm/output_norm，
36×3+1 处）。孤立数值 rel<1.6e-3 全形状，146µs/call。
- qkr+norm 全开: tg64 **0.78–0.79** vs 基线族 0.47–0.52（同 session A/B，**+55~65%**）
- 官方 smoke 四任务全 OK（Daily 2/2=100%、WER 4.545%、RTS RTF **1.0937**/1026ms
  vs 基线 1.1828/1175ms，误差分辨率内与基线逐指标一致）
- 旧 `fused_rmsnorm` N=4096 是标量大循环（元素赋值降级，201µs）——官方例子才是正解

## qk-norm+rope 两级 TileLang 融合 (OMNI_TL_QKR=1) — ✅ 已修通, +66% decode

**2026-08-16 修通并实测: tg64 0.47 → 0.78 t/s (+66%), 4 臂交错双复现; 短 prompt greedy
与原生链逐字一致, 长 prompt ~48 token 后良性数值分叉 (双方均通顺事实正确)。**

之前"E2E 未通"的根因不是 TileLang——是本桥接的两个 C++ bug:
1. **双重 RoPE**: try_qknorm_rope 已含 norm+rope, 但外层原 rope 块未互斥, 又 rope 一遍;
2. **view_3d 步长错**: 返回 3-D [128,H,T] 时 nb1/nb2 应为 512 / H*128*4, 误传 y2->nb。
误导排查的观测工具 bug: dump 的 vw 缓冲越界 + 变长记录(Q 8320/K 2176 floats)按定长解析
→ "4090/4096 错"与"同指针两次读不一致"都是解析伪影。`.so` launcher `<<<…,stream>>>`
流序自始至终正确, presync/scale 屏障均不需要(已撤)。

- kernel: `qknorm_strided`（wqkv 段直读 per-head RMSNorm，rel<1e-3 PASS 全形状）
  + `fused_rope_view`（已认证）→ 每层 Q+K 共 4 CUSTOM 替 ~8-12 aclnn launch（首次量级足够
  撼动 launch 税的融合）。AOT `tlqkn_H{32,8}_R{4096,1024}_T{1..8}_F32.so` 16 个。
- 已验证 ✓：kernel 孤立数值（torch 对照 rel<1e-3）；C++ 单测 `tl_qkr_selftest`
  （view+F16 权重+cast 全模拟，maxrel 2.9e-3）；python 回放 E2E dump 数据经 .so 全对；
  E2E 首层 norm 单点值正确；rope 级（OMNI_TL_ROPE=1）文本验证正确（首次文本级验证）。
- 未通 ✗：E2E 全量对照 4090/4096 错；同指针两次 D2H 读值不一致（0.4273 vs 0.0963），
  pre/scale 屏障无效。断点：`OMNI_TL_QKR_DUMP` / `OMNI_TL_ROPE_DUMP`（dump 越界已修）。
- TileLang 教训：`T.reduce_sum` 输出经标量直读不可靠——必须沿用 fused_rmsnorm 的
  verbatim 归约链（tile.mul 平方 → reduce_sum → Parallel(1) 改写 → tile.rsqrt）；
  裸 T.copy 进出（无 tile 算子消费）结果错误；jit 装饰函数内模块级 `T=1` 会遮蔽 tilelang.language。
