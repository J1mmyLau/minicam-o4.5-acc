# F6 Phase 2 — Baseline Device-Placement Audit
## 2026-08-04 | COMPLETE

**Question (T2):** 比赛/参考 baseline 的 T2W 到底跑在 CPU 还是 CANN？5× 是"相对官方
baseline 的新增优化"，还是"修正错误设备配置"？

**Verdict: `CPU_T2W_WAS_THE_MEASURED_AND_DEFAULT_BASELINE` — 5× 是相对实测 baseline 的
真实收益，同时性质上是 `DEVICE_PLACEMENT_CORRECTION`（修复已知限制的 CPU 回退，恢复
代码中本应执行的 CANN 路径）。两种口径都不夸大。**

---

## 1. 三个配置的完整记录

### A. Framework / reference baseline（比赛参考口径）

| 项 | 值 |
|----|----|
| T2W device env | **未设置**（无 `OMNI_T2W_DEVICE` / `OMNI_VOC_DEVICE`） |
| Flow 实际设备 | **CPU**（代码默认回退，见 §2） |
| Vocoder 实际设备 | **CPU**（代码默认回退） |
| 启动命令 | `llama-omni-server -m MiniCPM-o-4_5-F16.gguf -ngl 999 --device CANN0 -c 4096 -b 512 -ub 512 --split-mode layer --port 18093` |
| 其他 env | `OMNI_KV_CACHE_REUSE=1`（仅 KV 前缀复用，与 T2W 无关） |
| 说明 | 这是 S13 step7、step8 及此前所有服务端 baseline 的实际口径 |

### B. 当前 CPU T2W baseline（实测 S13 严格基线）

| 项 | 值 |
|----|----|
| Binary | `build/bin/llama-omni-server` SHA `e159b3ee…` |
| Model | `MiniCPM-o-4_5-F16.gguf` SHA `d1e69845…` |
| T2W env | 未设置 → Flow CPU / Vocoder CPU |
| 服务端证据 | `Token2Wav: CANN流跨线程需算子适配，flow_matching暂用CPU` / `vocoder暂用CPU` |
| W0 p50 / T2W inf p50 | 4798 ms / 4490 ms |
| RTF | 4.19 |

### C. CANN T2W candidate（Step 6 候选）

| 项 | 值 |
|----|----|
| Binary / Model | 同 B（同一 closure binary，零代码改动） |
| T2W env | `OMNI_T2W_DEVICE=cann-flow-only` + `OMNI_VOC_DEVICE=gpu` |
| Flow / Vocoder 实际设备 | **CANN（NPU）** — 服务端证据 `vocoder CANN GPU OK`，0 次 CPU fallback |
| W0 p50 / T2W inf p50 | 894 ms / ~200 ms |
| RTF | 0.26–0.33（多窗口） |
| 32/32 PCM | 16-bit @24 kHz |

---

## 2. CPU 是不是"故意设计"？不是 —— 是已知限制回退

代码默认分支（`tools/omni/omni.cpp` T2W device config）：

```cpp
if (t2w_dev_env && t2w_dev_env == "cann-flow-only") { /* CANN, worker-thread init, fail-fast */ }
else {
    print("Token2Wav: CANN流跨线程需算子适配，flow_matching暂用CPU\n");  // CPU fallback = DEFAULT
}
```

关键事实链：

1. **CANN 一直是 intended 路径**：更早的 operator-optimization 线程（2026-07-29，
   Q4/ngl-8 CLI）已经测得 Flow on CANN 可用（token2mel 3798ms/chunk）。
2. **服务端路径被线程归属 bug 阻断**：T2W session 在主线程初始化、在 T2W worker 线程
   使用 → CANN stream 跨线程 → 回退 CPU（`ROOT_CAUSE_CONFIRMED_THREAD_OWNERSHIP`）。
3. **`3fc0ed5`（07-21）** 引入 `OMNI_T2W_DEVICE=cann-flow-only`：worker 线程自建 CANN
   backend，绕开跨线程问题。**`0828de2`（07-30）** 加 fail-fast（CANN 不可用即拒绝，
   不再静默回退 CPU）。
4. **但 S13 baseline（binary 08-04 构建）的启动命令没有设置这两个 env** → 走默认分支
   → 仍然是 CPU 回退。这是"已知限制回退"，不是有意设计。

---

## 3. 结论口径（两种都成立，写法不同）

| 口径 | 是否成立 | 表述 |
|------|---------|------|
| **相对实测 baseline 的真实收益** | ✅ | 参考/官方 harness 若不加 env，实测得到的就是 CPU T2W（4798ms W0）。5× 是相对它的真实可复现收益。 |
| **device-placement correction** | ✅ | CPU T2W 是已知限制回退；候选恢复了代码中本应执行的 CANN 路径。 |

**推荐表述**：`PRIMARY_FIRST_AUDIO_BOTTLENECK = T2W_CPU_DEVICE_PLACEMENT`，
候选 = `CANN_T2W_DEVICE_CORRECTION`，对参考 baseline（未设 env）实测 **5× / −81.4%**
W0 提升；本质是修复已知限制的设备放置回退，而非凭空新增优化。不得把 5× 描述为
"在官方 CANN-T2W baseline 之上的额外优化"（官方参考若已设 env，则不存在 CPU 回退）。

---

## 4. 相关事实（旁证）

- kv-cache-production 线程的 soak 脚本（`p3-soak/run_stage_a_1h.sh` 等）已使用
  `OMNI_T2W_DEVICE=cann-flow-only`（未设 `OMNI_VOC_DEVICE`，vocoder 仍 CPU）。
- 本次候选比 soak 多一个 `OMNI_VOC_DEVICE=gpu`（vocoder 也上 CANN）。
- 两者都不改 CHUNK_SIZE / B6b / MTP，均为运行时配置。

## 5. Artifacts

| Artifact | Path |
|----------|------|
| 本审计 | `docs/F6_PHASE2_BASELINE_DEVICE_AUDIT.md` |
| 服务端设备证据 | `docs/f6-s13-closure/raw-data/step7/s13_step7_server.log`（`暂用CPU` 两行） |
| env 引入提交 | `3fc0ed5`（worker-thread CANN）、`0828de2`（fail-fast） |
| 候选 A/B 数据 | `docs/f6-s13-closure/phase2/step6_cann_t2w_ab.json` |
