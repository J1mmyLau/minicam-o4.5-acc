# F6 已知限制与官方 Gate 状态

> **候选源码**: `bdd4550` | **状态**: `FINAL_INTERNAL`
> 本文档"已知限制"严格区分已内部验证 vs 未验证 vs 被阻塞，不做不可验证的宣称。

---

## 1. 总体边界

```
┌─────────────────────────────────────────────────────────────────┐
│                       F6 内部冻结范围                             │
│                                                                  │
│  ✅ 已内部证明:                                                   │
│     - CANN T2W 设备放置 (Request→W0 p50 −81.4%, n=32, HISTORICAL_INTERNAL_RESULT)   │
│     - Static Prefix KV Cache (Prefill 2.4×)                     │
│     - Persistent 生命周期 (多请求复用)                             │
│     - TTS KV bounds guard                                        │
│     - Text + SSE 稳定性                                          │
│     - 二进制可复现构建                                             │
│                                                                  │
│  ⚠️ 内部已验证但样本/条件受限:                                     │
│     - Daily-Omni pilot (6/6 server gates, 非全量)                │
│     - G7 稳定性 (797 chunks, 30min)                              │
│                                                                  │
│  ❌ 未证明 / 未运行:                                              │
│     - 官方 Daily-Omni 准确率                                      │
│     - 官方 TTS-Seed 指标                                          │
│     - 官方 Video-MME 指标                                         │
│     - 官方 SPEAK→WAV RTF                                          │
│     - 多用户并发                                                   │
│     - 长稳 24h+                                                   │
│     - MTP (multi-token prediction)                               │
│                                                                  │
│  ⛔ 不适用 / 不可达:                                               │
│     - CANN async compute (caps.async=false)                      │
│     - CANN pipeline parallel (无硬件支持)                          │
│     - FLASH_ATTN_EXT F32/BF16 (双重 dtype 检查 bug)              │
│     - CUDA-specific 优化 (Graph replay 等)                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 详细限制

### 2.1 硬件/平台限制

| 限制 | 详情 | 影响 | 状态 |
|------|------|------|------|
| CANN 9.1.0-beta.1 `caps.async=false` | 无通用异步计算流水，无 pipeline parallel | 主 LLM decode + T2W 串行，无法 overlap | **硬件/驱动限制，非代码** |
| CANN 9.1.0-beta.1 `caps.events=true` | 有 event 支持但不用于计算流水 | 仅同步点可用 event | 平台限制 |
| 910C 单卡 dual-die | 无跨卡通信 (NVLINK/RDMA) | 多卡扩展不适用 | 固定部署 |
| FLASH_ATTN_EXT 仅 F16 Q/K/V | `ggml-cann.cpp:2789` 双重 dtype 检查 | F32/BF16 attention 走 CPU fallback | **已知 bug，未修复 (冻结)** |
| ACL graph 仅 decode | `graph_compute` min_nodes=100, seq_len=1 | Prefill 不使用 graph 加速 | 设计限制 |

### 2.2 软件/功能限制

| 限制 | 详情 | 状态 |
|------|------|------|
| SSE + `use_tts=true` 有边界条件 | duplex/slide 交互复杂度下已知边界 | `INTERNAL` (T9 fix 已覆盖主要路径) |
| Whisper 音频编码输入上限 | ~24-26s 音频 (内部 pilot 观察值) | 待官方 whisper 组件验证 |
| 单会话并发 | 非多用户并发优化，无 request queue multiplexing | 设计范围外 |
| 非流式 text 输出 | T9 fix 后已修复，但不保证所有 edge case | `INTERNAL` |
| Static Prefix KV 为 OPT_IN | `OMNI_KV_CACHE_REUSE=1` 手动开启，非 DEFAULT_ON | 设计决策 |
| Duplex 模式 | 交互式语音对话，测试覆盖有限 | `INTERNAL` (Duplex 5/5 basic PASS) |

### 2.3 模型/精度限制

| 限制 | 详情 | 状态 |
|------|------|------|
| 模型仅 MiniCPM-o-4_5-F16.gguf | 无其他模型尺寸/量化变体的验证 | 固定模型 |
| Daily-Omni 音频识别准确率 | 内部 pilot whisper ceiling ~24-26s, daily-omni audio = "?" | `INTERNAL_PILOT_ONLY` |
| TTS 音质 | 仅 16-bit PCM @24kHz WAV 有效性确认，无 MOS 评测 | 未运行主观评测 |
| Image + Audio 多模态组合 | think-loop 格式 fix 后基本通畅，全组合未穷尽 | `INTERNAL` |

### 2.4 证据/测量限制

| 限制 | 详情 | 状态 |
|------|------|------|
| `STREAM_SYNC_RUNTIME_COST` | 冻结 binary 未测量 aclrtSynchronizeStream 耗时 | `NOT_MEASURED` |
| `D2H_COST` | 冻结 binary 未测量 logits/hidden D2H 拷贝耗时 | `NOT_MEASURED` |
| `CPU_PER_CHUNK_CRITICAL_PATH` | 未完成逐 chunk Amdahl 判定 | `TO_MEASURE` |
| msprof 历史数据 | 2026-07-28 旧 commit, CANN 9.0 era，不等同于 bdd4550 | `HISTORICAL_REF_ONLY` |
| G7 稳定性数据 | pre-bdd4550 旧版本，非冻结 binary | `HISTORICAL_REF_ONLY` |

---

## 3. 官方 Gate 状态

### 3.1 Gate 总表

| Gate | 状态 | 阻塞原因 | 预期解阻塞条件 |
|------|------|---------|--------------|
| **Gate 0**: CANN LLM 主模型 decode | `INTERNAL_PASS` | — | — |
| **Gate 1**: CANN T2W (Flow+Vocoder) | `INTERNAL_PASS` | — | — |
| **Gate 2**: Persistent 生命周期 | `INTERNAL_PASS` | — | — |
| **Gate 3**: Static Prefix KV Cache | `INTERNAL_PASS` | — | — |
| **Gate 4**: T6 集成回归 (11/11) | `INTERNAL_PASS` | — | — |
| **Gate 5**: Daily-Omni 内部 pilot (6/6) | `INTERNAL_PASS` | — | — |
| **Gate 6**: 二进制可复现构建 | `INTERNAL_PASS` | — | — |
| **Gate 7**: 提交工具链 | `INTERNAL_PASS` | — | — |
| **Gate 8**: CANN CPU/NPU 放置审计 | `INTERNAL_PASS` (static) | — | `CPU_PER_CHUNK_CRITICAL_PATH=TO_MEASURE` |
| **Official A**: Daily-Omni 准确率 | `NOT_RUN` | `BLOCKED_BY_OFFICIAL_STARTER_KIT` | 官方 harness + 测试集到达 |
| **Official B**: TTS-Seed 指标 | `NOT_RUN` | `BLOCKED_BY_OFFICIAL_STARTER_KIT` | 官方 harness + 测试集到达 |
| **Official C**: Video-MME 指标 | `NOT_RUN` | `BLOCKED_BY_OFFICIAL_STARTER_KIT` | 官方 harness + 测试集到达 |
| **Official D**: Demo | `NOT_RUN` | `BLOCKED_BY_OFFICIAL_STARTER_KIT` | 官方 Demo 前端 + API 规范 |
| **Official E**: SPEAK→WAV RTF | `NOT_RUN` | 官方 harness 未到达 + parser 需 SPEAK 阶段分类升级 | 见 RTF_PARSER_AUDIT.md |

### 3.2 官方 Gate 执行流程 (待 unblock)

```
BLOCKED_BY_OFFICIAL_STARTER_KIT → 官方 harness 到达
    │
    ├── Step 1: Gate --dry-run (全部 rc=0)
    │     ├── run_daily_omni.sh --dry-run
    │     ├── run_tts_seed.sh --dry-run
    │     ├── run_video_mme.sh --dry-run
    │     └── run_demo.sh --dry-run
    │
    ├── Step 2: baseline + candidate 对称采集
    │     ├── RUN_ID=<id> run_*.sh baseline (官方基线 binary)
    │     └── RUN_ID=<id> run_*.sh candidate (bdd4550, db258375)
    │
    ├── Step 3: 对称性检查
    │     └── check_baseline_candidate_symmetry.py (同条件校验)
    │
    └── Step 4: 结果汇总
          └── 仅当全部 PASS 后 COMPETITION_COMPLETE=CLAIMED
```

### 3.3 内部 vs 官方标签纪律

| 标签 | 含义 | 可用于 |
|------|------|--------|
| `INTERNAL_PASS` | 内部验证通过 | 内部追踪、文档说明、历史记录 |
| `LLAMA_CONFIRMED` | 冻结日志实测值 | 内部指标引用 |
| `NOT_RUN` | 未运行 | 官方 Gate 待执行 |
| `NOT_MEASURED` | 未测量 | 特定指标未采集 |
| `TO_MEASURE` | 计划测量 | 路线图待办 |
| `BLOCKED_BY_OFFICIAL_STARTER_KIT` | 被官方阻塞 | 等待外部依赖 |
| `COMPETITION_COMPLETE=NOT_CLAIMED` | 比赛未完成 | — |
| `FINAL_INTERNAL` | 内部冻结 | 内部闭环声明 |

**不得使用**: `OFFICIAL_PASS` / `COMPETITION_COMPLETE` / `正式比赛完成` 等未验证标签。

---

## 4. 历史限制 (已解决)

| 限制 | 原状态 | 解决方案 | 证据 |
|------|--------|---------|------|
| T2W 全在 CPU | W0 p50=4798ms | env-only CANN T2W | E04, 32/32 pairs |
| Prefill 每次重新计算 | 210ms p50 | Static Prefix KV Cache | E02, 30/30 |
| 多请求 ctx 失效 | Drain timeout crash | Persistent 生命周期 fix | E03, 3 seq ok |
| TTS KV overflow | n_past 突破 4096 | T13 guard cap 256 | E06, PASS |
| SSE bad_alloc crash | Worker exit + sink.done | T9 worker-once fix | E08, resolved |
| 非流式 text 缺失 | Text field absent | T9 text field add | E07, resolved |
| Cross-request contamination | R7/R9 观察 | Server context 隔离 | 0 contamination confirmed |

---

## 5. 不优化清单 (Amdahl REJECT / 不可达)

| 候选 | 拒绝原因 | 证据 |
|------|---------|------|
| Chunk size 调整 (B6b) | CI95 跨 0，效果不显著 | E05 |
| MTP (multi-token prediction) | 模型不支持 | 设计限制 |
| O1 等参数调优 | 不改变瓶颈 (T2W 93% → T2W 已优化) | Amdahl |
| Pipeline parallel (compute + T2W overlap) | CANN caps.async=false | 硬件限制 |
| CANN graph mode for prefill | graph_compute min_nodes 需求不满足 | 设计限制 |
| KV cache CPU offload | 与 `-ngl 999` 矛盾 (offload 仅在 weight 在 CPU 时触发) | 源码分析 |
| Tensor parallelism (跨 die) | 非本阶段范围，且 CANN 无 async | 范围外 |
| CUDA graph replay | 无关平台 | 不适用 |
