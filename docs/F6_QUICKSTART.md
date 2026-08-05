# F6 快速开始

> 在 Ascend 910C 上 5 分钟跑通冻结候选。
> **候选源码**: `bdd4550` | **冻结 binary**: `db258375` | **状态**: `FINAL_INTERNAL`

---

## 前提

- Ascend 910C (dual-die)，CANN 9.1.0-beta.1
- 模型 `MiniCPM-o-4_5-F16.gguf` (SHA `d1e69845…`, 16.38 GB)
- 冻结 server 二进制 `build/bin/llama-omni-server`
- Python 3（标准库即可，无 pip 依赖）

---

## 1. 环境检查 (30s)

```bash
cd /workspace/llama.cpp-omni-f6
MODEL_PATH=/path/to/MiniCPM-o-4_5-F16.gguf \
  bash submission/environment/env_check.sh
```

期望输出: `ENV_CHECK=PASS`
检查项: CANN 环境、NPU 设备、模型文件、端口空闲。

---

## 2. 构建 (5-15min)

```bash
cd /workspace/llama.cpp-omni-f6

cmake -B build \
  -DGGML_CANN=ON \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON

cmake --build build --target llama-omni-server -j$(nproc)
```

> 只需构建 `llama-omni-server` 目标。standard server target（不带 omni）可能构建失败，属已知问题。

---

## 3. 离线自检 (1min, 不需要 NPU)

```bash
SELFTEST_MODEL_PATH=/path/to/MiniCPM-o-4_5-F16.gguf \
  bash submission/tests/run_selftest.sh
```

期望: `SELFTEST_RESULT PASS=14 FAIL=0`

---

## 4. 启动 Server (Canonical Command)

```bash
cd /workspace/llama.cpp-omni-f6

export MODEL_PATH=/path/to/MiniCPM-o-4_5-F16.gguf
export OMNI_T2W_DEVICE=cann-flow-only
export OMNI_VOC_DEVICE=gpu
export OMNI_KV_CACHE_REUSE=1

./build/bin/llama-omni-server \
  -m "$MODEL_PATH" \
  --host 0.0.0.0 \
  --port 18093 \
  -ngl 999 \
  -fa off \
  -c 4096 \
  -b 512 \
  -ub 512 \
  --split-mode layer \
  --device CANN0 \
  --no-mmap \
  --mlock
```

### 参数与 env 速查

| 参数/env | 值 | 为什么 |
|----------|-----|--------|
| `-ngl 999` | 全部 layer → CANN | 主模型 decode 在 NPU |
| `-fa off` | 关闭 Flash Attention | CANN FLASH_ATTN_EXT 仅支持 F16；关闭用 CPU fallback 避免 dtype 错误 |
| `-c 4096` | Context 长度 4096 | system prompt + ref audio + 多轮对话 |
| `-b 512` | Prefill batch size | — |
| `-ub 512` | UMA buffer size | — |
| `--split-mode layer` | 按 layer 分配 backend | `-ngl 999` 下全在 CANN |
| `--device CANN0` | 显式 CANN 设备 | — |
| `--no-mmap` | 关闭 mmap | 避免与 CANN 内存管理冲突 |
| `OMNI_T2W_DEVICE=cann-flow-only` | Flow (DiT) → CANN | **F6 最大收益来源** |
| `OMNI_VOC_DEVICE=gpu` | Vocoder (HiFi-GAN) → CANN | — |
| `OMNI_KV_CACHE_REUSE=1` | 静态 prefix KV 复用 | Prefill 2.4× speedup |

---

## 5. 发送 HTTP 请求

### 5.1 初始化会话

```bash
curl -X POST http://localhost:18093/v1/stream/omni_init \
  -H "Content-Type: application/json" \
  -d '{"media_type": 2, "use_tts": true, "duplex_mode": false}'
# → {"session_id": "...", "status": "ok"}
```

> **media_type**: `1` = audio-only, `2` = omni (vision+audio).
> **Prefill 协议**: 必须先 prefill 再 decode。一次 prefill 可服务多次 decode。

### 5.2 Prefill

```bash
SESSION_ID="<from omni_init>"

curl -X POST http://localhost:18093/v1/stream/prefill \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\", \"prompt\": \"<system prompt>\", \"media\": []}"
# → {"status": "complete"}
```

### 5.3 Decode (流式 SSE)

```bash
curl -X POST http://localhost:18093/v1/stream/decode \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\", \"user_text\": \"你好\"}" \
  --no-buffer
# SSE 流式输出: text delta + WAV base64 chunks → 以 [done] 结束
```

---

## 6. 开发常用命令

```bash
# === 构建 ===
cmake --build build --target llama-omni-server -j$(nproc)

# === 验证 ===
grep "vocoder_cann_dispatch_count" server.log      # T2W 在 CANN?
grep "cache_miss" server.log                        # KV cache hit?
grep "CANN error" server.log                        # CANN 错误?

# === 自检 ===
python3 -m unittest submission/tests/test_analyze_chunk_rtf.py -v
python3 submission/tests/check_no_private_paths.py --verbose
bash submission/scripts/run_performance.sh candidate --dry-run
bash submission/tests/run_selftest.sh

# === 离线分析 (无需 NPU) ===
python3 submission/scripts/analyze_chunk_rtf.py \
  server.log <run_id> \
  --out submission_runs/<run_id>/candidate/ \
  --binary-sha db258375... --model-sha d1e69845... \
  --mode candidate --warmup 0

# === 管理 ===
kill $(pgrep -f llama-omni-server)                 # 停止服务
lsof -i :18093                                       # 检查端口
```

---

## 7. 路径变量速查

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MODEL_PATH` | **必填，无默认** | GGUF 模型路径 |
| `REPO_ROOT` | 脚本自动推导 | 仓库根目录 |
| `DATA_ROOT` | `${REPO_ROOT}/../benchmarks` | 三 Benchmark 父目录 |
| `OUTPUT_ROOT` | `${REPO_ROOT}/submission_runs` | 评测输出根目录 |
| `DEMO_DIR` | `${REPO_ROOT}/third_party/MiniCPM-o-Demo` | 官方 Demo 前端 |
| `OFFICIAL_HARNESS_ROOT` | `${REPO_ROOT}/../llama.cpp-omni-official-eval/competition` | 官方 Harness |
| `SERVER_PORT` | `18093` | 服务端口 |

---

## 8. 官方 Gate 状态

全部 `NOT_RUN (BLOCKED_BY_OFFICIAL_STARTER_KIT)`。官方 starter kit 到达后：

```bash
# dry-run
bash submission/scripts/run_daily_omni.sh --dry-run
bash submission/scripts/run_tts_seed.sh --dry-run
bash submission/scripts/run_video_mme.sh --dry-run

# baseline + candidate 对称采集
RUN_ID=<id> bash submission/scripts/run_daily_omni.sh baseline
RUN_ID=<id> bash submission/scripts/run_daily_omni.sh candidate

# 对称性检查
python3 submission/scripts/check_baseline_candidate_symmetry.py submission_runs/$RUN_ID
```

---

## 下一步阅读

| 文档 | 内容 |
|------|------|
| [F6_README.md](F6_README.md) | 项目总览 + 状态表 |
| [F6_ARCHITECTURE.md](F6_ARCHITECTURE.md) | 全模态链路架构 (Mermaid 图) |
| [F6_OPTIMIZATION_AND_RESULTS.md](F6_OPTIMIZATION_AND_RESULTS.md) | 每项优化的详细证据 |
| [F6_REPRODUCTION_GUIDE.md](F6_REPRODUCTION_GUIDE.md) | 从 clean checkout 到核验 (16 step) |
| [F6_LIMITATIONS_AND_OFFICIAL_GATES.md](F6_LIMITATIONS_AND_OFFICIAL_GATES.md) | 已证明 / 未证明 / 被阻塞 |
| [F6_EVIDENCE_INDEX.md](F6_EVIDENCE_INDEX.md) | 每个结论→raw/commit/源码 |
