# F6 快速开始

在 Ascend 910C 上跑通冻结候选的提交工具链。

## 前提

- Ascend 910C（dual-die），CANN 9.1.0-beta.1
- 模型 `MiniCPM-o-4_5-F16.gguf`（SHA `d1e69845…`，16.38 GB）
- 冻结 server 二进制 `build/bin/llama-omni-server`（SHA `db258375…`）
- Python 3（标准库即可，无额外依赖）

## 1. 环境检查（30 秒）

```bash
cd /workspace/llama.cpp-omni-f6
MODEL_PATH=/path/to/MiniCPM-o-4_5-F16.gguf \
  bash submission/environment/env_check.sh
```

期望输出 `ENV_CHECK=PASS`。检查项：CANN 环境、NPU 设备、模型文件、冻结二进制 SHA、端口空闲。

## 2. 离线自检（1 分钟，不起服务）

```bash
SELFTEST_MODEL_PATH=/path/to/MiniCPM-o-4_5-F16.gguf \
  bash submission/tests/run_selftest.sh
```

期望 `SELFTEST_RESULT PASS=14 FAIL=0`。检查项：脚本语法、`--help`、Gate `--dry-run` 返回码、valid_audio 单测 21 例、对称性 fixture、私有路径审计。

## 3. 跑一轮 candidate RTF 采集（需要 NPU）

```bash
export MODEL_PATH=/path/to/MiniCPM-o-4_5-F16.gguf

# 先 dry-run 预检
bash submission/scripts/run_performance.sh candidate --dry-run
# 期望 rc=0 + DRY_RUN_OK

# 正式跑（N 个 TTS 请求，默认 3）
bash submission/scripts/run_performance.sh candidate
```

输出：
```
submission_runs/<run_id>/candidate/
├── manifest.json          ← 完整配置/命令/指纹
├── server.log             ← 冻结 server 日志（含 T2W线程 逐 chunk 计时）
├── client.log             ← 客户端请求日志
├── requests.txt           ← 实际使用的文本
└── out/
    ├── chunk_rtf_raw.csv  ← 逐 chunk 明细
    └── chunk_rtf_summary.json ← 统计（total/valid/invalid/exclusion_rate/RTF 分桶）
```

## 4. baseline + candidate 对称采集

```bash
export RUN_ID=run_$(date +%Y%m%d_%H%M%S)_perf

# baseline（官方基线二进制到达后）
BASELINE_SERVER_BIN=/path/to/baseline/server \
  RUN_ID=$RUN_ID bash submission/scripts/run_performance.sh baseline

# candidate
RUN_ID=$RUN_ID bash submission/scripts/run_performance.sh candidate

# 对称性检查（任一不一致退出非零）
python3 submission/scripts/check_baseline_candidate_symmetry.py \
  submission_runs/$RUN_ID
```

## 5. 只做离线分析（已有日志）

```bash
python3 submission/scripts/analyze_chunk_rtf.py \
  <server.log> <run_id> \
  --out <output_dir> \
  --binary-sha db258375... --model-sha d1e69845... \
  --mode candidate --warmup 0
```

无需 NPU、无需启动服务。输入是冻结 server 日志，输出是 CSV + summary JSON。

## 6. 每日开发常用命令

```bash
# 查看 valid_audio 单测
python3 -m unittest submission/tests/test_analyze_chunk_rtf.py -v

# 私有路径审计
python3 submission/tests/check_no_private_paths.py --verbose

# 对称性 fixture 验证
python3 submission/tests/make_symmetry_fixture.py

# 所有 Gate 脚本 dry-run
bash submission/scripts/run_daily_omni.sh --dry-run
bash submission/scripts/run_tts_seed.sh --dry-run
bash submission/scripts/run_video_mme.sh --dry-run

# 一键全量自检
bash submission/tests/run_selftest.sh
```

## 路径变量速查

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MODEL_PATH` | **必填，无默认** | GGUF 模型路径 |
| `REPO_ROOT` | 脚本自动推导 | 仓库根目录 |
| `DATA_ROOT` | `${REPO_ROOT}/../benchmarks` | 三 Benchmark 父目录 |
| `OUTPUT_ROOT` | `${REPO_ROOT}/submission_runs` | 评测输出根目录 |
| `DEMO_DIR` | `${REPO_ROOT}/third_party/MiniCPM-o-Demo` | 官方 Demo 前端 |
| `OFFICIAL_HARNESS_ROOT` | `${REPO_ROOT}/../llama.cpp-omni-official-eval/competition` | 官方 Harness |
| `SERVER_PORT` | `18093` | 服务端口 |

## 官方 Gate 当前状态

全部 `NOT_RUN (BLOCKED_BY_OFFICIAL_STARTER_KIT)`。官方 starter kit 到达后流程：

```bash
# 1. dry-run 预检
bash submission/scripts/run_daily_omni.sh --dry-run   # 期望 rc=0

# 2. baseline → candidate（同一 RUN_ID）
RUN_ID=<id> OFFICIAL_SCRIPT=<官方脚本> bash submission/scripts/run_daily_omni.sh baseline
RUN_ID=<id> OFFICIAL_SCRIPT=<官方脚本> bash submission/scripts/run_daily_omni.sh candidate

# 3. 对称性检查
python3 submission/scripts/check_baseline_candidate_symmetry.py submission_runs/$RUN_ID
```
