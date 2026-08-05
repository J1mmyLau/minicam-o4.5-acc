# MiniCPM-o 4.5 on Ascend 910C

本仓库基于 [llama.cpp-omni](https://github.com/ggml-org/llama.cpp)，记录 MiniCPM-o 4.5 在单卡
Ascend 910C + CANN 9.1.0-beta.1 环境下的推理部署、性能分析、设备迁移、生命周期修复和比赛交付工作。

上游原始 README 保存在 [`docs/upstream/LLAMA_CPP_OMNI_README.md`](docs/upstream/LLAMA_CPP_OMNI_README.md)。

---

## 项目状态

| 项 | 值 |
|---|-----|
| 冻结候选源码 | `bdd4550`（`f6-candidate-source-bdd4550` tag → `80c30cd`） |
| 文档 HEAD | `5df2add`（`f6-handoff-5df2add` tag） |
| `FINAL_INTERNAL` | **PASS** |
| `REPRODUCIBLE_BINARY` | **PASS**（server `db258375` / libomni `c4b16937`） |
| T6 集成回归 | **11/11 PASS**（S13 120/120, Extended 30/30, Voice 5/5, Disconnect 5/5, KV A/B 28/30, Smoke 5/5） |
| 安全审计 | **CLEAN**（0 secrets, 0 tokens, 0 credentials） |
| 官方 Gates | **BLOCKED_BY_OFFICIAL_STARTER_KIT** |
| `COMPETITION_COMPLETE` | **NOT_CLAIMED** |

---

## 核心内部结果

> 以下结果均为 **INTERNAL** 验证指标，不等同于官方 per-chunk RTF 或完整请求 E2E。
> 完整实验口径和原始证据见 [`docs/F6_OPTIMIZATION_AND_RESULTS.md`](docs/F6_OPTIMIZATION_AND_RESULTS.md)。

### Request-to-first-WAV（CANN T2W 设备迁移）

| 指标 | Baseline | Candidate | 变化 |
|---|---:|---:|---:|
| Request→W0 p50 | 4,798 ms | 894 ms | **−3,904 ms (−81.4%)** |
| 样本 | 32 pairs | 32 pairs | 同 binary / 硬件 / 模型 / 输入 |
| CI95 (bootstrap) | — | [−4,220, −3,732] ms | 不含 0 |

- **计时口径**: HTTP request arrival → 首个 WAV 文件 mtime（wall clock）
- **方案**: env-only 配置（`OMNI_T2W_DEVICE=cann-flow-only`, `OMNI_VOC_DEVICE=gpu`），零源码修改
- **标签**: `HISTORICAL_INTERNAL_RESULT` — 不是官方 chunk RTF，不是完整请求 E2E，不是 vLLM 结果
- **证据**: [`docs/F6_PHASE2_STEP6_CANN_T2W_AB.md`](docs/F6_PHASE2_STEP6_CANN_T2W_AB.md)

### Static Prefix KV Cache（Prefill 加速）

| 指标 | MISS（无 cache） | HIT（有 cache） | 变化 |
|---|---:|---:|---:|
| Prefill p50 | 206 ms | 85 ms | **−121 ms (−58.7%, 2.4×)** |
| 样本 | 30 pairs | 30 pairs | strict matched |
| CI95 (bootstrap) | — | [37, 249] ms | 不含 0 |

- **方案**: 首次 prefill → save KV to CANN buffer → 后续请求 skip prefill
- **使用**: `OMNI_KV_CACHE_REUSE=1`（opt-in, default off）
- **标签**: `INTERNAL_PREFILL_STAGE_RESULT`
- **证据**: [`docs/tracking/f6_lifecycle/R13_CANONICAL_STATIC_PREFIX_AB_FINAL.md`](docs/tracking/f6_lifecycle/R13_CANONICAL_STATIC_PREFIX_AB_FINAL.md)

---

## 系统链路

```mermaid
graph LR
    Client[Client] -->|HTTP/SSE| Server[llama-omni-server]
    Server -->|token| MainLLM[Main LLM<br/>CANN NPU]
    MainLLM -->|text delta| SSE[SSE Response]
    MainLLM -->|<|speak|>| Talker[Talker<br/>CANN NPU]
    Talker -->|speech tokens| T2WQueue[T2W Queue]
    T2WQueue --> Flow[Flow Model<br/>CANN NPU]
    Flow --> Vocoder[Vocoder<br/>CANN NPU]
    Vocoder -->|WAV chunk| Client
```

| 组件 | 设备 | 说明 |
|------|------|------|
| Main LLM（decode） | CANN NPU | 主模型 token 生成 |
| Talker | CANN NPU | `<\|speak\|>` 触发 TTS，复用主 LLM KV cache |
| Flow Model | CANN NPU | DiT transformer: token → mel spectrogram |
| Vocoder | CANN NPU | HiFi-GAN: mel spectrogram → waveform |
| Control / metadata / output assembly | Host CPU | Sampler, Tokenizer, HTTP response |

CANN 设备放置审计详见 [`docs/audit/CANN_CPU_NPU_PLACEMENT_AUDIT.md`](docs/audit/CANN_CPU_NPU_PLACEMENT_AUDIT.md)。

---

## 主要优化

| 优化 | 问题 | 方案 | 状态 | 文档 |
|------|------|------|------|------|
| CANN T2W | Flow+Vocoder 在 CPU，占 W0 93% | env-only 配置，零源码修改 | **ACCEPT** | [link](docs/F6_PHASE2_STEP6_CANN_T2W_AB.md) |
| Static Prefix KV Cache | 每次 prefill 210ms | 首次 save → 后续 load skip | **ACCEPT** (opt-in) | [link](docs/tracking/f6_lifecycle/R13_CANONICAL_STATIC_PREFIX_AB_FINAL.md) |
| Persistent server lifecycle | Drain timeout 导致 ctx 失效 | 修复 drain / timeout / ctx validity | **ACCEPT** | [link](docs/tracking/F6_C6_PROFILE_LIFECYCLE_STATE_MACHINE.md) |
| Per-generation active accounting | 跨请求 polling 竞争 | active_t2w_generation per-generation | **ACCEPT** | [link](docs/tracking/) |
| TTS KV bounds guard | n_past 可达 n_ctx 上限 | cap prefill_with_emb_tts at 256 | **ACCEPT** | [link](docs/tracking/) |
| Text non-streaming fix | 非流式响应缺 text 字段 | 补充 text 输出 | **ACCEPT** | [link](docs/tracking/) |
| SSE crash fix | bad_alloc + sink.done after worker exit | worker-once + sink.done guard | **ACCEPT** | [link](docs/tracking/) |
| Media / prefill protocol fix | media_type=2 / user_text 格式 | prompt 身份 + think-loop 修复 | **ACCEPT** | [link](docs/f6-s13-closure/) |
| T6 集成回归 | 全 Gate 冻结 binary 确认 | 11/11 gates, 0 cpu_fallback, 0 cann_error | **ACCEPT** | [link](docs/f6-s13-closure/phase2/T6_INTEGRATED_REGRESSION_REPORT.md) |

---

## 快速开始

```bash
# 环境变量
export OMNI_T2W_DEVICE=cann-flow-only
export OMNI_VOC_DEVICE=gpu
export OMNI_KV_CACHE_REUSE=1
export ASCEND_RT_VISIBLE_DEVICES=0

# 启动 server
./build/bin/llama-omni-server \
  -m "${MODEL_PATH}/MiniCPM-o-4_5-F16.gguf" \
  -ngl 999 -fa off -c 4096 -b 512 -ub 512 \
  --split-mode layer --device CANN0 \
  --no-mmap --mlock \
  --port 18093

# 健康检查
curl -s "http://127.0.0.1:18093/health" | head -c 200

# 冒烟测试
# 发送 OAI chat/completions 请求（含 system prompt + user text）
# 参考 scripts/f6_phase3_t6_integrated_regression.py
```

详细步骤见 [`docs/F6_QUICKSTART.md`](docs/F6_QUICKSTART.md) 和 [`docs/F6_REPRODUCTION_GUIDE.md`](docs/F6_REPRODUCTION_GUIDE.md)。

---

## 文档导航

| 阅读目标 | 时间 | 文档 |
|----------|------|------|
| 项目全貌 | 5 min | [`docs/F6_README.md`](docs/F6_README.md) |
| 快速启动 + 优化结果 | 15 min | [`docs/F6_QUICKSTART.md`](docs/F6_QUICKSTART.md), [`docs/F6_OPTIMIZATION_AND_RESULTS.md`](docs/F6_OPTIMIZATION_AND_RESULTS.md) |
| 架构 + 方法论 | 30 min | [`docs/F6_ARCHITECTURE.md`](docs/F6_ARCHITECTURE.md), [`docs/F6_METHODOLOGY.md`](docs/F6_METHODOLOGY.md) |
| 完整复现 | 1-2 h | [`docs/F6_REPRODUCTION_GUIDE.md`](docs/F6_REPRODUCTION_GUIDE.md), [`docs/F6_EVIDENCE_INDEX.md`](docs/F6_EVIDENCE_INDEX.md) |
| 比赛状态 | 10 min | [`docs/F6_LIMITATIONS_AND_OFFICIAL_GATES.md`](docs/F6_LIMITATIONS_AND_OFFICIAL_GATES.md), [`docs/competition-submission/`](docs/competition-submission/) |
| CANN 审计 | 30 min | [`docs/audit/CANN_CPU_NPU_PLACEMENT_AUDIT.md`](docs/audit/CANN_CPU_NPU_PLACEMENT_AUDIT.md) |
| vLLM 迁移 | 30 min | [`docs/vllm-migration/`](docs/vllm-migration/) |

---

## 仓库结构

```text
src/                  llama.cpp 核心源码（llama.cpp, llama-context, kv-cache 等）
tools/
  server/             HTTP/SSE server（llama-omni-server）
  omni/               Omni 推理引擎（talker, token2wav, prefill 协议）
ggml/src/ggml-cann/   CANN NPU backend（Ascend 910C）
examples/             llama.cpp 上游示例
docs/
  F6_*.md             8 份项目文档（README, Quickstart, Architecture, Results, Methodology,
                      Reproduction, Limitations, Evidence）
  audit/              CANN 放置审计（5 文件）
  f6-s13-closure/     S13 收口证据（223 文件）
  tracking/           实验追踪与决策记录（109 文件）
  competition-submission/  比赛提交工具链
  vllm-migration/     vLLM-Omni 迁移文档（10 文件）
  upstream/           上游 llama.cpp-omni README
submission/           提交脚本与配置（36 文件）
release/              交付归档（tarballs, SHA256SUMS）
```

---

## 版本与 Tag

| Tag | 指向 | 含义 |
|-----|------|------|
| `f6-candidate-source-bdd4550` | `80c30cd` | 冻结候选源码（源文件等价于原始 `bdd4550`，仅移除了误提交的 profiling 数据） |
| `f6-handoff-5df2add` | `5df2add` | 交接文档 HEAD（含全部文档、审计、工具链） |
| `f6-timing-instrumentation-pass-20260730` | (historical) | 计时打点 checkpoint |

- `bdd4550` 是原始冻结候选 commit；`80c30cd` 是经 `git filter-branch` 移除大文件后的等价 commit。
- 所有源码文件内容完全一致。仅 `profiles/decode-speak/` 被移除（超出 GitHub 100MB 限制）。
- `5df2add` = 当前 `perf/f6-decode-to-speak` 分支 HEAD。

---

## 已知限制

### 官方评测未运行

| Gate | 状态 |
|------|------|
| Official Daily-Omni | `NOT_RUN` |
| Official TTS-Seed | `NOT_RUN` |
| Official Video-MME | `NOT_RUN` |
| Official Demo | `NOT_RUN` |
| Official per-chunk RTF | `NOT_RUN` |

全部 `BLOCKED_BY_OFFICIAL_STARTER_KIT`。

### CANN 设备放置

| 项 | 状态 |
|----|------|
| `CANN_STATIC_CAPABILITY_AUDIT` | **PASS** |
| `MAIN_LLM_STATIC_PLACEMENT` | **PASS** |
| `MAIN_LLM_RUNTIME_PLACEMENT` | **PARTIAL**（缺 profiler 证据） |
| `CPU_PER_CHUNK_CRITICAL_PATH` | **TO_MEASURE** |
| `GRAPH_SPLIT_RUNTIME_COUNT` | **NOT_MEASURED** |
| `STREAM_SYNC_RUNTIME_COST` | **NOT_MEASURED** |
| `D2H_COST` | **NOT_MEASURED** |
| `MAIN_LLM_CPU_FALLBACK_OBSERVED` | **NO**（不等于证明无 fallback） |

完整内容见 [`docs/F6_LIMITATIONS_AND_OFFICIAL_GATES.md`](docs/F6_LIMITATIONS_AND_OFFICIAL_GATES.md)。

---

## 模型与大文件

本仓库 **不包含**:

- 模型权重（MiniCPM-o-4_5-F16.gguf, ~16 GB）
- 编译产物（build/, *.so, *.o）
- 音频文件（profiles/decode-speak/ — 已在 git history 中移除）
- Demo 视频
- 官方 Benchmark 结果

模型 SHA256 验证方式见 [`docs/F6_QUICKSTART.md`](docs/F6_QUICKSTART.md)。

---

## 上游与许可证

本项目基于 [llama.cpp](https://github.com/ggml-org/llama.cpp) 和
[llama.cpp-omni](https://github.com/ggml-org/llama.cpp-omni)，
保留 MIT License（[`LICENSE`](LICENSE)）。

上游原始 README: [`docs/upstream/LLAMA_CPP_OMNI_README.md`](docs/upstream/LLAMA_CPP_OMNI_README.md)。

模型: [MiniCPM-o 4.5](https://github.com/OpenBMB/MiniCPM-o) by ModelBest & Tsinghua University。

---

> **INTERNAL_COMPETITION_HANDOFF** — 本仓库为内部比赛交接状态，不代表官方最终提交。
> `COMPETITION_COMPLETE=NOT_CLAIMED`。
