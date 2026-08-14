# OFFICIAL_GATE_TOOLING_SELFTEST（官方 Gate 工具链离线自检）

> 生成：2026-08-05 · 结果：**14/14 PASS** · 状态：**OFFICIAL_GATE_TOOLING_READINESS=PASS**
> 全部自检**离线**执行：不起服务、不占 NPU、不发 benchmark 请求、不落成绩、不写 PASS 结果。
> 与 `OFFICIAL_GATE_READINESS_REPORT.md`（7 项核查）配套：本文件记录工具链修复后的可复现自检命令与结果。
> 统一评测分支已到达（`OFFICIAL_UNIFIED_EVAL_BRANCH=AVAILABLE`）；本文件**不产生任何 OFFICIAL 成绩**。

---

## 0. 工具链修复内容（本次收口提交）

| # | 项 | 交付 |
|---|---|---|
| 1 | baseline chunk RTF 入口 | `run_performance.sh MODE=baseline\|candidate`（同 runner/数据/seed/warmup/count/统计）+ 输出隔离 `${OUTPUT_ROOT}/<run_id>/<mode>/` + `manifest.json` + `check_baseline_candidate_symmetry.py` |
| 2 | 真实 valid_audio 判定 | `analyze_chunk_rtf.py::validate_chunk`（10 排除原因）+ total/valid/invalid/exclusion_rate/reason counts + `submission/tests/test_analyze_chunk_rtf.py`（21 例） |
| 3 | Gate 脚本显式 --dry-run | `run_daily_omni.sh` / `run_tts_seed.sh` / `run_video_mme.sh` / `run_performance.sh`，返回码 0/2/3/4 |
| 4 | 私有路径清除 + 统一变量 | `MODEL_PATH` 必填无默认；`DATA_ROOT/DEMO_DIR/OUTPUT_ROOT/OFFICIAL_HARNESS_ROOT` 从 REPO_ROOT 派生；`check_no_private_paths.py` 审计 |

---

## 1. 自检命令与结果（全量）

```bash
# 一键全量（可选 SELFTEST_MODEL_PATH=<真实模型> 启用 candidate exit-0 dry-run 检查）
SELFTEST_MODEL_PATH=/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf \
  bash submission/tests/run_selftest.sh
```

| # | 检查项 | 命令 | 期望 | 实测 |
|---|---|---|---|---|
| 1a | 解析脚本 --help | `python3 submission/scripts/analyze_chunk_rtf.py --help` | rc=0 | ✅ rc=0 |
| 1b | 客户端 --help | `python3 submission/scripts/run_chunk_rtf_client.py --help` | rc=0 | ✅ rc=0 |
| 1c | 对称性检查 --help | `python3 submission/scripts/check_baseline_candidate_symmetry.py --help` | rc=0 | ✅ rc=0 |
| 2a | Gate 缺官方 Harness | `bash submission/scripts/run_daily_omni.sh --dry-run` | rc=2 不起服务 | ✅ rc=2 |
| 2b | 同上 | `bash submission/scripts/run_tts_seed.sh --dry-run` | rc=2 | ✅ rc=2 |
| 2c | 同上 | `bash submission/scripts/run_video_mme.sh --dry-run` | rc=2 | ✅ rc=2 |
| 3a | run_performance 无效 MODE | `env MODE=bogus bash submission/scripts/run_performance.sh --dry-run` | rc=3 | ✅ rc=3 |
| 3b | baseline 未给二进制 | `env MODE=baseline bash submission/scripts/run_performance.sh --dry-run` | rc=3 | ✅ rc=3 |
| 3c | baseline 二进制不存在 | `env MODE=baseline BASELINE_SERVER_BIN=/nonexistent bash submission/scripts/run_performance.sh --dry-run` | rc=2 | ✅ rc=2 |
| 3d | candidate 资产齐全 | `env MODEL_PATH=<真实模型> bash submission/scripts/run_performance.sh candidate --dry-run` | rc=0 | ✅ rc=0 |
| 4 | valid_audio 单测 | `python3 -m unittest submission/tests/test_analyze_chunk_rtf.py` | 21 例全过 | ✅ 21/21 |
| 5 | 对称性 fixtures | `python3 submission/tests/make_symmetry_fixture.py` | 0/1/2 退出码 | ✅ 3/3 |
| 6 | 私有路径扫描 | `python3 submission/tests/check_no_private_paths.py --verbose` | 无 `/workspace /home /tmp` | ✅ PASS |
| 7 | 输出目录不在 /tmp | `grep -c '/tmp' submission/config/server.env submission/scripts/run_performance.sh` | 0 | ✅ 0 |

**结果**：`SELFTEST_RESULT PASS=14 FAIL=0`

---

## 2. run_performance.sh candidate --dry-run 实测输出（节选）

```
== DRY_RUN run_performance.sh (MODE=candidate) ==
  MODE            : candidate
  MODEL_PATH      : /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf (sha=d1e69845…)
  DATA            : builtin-default-texts (data_sha=c8b644f1…)
  SERVER_BIN      : …/build/bin/llama-omni-server (sha=db258375…)
  SERVER_PORT     : 18093
  RUN_DIR         : …/submission_runs/run_<ts>_perf/candidate
  N/WARMUP/SEED   : 3/0/0  sample_rate=24000
  source_commit   : <git HEAD>  candidate_source=bdd4550
  stats_code_sha  : 65ff2302…
  server_cmd      : stdbuf -oL -eL <SERVER_BIN> -m <MODEL> -ngl 999 --device CANN0 -c 4096 -b 512 -ub 512 --split-mode layer --port 18093
  benchmark_cmd   : python3 …/run_chunk_rtf_client.py --port 18093 --n 3 --warmup 0 --seed 0 --texts-out <RUN_DIR>/requests.txt
  analyze_cmd     : python3 …/analyze_chunk_rtf.py <RUN_DIR>/server.log <run_id> --out <RUN_DIR>/out … --warmup 0 --wav-dir <RUN_DIR>
  symmetry        : SKIP（baseline 尚未运行；同 RUN_ID 跑完对侧后可做对称性检查）
DRY_RUN_OK
```

> 注：dry-run **不创建任何目录、不启动 server、不发请求**；打印的 RUN_DIR 仅为将写入路径。

## 3. Gate 脚本 --dry-run 实测输出（run_daily_omni.sh 为例）

```
== DRY_RUN run_daily_omni.sh (MODE=candidate) ==
  MODE            : candidate
  DATA            : <REPO_ROOT>/../benchmarks/Daily-Omni
  MODEL_PATH      : <unset>
  OFFICIAL_SCRIPT : <unset>
  SERVER_PORT     : 18093
  OUT             : <REPO_ROOT>/submission_runs/run_<ts>_daily_omni/candidate
  server_cmd      : RUN_DIR=<OUT>/run bash …/start_server.sh
  benchmark_cmd   : python3 <official-harness> --data <DATA> --out <OUT>（以官方 Harness 为准）
  missing_official_assets : NO（统一评测分支已到达，仅需设置 OFFICIAL_SCRIPT 指向官方脚本）
DRY_RUN_OK(none)   → rc=2
```

## 4. 冻结日志离线验证（analyze_chunk_rtf.py 全链路）

```bash
python3 submission/scripts/analyze_chunk_rtf.py \
  docs/f6-s13-closure/phase2/t6_evidence_pass/t6_smoke_srv.log frozen_t6_smoke \
  --out <scratch> --binary-sha db258375… --model-sha d1e69845… --mode candidate
```

实测：329 chunk 全 valid（exclusion_rate=0.0），RTF 分布 p50=0.2784 / p95=0.3248，
首 chunk p50=0.3039 / 尾 chunk p50=0.2123；CSV 含 `exclusion_reason` 列。
（与 LLAMA_CONFIRMED 参考值 RTF=0.23 属不同运行，一致区间内。）

## 5. 返回码语义（所有 Gate wrapper 统一）

| 返回码 | 含义 | 触发示例 |
|---|---|---|
| 0 | 配置与资产完整可执行 | candidate 资产齐全 + --dry-run |
| 2 | 缺少官方资产或 Harness | `OFFICIAL_SCRIPT` 未设 / 数据目录缺失 / 模型缺失 / 二进制缺失 |
| 3 | 配置非法 | MODE 非 baseline\|candidate；baseline 未给 `BASELINE_SERVER_BIN` |
| 4 | baseline/candidate 不对称 | 对侧 manifest 存在且 `check_baseline_candidate_symmetry.py` 不一致 |

## 6. 复现

```bash
bash submission/tests/run_selftest.sh
python3 -m unittest submission/tests/test_analyze_chunk_rtf.py
python3 submission/tests/make_symmetry_fixture.py
python3 submission/tests/check_no_private_paths.py --verbose
```
