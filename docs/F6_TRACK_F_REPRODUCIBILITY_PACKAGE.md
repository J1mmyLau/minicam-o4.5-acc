# F6 — Track F：最终可复现提交包（Reproducibility Package）

Date: 2026-08-14 · Candidate `a77d6a8` (`fix/cann-fa-nan-ubatch16`) + `trackA_fixes.patch`（Config D）
Directive: 【BYPASS — LONG-RUN FINALIZATION QUEUE】Track F — 证据闭环

---

## 1. 候选身份（权威冻结）

| 项 | 值 |
|---|---|
| 源码 commit | `a77d6a8` `fix(cann): restore BOOL attenMask + Clamp in fused attention path` |
| 分支 | `fix/cann-fa-nan-ubatch16` |
| 附加补丁 | `experiments/nightly/trackA_fixes.patch`（19,803 B，4 文件，见 §3） |
| 运行时配置 | Config D（见 §4） |
| 保护资产 | `evaluation/` + 4 保护工具 byte-identical to `c9785cc`（0 行改动） |

**候选 = `a77d6a8` 源码 + `trackA_fixes.patch`（4 文件）+ Config D 环境变量。**
补丁不触碰任何受保护评测器（`omni-eval-cli.cpp` / `omni-eval-daily-cli.cpp` /
`omni-tts-eval.cpp` / `omni/CMakeLists.txt`）。

## 2. 二进制 SHA256（冻结候选，2026-08-13 23:17 构建，已逐字节复现）

| 产物 | SHA256（前 16 hex） |
|---|---|
| libomni.so | `b600ce5277be4eeb` |
| libggml-cann.so.0 | `c083aeea9aa57632` |
| libggml.so.0 | `f79467d9ea9ccf26` |
| libllama.so.0 | `cf5a0aaf2a68243a` |
| llama-omni-tts-eval | `0208071b329bb0c4` |
| llama-omni-server | `c330dc5aec2a334c` |
| llama-omni-eval-cli | `640aa777d0e79755` |
| llama-omni-eval-daily-cli | `1b06868cae6f0e30` |

4 个可执行文件均**动态链接** `libomni.so` + `libggml-cann.so`，补丁在运行时自动生效，
无需重建 server / eval-cli / eval-daily-cli。Track B 两次调查改动已逐字回滚后，
`libomni.so` 重建 SHA256 = `b600ce5277be4eeb`，证明可复现构建无漂移。

## 3. 补丁内容（`trackA_fixes.patch`，4 文件，296 行）

| 文件 | 改动 |
|---|---|
| `ggml/src/ggml-cann/aclnn_ops.cpp` | ① rope 修复（非-neox 用 `aclnn_repeat_interleave(dim=3,n=2)`，neox 用 `aclnn_repeat{1,1,1,2}`，恢复 pristine c9785cc Step 6）；② FA Q-split 源码默认 `16 → 0`（OFF） |
| `tools/omni/omni.cpp` | ③ simplex（Seed-TTS eval）→ NPU revert（与 pristine 一致）+ `OMNI_TTS_NGL` + pipeline drain |
| `tools/omni/token2wav/token2wav-impl.cpp` | ④ gf_enc 双重计算门控 `OMNI_T2W_ENC_TIMING`（默认 OFF） |
| `tools/server/server-omni.cpp` | ⑤ SSE duplex drain（RTS SPEAK=0 修复，非 Seed-TTS） |

三个污染源（Track A）彼此掩蔽，需全部修复才回 pristine（单修任一仅部分恢复）。详见
`F6_TRACK_A_SEEDTTS_RESOLUTION.md`。

## 4. Config D（运行时环境变量，零评测器改动注入）

```
OMNI_T2W_DEVICE=cann-flow-only
OMNI_VOC_DEVICE=gpu:0
OMNI_T2W_PIPELINE_OVERLAP=1
OMNI_CANN_FA_MAX_UBATCH=16      # 长多模态 NaN 保护（aclnnMm 有限输入→NaN 的 workaround）
GGML_CANN_WEIGHT_NZ=off
GGML_CANN_ACL_GRAPH=off
```

经 `EVAL_CONFIG` 钩子（`config_d_official.env`）注入。Fix 4 将 CANN flow/vocoder 限定
duplex-only，simplex Seed-TTS 保持 pristine NPU 路径 → 精度零副作用。

## 5. 结果汇总（冻结候选 + Config D）

### 5.1 准确率（三条基线全部 PASS，Track C）

| 基准 | 候选 | pristine 基线 | 验收 | 判定 |
|---|---|---|---|---|
| Daily-Omni | **79.43%**（950/1196） | 79.43% | ≥77.5% | **PASS**（+1.9pt） |
| VideoMME | **69.8%** | 69.8% | — | **PASS** |
| Seed-TTS ZH_WER | **1.422%**（2020/2020） | 1.5% | ≤1.56% | **PASS**（优于 pristine） |
| Seed-TTS SIM(ASV) | **0.969** | 0.97 | ≥0.689 | **PASS**（≈ pristine） |

- Seed-TTS 全量 2020 条，用时 9941s（~2.76h），0 NaN / 0 error / rc=0。
- 证据：`experiments/nightly/trackC_seedtts_full/summary_tts.json`。

### 5.2 性能（RTF，Track B — 结论性受阻）

- 官方 SPEAK→WAV RTF = **NULL**（`stage_timing.jsonl` 的 t2w 事件缺 `duration_ms`/`src_cnt`，C++ 需重编）。
- SPEAK→WAV 端到端延迟已捕获：1306–2747 ms（墙钟，非 RTF）。
- RTF 基线（pristine 服务端 [bench]）= **1.083**（official 1.087）。
- 官方 RTF 入口 `benchmark_client.py` 本就 CANNOT_RUN（WS adapter 占位、无 HTTP `/v1/stream`）。
- 详见 `F6_TRACK_B_RTS_RTF_EVIDENCE.md`。

### 5.3 稳定性（Track D — 无崩溃、无线程泄漏）

- 2 次 RTS soak（各 ~80s，37 chunk）0 崩溃，生命周期干净。
- 线程泄漏（libgomp 319-thread team）**不适用** RTS（full_reinit 每视频重启服务）与
  eval CLI（进程内加载）路径；仅 WS Demo 路径受影响，已 `-t 4` 修复。
- 详见 `F6_TRACK_D_STABILITY_SOAK.md`。

## 6. 已知限制（Known Limitations）

1. **SPEAK turn 楔死**：候选 `a77d6a8` 的 per-chunk drain 语义，SPEAK turn 残留 TTS
   超过 5s 超时 → `context_state=3`（NOT_REUSABLE）→ 拒绝后续请求。属候选级 F6
   lifecycle 限制，非 Config D 注入。两次修复（TOCTOU / timeout）均失败/回归，已回滚。
2. **官方 RTF 不可测**：t2w 计时事件缺字段 + 官方 benchmark 入口 CANNOT_RUN。
3. **官方 starter kit 资产**：`OFFICIAL_*` 评测依赖官方 starter kit（BLOCKED_BY_OFFICIAL_STARTER_KIT）。

## 7. 复现协议

```
# 1. 检出冻结 commit
git checkout a77d6a8                      # fix/cann-fa-nan-ubatch16

# 2. 应用 4 文件补丁
git apply experiments/nightly/trackA_fixes.patch

# 3. 构建 4 目标（libomni.so 等动态库 + server/tts-eval/eval-cli/eval-daily-cli）
#    标准 llama.cpp CMake 目标；构建后校验 SHA256 = §2 表

# 4. 运行时注入 Config D（§4 环境变量）
```

## 8. 提交清单（Submission Checklist）

- [x] 候选身份冻结（commit + patch + SHA256 + Config D）
- [x] 保护资产 pristine（`evaluation/` + 4 工具 0 行改动）
- [x] 三条准确率基线 PASS（Daily 79.43% / VideoMME 69.8% / Seed-TTS 1.422%/0.969）
- [x] 稳定性 soak 0 崩溃、无线程泄漏
- [ ] 官方 SPEAK→WAV RTF（BLOCKED：计时字段缺失 + 官方入口 CANNOT_RUN）
- [ ] 官方 starter kit 评测（BLOCKED_BY_OFFICIAL_STARTER_KIT）

## 9. 处置

Track F 证据闭环**核心完成**：候选身份 + 二进制 + 补丁 + 配置 + 三条准确率 + 稳定性
全部权威冻结，可复现构建验证通过。剩余两个 `[ ]` 项（官方 RTF、官方 starter kit 评测）
为**外部阻塞**（非候选问题），按 directive 记录不阻塞提交。
