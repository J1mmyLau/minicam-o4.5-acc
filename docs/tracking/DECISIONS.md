# DECISIONS — 技术决策记录

## D-020：F-003 Talker NPU 阻塞 — GGML_CANN_LOWERING_BUG confirmed

- 状态：Accepted (Root Cause Confirmed, Fix Pending)
- 日期：2026-07-23
- 背景：Talker/TTS 模型在 CANN 上崩溃（F-003），阻塞 Talker NPU 迁移。CANN 9.1 未解决。
- 实验：最小 ACLNN repro 确认 `aclnnRepeatInterleaveIntWithDim` 参数错误。
  - `output_size=2` (correct: dim_size × repeats) → PASS
  - `output_size=128` (wrong: total_elements × repeats, as in production code) → EZ1001 FAIL
- 决定：**GGML_CANN_LOWERING_BUG** — 不是 CANN 算子缺陷，是 ggml-cann ROPE 的 repeat_interleave lowering 有两个 bug：
  1. `output_size` 传 total_elements（应传 dim_size × repeats）
  2. destination tensor 的 dim=3 未更新为 repeat 后的大小
  3. ROPE cache 跨调用复用 buffer，形状不匹配
- 影响：Talker NPU 迁移被阻塞。Talker 在 CPU 上以 ~36ms/token 运行，占 First Audio 的 57%（~1074ms）。
- 修复方向：协调修复 output_size、dest tensor shape、cache buffer sizing，涉及 neox/non-neox 双路径。
- 证据：`/tmp/test_ri3` 最小复现

## D-019：Token2Wav CANN 迁移 — ROOT_CAUSE_CONFIRMED_THREAD_OWNERSHIP

- 状态：Accepted
- 日期：2026-07-21
- 背景：Token2Wav 在 CANN 下硬编码 CPU（`device_token2mel="cpu"`, `device_vocoder="cpu"`）。推测是算子不支持，但审计发现 GGML_CANN 已支持所有 T2W 所需 op。
- 实验：A/B/C/D 线程矩阵。
  - A (main create/use/destroy): PASS
  - B (main create, worker use): **FAIL — ctx=NULL, device=-1, rtMemcpyAsync crash**
  - C (worker create/use/destroy): PASS
  - D (worker persistent reuse): PASS
- 决定：**ROOT_CAUSE_CONFIRMED_THREAD_OWNERSHIP** — GGML_CANN backend/stream/context 具有线程亲和性，必须在同一线程创建、使用、销毁。
- 修复：commit `3fc0ed5` — `OMNI_T2W_DEVICE=cann-flow-only` 时，Token2WavSession 延迟到 worker 线程内初始化，backend 生命周期完全在 worker 内。
- 结果：
  - RTF: 4.19 → 0.65（7.1×，实时达成）
  - First Audio: 5921ms → 1754ms（3.2×）
  - 8 CANN + 9 CPU A/B 复现通过
- 影响：将 CANN backend 生命周期绑定到使用线程，是 Ascend 项目的基础架构规则。后续任何 CANN 加速模块都应遵循此规则。
- 证据：`analysis/token2wav-cann/thread_runtime_matrix.csv`, `analysis/token2wav-cann/thread_runtime_conclusion.md`

## D-018：FINAL-AB — 16-thread NUMA Optimization No Significant Gain for Full Omni

- 状态：Accepted
- 日期：2026-07-18
- 背景：FINAL-AB 对比 Baseline (8 threads, no NUMA) vs Optimized (16 threads, NUMA node0) 在 Full Omni pipeline
- 决定：16-thread NUMA 优化对 Full Omni 无显著性能收益，不强制推荐
- 证据：
  - warmed_pairs (A2-A10 vs B2-B10):
    - ms/audio-second: A=4223.7, B=4259.6 (+0.8% — B 略慢)
    - Avg RTF: A=4.24, B=4.29 (+1.1%)
    - First Audio: A=5825ms, B=5899ms (+1.3%)
  - 所有差异在噪声范围内
  - 20/20 exit=0, NaN=0, Inf=0, CANN error=0
  - LLM 非确定性导致 A/B 输出长度不可比（0.84s–20.84s）
  - vocoder 线程数不一致：A=16, B=8（尽管 B 配置为 16 threads）
  - Warmup 不对称：A=2, B=1
  - Wall timer bug (F-009): run_ab.sh Python f-string 错误
- 影响：
  - 16-thread NUMA 优化对 Full Omni pipeline 无明确推荐价值
  - T2W 独立 benchmark 中的 -4.07% NUMA 收益在 Full Omni E2E 中被稀释
  - 最终分支以 baseline (8 threads, no NUMA) 为基础构建 release
  - VOCoder 线程数不一致可能混淆部分结果
- 回滚方式：使用 baseline commit 3f7a7f0 构建 release 分支
- 证据：harness/experiments/FINAL-AB/

## D-017：Phase 5 Closure — All CPU T2W Optimizations Exhausted

- 状态：Accepted
- 日期：2026-07-17
- 背景：经过 9 个优化方向的尝试，所有 CPU-level T2W op 优化路径已穷尽
- 决定：关闭 Phase 5，进入 Phase 8-10 (Harness alignment + Final acceptance)
- 证据：
  - MUL_MAT (73-75%): OpenBLAS NEUTRAL (D-012), Q8_0 NEGATIVE +19.8% (D-015), Fused QKV already upstream (D-014)
  - CONCAT (12-14%): NEUTRAL (D-016) — graph infrastructure, not data movement
  - Pipeline overlap (V3/V3-B/V4): ALL ARCHIVED (D-005, D-007)
  - Remaining profile targets (REPEAT 2.3%, UNARY 3%, SOFT_MAX 2.5%, CONT 3.5%): all <5%
  - Cumulative gain: V5 (-1.2%) + NUMA (-4.07%) = -5.2% T2W, -0.37% E2E
  - TASK-026 E2E Integration: 6/6 PASS, all configs E2E-safe
- 影响：
  - 不再尝试新的 CPU T2W op 级别优化
  - 当前已接受优化 (16 threads + NUMA binding) 进入最终验收
  - AscendC Gate STILL NOT SATISFIED — 无 profiler hotspot 证据
  - NPU T2W offload 需要 CANN 多设备算子修复，超出当前 scope
- 回滚方式：—

## D-016：TASK-025 CONCAT Optimization — Archived (Neutral)

- 状态：Archived (No Meaningful Benefit)
- 日期：2026-07-17
- 背景：CONCAT = 12-14% of token2mel (871 calls/window)。尝试消除 fmCausalConv1d rolling-window cache concat
- 决定：不默认启用
- 证据：
  - 正确性：WAV SHA256 完美一致 (585ab0f8...), 160 concat calls eliminated, 0 fallback
  - 性能：NEUTRAL (-0.70% median, within noise)
  - 根因：每个 concat 仅复制 ~4KB；612us profiled CONCAT 时间主要消耗在 ggml graph infrastructure (node creation, hash table, scheduling)，非数据搬运
  - 与 TASK-024/EXP-007/TASK-023 相同模式：op-level elimination 无法解决 graph overhead
- 影响：
  - CONCAT 优化路径已穷尽
  - 代码保留 (gate: OMNI_T2W_CONCAT_OPT=1, default OFF)
  - 剩余 profile hotspots (REPEAT 2.3%, UNARY 3%, SOFT_MAX 2.5%, CONT 3.5%) 均 < 5%，不值得投入
- 回滚方式：保持默认 OFF，无功能影响

## D-009：NUMA Affinity — Accepted

- 状态：Accepted (Experimental Evidence)
- 日期：2026-07-17
- 背景：Kunpeng 920 8 NUMA nodes，ggml 线程池无亲和性控制
- 决定：NUMA node binding 显著改善 T2W CPU 性能 (-4.07%)
- 证据：
  - unbound (baseline): 4118.6ms median
  - NUMA node0 (taskset -c 0-79): 3950.8ms median (-4.07%)
  - Cluster 0 (taskset -c 0-159): 3991.8ms median (-3.08%)
  - Correctness: SHA256 identical across all 3 conditions
- 影响：
  - 单节点绑定是最佳策略（16 threads << 80 CPUs/node）
  - 建议实现 `OMNI_T2W_CPU_AFFINITY` env var
  - 可自动检测最优 NUMA node（选负载最低的）
- 回滚方式：unset OMNI_T2W_CPU_AFFINITY 恢复默认行为

## D-010：EXP-006 Productionization — Accepted (with caveat)

- 状态：Accepted
- 日期：2026-07-17
- 背景：EXP-006 证实 NUMA node 绑定 -4.07% T2W 改善，需实现进程内 API
- 决定：实现 OMNI_T2W_CPU_AFFINITY env var，支持显式范围和 auto 检测
- 证据：
  - 正确性：三条件 (unbound, 0-79, auto) SHA256 完全一致
  - 进程内性能：-0.65% (弱于外部 taskset -4.07%)
  - 原因：sched_setaffinity 只影响调用线程；ggml thread pool 可能提前创建
- 影响：
  - 功能可用、正确性通过
  - 如需最大 NUMA 收益，推荐外部 taskset/numactl
  - "auto" 模式可自动检测当前 NUMA node
- 回滚方式：unset OMNI_T2W_CPU_AFFINITY

## D-015：TASK-024 Q8_0 Weight Quantization — Rejected (Negative Performance)

- 状态：Rejected (No Benefit)
- 日期：2026-07-17
- 背景：MUL_MAT is 73-75% of token2mel time. Q8_0 quantizes F32 weights to 8-bit.
- 决定：不实施 Q8_0 weight quantization
- 证据：
  - 正确性：确定性的但与基线不同的输出（有损量化）
  - 性能：+19.8%（19794ms vs 16521ms baseline）
  - 根因：T2W MUL_MAT 在 Kunpeng 920 上是计算密集的，不是内存带宽限制
  - Q8_0 反量化 (int8→float) 在每个元素上增加 2-3 条额外指令
  - 矩阵维度小（512×512, 64×64）：F32 kernel 已经使 compute unit 饱和
- 影响：
  - Q8_0 路径已死；同时量化权重和激活才可能有收益
  - 与 EXP-007 (OpenBLAS) 相同模式：小矩阵维度 = 计算密集
  - 剩余优化方向：CONCAT 简化，或硬件无关的图优化
- 回滚方式：代码已从 tree 中移除

## D-014：TASK-023 Fused Attention MatMul — Closed (Already Upstream)

- 状态: Closed (Already Implemented)
- 日期: 2026-07-17
- 背景: TASK-023 aimed to fuse QKV projections to reduce 852→~300 MUL_MAT calls
- 决定: Close as ALREADY_IMPLEMENTED — no further fusion possible
- 证据:
  - Fused QKV present since baseline 3f7a7f0 (`fmAttention` with `to_qkv_weight_`)
  - A/B confirmed: 852 MUL_MAT (fused) vs 1012 (unfused, FUSED_QKV=0)
  - WAV SHA256 identical — correctness confirmed
  - Performance NEUTRAL (+0.02% in total time)
  - DiT estimator architecture: 5 ODE steps × 16 blocks, each block fully fused
  - Remaining MUL_MATs (Q*K^T, V*P, conv, MLP) cannot be fused without model change
- 影响:
  - TASK-023 closed; resources redirect to TASK-024 (Q8_0 quantization)
  - Attention fusion optimization path exhausted for DiT
  - Encoder QKV fusion possible but small benefit (~12 MUL_MATs)
- 回滚方式: N/A (no code change; finding only)

## D-013：GGML_CPU_OP_PROFILE Infrastructure — Accepted

- 状态：Accepted
- 日期：2026-07-17
- 背景：需要 per-op-type CPU profiling 来识别 T2W token2mel 热点
- 决定：在 ggml-cpu.c 中添加 GGML_CPU_OP_PROFILE=1 环境变量门控的 per-op timing
- 证据：
  - Token2mel: MUL_MAT 73-75% (852 calls), CONCAT 12-14% (871 calls)
  - Vocoder: REPEAT 41-44% (172 calls), MUL_MAT 33-35% (88 calls)
  - 零性能开销（env var gated），打印每个 graph compute 后的排序 breakdown
- 影响：
  - 可用于任何 ggml-cpu 工作负载的快速热点分析
  - 不需要 perf / external profiler
  - 代码最小化（~40 行），完全向后兼容
- 回滚方式：unset GGML_CPU_OP_PROFILE

## D-012：OpenBLAS for T2W MatMul — Rejected

- 状态：Rejected (No Benefit)
- 日期：2026-07-17
- 背景：T2W token2mel 在 CPU 上运行，3.6-4.0s/window，需探索 MatMul 加速
- 决定：不启用 OpenBLAS
- 证据：
  - 正确性：SHA256 完全一致 (f255f343...)
  - 稳定区域性能：+0.28%（中性，在噪声范围内）
  - 总体推理：+2.35%（OpenBLAS 初始化开销）
  - Token2mel 延迟：+1.04%（中性）
- 影响：
  - T2W 矩阵维度太小（<1000），BLAS 无法超越 ggml 自带 CPU kernel
  - ggml 已有高度优化的 CPU MatMul（packing + threading）
  - 不推荐 LLM CPU 场景启用（未评估，LLM 当前运行在 NPU）
- 回滚方式：保持 GGML_BLAS=OFF

## D-011：V3-B Worker Code Removal — Accepted

- 状态：Accepted
- 日期：2026-07-17
- 背景：EXP-005-V3-B persistent worker 已 ARCHIVED，代码保留污染代码库
- 决定：完全移除 V3-B worker 代码 (ensure_worker_started, stop_worker, vocoder_worker_loop 及关联成员)
- 修复 bug: voc_speech_window_ 在 is_final 路径被错误赋值为 mel_in_bct
- 影响：push_tokens_window 恢复统一同步路径 (与 3f7a7f0 baseline 一致)，代码简化
- 回滚方式：git revert

## D-006：T2W Pipeline Backend 确认 — ALL CPU on CANN

- 状态：Confirmed
- 日期：2026-07-17
- 背景：需要确认 Encoder/Flow/Vocoder 实际 backend 以指导优化方向
- 决定：`GGML_USE_CANN` 下 T2W 全部组件运行在 CPU
- 证据：`omni.cpp:4396-4419` 对 CANN 硬编码 `device_token2mel="cpu"`, `device_vocoder="cpu"`
- 影响：
  - Pipeline overlap 实验（V3, V3-B）无法提供计算并行性
  - CPU thread tuning 是主要优化方向
  - "same-NPU serialization" 先前假设被证伪
  - V3-B sync baseline 中没有线程创建开销需要消除
- 回滚方式：如需 NPU T2W，移除 CANN cpu gate 并适配流跨线程算子

## D-007：EXP-005-V3-B Persistent Worker — ARCHIVED

- 状态：Archived（Correctness PASS, Performance NEUTRAL）
- 日期：2026-07-17
- 背景：EXP-005-V3 失败后，验证 persistent worker 能否消除 ~200ms 线程创建开销
- 决定：归档，不合并
- 原因：
  - Sync 基线 (3f7a7f0) 的 vocoder 是 INLINE 模式，无线程创建开销
  - V3-B 增加 mutex+cv 同步开销（~17-35ms/window），性能中性偏负
  - 预期收益 <1%，不满足采纳标准
- 影响：Pipeline 方向至此完全归档（V3/V3-B/V4 均无正收益）
- 回滚方式：保持 sync inline vocoder

## D-008：V5 默认线程数 8 → 16

- 状态：Accepted
- 日期：2026-07-17
- 背景：640核 Kunpeng 920 平台，T2W 全部运行在 CPU
- 决定：将 `kDefaultThreads` 从 8 改为 16，同时支持 `OMNI_T2W_N_THREADS` env var override
- 证据：Thread sweep: 16 threads = 16542.6ms (-1.2% vs 8), all counts produce identical output
- 影响：T2W CPU 推理轻微加速，需在 omni.cpp 同步应用
- 回滚方式：`OMNI_T2W_N_THREADS=8` 或修改回默认值

## D-005：EXP-005-V3（async vocoder pipeline）正式拒绝

- 状态：Rejected
- 日期：2026-07-17
- 背景：使用 std::async 重叠 vocoder 与下一窗口 encoder+flow
- 决定：标记 REJECTED_CORRECTNESS_AND_PERFORMANCE
- 原因：
  - 正确性：async_wave_out_ 取回偏移导致音频输出减少 5.3%（451,200→427,200 samples）
  - 性能：归一化单位音频延迟恶化 1.4%（255.7→259.3 ms/s audio）
  - 架构：encoder+flow 和 vocoder 可能在同一设备上，std::async 线程创建开销 ~200ms
- 影响：该实现不得作为 Accepted Candidate、不得合入组合实验
- 回滚方式：切回 sync vocoder 路径（ce2dbe1→3f7a7f0）
- 后续：V3-B 持久 worker 仅验证能否消除线程创建开销，不假设计算重叠

## D-004：建立 harness/ 证据体系

- 状态：Accepted
- 背景：比赛需在 Ascend 上完成 MiniCPM-o 4.5 推理优化
- 决定：llama.cpp-omni + GGML_CANN 作为当前主线
- 原因：feat/ascend-cann 分支具备 CANN 后端，可快速建立 baseline
- 影响：暂不投入 vLLM-Omni / vLLM-Ascend / SGLang
- 回滚方式：切换到 vLLM-Omni（需重新建立环境和 baseline）

## D-002：TTS 使用 CPU

- 状态：Accepted
- 背景：CANN 多设备 (device 1) RoPE 和 aclnnRepeatInterleave 算子崩溃
- 决定：tts_gpu_layers=0，TTS 退 CPU
- 原因：CANN 9.0.0 多设备算子注册不完整
- 影响：TTS RTF ~3.9，后续需修复 CANN 算子后恢复 GPU
- 回滚方式：tts_gpu_layers=-1 恢复 CANN TTS

## D-003：Vision NaN 不认定为 max_slice_nums Bug 根因

- 状态：Accepted
- 背景：修复 max_slice_nums=0 后单图和多切片路径均 NaN=0，但修复前单图同样 NaN=0
- 决定：max_slice_nums=0 是多切片失效 Bug，不是原始 NaN 的确定根因
- 原因：原始 NaN 在当前环境始终未复现
- 影响：若 NaN 再次出现需独立调查
- 回滚方式：—

## D-005：EXP-005-V3 Async Vocoder → FAILED

- 状态：Rejected
- 背景：EXP-005-V3 使用 std::async per-window 异步 vocoder 管线
- 决定：V3 标记 FAILED，进入 V3-B（persistent worker thread）或下一个候选
- 原因：
  1. Correctness FAIL：async_wave_out_ retrieval offset bug 导致音频输出偏移/丢失
  2. Performance NEGATIVE：per-unit-audio async 1.4% WORSE（259.3 vs 255.7 ms/s）
  3. Same NPU device serialization：encoder+flow 和 vocoder 共享同一 NPU，无法真正重叠
  4. std::async thread creation overhead：~200ms per 19 windows
- 影响：V3 不进入 ACCEPTED_CANDIDATE，不 promote，不 merge
- 回滚方式：perf/exp005-instrumentation 分支废弃，回退到 3f7a7f0 baseline
- 下一步：V3-B 或 V5

## D-004：建立 harness/ 证据体系

- 状态：Accepted
- 背景：项目需要可追溯、可复现的实验证据链
- 决定：所有运行、baseline、profiling、实验归档到 harness/ 目录
- 原因：分离证据和源码，防止 Git 提交混乱
- 影响：每次任务结束后必须归档 harness 证据
- 回滚方式：—
