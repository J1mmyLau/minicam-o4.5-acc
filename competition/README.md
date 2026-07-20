# Competition — Official Evaluation Infrastructure

评测对象：`llama-omni-server`（常驻服务），非 CLI。
评测 worktree：`/workspace/llama.cpp-omni-official-eval`（branch `eval/official-baseline`, commit `bde403d`）。

## 文件

| 文件 | 用途 | 状态 |
|------|------|------|
| `README.md` | 评测目录入口 | done |
| `METRIC_CONTRACT.md` | 指标定义协议——starter kit 到后必须逐项核对 | provisional |
| `benchmark_client.py` | 并发 benchmark（协议解耦：HTTP/WS/Official adapter） | provisional, official adapter pending |
| `run_concurrency_matrix.sh` | 并发矩阵扫描（C1/C2/C4/C8） | provisional |
| `resource_monitor.sh` | CPU/NPU/HBM/RSS 采样 | static-ready |
| `correctness_check.py` | WAV format + 请求成功率校验 | provisional |
| `parse_results.py` | JSONL → CSV/JSON 统计报告 | static-ready |
| `report_template.md` | 官方报告模板 | done |
| `STARTER_KIT_CHECKLIST.md` | 45 项 starter kit 核对清单 | pending |

## 使用顺序

```bash
# 1. 启动服务
/workspace/llama.cpp-omni-official-eval/build/bin/llama-omni-server ...

# 2. 启动资源监控（后台）
bash resource_monitor.sh <server-pid> &

# 3. 跑并发矩阵
bash run_concurrency_matrix.sh

# 4. 解析结果
python3 parse_results.py results/*.jsonl

# 5. 生成报告
cat report_template.md  # 填入数据
```

## 当前状态

**provisional**——所有指标定义均为预估值。正式定义以官方 starter kit 为准。
