# 提交包总览 — 赛道一（高性能推理优化赛道）

**候选**: MiniCPM-o 2.5 全双工端到端（llama.cpp-omni 移植 + Ascend 910C TileLang 优化）
**源码**: branch `perf/tilelang-bridge` @ `df45b47c3` + 工作区 diff（见 patches/）
**主指标**: SPEAK→WAV 完整链路 RTF = **0.4829 ± 0.0161**（4-run 主统计，取最小统计口径）
最优单次 0.4603（seed1002）；提交前复测（2026-08-31，3-run）= 0.4840 ± 0.0125（一致性确认）
官方基线 1.087，本地基线 0.6754

## 目录结构（对应官方规范 5 类内容）

| 官方要求 | 位置 | 状态 |
|---|---|---|
| (a) 完整代码与配置 | 仓库本体 + `patches/uncommitted-worktree.patch` + `config/{server.env,config-accuracy.env}` | ✅ |
| (b) Benchmark 评测结果 | `benchmark_results/{videomme,daily_omni,tts_seed,rts}/` | ✅ 4 项全达标 |
| (c) 性能测试报告 | `performance/PERFORMANCE_REPORT.md` | ✅ 4-run 统计 + 分解 + 逐杠杆 |
| (d) 可运行 Demo | `demo/`（README + 归档音频 + run_demo.sh + demo_smoke.sh） | ✅ |
| (e) 优化与复现说明 | `docs/OPTIMIZATION_REPORT.md` | ✅ |
| (f) DSpark draft 交付 | `dspark/`（1.85GB q8mixed-C 量化 draft + 转换/量化脚本 + 验收数据） | ✅ |

## 核心数字

| 指标 | 官方基线 | 本地基线 | 候选（本提交） | 达标线 | 判定 |
|---|---|---|---|---|---|
| SPEAK→WAV RTF（主优化目标） | 1.087 | 0.6754±0.0152 | **0.4829±0.0161** | 越低越好 | **−55.6% vs 官方基线** |
| SPEAK→wav 时延 | 1087.3ms | 827.1ms | **647.9ms** | — | −40.4% |
| VideoMME | 69.0 | 69.8（实测） | **达标** | ≥67.0 | ✅ 降幅 ≤2pp |
| Daily-Omni | 79.5 | 79.43（实测） | **达标** | ≥77.5 | ✅ 降幅 ≤2pp |
| TTS-Seed ASV | 0.709 | 0.969（实测） | **达标** | ≥0.689 | ✅ 降幅 ≤0.02 |
| TTS-Seed WER | 1.414 | 1.422%（实测） | **达标** | ≤1.56 | ✅ 增幅 ≤10% |

## 关键工程事实（评审必读）

1. **GM3M9G 精度隔离**：性能 env 与精度 env 两套严格分离（config/ 下两个文件）。
   历史上 perf env 泄漏进精度 CLI 导致 videomme 8%；已修复并验证——精度恢复达标。
2. **精度基线参照**：pristine 树同 harness 实测四项全 PASS（2026-08-13:
   WER 1.422/SIM 0.969/VideoMME 69.8/Daily 79.43），候选优化不改动精度路径
   （A+C 杠杆仅在 server 启动 env 注入、精度任务走独立 accuracy env）。
3. **二进制溯源**：VERSION_MANIFEST.md 列全 SHA256（5 二进制 + 4 库 + 模型）。
4. **保护资产 0 改动**：evaluation/ 与 4 个评测 CLI、CMakeLists、token2wav 验证器
   与上游 byte-identical（已验证 `git diff` 为空）。

## 快速上手

```bash
./submission/scripts/run_rts.sh 1001        # 性能主指标
./submission/scripts/demo_smoke.sh          # Demo 资产自检
./submission/scripts/run_demo.sh             # 完整双工 Demo（录制用）
./submission/scripts/run_videomme.sh full    # 精度复测入口
```
