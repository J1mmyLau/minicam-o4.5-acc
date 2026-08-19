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

## talker (TTS) 热循环优化 — ✅ RTF 1.084 → 0.998（2026-08-16, commits 7a42d2270 + c43fe9880）

RTS tts 段 235ms 的真相：每个 audio token（~27 个/chunk）= NPU 前向 + **CPU 标量 head_code GEMV** + 采样。

| 优化 | 开关 | 内容 | 效果（交错 4×4 RTS A/B） |
|---|---|---|---|
| head_code GEMV NEON 向量化 | 默认开启（`OMNI_TL_GEMV=scalar` 回退标量） | 6562×768 标量循环 3.3ms/token（FP 归约不可重排→不向量化）→ NEON 4×4 FMA 0.55ms（6.0×），max&#124;Δlogit&#124;=2.4e-6 | tts 段 255.8→205.7ms，e2e 1044→1020，RTF 1.084→1.043（4/4 对一致）；WER 4.545% 不变 |
| talker norm+rope TileLang 融合 | `OMNI_TL_TTS=1` | talker=llama arch 20L/768/12H×64/θ=1e4/NEOX，前向 5.3ms/token 纯 launch 税。41 norm 位点 + 40 Q/K rope → `tltsnorm_N768`/`tltsrope_H12_D64_R768`（指纹 n_embd==768&&n_head==12，不伤其他 llama-arch 模型） | tts 段 218→174ms，e2e 1031→990，RTF 1.0654→**0.9981**（完全分离，首次 <1.0；官方基线 1.087）；WER 4.545% 不变 |

**坑**：Q/K 从 build_qkv 出来是 3-D [64,12,T] view（非 2-D [768,T]，内存布局等价）；`norm_row(M,N)` 的 M 必须传 T（M=1 时 T>1 只处理首行）；RTS 单轮 RTF 方差 ±0.1（轮次形态随机），必须同二进制 env 对照臂交错 ≥4 轮看方向一致性；约 1/6 的 RTS session 会整场 0-SPEAK（主 LLM 全程 LISTEN，会话时序 flake，双臂等概率，非融合问题，剔除即可）。

完整栈（QKR+norm_row+NEON GEMV+TTS 融合，见 `config-local.env`）：官方 smoke 4 任务 RC=0（Daily 2/2、WER 4.545%、videomme 0/2 均与融合前 smoke 一致），RTS RTF ~1.00-1.02。

### conv 融合接入 RTS 流式路径（2026-08-16 补充）

`OMNI_TL_CONV=1` 在 RTS server 流式 t2w 路径（token2wav-impl 同一代码）4×4 交错 A/B：**t2w 段 234.0→224.2ms（4/4 对一致，−10ms/窗）**，e2e 净零（−4ms，方差内）；WER 4.545% 不变。保留开启（免费小赢），但不要按离线 −20% 外推——流式路径 vocoder 只占 t2w 一部分且被队列稀释。

## VPM (视觉编码) 197 → 125ms — ✅ RTF 0.99 → 0.911（2026-08-17, commit f22d69f70）

重新 profile 发现 VPM 197ms 是墙内最大单项 (29% of SPEAK wall)。三层分解:

1. **bicubic_resize 死写修正**（位级一致, 免费）: 上游实现的垂直插值多项式放在 jj
   tap 循环**内部** —— C[0..3] 每填一个就完整算一次垂直 poly 并写 dst, 每像素 4 次
   垂直 poly 其中 3 次死写 (~3/4 浮点工作量白做)。重排为填满 C[0..3] 再做一次;
   浮点表达式逐字保留 (含 `-1.0/3` double 字面量) → 服务端代码级校验 **0/592704
   字节差异**。独立基准 540×960→336×588: 30.5→11.2ms (2.7×)。VPM stage
   189.4→166.3ms (4/4 对一致)。`OMNI_TL_BICUBIC=orig` 可切回对照。

2. **msprof 破案**: ViT 单次编码 device 34ms / wall 68ms —— **50% 是 host launch 税**
   (~1120 op/encode: Add 281 + Cast 339 + Transpose 114 + LN 58 + Mul 86...)。
   BatchMatMulV2 才 8.8ms、MatMulV2 7.1ms。不是算不快, 是发不完。

3. **双 ctx 双流并行**（`OMNI_VPM_PAR=1`）: overview 与 slice 两张图完全独立, 第二个
   vision_ctx（各自独立 CANN stream, +1.1GB HBM/64GB）让 slice 编码在并行线程跑,
   NPU 上重叠。同权重同输入同数学 → 输出位级一致。失败自动回退串行。
   交错 4×4 A/B: RTF 1.021→**0.911**, e2e 1020.7→946.9ms, **4/4 对完全分离**
   (ON 全 <0.94, OFF 全 >0.98)。VPM stage → ~125ms。

完整栈 smoke (`run_all --smoke 2`, RC=0): RTS **0.8831** (encode 份额 0.200→0.125),
Daily 2/2, WER 4.545% 逐位同, videomme 0/2 (与融合前一致, n=2 无统计力)。
累计: 1.084 → 1.043 (NEON GEMV) → 0.998 (talker 融合) → **0.911** (VPM)。
官方基线 1.087, 现低 16%。

**遗留线索（下轮）**: llama-bench 主模型 pp256 仅 ~110 t/s ≈ 1.9 TFLOPS 有效算力
（8.8ms/token, 与 ubatch 16/64/512 无关）, 与 GEMM 微基准 F32 63-73 TF 差 33×;
但服务端 in-situ prefill 等效 ~1300 t/s —— 两条路径行为矛盾, 需 in-situ msprof
（server 进程跑 SPEAK 时 attach）定论 prefill 187ms 的真实构成。

## in-situ msprof 全景 + llama-bench 证伪（2026-08-17, task #27）

llama-bench pp256 仅 110 t/s 且 84% 耗在 ScatterUpdate(1953µs/次) —— **是 bench 独有病态**
（memory_clear 路径），in-situ ScatterUpdate 11.7µs/次占 2.2%，服务端 KV 无病。
同二进制 llama-completion = 618 t/s 与服务端（1.27ms/token）一致。**llama-bench 不能
用于评估主模型 pp。**

in-situ 全景（9135ms device / 37 chunks）: MatMulV2 26.7% + **Cast 19.9%**（196K 次，
≈每 mul_mat 2.5 个 F32↔F16）+ BatchMatMulV2 11.6% + Add/Mul/Transpose 17% + Im2col 4.2%
+ Softmax 3.4% + TileLang 1.6%。session duty 仅 ~12% → host/串行仍是主矛盾。

**下一刀候选（按 ROI）**: ① F16 激活化（吃 Cast 全税 + GEMM 2-3×, device −40% 潜力,
需全量精度重验）; ② host 税结构治理（VPM 双流范式推广到 prefill/decode/t2w 段）;
③ flow CFM 融合（t2w 尾巴 111ms/窗）。

## F16 激活化 — ❌ 全线负结果（2026-08-18, task #28）

假设: in-situ Cast 19.9% + GEMM 微基准 F16 2-3× → F16 激活能吃双税。实测三层否决:

1. **ViT 图级 cast（OMNI_VPM_F16）**: 图内 ln 输出 cast 成 F16 喂 matmul → **wall +9%**。
   BMM(F16,F16)→F32 dst 反而慢 25%, 4-D aclnnMatmul F16 scratch 直接 aivec 崩(MTE 越界)。
2. **aclnnMm 纯 F16 scratch 快路径**: 最小隔离测试全对(含列主序/真实 shape, maxrel 5e-4),
   但集成层把 **stock 图里本来就有的 F16×F16（patch conv 的 im2col 输出）也吞了并产出错误
   数据(cosine 0.65)**; 修门控后 ViT 仍慢。**GGUF 里 bias/norm 全是 F32, F16 只有 2-D 线性权重**。
3. **主模型 mixed 路径(GGML_CANN_F16_MM=1)**: F32 act →F16 cast + 纯 F16 Mm + dst cast:
   tg 17.5→17.6ms/token **持平**。ACL 的混合精度处理已近最优; torch 微基准差距不落此路径。

结论: 196K Cast 的真实来源是 ACL 对每个 Mm 的内部处理, 显式化不省钱; 该方向关闭。
代码保留 env 门控默认 OFF(GGML_CANN_F16_MM / OMNI_VPM_F16), stock 路径 bit 级验证
(rms 0.931691 逐位同)。⚠️ 崩溃会毒化 die(aivec), 后续同 die 全崩——遇怪错先查僵尸进程。

## VPM host 启动税三连 — ✅ 全 bit 级一致（2026-08-18, task #29）

msprof trace(--runtime-api) 定案 host 大头（每 encode ~1400 kernel launch）:
- **aclnnIm2col host 阻塞 22.5ms/次**(此 CANN 是 host 实现) + 511 次 memcpy;
- launch 18270 次×6.6µs; 58 次 SyncStream;
- **根因: USE_ACL_GRAPH 是 CMake 选项且本构建 OFF** → capture 机制整个被编译掉,
  GGML_CANN_ACL_GRAPH env 一直无效(此前 on/off 的 9ms 差是噪声)。

三项修复(全部逐位一致):
1. **OMNI_VPM_PATCHMM=1**: patch conv(k=s=14 无 pad) = reshape+matmul。host 预处理顺手
   提取 patch(替换原 HWC→CHW deinterleave, 零额外内存流量), 图内 conv→mul_mat,
   还省掉 transpose+cont 两个节点。embedding dump **bit 级一致**。
2. **-DUSE_ACL_GRAPH=ON 重新编译** + `GGML_CANN_GRAPH_MAX_NODES=4000`(flow 11740 节点
   排除——Phase 7 已证 capture 对 flow 负)。ViT 图 931 节点 1 次 CAPTURE 后全程 REPLAY,
   launch 18214→1301(只剩捕获那一次); 输出 bit 级一致。主模型 decode 图(1120 节点,
   canonical KV 使形状逐 token 不变)也 REPLAY——但 tg 持平(decode 非 launch-bound)。
   LRU 匹配按每节点 data 地址, vision 每 encode 重建图但 sched 分配确定性 → 命中。
3. **GGML_CANN_OPERATOR_FUSION=1**(树内已有 ADD+RMS_NORM/ADD+NORM 融合): bench −2~5ms。

RTS 交错 4×4: RTF 0.9082→0.8931(对内 2-2 噪声主导), SPEAK→wav wall 955.7→930.9ms
(3/4 对更优, −2.6%)。**小幅正向 + 零精度风险**。残留 host 税: 每 encode 的 ggml 图构建
+ sched 分配(~1100 节点) 与预处理(bicubic/JPEG), 治本需图复用重构。

## LayerNorm/RMSNorm 仿射融合 — ✅ RTF −8.5%（2026-08-18 晚, task #30）

图算子直方图探针（OMNI_GRAPH_OPS_DBG）定下未融合簇后，把树内 GGML_CANN_OPERATOR_FUSION
从 {ADD+RMS_NORM} 扩展出两个带真实仿射参数的模式：
- **{NORM→MUL(gain)→ADD(bias)} → 单次 aclnnLayerNorm(x, gamma, beta)**: ViT 58 位点/encode
  + APM 49 + flow 图部分（msprof 实证 Mul 计数 1032→348，Add −700）；
- **{RMS_NORM→MUL(gain)} → 单次 aclnnRmsNorm(x, gamma)**: prefill 图 143 位点。

工程要点：
- 权重 F16→F32 一次性缓存（按 device 指针键），**设备侧 aclnnCast 转换**（capture 安全，
  无 host memcpy），但 aclrtMalloc 必须在 capture 外 → 学 rope_cache_preload 在
  aclmdlRICaptureBegin 前全图预热 row-vector MUL/ADD 操作数。
- ⚠️ 数值非 bit 级（cos 0.9999886，个别元素经非线性放大到 |Δ|0.34）——与上午三连的
  bit 级不同，**提交前必须全量 Daily/videomme 重验**（smoke n=2 无统计力: Daily 1/2,
  videomme 0/2 与往轮持平; WER 4.545% 逐位同, TTS 路径不受影响）。
- ⚠️ 探针教训：smoke/eval 期间不要并行跑其它 NPU/CPU 任务——本轮一次 0.9817 的"回归"
  是并行 llama-completion 的 CPU 争抢假象，清场后 2×2 完全分离（ON 全 <0.86）。

收益（清场 2×2 交错）: RTF 0.9272/0.9568 → **0.8553/0.8539**, SPEAK→wav 985.7/983.0 →
902.1/900.2 (−84ms)。构成: prefill +9% t/s (955→1097, 2/2) + ViT Mul −66% + flow
NORM 融合（t2w 在 RTF 分子内，eager 图 508 处）。
累计: 1.084 → 1.043 → 0.998 → 0.911 → **~0.855**（官方基线 1.087, 现低 ~21%）。

## TileLang vs aclnn（norm 仿射重写对比）— ❌ TileLang 全面劣势（2026-08-18, task #31）

把 aclnn 融合的 LN/RMS 仿射用 TileLang 重写（ln_affine_row / rms_affine_row，
qknorm 范式: T.Kernel(M) 每核一行 + 块状 N + tile op 标量 + broadcast epilogue），
NPU event 计时 + F64 CPU 参考对比：

| 形状 | TileLang | aclnn 单核 | 精度(TL) | 精度(aclnn) |
|---|---|---|---|---|
| LN 1008×1152 (ViT) | 144µs | **20-38µs (4-7×快)** | mean 2.0e-3 | **1.4e-7** |
| RMS 144×4096 | 35µs | ~96µs(组合)/单核更快 | 2.1e-3 | ~1e-7 |

**判决：两种轴都输** ——
1. 精度：该 fork 的 tile-op F32 原语内部按 ~F16 精度计算（**生产版 norm_row 同样
   mean_rel≈1.3e-3**，非新 kernel bug；decode 路径 E2E 精度门能过，但 ViT 特征
   喂 LLM 没必要吃这 4 个数量级）。
2. 带宽：TL 每核一行的 T.copy 流水只到 ~120GB/s，aclnn LayerNormV3 ~450GB/s。
   block_N=全行/384 无差别。

**分工结论（已验证的经验法则）**：TileLang 赢在小 M、launch-bound 的多算子链融合
（decode 的 QKR/norm_row，3+ 次 aclnn launch → 1 kernel，+25~66% decode）；aclnn 赢在
大形状带宽 bound 的单算子融合（本回合 LayerNormV3）。两者不可互换。
其余融合候选复查：ViT bias-ADD(281/encode) 需 4-D aclnnMatmul-with-bias（语义险）；
flow 的 CONT/PERMUTE/CONCAT 布局链(3600+) = zcat2 已试过负结果(DO_NOT_PROMOTE)。

## TileLang fast-rsqrt 精度修复 — ✅ decode 数值质量免费提升（2026-08-19, task #32）

用户质疑"tilelang 有问题"成立：前轮"平台 ~F16 特性"结论**错误**。二分定位（元素级
x*g+g 位级精确、reduce 2.4e-7、唯 `T.tile.rsqrt` 3.3e-3）证明：
**该 fork 的 `T.tile.rsqrt` 是快速近似内建；`1.0/T.tile.sqrt` 组合 = 1.9e-7 全精度。**

修复（T.tile.fill(1.0)+sqrt+div 三连替换全部 rsqrt 位点）：
- 生产 `norm_row`（2 处）：mean_rel 1.3e-3 → **4.6e-8**；8 个 tlnormrow .so 重建换入
- 生产 `qknorm_strided`（7 处）：→ **2.3e-8**；44 个 tlqkn 全矩阵重建
  （aot_qknorm_full.py：H32_R4096/H8_R1024 T1-512 + R6144 r0/r4096 段变体）
- 实验 ln/rms_affine kernel：2e-3 → 2.2e-7 / 8.7e-8

代价：**零**。decode tg 17.90ms/token（历史带 17.5-18.3 持平）；smoke RC=0
（WER 4.545% 同，RTS 0.8952）。此前精度门一直能过是因为 decode 链误差被下游吸收——
此修复把整条 TileLang decode 路径从 2e-3/site 拉到 1e-7/site，与 aclnn 同级。

速度结论不变（aclnn LN 20.8µs ≈ 带宽极限 ~670GB/s；TL 单行每核设计 148µs ≈ 95GB/s，
非本质但重设计也只能逼近极限）。

版本调查：官方 pip tilelang（0.1.9/0.1.13）**无 NPU 支持**；gitcode 镜像 ascendc_pto
尖端 2025-11 反而更旧；本地 /tmp 快照即最新（README 含 2026-03 条目）；wheel 在
GitHub releases（本机不可达）。tilelang-ascend 上游 = tile-ai/tilelang-ascend。
