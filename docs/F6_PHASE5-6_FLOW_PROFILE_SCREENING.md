# F6 — Phase 5/6: Flow_match 关键路径 Profile + First-Cut 筛选

Date: 2026-08-13 · Commit: a77d6a8 (`fix/cann-fa-nan-ubatch16`)
Directive: 【BYPASS — FINAL OFFICIAL GATE THEN FLOW OPTIMIZATION】 Phases 5-8

## Phase 5 — Flow Profile（FLOW_TOTAL / FLOW_DEVICE / FLOW_HOST）

| Field | Value | Source |
|---|---|---|
| FLOW_TOTAL_MS | **145ms** serial / **202.5ms** Config D（contended） | Config D A/B + Phase 4 |
| FLOW_DEVICE_MS | **≈41ms**（纯 NPU 计算） | msprof 分解 |
| FLOW_HOST_MS | **≈104–160ms**（graph build + 188k kernel launch + sync） | 减法 |
| FLOW_KERNELS | **188,565**（单次全链路） | P15C msprof |
| Launch overhead | **~73%** of flow host time | P15C + KERNEL_CANDIDATE_RANKING |

### 分解（P15C_CANN_FLOW_MSPROF.md）

- Device 时间分布：Im2col 42.1% / Transpose 11.0% / Add 8.2% / Mul 5.8% / …
- **仅 5.7% NPU 时间花在真正的矩阵乘**（Cube）；94.3% 是数据搬运 + element-wise + norm。
- 根本症结：**EAGER 模式下 188k 个 kernel 逐一定义/发射/等待**，per-kernel launch+wait
  才是 host 侧的绝对主导（KERNEL_CANDIDATE_RANKING 已在 decode 侧确认同源问题：Mul 16k 次
  × 3.5ms wait = 56s，占总 wait 77.7%）。

### 关键代码事实

- `token2wav-impl.cpp::fmFlowMatchingGGUFModelLoader::forward_chunk`（~line 2685）**每个 chunk
  都重建 ggml 图**：`ggml_init(2048MB)` → `build_forward_chunk_graph` → `ggml_new_graph_custom`
  → `ggml_build_forward_expand` → `ggml_gallocr_alloc_graph` → compute → `ggml_free(ctx)`。
- flow 图是纯 feed-forward（mul_mat / add / soft_max_ext / im2col / silu / gelu / rms_norm），
  **无 FLASH_ATTN_EXT、无图内 sync copy**（D2H/H2D 在 compute 之外的 tensor_set/get）。
- `ggml-cann.cpp::ggml_backend_cann_graph_compute`（~line 2604）：`acl_graph_mode`（env
  `GGML_CANN_ACL_GRAPH`）+ `GGML_CANN_PREFILL_USE_GRAPH` + `GRAPH_MIN_NODES` 共同决定是否
  capture；`graph_lru_cache`（容量 12）按 `node->data`/`src->data` 地址匹配复用。

## Phase 6 — First-Cut 筛选（无自定义 AscendC kernel）

### 硬约束（本轮新发现）

`evaluation/README.md:237` 明确要求 **`GGML_CANN_ACL_GRAPH=off` 必须保持**，否则
"vision encode 阶段可能因非法同步拷贝直接 abort"。该默认值同时存在于 pristine `config.env`，
且 `run_eval.py` 对**所有** task 传递 `GGML_CANN_ACL_GRAPH=off`（lines 142/185/271/322）。

→ **全局开启 ACL graph 被否决**（会破坏 vision encode 精度）。这是候选筛选的决定性约束。

### 候选排序

| Rank | Candidate | 价值 | 风险 | 结论 |
|---|---|---|---|---|
| 1 | **Flow-scoped ACL graph capture**（`GGML_CANN_FLOW_ACL_GRAPH`，仅对 flow 图开 capture） | 高（消 188k launch，flow 202→~76ms） | 中 | **SELECT** |
| 2 | 持久化 flow ggml 图（跨 chunk 缓存 ctx/graph/galloc） | 中（消 50-70ms graph build） | 中高 | 作为 #1 的前提按需做 |
| 3 | 运行时开销（cache aclrtSetDevice 6559 次 / 减 aclrtSynchronizeStream） | 低（累计非 per-chunk） | 低 | SKIP |
| 4 | Operator fusion（aclnnAddRmsNorm） | 低（仅融合 2-op 模式） | 低 | SKIP（已实现，gated） |
| 5 | 全局 `GGML_CANN_ACL_GRAPH=on` | 高 | 高（破坏 vision encode） | **REJECT** |

### 选中候选的机理

1. flow 图（~11740 nodes，含 `GGML_OP_IM2COL` conv、无 `GGML_OP_FLASH_ATTN_EXT`）在
   `ggml_backend_cann_graph_compute` 中被唯一识别 → 强制 `use_cann_graph=true`。
2. 首次 capture 后，`graph_lru_cache` 按地址匹配复用 → 后续 chunk 只 `aclmdlRIExecuteAsync`
   （1 次 launch 替代 188k 次）。
3. vision encode / LLM prefill / decode 仍走 EAGER（`GGML_CANN_ACL_GRAPH=off` 不变），
   精度路径零改动。

### 关键不确定性（决定是否需要 #2 前提）

`graph_lru_cache::matches_cgraph` 以 `node->data`（设备地址）为 key。flow 每个 chunk 用全新
ggml context 重建图 → gallocr 需要 realloc。是否复用相同设备地址取决于 `ggml_dyn_tallocr`
确定性（同 size 同顺序 → 同 offset；buffer `realloc=false` → 同基址）。**倾向稳定，但需实测**。

- 若 cache HIT（地址稳定）→ 仅 #1 一个 ggml-cann.cpp 改动即可。
- 若 cache MISS（每 chunk recapture）→ 追加 #2 持久化图，锁定地址稳定。

## Phase 7 待办

1. ggml-cann.cpp：`GGML_CANN_FLOW_ACL_GRAPH` + IM2COL 识别 + cache HIT/MISS 诊断日志。
2. build + 实测地址稳定性。
3. 按需追加 token2wav 持久化图。
4. 验证：valid text / valid WAV / 0 NaN / no FA regression / 可测 E2E 增益。

## Phase 8 待办

最终官方校验（accuracy + SPEAK→WAV RTF）post-flow-opt。
