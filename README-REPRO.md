# 最小复现提交 — Track A 候选（RTF 0.4829）

单 commit 快照 = `perf/tilelang-bridge` @ `df45b47c3`（已提交部分）
**+** 工作区 diff（A+C 配方 + TileLang 桥，`submission/patches/uncommitted-worktree.patch` 同源）
**+** 未跟踪 `tools/omni/talker_rollout.py` — 即完整候选源码状态。

## 复现步骤

```bash
# 1) 构建（aarch64 + CANN 9.1.0-beta.1，目标 llama-omni-server）
cmake -B build && cmake --build build --target llama-omni-server -j

# 2) 性能主指标（SPEAK→WAV RTF，judge-final harness）
./submission/scripts/run_rts.sh 1001        # 期望 core RTF ≈ 0.48（4-run 0.4829±0.0161）

# 3) 精度复测（独立 accuracy env，与 perf env 严格分离）
./submission/scripts/run_videomme.sh full   # ≥67.0
./submission/scripts/run_daily_omni.sh     # ≥77.5
./submission/scripts/run_tts_seed.sh       # ASV ≥0.689 / WER ≤1.56

# 4) Demo（录制入口，自动 source CANN + A+C + NFE2）
./submission/scripts/run_demo.sh
```

## 依赖（不在本包内，需另备）

| 资产 | 位置 |
|---|---|
| 模型 | MiniCPM-o-4_5-F16.gguf（含 tts/ token2wav-gguf/） |
| NFE2 cache | /workspace/models/token2wav-rts-nfe2/prompt_cache.gguf |
| TileLang 生成器 | /workspace/tilelang-ascend（tilelang-aot/ 已含 224 个预编 .so） |
| 硬件 | 1× Ascend 910C dual-die, CANN 9.1.0-beta.1 |

详见 `submission/VERSION_MANIFEST.md`（SHA256 溯源）与 `submission/README.md`。
