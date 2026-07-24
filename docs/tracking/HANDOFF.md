# HANDOFF — MiniCPM-o 4.5 × Ascend 910C

> 最后更新：2026-07-17 ITER-010

## 持续自主运行

已建立 watchdog 自动续跑器。单个 CC 会话会自然结束，watchdog 每轮以全新上下文自动重启。

```bash
# 在现有 gfh tmux 中启动 16 小时
tmux new-window -t gfh -n autopilot \
  "bash -ic 'HOURS=16 MAX_ITERATIONS=100 /workspace/llama.cpp-omni/scripts/cc-autopilot.sh'"

# 查看进度
ROOT="$(find /workspace/llama.cpp-omni/harness/autonomous -maxdepth 1 -type d -name '*-cc-autopilot' | sort | tail -1)"
tail -f "$ROOT/watchdog.log"
```

## HEAD

`3f7a7f0` (baseline, unmodified) + uncommitted changes on `perf/exp005-v3b-persistent-worker`

## 当前阶段

Autonomous Optimization — **ITER-010 COMPLETE**: TASK-026 E2E Integration PASS, Phase 5 CLOSED

## 最新发现

1. **TASK-026 E2E Integration Test PASS (6/6)**:
   - 3 configs × 2 runs: exit=0, WAVs correct, vision NaN=0 all 18 chunks
   - All cumulative optimizations (16 threads + NUMA + CONCAT_OPT) E2E-safe
   - Wall time 36-96s (within baseline range)

2. **Phase 5 CLOSED — All CPU T2W paths exhausted**:
   - MUL_MAT (73-75%): OpenBLAS NEUTRAL, Q8_0 NEGATIVE, Fused QKV already upstream
   - CONCAT (12-14%): NEUTRAL (graph infrastructure, not data movement)
   - Cumulative: V5 (-1.2%) + NUMA (-4.07%) = **-5.2% T2W, -0.37% E2E**

3. **Phase 8–10 ACTIVE**: TASK-030 (Harness alignment), TASK-040 (Final acceptance)

## 优化成果累积

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

## 下一会话关键任务

1. **TASK-030: Official Harness Alignment**
   - Verify against competition evaluation criteria
   - Ensure output format compatibility
   - Document any gaps

2. **TASK-040: Final Acceptance**
   - Full Omni + TTS with all accepted optimizations
   - 16 threads (default), taskset NUMA binding recommended
   - Verify: exit=0, WAV count, vision NaN=0, E2E wall time

## Phase 5 Cumulative

```
harness/experiments/TASK-025-concat-opt/
harness/experiments/TASK-024-q8_0-weights/
harness/experiments/TASK-023-fused-qkv-verify/
harness/experiments/TASK-022-cpu-op-profile/
harness/autonomous/20260717-041023-cc-autopilot/
```
