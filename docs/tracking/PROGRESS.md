# PROGRESS — 项目进度追加日志

> 只能追加，不删除历史内容。

---

## 2026-07-17 ITER-010 TASK-026 E2E Integration Test + Phase 5 Closure

- 目的: Verify correctness of all combined optimizations in full Omni E2E pipeline
- 方法: 3 configs × 2 runs each, Full Omni test case (2 rounds)
- 平台: llama-omni-cli, CANN NPU + CPU T2W, 16 threads
- Baseline commit: 3f7a7f0

### Configurations

| Config | NUMA Binding | CONCAT_OPT | Runs |
|--------|-------------|------------|------|
| A | In-process (OMNI_T2W_CPU_AFFINITY=0-79) | OFF | 2 |
| B | External (taskset -c 0-79) | OFF | 2 |
| C | External (taskset -c 0-79) | ON (OMNI_T2W_CONCAT_OPT=1) | 2 |

### Results

- **6/6 PASS** (exit=0, WAVs=5-20, NaN=0 all 18 vision chunks, CANN errors=0)
- Wall time: 36-96s (within baseline range 35.8-120.9s)
- All cumulative optimizations confirmed E2E-safe

### Phase 5 Closure

All CPU-level T2W optimization paths now EXHAUSTED:
- MUL_MAT (73-75%): OpenBLAS NEUTRAL, Q8_0 NEGATIVE, Fused QKV already upstream
- CONCAT (12-14%): NEUTRAL — graph infrastructure, not data movement
- REPEAT/UNARY/SOFT_MAX/CONT: all <5% individually

Cumulative optimization results:
| Optimization | T2W Δ | E2E Δ | Status |
|-------------|-------|-------|--------|
| V5: 8→16 threads | -1.2% | -0.09% | DONE |
| EXP-006: NUMA node0 (taskset) | -4.07% | -0.29% | DONE |
| EXP-006-PROD: in-process affinity | -0.65% | -0.05% | DONE |
| EXP-007: OpenBLAS | +0.28% | — | ARCHIVED NEUTRAL |
| TASK-023: Fused Attention | NEUTRAL | NEUTRAL | CLOSED (already upstream) |
| TASK-024: Q8_0 Quantization | +19.8% | — | ARCHIVED NEGATIVE |
| TASK-025: CONCAT Optimization | -0.70% | — | ARCHIVED NEUTRAL |
| V5 + NUMA combined (taskset) | -5.2% | -0.37% | Cumulative |

### Decision
- TASK-026: DONE — all optimizations E2E-safe
- Phase 5: CLOSED — all CPU T2W paths exhausted
- Phase 8–10: ACTIVE — TASK-030 (Harness alignment), TASK-040 (Final acceptance)
- AscendC Gate: STILL NOT SATISFIED

- 证据: harness/experiments/TASK-026-e2e-integration/
  - conclusion.md, run_e2e.sh
  - runs/A-inprocess-affinity-run{1,2}/
  - runs/B-taskset-numa-run{1,2}/
  - runs/C-all-combined-run{1,2}/

---

## 2026-07-17 ITER-009 TASK-025 CONCAT Optimization

- 目的: Optimize CONCAT operations (12-14% of token2mel, 871 calls/window)
- 方法: A/B interleaved benchmark (3 warmup + 5 measured), OMNI_T2W_CONCAT_OPT=1
- 平台: token2wav-example, CPU 16 threads
- Baseline commit: 3f7a7f0

### Implementation
- Optimized `fmCausalConv1d::build_forward_chunk_graph` cache update path
- When `dt >= pad` (kernel_size-1), skip `ggml_concat(cache_in, x_cont, 1)` — use ggml_view_3d directly
- Gate: `OMNI_T2W_CONCAT_OPT=1` (default OFF), env var evaluated once via static lambda

### Key Findings
- CORRECTNESS: PASS — WAV SHA256 identical across 10/10 runs (585ab0f8...)
  - 160 concat calls eliminated per window, 0 fallback (dt=50 >= pad=2 in all cases)
- PERFORMANCE: **NEUTRAL (-0.70% median, within noise)**
  - Baseline (median): 17282ms infer
  - Experiment (median): 17161ms infer
  - 160 concat calls saved, but each copies only ~4KB (pad=2 × Cin=512 × sizeof(float))
- ROOT CAUSE: CONCAT profiled at 612us/node, but data movement is negligible (~3.2us for 4KB on Kunpeng 920)
  - The 12-14% CONCAT overhead is **graph infrastructure** (node creation, hash table, scheduling), not data movement
  - Same pattern as: EXP-007 (BLAS NEUTRAL) and TASK-024 (Q8_0 NEGATIVE) — op-level elimination cannot solve graph overhead

### Decision
- TASK-025: ARCHIVED as NEUTRAL (D-016)
- Code kept with gate (OMNI_T2W_CONCAT_OPT=1, default OFF, zero impact when off)
- All CPU-level T2W op optimizations now exhausted:
  - MUL_MAT: OpenBLAS (NEUTRAL), Q8_0 (NEGATIVE), Fused QKV (already upstream)
  - CONCAT: NEUTRAL (graph infra dominates)
  - Remaining targets: REPEAT (2.3%), UNARY (3%), SOFT_MAX (2.5%), CONT (3.5%) — all < 5%

### Cumulative Optimization Status
| Optimization | T2W Δ | Status |
|-------------|-------|--------|
| V5: 8→16 threads | -1.2% | DONE |
| EXP-006: NUMA node0 (taskset) | -4.07% | DONE |
| EXP-006-PROD: in-process affinity | -0.65% | DONE |
| EXP-007: OpenBLAS | +0.28% | ARCHIVED NEUTRAL |
| TASK-023: Fused Attention | NEUTRAL | CLOSED (already upstream) |
| TASK-024: Q8_0 Quantization | +19.8% | ARCHIVED NEGATIVE |
| TASK-025: CONCAT Optimization | -0.70% | ARCHIVED NEUTRAL |
| V5 + NUMA combined (taskset) | -5.2% | Cumulative |

- 证据: harness/experiments/TASK-025-concat-opt/
  - conclusion.md, run_ab.sh, run_ab.log

---

## 2026-07-17 ITER-008 TASK-024 Q8_0 Weight Quantization

- 目的: Quantize T2W DiT linear weights from F32 to Q8_0 for memory bandwidth reduction
- 方法: A/B interleaved benchmark (3 warmup + 5 measured), OMNI_T2W_Q8_0=1
- 平台: token2wav-example, CPU 16 threads
- Baseline commit: 3f7a7f0

### Implementation
- Added `fmFlowMatchingModelLoaderGGUF::quantize_linear_weights_q8_0()`
- Quantizes 2D weight tensors ending with ".weight", skipping conv/biases/embeddings
- Uses `ggml_quantize_chunk(GGML_TYPE_Q8_0, ...)` for row-wise quantization
- Creates separate backend buffer for Q8_0 tensors; swaps pointers in tensors_ map
- Gate: OMNI_T2W_Q8_0=1

### Key Findings
- CORRECTNESS: Q8_0 produces different but deterministic output (SHA256 973546e3...)
  - Expected: lossy quantization changes numerical trajectory through 5 ODE steps
  - Sample count: 90240 (identical to baseline)
- PERFORMANCE: **NEGATIVE — +19.8% SLOWER**
  - F32 baseline (median): 16521ms
  - Q8_0 (median): 19794ms
  - Init overhead: ~270ms for quantization
- Root cause: MUL_MAT is compute-bound on Kunpeng 920, not memory-bandwidth-bound
  - Matrix dims (512×512, 64×64) are too small for memory bandwidth to matter
  - F32 kernel is highly SIMD-optimized; Q8_0 dequantization adds per-element overhead
  - Same pattern as EXP-007 (OpenBLAS): small matrices favor compute over bandwidth optimization
  - To benefit from quantization, both weights AND activations need to be quantized

### Decision
- TASK-024: ARCHIVED as NEGATIVE (D-015)
- Q8_0 code: REVERTED (no functional change retained)
- Q8_0 path is dead for T2W on Kunpeng 920

### Cumulative Optimization Status
| Optimization | T2W Δ | Status |
|-------------|-------|--------|
| V5: 8→16 threads | -1.2% | DONE |
| EXP-006: NUMA node0 (taskset) | -4.07% | DONE |
| EXP-006-PROD: in-process affinity | -0.65% | DONE |
| EXP-007: OpenBLAS | +0.28% | ARCHIVED NEUTRAL |
| TASK-023: Fused Attention | NEUTRAL | CLOSED (already upstream) |
| TASK-024: Q8_0 Quantization | +19.8% | ARCHIVED NEGATIVE |
| V5 + NUMA combined (taskset) | -5.2% | Cumulative |

- 证据: harness/experiments/TASK-024-q8_0-weights/
  - conclusion.md, run_ab.sh, run_ab.log

---

## 2026-07-17 ITER-007 TASK-023 Fused QKV Verification

- 目的: Verify fused QKV benefit and determine remaining TASK-023 scope
- 方法: A/B comparison OMNI_T2W_FUSED_QKV=0 vs =1, 3 runs each
- 平台: token2wav-example, CPU 16 threads
- Baseline commit: 3f7a7f0

### Key Findings

- Fused QKV ALREADY implemented upstream (since baseline 3f7a7f0)
- MUL_MAT: 1012 (unfused) → 852 (fused), -15.8% (160 calls saved)
- Correctness: WAV SHA256 identical across all 6 runs (423caa8a...)
- Performance: NEUTRAL (+0.02% in total inference time, within noise)
- Root cause: Fused MUL_MAT is 3× larger per call → longer individual execution offsets dispatch savings

### Architecture Analysis

- 852 MUL_MAT = 720 (5 ODE steps × 16 blocks × 9) + 132 (encoder)
- QKV fusion already saves maximum possible per-block MUL_MAT calls (3→1)
- Q*K^T and V*P are already batched across heads, conv/mlp not fusable
- Reducing to ~300 would require model trade-off (n_timesteps 5→2)

### Decision

- TASK-023: CLOSED as ALREADY_IMPLEMENTED_UPSTREAM
- No further MUL_MAT fusion possible without model change
- Move to TASK-024 (Q8_0 weight quantization)

- 证据: harness/experiments/TASK-023-fused-qkv-verify/
  - conclusion.md, run_ab.sh
  - unfused/{stderr,stdout}_[1-3].txt
  - fused/{stderr,stdout}_[1-3].txt

---

## 2026-07-17 ITER-006 TASK-022 CPU Op-Level Token2Mel Profile

- 目的：Per-op-type CPU profiling of T2W token2mel graphs
- 方法：Instrumented ggml-cpu.c with GGML_CPU_OP_PROFILE=1 env var
- Commit baseline：3f7a7f0 (plus uncommitted ggml-cpu.c changes)
- Branch：perf/exp005-v3b-persistent-worker
- 平台：token2wav-example, CPU backend, 16 threads

### Token2Mel Op Breakdown (per non-last window, ~4.1s)

| Op | % time | calls | avg us |
|---|--------|-------|--------|
| MUL_MAT | 73-75% | 852 | 3185-3924 |
| CONCAT | 12-14% | 871 | 612-633 |
| CONT | 3.4-3.9% | 1621 | 88-106 |
| UNARY (GELU) | 2.8-3.3% | 420 | 294-342 |
| SOFT_MAX | 2.1-2.5% | 90 | 1017-1180 |

### Vocoder Op Breakdown (per window, ~0.24s)

| Op | % time | calls | avg us |
|---|--------|-------|--------|
| REPEAT | 41-44% | 172 | 467-568 |
| MUL_MAT | 33-35% | 88 | 697-917 |
| CONV_TRANSPOSE_1D | 6.7-8.0% | 5 | 2934-3251 |

### Key Insights

- MUL_MAT is 73-75% of token2mel → ~3.1s/window, 852 calls
- OpenBLAS was NEUTRAL (D-012) because dims are small
- CONCAT at 12-14% is surprisingly high (conformer cache concatenation)
- REPEAT dominates vocoder but vocoder is only 5.5% of total

### Next Optimizations

- TASK-023: Fused Attention MatMul (KVQ batch) → reduce 852→~300 MUL_MAT calls
- TASK-024: Quantized T2W Weights (Q8_0) → 2× mem bandwidth reduction

- 证据：harness/experiments/TASK-022-cpu-op-profile/
  - run-cpu.log (complete profile output, SHA256 bc000762)
  - conclusion.md (analysis)

- 代码变更：ggml/src/ggml-cpu/ggml-cpu.c (+GGML_CPU_OP_PROFILE instrumentation)

---

## 2026-07-17 05:15–06:20 ITER-003 E2E Regression + NUMA Affinity (EXP-006)

- 目的：验证 16 threads E2E 正确性 + NUMA 亲和性实验
- Baseline commit：3f7a7f0
- Experiment branch：perf/exp005-v3b-persistent-worker

### E2E Regression (16 threads)

- 运行 2 轮 Full Omni test case
- 结果：2/2 PASS
- Vision: NaN=0 全部 6 个 chunk (2 runs × 3 chunks)
- 16 threads confirmed: "voc_hg2_model: CPU backend using 16 threads"
- Run 1: First audio 5705ms, 5 WAVs
- Run 2: First audio 5839ms, 20 WAVs
- 证据：harness/experiments/ITER-003-e2e-regression/

### EXP-006 NUMA Affinity

- 目的：测量 CPU 亲和性绑定对 T2W CPU 推理的影响
- 平台：token2wav-example standalone, 16 threads, 3 conditions × (3 warmup + 5 measured)
- 条件：unbound baseline, taskset -c 0-79 (NUMA node0), taskset -c 0-159 (cluster 0)
- 结果：
  - **NUMA node0: -4.07%** (3950.8ms vs 4118.6ms baseline) ← NEW BEST single optimization
  - Cluster 0: -3.08% (3991.8ms vs 4118.6ms)
  - Correctness: ALL IDENTICAL SHA256 (f255f343...), 902444 bytes, 451200 samples
- 分析：
  - 单 node 绑定消除跨 NUMA 内存访问
  - 16 threads fit within single node (80 CPUs)
  - Unbound scheduler distributes across 8 nodes → max cross-node overhead
- E2E impact: ~0.3% (T2W is ~7.2% of E2E wall time)
- Cumulative with V5: -5.2% T2W (= 16 threads + NUMA binding)
- 证据：harness/experiments/EXP-006-numa-affinity/

### 本轮产出

- E2E-REGRESSION-16t: DONE ✅
- EXP-006: DONE ✅ (NEW BEST single optimization)
- 下一优先：EXP-006 生产化 (OMNI_T2W_CPU_AFFINITY env var) → 全链路 Omni 验证

---

## 2026-07-17 06:24–07:05 ITER-004 EXP-006 Productionization + V3-B Cleanup

- 目的：实现 OMNI_T2W_CPU_AFFINITY env var 并清理 ARCHIVED V3-B worker 代码
- Baseline commit：3f7a7f0
- Experiment branch：perf/exp005-v3b-persistent-worker

### EXP-006 Productionization

- 在 load_models() 中添加 apply_cpu_affinity_from_env() 调用
- 支持格式：
  - "0-79" — 单范围绑定
  - "0-79,160-239" — 多范围逗号分隔
  - "auto" — 自动检测当前 NUMA node (via /sys/devices/system/node/node*/cpulist)
- 正确性：SHA256 与 baseline 完全一致 (f255f343a62...)
- 性能：
  - 外部 taskset: -4.07% (EXP-006)
  - 进程内 sched_setaffinity: -0.65% (弱于外部绑定)
  - 原因：sched_setaffinity 只影响调用线程及其后续子线程；taskset 绑定整个进程
- 结论：API 可用、正确性通过，但推荐外部 taskset 以获得最佳 NUMA 收益

### V3-B Cleanup

- 移除 ARCHIVED V3-B worker 代码：
  - ensure_worker_started(), stop_worker(), vocoder_worker_loop() 函数
  - Worker 成员变量 (thread, mutex, cv, queues)
  - stop_worker() 析构调用
- 恢复统一同步路径 (与 3f7a7f0 baseline 一致)
- Bug fix: is_final 路径中的 voc_speech_window_ 错误赋值 (mel 数据覆盖 hamming window)
- 正确性验证：SHA256 f255f343a62... 匹配 baseline

### 本轮产出

- EXP-006-PROD: DONE ✅ (OMNI_T2W_CPU_AFFINITY implemented, correctness PASS)
- V3-B-CLEANUP: DONE ✅ (ARCHIVED code removed, unified sync path restored)
- 代码变更：token2wav-impl.cpp (+apply_cpu_affinity_from_env, -V3-B worker methods)
- 代码变更：token2wav-impl.h (-V3-B worker declarations)
- 下一优先：E2E-NUMA-VALIDATION (全链路 Omni + NUMA)
- 证据：harness/experiments/EXP-006-productionization/

---

## 2026-07-17 07:00–07:25 ITER-005 E2E NUMA Validation

- 目的：Full Omni + NUMA affinity E2E correctness validation
- Baseline commit：3f7a7f0
- Experiment branch：perf/exp005-v3b-persistent-worker
- Build: includes OMNI_T2W_CPU_AFFINITY + 16 threads + unified sync

### E2E NUMA Validation

- 3 runs total:
  - Run 1: OMNI_T2W_CPU_AFFINITY=0-79 (in-process), PASS
  - Run 2: OMNI_T2W_CPU_AFFINITY=0-79 (in-process, repeat), PASS
  - Run 3: taskset -c 0-79 (external), PASS
- Results:
  - Exit code: 0/0/0
  - WAVs: 20/20/20
  - Vision NaN: 0/3 chunks × 3 runs = 0/9 total
  - E2E wall time: ~91s each (consistent with baseline 35.8-120.9s)
  - First audio: 5616-6258ms (normal variation)
- Conclusion: NUMA binding safe for E2E, E2E impact ~0.05-0.29% (within noise)
- Recommendation: external taskset/numactl for max NUMA benefit
- 证据：harness/experiments/E2E-NUMA-VALIDATION/

### OpenBLAS Feasibility

- libopenblas-dev available via apt-get
- Current build: GGML_BLAS=OFF
- Next: install OpenBLAS → rebuild with GGML_BLAS=ON → A/B benchmark

### 本轮产出

- E2E-NUMA-VALIDATION: DONE ✅
- 下一优先：T2W MatMul with OpenBLAS (TASK-021)

---

## 2026-07-17 04:10–04:25 ITER-002 Backend Confirm + V3-B Fix + V5 Thread Sweep

- 目的：确认 T2W backend/device → 修复 V3-B correctness bug → 执行 V5 线程扫描
- 平台：token2wav-example standalone binary (CPU)
- Baseline commit：3f7a7f0 (sync vocoder, inline, 8 threads)
- Experiment branch：perf/exp005-v3b-persistent-worker

### Backend Confirmation (TASK-BACKEND-CONFIRM)

- 从 omni.cpp 源码确认：`GGML_USE_CANN` → `device_token2mel = "cpu"`, `device_vocoder = "cpu"`
- Encoder (UpsampleConformerEncoderV2) → CPU
- Flow Matching (fmDiT + CFM) → CPU
- Vocoder (HIFiGAN2) → CPU
- Runtime 验证：voc_hg2_model: CPU backend using N threads
- **关键发现**：T2W 全部组件在 CANN 下运行在 CPU，不是 NPU
  - 之前的 "same-NPU serialization" 假设是错误的
  - Pipeline overlap (V3, V3-B) 无法提供计算并行性

### V3-B Persistent Worker (EXP-005-V3-B)

- 原始实现有 deadlock bug：call 0 在 worker 中同步消费结果 → call 1 等待已消费结果
- 修复：统一 synchronous-via-worker 模式（submit → wait → get），消除 broken pipeline pattern
- Correctness：**PASS** — WAV SHA256 完全一致 (585ab0f...276a1f, 90240 samples)
- Performance：**NEUTRAL** (+0.3%, 16725.6→16777.6ms)
  - Root cause：sync 基线没有线程创建开销（vocoder inline），V3-B 增加了 mutex+cv 同步开销
- 决策：**ARCHIVED** — 收益 <1%，转 V5
- 证据：harness/experiments/EXP-005-V3-B-persistent-worker/

### V5 CPU Thread Sweep (EXP-005-V5)

- 添加 `OMNI_T2W_N_THREADS` env var 支持
- 测试 thread counts：1, 2, 4, 8, 16, 32
- 结果：
  - 1 thread: 17397.6ms (+3.9% vs 8)
  - 2 threads: 19106.0ms (+14.1%) — WORST, contention
  - 4 threads: 17474.0ms (+4.4%)
  - 8 threads: 16743.1ms (BASELINE)
  - **16 threads: 16542.6ms (-1.2%)** — OPTIMAL
  - 32 threads: 16668.6ms (+0.4%)
- 默认值更新：8 → 16
- Correctness：**ALL PASS** (90240 samples, 所有线程数一致)
- 结论：有限的可并行扩展性（1 thread 仅比 8 thread 慢 3.9%），建议 NUMA affinity 作为后续方向
- 证据：harness/experiments/EXP-005-V5-cpu-threads/

### 本轮产出

- TASK-BACKEND-CONFIRM: DONE ✅
- EXP-005-V3-B: ARCHIVED (CORRECTNESS PASS, PERF NEUTRAL)
- EXP-005-V5: DONE (16 threads optimal, +1.2%)
- 代码变更：token2wav-impl.cpp (+OMNI_T2W_N_THREADS, default 16)
- 下一优先：应用 16 threads 到 llama-omni-cli，CPU affinity/NUMA

---

## 2026-07-17 03:21–03:52 ITER-001 EXP-005-V3 Dedicated T2W A/B Benchmark

- 目的：EXP-005-V3 async vocoder pipeline 专用 T2W benchmark
- 平台：token2wav-example standalone binary（排除 Vision/Audio/LLM 波动）
- Baseline commit：3f7a7f0（sync vocoder）
- Experiment commit：ce2dbe1（async vocoder, perf/exp005-instrumentation）
- 协议：3 warmup + 8 measured, A/B interleaved
- 输入：93 tokens × 5 repeat = 19 sliding windows
- 指标：OMNI_T2W_PROFILE=2 per-window timing
- 关键发现：
  1. **CORRECTNESS FAIL**: Async 产生与 sync 不同的音频输出（451200 vs 427200 samples, -5.3%）
     - Root cause: async_wave_out_ retrieval offset bug（call 0 consumes output, call 1 gets empty, call 17's output lost）
  2. **NEGATIVE PERFORMANCE**: Per-unit-audio async is 1.4% WORSE（259.3 vs 255.7 ms/s audio）
     - Apparent -4.0% improvement is illusion from producing less audio
     - Same NPU device serializes encoder+flow and vocoder
     - std::async thread creation overhead: ~200ms across 19 windows
  3. WAV I/O <0.03% total → EXP-005-V4 marked LOW_UPPER_BOUND
- 产物：comparison.json/csv, conclusion.md, correctness_summary.md, resource_summary.md, window_timeline.csv
- 决策：V3 FAILED → V3-B persistent worker thread 或 V5 CPU threads
- 证据：harness/experiments/EXP-005-token2wav-pipeline/benchmarks/

---

## 2026-07-16 10:39 TASK-000

- 目的：冻结当前工作区，保存所有未提交调试内容
- 提交：3f7a7f0
- 命令：git diff --binary > workspace.patch
- 结果：工作区已冻结，patch 已保存
- 证据：harness/runs/20260716-103910-workspace-freeze/
- 结论：6 个文件未提交修改 (+137/-16)，debug-infra.patch 完整保存
- 下一步：TASK-001 clean-tree Full Omni 功能验收

---

## 2026-07-16 10:44 TASK-003A

- 目的：Full Omni + TTS Reference Baseline (2 warmup + 5 measured)
- 提交：3f7a7f0
- baseline_id：20260716-104122-full-omni-tts-reference
- warmup：2 轮（均 PASS）
- measured：5 轮（全部 PASS）
- 聚合结果：
  - Wall time: median 67.9s (35.8–120.9s)
  - Vision encode: median 284.5ms (283.3–291.6ms)
  - First audio: median 5728ms (3/5 captured)
  - WAVs: median 11 (5–26)
- 失败数量：0
- 结论：Full Omni + TTS 在 clean 3f7a7f0 + TTS CPU workaround 下稳定通过
- 证据：harness/baselines/20260716-104122-full-omni-tts-reference/
- 下一步：TASK-003B Audio-only / TASK-003C Vision single / TASK-003D Vision multi-slice / TASK-003E Duplex real-time / TASK-003F Duplex back-to-back

---

## 2026-07-16 11:25 TASK-003B/003E/003F

- 目的：完成剩余 3 个 Reference Baseline 场景
- 提交：3f7a7f0 + TTS CPU workaround
- TASK-003B Audio-only: PASS (4/4 measured, run-02 超时中断, 14–81 WAVs)
- TASK-003E Duplex real-time: PASS (5/5, stream-interval 1000ms, median 24.9s)
- TASK-003F Duplex B2B: PASS (5/5, stream-interval 0ms, median 23.9s)
- 失败数量：0 (run-02 超时非功能失败)
- 证据：harness/baselines/20260716-{110723-audio,105852-duplex,110154-b2b}-*/
- 结论：全部 4 个 Baseline 场景完成，Phase B 可关闭
- 下一步：TASK-004 30 分钟稳定性测试

---

## 2026-07-16 11:38 TASK-004 STARTED → HARNESS FAILURE

- 启动：11:31:20 UTC，3 轮后终止
- 测试类型：30 次迭代稳定性（非 30 分钟连续）
- 结果：3/3 FAIL（2 个 harness 脚本 bug）
  - Bug 1：WAV 输出路径 `./tools/omni/output/` vs 搜索路径不匹配
  - Bug 2：timeout=180s 过短（Full Omni median=68s, max=121s）
- iter-1 实际模型正常通过（exit=0, TTS=0, 4 WAVs），被误判
- 结论：STABILITY_HARNESS_FAILURE，模型未证明不稳定
- 证据：`harness/tasks/TASK-004/FAILURE_ANALYSIS.md`
- 下一步：修正脚本（路径 + timeout≥300s），重新执行

---

## 2026-07-16 12:01 TASK-004 Harness Smoke PASS

- Harness 修正验证：2/2 PASS
- iter-1: 110s, 23 WAVs, 24000Hz/mono/0.84s
- iter-2: 129s, 24 WAVs, 24000Hz/mono/0.84s
- 修正内容：独立 workdir + timeout=300s + checks.json + bc→纯bash
- 证据：`harness/tasks/TASK-004/smoke-fixed/`
- TASK-004 → READY

---

## 2026-07-16 12:33 TASK-004 DONE：30-Minute Stability PASS

- 目的：验证 Full Omni + TTS 30 分钟持续运行稳定性
- 提交：3f7a7f0
- 持续时间：1858s (~31 min)，14 轮迭代
- 结果：14/14 PASS，0 FAIL，0 TIMEOUT
- 延迟：median 131.6s（前半段 127.4s → 后半段 135.8s）
- 退化：NONE
- NaN/Inf：0，CANN error：0，TTS failure：0
- 证据：`harness/runs/20260716-120243-stability-30min/`
- 结论：模型链路在 31 分钟内稳定，无内存泄漏、无延迟退化、无正确性退化
- 下一步：TASK-006 CANNBot Profiling

---

## 2026-07-16 11:30 TASK-005 DONE

- 目的：CANNBot Skills 安装与索引
- CANNBot commit：5b1802b
- 启用：ascendc-env-check, npu-arch, model-infer-profiling, model-infer-perf-breakdown
- 索引：`harness/tooling/cannbot/SKILL_INDEX.md`
- Profiling：未启动

---

## 2026-07-16 13:26 TASK-006 DONE：msprof 采集 + CANN-level 分析

- 目的：Full Omni CANN profiling + operator-level analysis
- 提交：3f7a7f0
- Profile ID：20260716-131033-full-omni-msprof
- msprof 数据：COMPLETE（host + device_0 + device_1, all_file.complete markers）
- 应用退出：正常结束（omni test case 2 轮, TTS 27 chunks, 自然退出）
- CSV 导出：op_summary (61MB, 193K rows), task_time (24MB, 183K rows), op_statistic, api_statistic
- model-infer-perf-breakdown Skill：NOT_APPLICABLE — 面向 PyTorch + torch_npu.profiler + modeling\*.py，当前是 C++ llama.cpp-omni + GGML\_CANN + msprof
- Fallback：CANN-level 分析脚本（analyze_cann.py），16 个输出文件
- 关键发现：
  - MatMulV2：68% (dev0) / 75% (dev1) of device time — transformer 推理正常热点
  - Cast：~7% device time — dtype 转换，优化空间
  - Host sync：aclrtSynchronizeStream 172ms (4535 calls) — 同步点减少候选
  - Host memcpy：2325ms sync memcpy — async 化候选
  - Memory alloc/free：~1170ms — 池化候选
  - AscendC Gate：NOT YET SATISFIED — 热点存在但未定位具体低效 shape，ACLNN 优化未穷尽
- 优化候选：8 个优先级排序候选（P1: sync/memcpy/malloc, P2: cast/fusion, P3: pipeline overlap, P4: matmul shape, P5: AscendC）
- 证据：`harness/profiling/20260716-131033-full-omni-msprof/` + `harness/experiments/OPTIMIZATION_BACKLOG.md`
- 下一步：TASK-007 优化候选排序 → TASK-008+ 逐项 A/B

---

## 2026-07-16 13:32 TASK-007 DONE：优化候选排序与实验设计

- 目的：对 8 个优化候选进行优先级评分和层次划分，设计第一批 3 个实验
- 提交：3f7a7f0（未修改源码）
- 候选层次：
  - L2 (low-risk source): CAND-002 (memcpy, 8.89), CAND-003 (pool, 6.67), CAND-004 (cast, 2.25), CAND-001 (sync, 7.50)
  - L3 (pipeline): CAND-006 (encode overlap, 0.32), CAND-007 (T2W, 1.60)
  - L5 (operator): CAND-005 (fusion, 0.50), CAND-008 (matmul, 0.27)
- Scoring formula: Gain × Confidence × Reproducibility ÷ (Risk × Engineering_Cost)
- Key insight: E2E is 130s, but device time is only 2.6s (2%). Host-side 10.3s (8%). CPU TTS 110s (85%). Optimize host first.
- First batch: EXP-001 (sync memcpy, READY), EXP-002 (buffer pool, PLANNED), EXP-003 (cast/layout, PLANNED)
- MatMul conclusion: NOT first — E2E impact limited, CubinUtil already 87%, no specific shape identified
- AscendC Gate: NOT SATISFIED — 5 conditions unmet
- 产物：
  - `harness/experiments/OPTIMIZATION_PRIORITY.csv` + `.md`
  - `harness/experiments/TASK-007_CONCLUSION.md`
  - `harness/experiments/EXP-001-sync-memcpy/` (6 plan files)
  - `harness/experiments/EXP-002-memory-allocation-pooling/` (6 plan files)
  - `harness/experiments/EXP-003-cast-layout/` (6 plan files)
- 下一步：EXP-001（不自动执行，等用户指令）
