# CANN KV Cache 放置审计

> **源码**: `src/llama-kv-cache.cpp`, `src/llama-context.cpp`, `src/llama-cparams.h`, `tools/omni/omni.cpp`, `tools/omni/voxcpm2/voxcpm2_llm.cpp`
> **冻结 commit**: `bdd4550`

---

## 1. KV Cache 实例清单

MiniCPM-o 4.5 在 llama.cpp-omni 中有 **2 个独立的 `llama_context`**，每个有自己独立的 KV cache：

| # | Owner | 创建函数 | Context 变量 | Backend | `offload_kqv` | K/V Tensor 位置 | Capacity (`n_ctx`) | Reset 时机 |
|---|-------|---------|-------------|---------|---------------|-----------------|-------------------|-----------|
| 1 | 主 LLM | `llama_new_context_with_model(model, ctx_params)` | `ctx_omni->ctx_llama` | CANN | `true` | CANN buffer | `params->n_ctx` | 模式切换 (`memory_clear`) / 滑窗 (`seq_rm`) |
| 2 | TTS 子模型 | `llama_new_context_with_model(tts_model, tts_ctx_params)` | `ctx_omni->ctx_tts_llama` | CANN | `true` | CANN buffer | `params->n_ctx` | 每次 TTS chunk 生成后 |

**非 KV cache 的模型组件**（无 KV cache，不需要在此审计中展开）:

| 组件 | 类型 | Backend | 说明 |
|------|------|---------|------|
| Vision encoder (`vision_ctx`) | CNN | CPU (n_threads) / GPU | 无 attention，无 KV cache |
| Audio encoder (`audition_ctx`) | CNN | CPU (n_threads) | 无 attention，无 KV cache |
| Projector (`projector_model`) | MLP (2-layer) | CPU or GPU (by `GGML_USE_CANN`) | 无 attention，无 KV cache |
| T2W Flow/Vocoder | DiT + HiFi-GAN | CANN NPU（F6 Phase 2 后） | 无 attention / 有 cross-attn cache（非 llama_kv_cache） |

**关于"Talker KV"**: 在 `tools/omni/omni.cpp` 中，"Talker" 不是独立模型——它是主 LLM（`ctx_omni->ctx_llama`）在 TTS 模式下的文本生成阶段。Talker 的 token 生成复用主 LLM 的 KV cache（#1）。不存在独立的第三套 KV cache。

---

## 2. `offload_kqv` 机制

### 2.1 默认值

```cpp
// src/llama-cparams.h:34
struct llama_cparams {
    bool offload_kqv;  // 是否将 KV cache offload 到 GPU
};

// src/llama-context.cpp:70
cparams.offload_kqv = params.offload_kqv;  // 从用户参数读取

// src/llama-context.cpp:3362 (llama_context_default_params)
/*.offload_kqv = */ true,  // 默认开启

// tools/omni/voxcpm2/voxcpm2_llm.cpp:45
cparams_local.offload_kqv = true;  // VoxCPM2 显式开启
```

### 2.2 生效路径

```cpp
// src/llama-context.cpp:342
cparams.offload_kqv && !model.has_tensor_overrides()
```

当 `offload_kqv = true` 时: KV cache K/V tensor 的 buffer type 跟随 device backend（CANN）。

### 2.3 `offload_kqv = false` 的行为

KV cache tensor 分配在 CPU host memory → 每次 attention 需要 H2D 拷贝 K/V → 大量 PCIe 带宽消耗。在 CANN 上，`caps.async=false` → 拷贝必须 sync → 延迟显著增加。冻结候选未使用此路径。

---

## 3. KV Cache 内部结构

### 3.1 Multi-Backend Buffer 共存

```cpp
// src/llama-kv-cache.cpp:108
// 每种 buffer type 创建一个独立的 ggml context
std::map<ggml_backend_buffer_type_t, ggml_context_ptr> ctx_map;

auto ctx_for_buft = [&](ggml_backend_buffer_type_t buft) -> ggml_context * {
    // 为不同 buffer type 维护独立的 ggml context
};
```

- **CANN buffer type** → K/V tensor 的 ggml context（在 NPU HBM）
- **CPU buffer type** (`ggml_backend_cpu_buffer_type()`) → 元数据/索引的 ggml context（在 Host RAM）

### 3.2 内存布局

| 数据 | Buffer Type | 大小估算 |
|------|------------|---------|
| K cache | CANN | `n_layer × n_ctx × n_embd_head × n_head_kv × sizeof(fp16)` |
| V cache | CANN | 同上 |
| Cell 状态 | CPU (meta) | ~MB |
| Seq 映射 | CPU (meta) | ~KB |
| Head 管理 | CPU (meta) | ~KB |

**大块 K/V 在 NPU**（attention 计算延迟低），**小块元数据在 CPU**（调度逻辑访问方便）。

---

## 4. 静态 Prefix Cache（F6 Phase 3 产物）

```
第一次请求:
  prefetch prompt → prefill (CANN) → KV cache 写入 CANN → SAVED

后续请求 (KV HIT):
  跳过 prefill → 从 CANN buffer 加载 prefix KV → 仅在 prefix 后 decode token
```

**KV cache 始终在 CANN 上**：复用不需要 D2H/H2D 拷贝。这就是 prefill 从 MISS=210ms 降到 HIT=86ms p50（2.5× 加速）的原因（F6 S13 Step 8, 30-pair A/B）。

---

## 5. KV Cache 操作与 RTF 关系

| 操作 | 频率 | 是否在 chunk 关键路径 | Backend | 开销 |
|------|------|----------------------|---------|------|
| K/V 写入（decode token） | 每个 token | **是** | CANN（内部） | ~ns |
| K/V 读取（attention） | 每个 token | **是** | CANN（内部） | ~ns |
| seq_rm（滑窗） | 每次滑窗触发 | 否（非 chunk 时机） | CANN（原位操作） | ~μs-ms |
| memory_clear | 模式切换 | 否 | CANN（原位操作） | ~ms |
| memory_save（静态 prefix） | 每类 prompt 首次 | 否（prefill 完成时） | CANN（内部） | ~ms |

K/V 写入和读取都在 CANN NPU 内部完成，不经过 PCIe。**KV cache 操作不是 per-chunk RTF 的瓶颈**（静态结论，基于源码路径，未运行时测量）。

---

## 6. 多 Context 隔离

```
ctx_llama (LLM):
  → llama_kv_cache (CANN NPU device 0)
  → KV dim: [n_layer, n_ctx, n_embd_head, n_head_kv]

ctx_tts_llama (TTS):
  → llama_kv_cache (CANN NPU device 0，独立 buffer)
  → KV dim: 较小（TTS 子模型层数/维度更小）

它们在同一 NPU 上但 buffer 完全隔离。
```

**内存占用**（估算）:
- LLM 权重: ~16 GB (F16)
- LLM KV cache: ~2 × n_layer × n_ctx × n_embd_head × n_head_kv × 2 bytes
- TTS 权重: ~数百 MB
- TTS KV cache: 类似但更小
- T2W/Flow/Vocoder 权重: ~数百 MB
- 中间 activation tensor: ~数百 MB（受 `n_batch`/`n_ubatch` 限制）

在一张 910C (64 GB HBM) 上绰绰有余。

---

## 7. CANN 特有考量

- **No unified memory**: CANN buffer 是纯 device memory。CPU 无法直接访问 CANN 上的 KV cache。需要读取时（如 debug dump），必须显式 `aclrtMemcpy` D2H。
- **Dual-die**: 910C 双 die 共享 HBM，KV cache 在 HBM 上，两个 die 都可以访问。
- **ACL Graph 兼容**: CANN graph capture 会捕获 attention kernel 的 KV 读写。KV cache 的 buffer 指针在 graph 中固定，不能跨 graph capture 重新分配。
