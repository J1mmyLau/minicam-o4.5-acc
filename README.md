# MiniCPM-o 4.5 昇腾优化项目

> MiniCPM-o-4_5 on Ascend 910C via llama.cpp-omni — 比赛提交项目
>
> **当前状态 (2026-08-10):** 🟡 FROZEN — 等待官方统一测评分支
>
> 性能优化轮次已完成 (RTF=0.452 LOCAL_BEST_EFFORT)。Accuracy 评测暂停，等官方明天提供统一评测分支后重新跑。

---

## 30 秒版

```text
模型:     MiniCPM-o-4_5-F16.gguf (自研 GGUF 转换)
硬件:     1× Ascend 910C (dual-die, 2× Ascend910 chips)
框架:     llama.cpp-omni (FORK from ggml-org/llama.cpp)
后端:     CANN (Ascend NPU) + CPU fallback for unsupported ops
基线:     051e993 (F16, 性能冻结)
性能:     LOCAL_BEST_EFFORT SPEAK→WAV RTF=0.452 (Flow ∥ Vocoder pipeline)
稳定性:   50-session reuse + 100-round soak → 0 failures
Accuracy: PENDING_OFFICIAL_UNIFIED_EVAL_BRANCH (明天提供)
```

---

## 当前状态矩阵 (2026-08-10)

| 维度 | 状态 | 关键指标 |
|------|------|----------|
| **性能** | ✅ COMPLETE | RTF=0.452 (Flow ∥ Vocoder, OMNI_T2W_PIPELINE_OVERLAP=1) |
| **稳定性** | ✅ COMPLETE | 50-reuse + 100-soak, 0 failures |
| **Demo Text** | ✅ COMPLETE | 30/30 valid Chinese UTF-8 via Gateway |
| **Demo Audio** | ✅ COMPLETE | valid WAV output via Gateway |
| **Accuracy** | ⏸️ FROZEN | 等待明天官方统一测评分支 |
| **WS NaN** | 🔬 TRACED | mel 预处理 160/2400 NaN → 等官方分支验证 |
| **Q8_0 contiguous-y** | 🔬 TRACED | [4096,17] multi-token → CANN 算子限制 → 等官方分支验证 |
| **提交就绪** | ❌ NO | 等官方 Accuracy 结果 |

---

## 分支地图

### 主分支

| 分支 | 用途 | 状态 |
|------|------|------|
| **[main](https://github.com/Phoenix3334/minicpmo45-ascend-private)** | 提交主分支，frozen @ 051e993 | `FROZEN_BASELINE` |
| **[release/final-integration](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/release/final-integration)** | 最终集成候选 | `INTEGRATION` |

### 稳定性修复

| 分支 | 修复内容 | 状态 |
|------|---------|------|
| **[fix/ws-session-lifecycle](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/fix/ws-session-lifecycle)** | WS session 生命周期: CTX_STATE_REUSABLE 重置, drain timeout, 线程泄漏 | `MERGED` |
| **[fix/tts-thread-lifecycle](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/fix/tts-thread-lifecycle)** | TTS 线程生命周期: per-gen active, drain predicate, fault injection | `MERGED` |
| **[fix/full-duplex-request-max-tokens](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/fix/full-duplex-request-max-tokens)** | full_duplex ws_handler 未设置 request_max_tokens → max_tgt_len=0 | `MERGED` |
| **[fix/f003-cann-rope-repeat-interleave](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/fix/f003-cann-rope-repeat-interleave)** | CANN RoPE repeat_interleave 修复 (GPU TTS 启用) | `MERGED` |
| **[fix/ws-multimodal-nan](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/fix/ws-multimodal-nan)** | WS 多模态 NaN logits 调查 (已追踪根因, 修复待定) | `INVESTIGATION` |

### 性能优化

| 分支 | 优化内容 | 状态 |
|------|---------|------|
| **[perf/f6-decode-to-speak](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/perf/f6-decode-to-speak)** | decode→speak 性能优化 (CANN T2W) | `MERGED` |
| **[perf/flow-chunk-rtf](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/perf/flow-chunk-rtf)** | Flow chunk RTF 离线链路 | `COMPLETE` |
| **[perf/kv-cache-production-gates](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/perf/kv-cache-production-gates)** | KV Cache 静态前缀复用 (prefill 2.4× speedup) | `COMPLETE` |
| **[perf/operator-decode-speak](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/perf/operator-decode-speak)** | 算子级 decode→speak 分解 | `COMPLETE` |
| **[perf/ngl8-e2e-stage-profiling](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/perf/ngl8-e2e-stage-profiling)** | NGL8 E2E stage profiling | `COMPLETE` |

### 实验 & 优化分支

| 分支 | 内容 | 状态 |
|------|------|------|
| **[exp/token2wav-cann-runtime](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/exp/token2wav-cann-runtime)** | T2W CANN runtime 放置实验 (FM+CANN) | `EXPERIMENTAL` |
| **[exp/f003-neox-layout](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/exp/f003-neox-layout)** | F003 NeoX layout 实验 | `EXPERIMENTAL` |
| **[exp/f004-precision-ablation](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/exp/f004-precision-ablation)** | F004 precision ablation 实验 | `EXPERIMENTAL` |
| **[opt/r4.2-t2w-trt](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/opt/r4.2-t2w-trt)** | T2W TRT 优化 | `OPTIMIZATION` |
| **[opt/r4.3-vit-trt](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/opt/r4.3-vit-trt)** | ViT TRT 优化 | `OPTIMIZATION` |

### 功能分支

| 分支 | 内容 | 状态 |
|------|------|------|
| **[feat/omni-duplex-r2](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/feat/omni-duplex-r2)** | Omni 全双工 R2 | `FEATURE` |
| **[feat/ascend-cann](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/feat/ascend-cann)** | Ascend CANN backend 适配 | `FEATURE` |
| **[feat/web-server](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/feat/web-server)** | Web 服务器 (HTTP API) | `FEATURE` |
| **[feat/web-demo](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/feat/web-demo)** | Web Demo (Gateway + Worker) | `FEATURE` |
| **[feat/speed-test](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/feat/speed-test)** | 速度测试工具 | `TOOLING` |

### 基准 & 快照

| 分支 | 内容 | 状态 |
|------|------|------|
| **[eval/official-baseline](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/eval/official-baseline)** | 官方基线 (Demo clone @ ba7fa9c) | `BASELINE` |
| **[backup-pre-filter-20260808](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/backup-pre-filter-20260808)** | 2026-08-08 pre-filter 快照 | `SNAPSHOT` |
| **[app](https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/app)** | 应用层 | `APP` |

---

## 阶段推进时间线

### Phase A: F16 校准 (COMPLETE)

```
模型:     F16 (FP32 weight, FP16 act)
RTF:      F16_LOCAL_SPEAK_RTF_MEAN=1.560 (per-chunk old method)
结论:     可靠本地基线建立; 与官方不可直接比较 (timer boundary diff +44%/+132%)
```

### Phase B: Q8_0 量化 A/B (COMPLETE)

```
模型:     Q8_0 (8-bit 权重量化)
RTF:      10.3% SLOWER than F16 (182.7ms/chunk vs 165.5ms)
结论:     CANN 量化路径有损; Q8_0 不会改善性能
根因:     aclnnWeightQuantBatchmatmulV2 瓶颈 (NZ layout ~10%, kernel ~90%)
```

### Phase C: W8A8 量化 Matmul (COMPLETE)

```
技术:     W8A8 (weight + activation 量化) via QuantMatmul + DynamicQuant
性能:     4.76× vs Q8_0 V2 (model-weighted), 但仍慢于 F16 (0.40×)
决策:     ROUTE A — F16 作为主力 MUL_MAT, W8A8 作为 Q8_0 可选优化
文档:     docs/w8a8-cann-quant-matmul.md
```

### Phase 1: 性能优化 (COMPLETE)

```
瓶颈定位:  decode→speak=142ms(2.9%), T2W CPU=4490ms(93%)
关键优化:  CANN T2W 设备放置 (W0 p50 4798→894ms, −81.4%)
          Flow ∥ Vocoder pipeline (601→375ms/window, 1.60×)
          静态前缀 KV Cache 复用 (prefill 206→85ms, 2.4×)
最终 RTF:  0.452 (LOCAL_BEST_EFFORT)
```

### Phase 2: 稳定性 (COMPLETE)

```
50-reuse gate:  50/50 PASS
100-round soak: 100/100 PASS, 0 errors
线程泄漏:       已修复 (libgomp -t4 → 3 threads/session)
WS lifecycle:   CTX_STATE_REUSABLE 正确重置
Drain timeout:  CV notify 替代 polling
```

### Phase 3: Demo 路径 (COMPLETE)

```
Demo Text:   30/30 valid Chinese UTF-8 (Gateway→Worker→Backend)
Demo Audio:  valid WAV via Gateway
Demo Video:  CONDITIONAL PASS (WS NaN blocks full chain)
UTF-8 Fix:   SSE worker-once + sink.done 修复
```

### Phase 4: 最终收口 (COMPLETE)

```
F16 候选冻结: 051e993 (binary SHA: 768614ab)
最终 Gate 表: FINAL_GATE_CLOSURE — 4 phases complete
提交骨架:     docs/competition-submission/
vLLM 迁移:    docs/vllm-migration/ (10 个迁移文档)
```

### Phase 5: Accuracy (🟡 FROZEN)

```
状态:         PENDING_OFFICIAL_UNIFIED_EVAL_BRANCH
Daily-Omni:   40% single-frame (INVALID as final — 非统一评测路径)
TTS-Seed:     BLOCKED (WS NaN)
VideoMME:     BLOCKED (WS NaN)
NaN 根因:     已追踪至 mel 预处理 (160/2400 NaN)
Q8_0 错误:    [4096,17] contiguous-y → CANN 算子限制
明天计划:     拉官方统一分支 → 先 F16 → 再 Q8_0 → 重新评估
```

---

## 性能指标

### F16 最终候选 (051e993)

```
SPEAK→WAV RTF (LOCAL_BEST_EFFORT):  0.452
  └─ Flow ∥ Vocoder pipeline:       1.60× speedup
  └─ CANN T2W placement:            −81.4% W0 latency
  └─ KV Cache static prefix:        2.4× prefill speedup
  └─ -t4 thread config:             optimal (vs -t8 14% slower decode)

Sub-components (per chunk):
  LLM decode:      ~142ms (2.9%)
  T2W (Flow):      ~189ms (CANN)
  T2W (Vocoder):   ~432ms (CPU)
  Prefill:         ~85ms (KV cache hit)
```

### 硬件

```
平台:     1× Ascend 910C (dual-die)
芯片:     2× Ascend910 chips
CANN:     Community Edition 8.5.0.alpha002
驱动:     固件 xxx
NPU 内存:  ~60GB HBM
```

---

## 快速开始

### 构建

```bash
cd /workspace/llama.cpp-omni-session-fix
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON
cmake --build . --target llama-omni-server -j$(nproc)
```

### 启动服务 (F16 候选)

```bash
OMNI_T2W_PIPELINE_OVERLAP=1 \
OMNI_T2W_DEVICE=cann-flow-only \
build/bin/llama-omni-server \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf \
  --host 127.0.0.1 --port 18094 \
  -ngl 999 --device CANN0 \
  --ctx-size 4096 --batch-size 512 --ubatch-size 512 \
  --split-mode layer -t 4
```

### 环境变量参考

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OMNI_T2W_PIPELINE_OVERLAP=1` | 0 | Flow ∥ Vocoder 并行 |
| `OMNI_T2W_DEVICE=cann-flow-only` | (空) | T2W Flow 放 CANN |
| `OMNI_T2W_DRAIN_TIMEOUT_MS=5000` | 自动 | T2W drain 超时 |
| `OMNI_NAN_DIAG=1` | 0 | NaN 诊断追踪 |
| `OMNI_T2W_QUEUE_DIAG=1` | 0 | T2W 队列诊断 |
| `OMNI_ENCODING_DIAG=1` | 0 | UTF-8 编码诊断 |
| `GGML_CANN_W8A8=1` | 0 | W8A8 量化 MatMul (opt-in) |
| `OMNI_KV_CACHE_REUSE=1` | 0 | 静态前缀 KV Cache 复用 |

---

## 文档索引

### 性能 & 优化

| 文档 | 内容 |
|------|------|
| [F6 Phase2 Step6 CANN T2W A/B](docs/F6_PHASE2_STEP6_CANN_T2W_AB.md) | CANN T2W 设备放置 A/B 详细 |
| [F6 Phase2 Step3 Decode-Speak 分解](docs/F6_PHASE2_STEP3_DECODE_SPEAK_BREAKDOWN.md) | decode→speak 子组件分解 |
| [F6 Phase2 Baseline Device Audit](docs/F6_PHASE2_BASELINE_DEVICE_AUDIT.md) | 基线设备放置审计 |
| [W8A8 CANN Quant Matmul](docs/w8a8-cann-quant-matmul.md) | W8A8 量化 MatMul 完整指南 (Phase C) |
| [F6 S13 Final Gate Closure](docs/F6_S13_FINAL_GATE_CLOSURE.md) | 最终 Gate 收口 |

### 稳定性 & Bug

| 文档 | 内容 |
|------|------|
| [WS NaN Investigation](docs/ws-nan-investigation.md) | WS 多模态 NaN logits 调查报告 (2026-08-10) |
| [F6 Thread Exhaustion Root Cause](docs/f6-thread-exhaustion-root-cause.md) | 线程泄漏根因 (如引用在 memory) |

### vLLM 迁移 (给接手 vLLM-Omni 的人)

| 文档 | 内容 |
|------|------|
| [vLLM Migration README](docs/vllm-migration/README.md) | 入口：30s 版 / 10min 版 / 关键约定 |
| [Llama-to-vLLM 经验迁移](docs/vllm-migration/LLAMA_TO_VLLM_EXPERIENCE_MIGRATION.md) | 12 条核心经验 + 决策树 |
| [Llama ↔ vLLM 组件映射](docs/vllm-migration/LLAMA_VLLM_COMPONENT_MAPPING.md) | 13 个组件逐一映射 + 源码导航 |
| [vLLM 优化执行计划](docs/vllm-migration/VLLM_OPTIMIZATION_EXECUTION_PLAN.md) | 动手路线 V0–V12 |
| [vLLM 风险与验证矩阵](docs/vllm-migration/VLLM_RISK_AND_VALIDATION_MATRIX.md) | 16 证据 + 25 风险 + 候选决策 |
| [vLLM 团队交接](docs/vllm-migration/VLLM_TEAM_HANDOFF.md) | 第一周计划 + 最终交付清单 |
| [Llama 原始证据附录](docs/vllm-migration/LLAMA_RAW_EVIDENCE_APPENDIX.md) | llama 所有数字的出处 |
| [实验模板](docs/vllm-migration/EXPERIMENT_TEMPLATES.md) | 4 种实验模板 |

### 比赛提交

| 文档 | 内容 |
|------|------|
| [STATUS.md](STATUS.md) | 实时项目状态 |

---

## 提交仓库

```bash
# 官方上游 (只读)
origin:     https://github.com/tc-mb/llama.cpp-omni.git
origin-ssh: git@ssh.github.com:tc-mb/llama.cpp-omni.git

# 私有工作仓库 (推送)
private:    ssh.github.com:Phoenix3334/minicpmo45-ascend-private.git
           (认证: ~/.ssh/minicpmo45_ascend_private deploy key, port 443)
```

---

## 明天行动计划

1. 拉取官方统一测评分支
2. 记录官方 commit SHA
3. 按官方命令不变运行
4. F16 先跑 → Accuracy baseline
5. Q8_0 再跑
6. 重新评估：
   - Daily-Omni / VideoMME / TTS-Seed
   - WS NaN (OMNI_NAN_DIAG=1)
   - Q8_0 contiguous-y 错误
7. 只有在官方分支上复现的 bug 才升级为提交阻塞项

---

> 项目冻结时间: 2026-08-10 | 基线: 051e993 | 状态: `WAIT_OFFICIAL_UNIFIED_EVAL_BRANCH`
