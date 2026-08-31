# 06 · 内核与运行时优化（TileLang / host 税 / 杠杆 / 被否决路线）

> E2E 数据链与配方见 [02-rts-optimization.md](02-rts-optimization.md)；
> 本文是内核层细节与「为什么」。每项：问题 → 证据 → 实验 → 结果 → 决策。

## 1. TileLang 融合核（decode 主增益）

**装配**：自建 `tilelang-ascend`（910C 后端）——TVM 补丁 6 处 +
torch2.12-npu + gitcode 子模块；AOT 编出 `.so` 纯 C ABI，单核 15.3µs/call。
桥接放 ggml-cann side-loading（绕开冻结 CMakeLists），输出与原生位相等。

**性能注**：tile-op 向量化很关键——元素赋值写法会退化到 927µs（慢 6.5×）；
cos/sin 必须 host 预取（tir.cos 不支持）。

### 1.1 QK-norm + RoPE 整段融合核（`OMNI_TL_QKR=1`，commit `6dbb79247`）

- **问题**：decode 每步 36 层 × (q/k norm + rope) 三算子串，launch 税叠加。
- **实验**：NPU A/B（位级一致验证后合入）。
- **结果**：**decode 吞吐 +66%（0.47→0.78 t/s）**。
- **调试血泪**：初版桥接**双重 RoPE + `view_3d` 步长错**，TileLang 无辜；
  dump 越界 + 变长记录定长解析制造了流竞态幻影。
- **决策**：合入；同时推翻「launch 税墙不可动」的单算子结论。

### 1.2 RMSNorm 行融合核（`OMNI_TL_NORM=1`，commit `5d8044e06`）

- **问题**：3 个 norm 位点/层 × 36 层的逐行 norm。
- **结果**：单开 +25%，**与 1.1 叠加 +55~65%（0.78–0.79 t/s）**。
- **坑**：M<2 官方 tiling 崩；1-D copy 进 2-D tile 是垃圾。
- 模板：`examples/normalization/rms_norm.py`（tile.fill / reduce dim=-1 /
  标量 tile.mul / broadcast）。

### 1.3 vocoder conv1d TileLang im2col（`OMNI_TL_CONV=1`）

- **问题**：im2col 占 vocoder 85%（351ms/chunk）。
- **结果**：**t2w stage −21%；E2E −0.01~0.02；WAV corr 0.9993**。
- **真根因**：初版崩 = **cast 流竞态 + galloc 地址复用**（非 conv 语义），
  修复 = 根 F32 回溯重排缓存；**host 读图节点必须 SynchronizeStream**。

### 1.4 TTS 链融合核（`OMNI_TL_TTS=1`）与 VPM 并行（`OMNI_VPM_PAR/PATCHMM`）

talker 生成链融合 + VPM 视觉图并行调度/patch mm 融合（host 税三连成员）。

## 2. host 税三连（launch 18214 → 1301）

VPM `patchmm` 融合 + `GGML_CANN_ACL_GRAPH=on`（MAX_NODES=4000）+
`GGML_CANN_OPERATOR_FUSION=1`，三项位级一致后合入。

## 3. vocoder T-bucket kernels（全形状覆盖）

- **结果**：72 个 bucket kernel + 桥 bucket 回落全部跑通，t2w stage −21%。
- **但** E2E 仅 −0.01~0.02（vocoder 只占 t2w ~1/3）→ **到 0.45 的杠杆在
  llm_decode/tts，不在 vocoder**。
- ⚠️ kernel 生成须 `PYTHONPATH=/workspace/tilelang-ascend`。

## 4. VPM/多 shape 图缓存

- 多 shape 图缓存**位级 parity ✅**
- ⚠️ ggml 输入存储会被临时复用 → **命中必须按 entry 重传常量**
  （否则全幅噪声静默通过）
- build_alloc 仅 2.4ms → 图缓存收益可忽略，default-off

## 5. NFE2（flow 步数 5→2，launch-only）

- `OMNI_T2W_N_TIMESTEPS=2` + 预铸 `prompt_cache.gguf`
  （手术：est cache ne[2]=n_ts×16 slots step-major，ne[3]=batch CFG=2，
  main-first）
- **launch-only**：不改 config 默认 NFE5（精度任务仍走 5）
- **姊妹实验**：NFE1 铸成但音频垃圾（dt=1 过冲）→ 否决；
  no-CFG flow −21% 但 E2E 噪声内 + 音质未验 → 存档不默认

## 6. A+C 杠杆（E2E 数据见 02 §5-6）

| 杠杆 | env | 机制 |
|---|---|---|
| A | `OMNI_DUPLEX_MAX_SLICE=0` | 每帧 vision 128→64 token（仅 overview），encode+prefill 双降 |
| C | `OMNI_TTS_FIRST_CHUNK_STEP=10` | 首 chunk 5→10 token，chunk 边界税摊薄（decode per-token −22%） |

## 7. 被否决的路线（记录防重试）

| 路线 | 结果 | 原因 |
|---|---|---|
| Q8_0 主模型（杠杆B） | **净负**（0.5215 vs 0.5257 同 seed） | aclnn Q8 kernel 慢：prefill +25.5% / decode +7.9% |
| flow ACL graph capture（Phase 7） | **负**（flow p50 −20.4% 但 E2E +11%） | capture 尾部 + CPU vocoder 争抢；已回滚 |
| flow 零拼融合 zcat2 | 空（位相等 Δ<1%） | DO_NOT_PROMOTE |
| decode RoPE 单换装 | 0 增益 | rope 占 0.05%，host 税主导 |
| sel-emb 换装 | 211 vs 213s | 零 |
| F16 激活化 3 层 | 否决 | GGUF bias/norm 本就 F32，2×cast/Mm 不可消 |
| thinker 域投机（DSpark RTS） | 净负（RTF +12%） | 见 [dspark-910c-inference.md](dspark-910c-inference.md) §4 |

## 8. 已验证未上线的下一步（Talker 侧）

- **块批前向 k=8**：3.55→1.46 ms/tok（2.44×），decode 摊薄 3.6×；
  k=2 反慢 0.86×；fault-injection 全过。生产接线需流水形态 + 采样语义改造。
- **Talker 投机（#41）**：rollout 捕获契约 + CPU-MLP draft 闭环已建成；
  draft 预算 ≤0.3ms/步可达；数据量是瓶颈（top-1 真实命中率 9.2%，
  hold top-1 0.689 是 greedy 泄漏伪影）。
