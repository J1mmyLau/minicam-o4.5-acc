# F6 复现指南

> 从 clean checkout 到冻结 binary 结果核验的完整步骤。
> **候选源码**: `bdd4550` | **状态**: `FINAL_INTERNAL`

---

## 前提

- **硬件**: Ascend 910C (dual-die, 64 GB HBM)
- **驱动**: CANN 9.1.0-beta.1 (Ascend-hdk-9.1.0beta1)
- **模型**: `MiniCPM-o-4_5-F16.gguf` (SHA `d1e69845…`, 16.38 GB)
- **OS**: openEuler 22.03 SP4 (aarch64)
- **编译工具**: CMake 3.22+, GCC 11.4+, ASCEND TOOLCHAIN
- **Python**: Python 3 (标准库，无 pip 包依赖)

---

## Step 1: 环境验证 (30s)

```bash
cd /workspace/llama.cpp-omni-f6

# 检查 NPU 设备
npu-smi info -l

# 检查 CANN 环境
echo $ASCEND_HOME
ls $ASCEND_HOME/compiler/lib64/libacl.so

# 检查模型文件
sha256sum /path/to/MiniCPM-o-4_5-F16.gguf
# 期望: d1e69845...

# 一键环境检查
MODEL_PATH=/path/to/MiniCPM-o-4_5-F16.gguf \
  bash submission/environment/env_check.sh
# 期望输出: ENV_CHECK=PASS
```

**期望**:
- 至少 1 个 NPU 设备 (Ascend910C)
- `ASCEND_HOME` 指向 CANN 安装目录
- 模型文件存在且 SHA 匹配
- 端口 18093 可用

---

## Step 2: 源码 checkout (10s)

```bash
cd /workspace/llama.cpp-omni-f6
git checkout bdd4550
git log --oneline -1
# 期望: bdd4550 <commit message>
git status --short
# 期望: 干净（无未提交修改）
```

**重要**: 冻结候选 `bdd4550` 不得修改。如果需要实验，必须在独立分支/worktree 上进行。

---

## Step 3: 构建 (5-15min, 取决于缓存)

```bash
cd /workspace/llama.cpp-omni-f6

# 清理旧构建（可选但推荐）
rm -rf build

# CMake 配置
cmake -B build \
  -DGGML_CANN=ON \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DGGML_CPU_ALL_VARIANTS=OFF \
  -DGGML_CPU_ARM_ARCH=armv8.2-a

# 构建（单目标，避免 standard server target 问题）
cmake --build build --target llama-omni-server -j$(nproc)
```

**已知问题**: standard server target (不带 omni 的) 可能构建失败。只需构建 `llama-omni-server` 目标。

**可选验证步骤** (build-twice-same-dir 复现协议):
```bash
# 第一次构建
cmake --build build --target llama-omni-server -j$(nproc)
sha256sum build/bin/llama-omni-server > /tmp/sha1.txt

# 增量重建（不 clean）
cmake --build build --target llama-omni-server -j$(nproc)
sha256sum build/bin/llama-omni-server > /tmp/sha2.txt

# 逐字节一致性检查
diff /tmp/sha1.txt /tmp/sha2.txt
# 期望: no difference
```

**期望二进制 SHA** (在当前工具链/环境下的参考值):
- `llama-omni-server`: `db258375c3d2185ca2181da2a5c8f99a95d381413fcb7ab92a771850ba3a4a21`
- `libomni.so`: `c4b169376bced6bc3107cfda2f77abf35a634c1e146eed313a193e99e3739ea1`

> **注意**: 二进制 SHA 在相同工具链和构建目录下应一致；不同环境可能因 libstdc++ rpath、ASCEND 路径嵌入等原因有差异。不要求跨环境逐字节一致。

---

## Step 4: 离线自检 (1min, 不需要 NPU)

```bash
SELFTEST_MODEL_PATH=/path/to/MiniCPM-o-4_5-F16.gguf \
  bash submission/tests/run_selftest.sh
# 期望: SELFTEST_RESULT PASS=14 FAIL=0
```

检查项:
- 所有脚本语法检查
- `--help` 输出
- Gate `--dry-run` 返回码 (rc=0/2/3/4)
- `valid_audio` 单测 (21 例)
- 对称性 fixture
- 私有路径审计

---

## Step 5: 启动 Server (自动化脚本)

```bash
export MODEL_PATH=/path/to/MiniCPM-o-4_5-F16.gguf
export OMNI_T2W_DEVICE=cann-flow-only
export OMNI_VOC_DEVICE=gpu
export OMNI_KV_CACHE_REUSE=1

bash submission/scripts/run_performance.sh candidate --dry-run
# 期望: rc=0 + DRY_RUN_OK
```

---

## Step 6: 启动 Server (手动，用于开发/调试)

```bash
cd /workspace/llama.cpp-omni-f6

export MODEL_PATH=/path/to/MiniCPM-o-4_5-F16.gguf
export OMNI_T2W_DEVICE=cann-flow-only
export OMNI_VOC_DEVICE=gpu
export OMNI_KV_CACHE_REUSE=1

./build/bin/llama-omni-server \
  -m "$MODEL_PATH" \
  --host 0.0.0.0 --port 18093 \
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

**参数说明**:

| 参数 | 值 | 原因 |
|------|-----|------|
| `-ngl` | `999` | 全部模型 weight → CANN NPU |
| `-fa` | `off` | CANN FLASH_ATTN_EXT 仅 F16；关闭用 fallback |
| `-c` | `4096` | 足够容纳 system prompt + ref audio + 多轮对话 |
| `-b` | `512` | Prefill batch size |
| `-ub` | `512` | UMA buffer size |
| `--split-mode` | `layer` | 按 layer 分配 backend（-ngl 999 下全在 CANN） |
| `--device` | `CANN0` | 显式指定 CANN 设备 |
| `--no-mmap` | — | 避免 mmap 与 CANN 的兼容问题 |

**环境变量**:

| 变量 | 值 | 原因 |
|------|-----|------|
| `OMNI_T2W_DEVICE` | `cann-flow-only` | Flow (DiT) 强制 CANN + FAIL-FAST |
| `OMNI_VOC_DEVICE` | `gpu` | Vocoder (HiFi-GAN) 强制 CANN |
| `OMNI_KV_CACHE_REUSE` | `1` | 启用静态 prefix KV 复用 |

---

## Step 7: 发送请求 (HTTP)

### 7.1 omni_init (初始化会话)

```bash
curl -X POST http://localhost:18093/v1/stream/omni_init \
  -H "Content-Type: application/json" \
  -d '{
    "media_type": 2,
    "use_tts": true,
    "duplex_mode": false
  }'
# 期望: {"session_id": "...", "status": "ok"}
```

**media_type 说明**:
- `1`: audio-only (whisper → LLM → text/tts)
- `2`: omni (vision + audio → LLM → text/tts)

### 7.2 Prefill (一次性，首次请求)

```bash
# system prompt + reference audio embedding
curl -X POST http://localhost:18093/v1/stream/prefill \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "<from omni_init>",
    "prompt": "<system prompt text>",
    "media": []
  }'
# 期望: {"status": "complete"}
```

**Prefill 协议**:
- 首次 prefill → system prompt + reference audio → 耗时 ~206ms (MISS)
- 如果 `OMNI_KV_CACHE_REUSE=1`: 后续请求 → 复用 KV cache → 耗时 ~85ms (HIT)
- 必须在全部 decode 之前完成；一次 prefill 可服务多次 decode

### 7.3 Decode (流式)

```bash
curl -X POST http://localhost:18093/v1/stream/decode \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "<from omni_init>",
    "user_text": "你好，请介绍一下你自己"
  }' \
  --no-buffer
# SSE 流式输出: text delta + WAV base64 chunks
```

**预期行为**:
- SSE 流式返回 text delta
- 当 `<|speak|>` 触发后，返回 WAV chunks (16-bit PCM @24kHz, base64)
- 以 `<|chunk_eos|>` 或 `[done]` 结束

### 7.4 Break / Reset

```bash
# 中断当前生成
curl -X POST http://localhost:18093/v1/stream/break \
  -H "Content-Type: application/json" \
  -d '{"session_id": "<session_id>"}'

# 重置 session (释放 KV cache，重新 prefill)
curl -X POST http://localhost:18093/v1/stream/reset \
  -H "Content-Type: application/json" \
  -d '{"session_id": "<session_id>"}'
```

---

## Step 8: 验证优化效果

### 8.1 T2W 设备放置验证

验证 Flow + Vocoder 在 CANN 上运行：

```bash
# 启动 server 时开启 path stats
OMNI_VOC_PATH_STATS=1 ./build/bin/llama-omni-server ...

# 检查日志
grep "vocoder_cann_dispatch_count" server.log
# 期望: >0 (CANN path 被使用)

grep "vocoder_cpu_dispatch_count" server.log
# 期望: 0 (无 CPU fallback)
```

### 8.2 Static Prefix KV Cache 验证

```bash
# 启动时开启 KV reuse
OMNI_KV_CACHE_REUSE=1 ./build/bin/llama-omni-server ...

# 检查日志
grep "KV_CACHE_REUSE" server.log
grep "cache_miss" server.log
# 期望: miss=1 (首次), miss=0 (后续)
```

### 8.3 延时测量

请求首包 WAV 延迟可在 server 日志中查看 `T2W线程` 行，或通过客户端计时 HTTP request → 首个含 WAV 的 SSE chunk。

---

## Step 9: chunk RTF 采集 (内部工具链)

```bash
# 离线分析已有 server 日志
python3 submission/scripts/analyze_chunk_rtf.py \
  <server.log> <run_id> \
  --out submission_runs/<run_id>/candidate/ \
  --binary-sha db258375... \
  --model-sha d1e69845... \
  --mode candidate \
  --warmup 0
```

输出:
- `chunk_rtf_raw.csv`: 逐 chunk 明细
- `chunk_rtf_summary.json`: 统计 (total/valid/invalid/exclusion_rate/RTF 分桶)

---

## Step 10: 正确性冒烟 (5 requests)

```bash
# 5 组不同 prompt，检查输出有效性
for prompt in \
  "你好，请介绍一下你自己" \
  "今天天气怎么样" \
  "请用一句话总结人工智能" \
  "What is the capital of France?" \
  "1234567"
do
  echo "Testing: $prompt"
  curl -s -X POST http://localhost:18093/v1/stream/decode \
    -H "Content-Type: application/json" \
    -d "{\"session_id\":\"$SESSION_ID\",\"user_text\":\"$prompt\"}" \
    --no-buffer -o /tmp/resp_$(echo $prompt | md5sum | cut -c1-8).txt
done

# 检查输出有效性
# - 所有请求返回 HTTP 200
# - 无 CANN error (grep server.log)
# - 无 CPU fallback (grep server.log)
# - text 输出非空
# - WAV chunks 存在（当 use_tts=true）
```

---

## Step 11: 生命周期验证 (3 sequential)

```bash
# 同一 session 连续 3 次 decode，验证 ctx 复用
for i in 1 2 3; do
  echo "=== Request $i ==="
  curl -s -X POST http://localhost:18093/v1/stream/decode \
    -H "Content-Type: application/json" \
    -d "{\"session_id\":\"$SESSION_ID\",\"user_text\":\"请求 $i\"}" \
    --no-buffer -o /tmp/resp_seq_$i.txt
  sleep 1
done

# 检查
# - 3 次全部 HTTP 200
# - 无 drain timeout
# - 无 ctx validity error
# - 跨请求无 contamination
```

---

## Step 12: 回归测试 (Gate --dry-run)

```bash
# 全部 Gate dry-run
cd /workspace/llama.cpp-omni-f6
bash submission/scripts/run_daily_omni.sh --dry-run
bash submission/scripts/run_tts_seed.sh --dry-run
bash submission/scripts/run_video_mme.sh --dry-run
bash submission/scripts/run_demo.sh --dry-run
bash submission/scripts/run_performance.sh candidate --dry-run

# 期望: 全部 rc=0
```

---

## Step 13: 结果核验清单

完成以上步骤后，按此清单逐项核验：

- [ ] `env_check.sh` → `ENV_CHECK=PASS`
- [ ] `selftest.sh` → `SELFTEST_RESULT PASS=14 FAIL=0`
- [ ] 构建 → 二进制 SHA 与冻结记录一致 (在当前环境下)
- [ ] 离线分析 → chunk RTF summary 产生 valid/exclusion_rate
- [ ] 服务启动 → 无 CANN error, `-ngl 999` 生效
- [ ] T2W device → `vocoder_cann_dispatch_count > 0`, `vocoder_cpu_dispatch_count = 0`
- [ ] KV cache → `cache_miss=1` (首次) → `cache_miss=0` (后续)
- [ ] 5 请求冒烟 → 全部 200, text/WAV 有效
- [ ] 3 请求生命周期 → ctx 复用成功
- [ ] Gate dry-run → 全部 rc=0
- [ ] 无 CANN error / CPU fallback / 内存泄漏迹象

---

## Step 14: 输出归档

```bash
RUN_ID=run_$(date +%Y%m%d_%H%M%S)
mkdir -p submission_runs/$RUN_ID/candidate

# 保存 manifest
python3 submission/scripts/make_manifest.py \
  --binary-sha $(sha256sum build/bin/llama-omni-server | cut -d' ' -f1) \
  --model-sha $(sha256sum "$MODEL_PATH" | cut -d' ' -f1) \
  --commit bdd4550 \
  --env-file server.env \
  --out submission_runs/$RUN_ID/candidate/manifest.json

# 保存 server 日志
cp server.log submission_runs/$RUN_ID/candidate/

# 运行离线分析
python3 submission/scripts/analyze_chunk_rtf.py \
  server.log $RUN_ID \
  --out submission_runs/$RUN_ID/candidate/ \
  --binary-sha db258375... --model-sha d1e69845... \
  --mode candidate --warmup 0
```

---

## Step 15: 排查常见问题

| 症状 | 可能原因 | 检查 |
|------|---------|------|
| Server 启动失败 `CANN error` | CANN 环境变量未设 | `echo $ASCEND_HOME`, `source set_env.sh` |
| `-ngl 999` 后仍有 CPU op | `-fa off` 未设置 (FLASH_ATTN_EXT F32 回退) | 检查启动参数 |
| Prefill 耗时远超 206ms | KV cache 未 HIT, 首次 prefill | 正常，首次 MISS 预期 206ms |
| T2W 仍然在 CPU | env var 未设置或拼写错误 | `env | grep OMNI_T2W_DEVICE` |
| WAV 文件无效 | 采样率/编码不匹配 | 期望 16-bit PCM @24kHz |
| 构建失败 (standard server) | 非 omni server target | 只构建 `llama-omni-server` 目标 |
| 端口占用 | 旧进程未退出 | `lsof -i :18093` |

---

## Step 16: 清理

```bash
# 停止 server
kill $(pgrep -f llama-omni-server)

# 清理运行数据 (可选)
rm -rf submission_runs/run_*
```
