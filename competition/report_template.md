# Official Benchmark Report

> **模板** — starter kit 到来后填入数据。  
> 评测 worktree: `/workspace/llama.cpp-omni-official-eval`  
> Release commit: `bde403d`

---

## 1. 环境

| 项目 | 值 |
|------|-----|
| NPU | 2× Ascend 910C, 64 GB HBM each |
| CPU | Kunpeng 920, 640 cores, 8 NUMA nodes |
| CANN | 9.0.0 |
| Driver | 25.5.1 |
| OS | openEuler 22.03 SP4, aarch64 |
| Release commit | `bde403d` |
| Binary SHA256 | `f89c6651d3f1baa21110de083263a71ac75c3f1b4308c7752243295da45acff5` |
| Model SHA256 | `d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de` |

---

## 2. 性能指标

### Concurrency = 1

| 指标 | median | p90 | p99 |
|------|--------|-----|-----|
| TTFT (ms) | 待测 | | |
| First Audio (ms) | 待测 | | |
| Chunk Interval (ms) | 待测 | | |
| E2E (ms) | 待测 | | |

### Concurrency = 2

| 指标 | median | p90 | p99 |
|------|--------|-----|-----|
| TTFT (ms) | 待测 | | |
| First Audio (ms) | 待测 | | |
| Chunk Interval (ms) | 待测 | | |
| E2E (ms) | 待测 | | |

### Concurrency = 4

| 指标 | median | p90 | p99 |
|------|--------|-----|-----|
| TTFT (ms) | 待测 | | |
| First Audio (ms) | 待测 | | |
| Chunk Interval (ms) | 待测 | | |
| E2E (ms) | 待测 | | |

### Concurrency = 8

| 指标 | median | p90 | p99 |
|------|--------|-----|-----|
| TTFT (ms) | 待测 | | |
| First Audio (ms) | 待测 | | |
| Chunk Interval (ms) | 待测 | | |
| E2E (ms) | 待测 | | |

---

## 3. Throughput

| Concurrency | Throughput (req/s) | Success Rate |
|-------------|-------------------|--------------|
| 1 | 待测 | 待测 |
| 2 | 待测 | 待测 |
| 4 | 待测 | 待测 |
| 8 | 待测 | 待测 |

---

## 4. 资源占用

| 指标 | idle | C=1 | C=4 | C=8 |
|------|------|-----|-----|-----|
| RSS (MB) | 待测 | | | |
| HBM0 (MB) | 待测 | | | |
| HBM1 (MB) | 待测 | | | |
| CPU (%) | 待测 | | | |
| Threads | 待测 | | | |

---

## 5. 正确性

| 项目 | 结果 |
|------|------|
| 成功率 | 待测 |
| WAV 格式 | 待测 |
| NaN/Inf | 待测 |
| 官方样例 | 待测 |

---

## 6. 已知问题

- TTS 在 CPU 运行（CANN 设备 1 兼容 workaround, F-003）
- Vision 批量编码不可用（BatchMatMulV3 缺失, F-002）
- 历史 Vision NaN 未复现（F-001）
