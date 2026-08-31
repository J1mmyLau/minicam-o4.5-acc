# 04 · 系统架构

**问题**：优化前必须先钉死「这条链路上到底有什么、跑在哪、代码在哪」。
**证据**：两棵代码树 + 磁盘模型资产 + msprof/日志（见 05）。
**决策**：架构图定下来后，所有优化按段归属落到对应模块（02/06）。

## 1. 硬件与运行时

- **1× Ascend 910C，dual-die**：必须 `ASCEND_RT_VISIBLE_DEVICES` pin 到单 die
  （0 或 1）——跨 die 会拿到垃圾数值；所有精度/性能任务均单 die。
- **CANN 9.1.0-beta.1**（真实 OPP 目录 `/usr/local/Ascend/cann-9.1.0-beta.1/opp`，
  算子目录名是 `built-in` 不是 `builtin`——校验脚本两者都要认）。
- ggml-cann 后端 + aclnn 算子库；ACL graph capture/replay 可用
  （`GGML_CANN_ACL_GRAPH=on` + MAX_NODES）。

## 2. 推理链路（每个 duplex chunk 五段）

```
视频/音频输入
  │
  ├─ VPM (vision encoder, mmproj)          → encode 段
  ├─ thinker = Qwen3 4096/36L/32h LLM       → prefill / decode 段
  ├─ talker = TTS 头（音频 token 生成）      → tts 段
  └─ token2wav = flow (token2mel, NFE) + vocoder → t2w 段
                                                      ↓
                                            流式 WAV (24kHz 16-bit)
```

- **thinker 主干是 Qwen3 4096/36 层/32 头**（不是 1152/27 层——早期 profile
  纠正过），lm_head 仅占 forward 0.65%。
- **talker**：768 维 pre-decision hidden → 6562 类相对音频码 → `emb_code`
  回馈进跨 chunk KV 流；per-token 4.9ms = 单 die 带宽地板。
- **token2wav**：flow（流匹配，默认 NFE=5，CFG=2）+ vocoder（conv1d 主导）。

## 3. 代码资产（两棵树，无公共祖先）

| 树 | 路径 | 内容 |
|---|---|---|
| **bench-huawei / omni-tilelang-opt** | `/workspace/omni-tilelang-opt`（`perf/tilelang-bridge` @ `df45b47c3`） | RTF 候选主线：A+C 杠杆 + TileLang 桥 + submission/ 全套 |
| **upstream-dspark** | `/workspace/llama-cpp-upstream-dspark` | DSpark/dflash 投机解码树（Aug 孤儿 squash） |

- TileLang 桥以 side-loading 方式挂进 ggml-cann（绕开冻结的 CMakeLists），
  输出与原生位相等；AOT `.so` 224 个随 submission 的 `tilelang-aot/` 交付。
- **两树禁止 cherry-pick 互搬**（dflash 依赖 Aug 内存系统）。

## 4. 模型资产（磁盘）

| 资产 | 路径 |
|---|---|
| target F16 | `MiniCPM-o-4_5-F16.gguf`（+ mmproj） |
| DSpark draft | `/workspace/models/dspark-stage11/dspark_stage11-draft-q8mixed-C.gguf`（1.85GB） |
| 910C ft 系列 | `/workspace/models/dspark-stage10/dspark_stage10-draft-ascendft*` |
| NFE2 prompt cache | `/workspace/models/token2wav-rts-nfe2/prompt_cache.gguf` |

## 5. 评测/服务装置

- **server**：`llama-omni-server`（bench-huawei 树定向构建；标准 server
  target 不含 omni 修改）
- **judge-final 客户端**：`evaluation/judge-final/run_judge_direct.py`——
  起 server→发视频→收流式语音→逐段计时→`metrics_rts.json`；
  可跨树（`--llamacpp-root` + `OMNI_SERVER_BIN` wrapper 注入）
- **双 env**：`server.env`（性能）与 `config-accuracy.env`（精度）严格分离
  （原因见 [07-evaluation.md](07-evaluation.md)）

## 6. 线程模型（踩坑来源）

duplex 会话内有：duplex encoder 线程 / TTS 生成线程 / t2w worker 线程 /
server 会话线程。历史坑：线程单调增长导致 cgroup PID 耗尽（1598→4480，
pids.max=10000，~5-6 会话崩一次）——修复后单会话路径稳定；连续多会话
建议仍会话间重启。T2W drain 用 CV 通知 + 500ms 轮询兜底。
