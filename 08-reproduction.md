# 08 · 复现与交付资产

## 1. 复现四步（本仓 README-REPRO 摘要）

```bash
# 0) 环境：910C + CANN 9.1.0-beta.1；tilelang-ascend 在
#    /workspace/tilelang-ascend（生成 kernel 须 PYTHONPATH 指它）

# 1) 定向构建 llama-omni-server + libomni（标准 server target 不含 omni 修改）
#    tilelang-aot/ 224 个预编 .so 就位

# 2) RTF 复现（A+C 配方 launch-only 注入）
./submission/scripts/run_rts.sh 1001        # 单 run 0.474–0.498
#   4-run 0.4829±0.0161；原始产物 benchmark_results/rts/raw/rts_final_s100*.json

# 3) 三精度脚本（config-accuracy.env 隔离口径，perf 全关）
./submission/scripts/run_videomme.sh full
./submission/scripts/run_daily.sh  full
./submission/scripts/run_tts.sh

# 4) Demo（交互双工会话）
./submission/scripts/run_demo.sh            # 或带自定义视频路径
```

**依赖**：MiniCPM-o-4_5-F16.gguf（+mmproj）、
`/workspace/models/token2wav-rts-nfe2/prompt_cache.gguf`、tilelang-ascend、
（可选）dspark draft 1.85GB。

## 2. 交互 Demo（录制）

演示 = 输入含语音视频 → **流式**语音回复（逐 chunk WAV），对应官方 Demo
准入四条：服务启动连接 / 音视频文本输入 / 流式连续 / 120s 全流程 37 chunk
零失败（4-run）。

输出：`sessions/<stamp>/speak_turns/turn_0N.wav`（24kHz 16-bit）、
`eval_e2e_report.json`（n_speak / SPEAK→wav / core RTF）、demo.log。

录制节奏：`demo_smoke.sh` 全 PASS（15s）→ `run_demo.sh` 横幅+加载（30s）→
终端逐 chunk + 同时播 WAV（2-3min）→ json 展示 RTF 收尾（30s）。

### EZ1002 崩溃根因链（run_demo.sh 的两次修复）

**现象**：server 起后在首个 prefill 崩，客户端 `RemoteProtocolError`；
cpp.log：`EZ1002 Config_Error_Invalid_Environment_Variable`。

**根因**：终端里 ASCEND_OPP_PATH 未设置 / 未 export / **已设置但失效**——
任一都让 aclnn 找不到算子目录直接崩。

**修复（最终形态）**：
1. **无条件** source `set_env.sh`（幂等）+ 显式 export 四个 CANN 变量
2. **硬校验** OPP 目录存在且含 `built-in` **或** `builtin` 子目录
   （首版只查 builtin 误杀自己——真实目录叫 built-in）
3. `OMNI_SAMPLER_SEED` 默认 1001——固定采样种子保证录制确定性出 SPEAK 轮
   （30s 彩排曾因随机种子 SPEAK=0）

clean-env 注入（`env -u ASCEND_OPP_PATH …`）端到端验证通过。

## 3. 提交资产与版本指纹

| 资产 | 说明 |
|---|---|
| `/workspace/SUBMIT-track1-final-20260831.tar.gz` | **Track 1 终版 v2**，1.55GB，只读 |
| sha256 | `fcc8ca8caab084b06aa4485f350d8f594f0a74b87891a9c36442905d1ae782e3`（v1 `b25260a8…` 作废） |
| `/workspace/SUBMIT-minimal-repro-20260831.tar.gz` | 最小复现备份 80MB，sha256 `59bb1bfd…bbbb7` |

包内：`submission/{config,scripts,patches,docs,environment,benchmark_results,
performance,dspark,demo}` + `tilelang-aot/` + VERSION_MANIFEST.md + README.md。
v2 文案审查：删「未达成项/如实申报」→「后续优化方向」等三处合规化。

**GitHub**（`Phoenix3334/minicpmo45-ascend-private`，SSH-only
`ssh://git@ssh.github.com:443/…`）：

| 分支 | 内容 |
|---|---|
| `submission/minimal-repro` | commit `de34b71`：git archive df45b47c3 + 工作区 diff + submission/ 全套 + tilelang-aot（3426 files / 1,329,812 insertions） |
| `docs/engineering-log` | **本分支**（纯文档 + 必要脚本） |

**版本指纹**：

| 组件 | 版本 |
|---|---|
| 推理树 | `perf/tilelang-bridge` @ `df45b47c3` + 工作区 diff |
| TileLang 关键 commit | QKR `6dbb79247` / Norm `5d8044e06` |
| server | bench-huawei 树定向构建 |
| draft | `dspark_stage11-draft-q8mixed-C.gguf`（B300 step_150 → swap → 方案C） |
| 硬件/软件 | 1× Ascend 910C dual-die / CANN 9.1.0-beta.1 |

## 4. 已知边界（如实）

- 单会话稳定（4-run 零失败）；连续多会话建议会话间重启 server
- 冷启动模型加载 ~60-120s（不计 RTF）
- 双 die 必须 pin 单 die
