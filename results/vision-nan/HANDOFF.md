# Vision CANN NaN 定位 — 交接文档 (更新 2026-07-16)

## 一句话状态

**F16 Full Omni Vision CANN 编码，单图(grid 1×1)和多 slice(grid 2×1)路径均已验证 NaN=0。原始 NaN 在当前环境无法复现。**

## 环境

| 项目 | 值 |
|------|-----|
| 仓库 | `llama.cpp-omni` |
| 分支/commit | `feat/ascend-cann` @ `6eeeb4d` |
| CANN 版本 | 9.0.0 |
| 芯片 | Ascend910_9382 |
| 构建选项 | `-DGGML_CANN=ON -DUSE_ACL_GRAPH=ON` |
| 工作目录 | `/workspace/llama.cpp-omni` |
| 构建目录 | `/workspace/llama.cpp-omni/build` |

## 本文档的代码修改 (synchronize 已恢复，调试输出已移除)

相比 `6eeeb4d` 的 3 个功能性修改：

1. **vision.cpp — minicpmv_max_slice_nums 修复**: MiniCPM_o case (model_type=0) 缺失 `hparams.minicpmv_max_slice_nums = 9`，导致运行时 max_slice_nums=0，所有图片强制 grid 1×1。已在 MiniCPM_o case 添加该赋值。
2. **vision.cpp — NaN 检测 cb 增强**: build_norm 移除条件限制，新增 patch_conv/learned_pos_embd/final_projection cb，启用 kq_pre/post_softmax cb。
3. **omni.cpp — nan_check_embed() 边界检查**: vision_chunk overview/serial/batch_slice 和 vision_embed before_prefill 的 NaN/Inf 检查点。

## 已完成测试

### K1: F16 Full Omni + synchronize=ON (单图 grid 1×1)
日志: `results/vision-nan/v2/k1-f16-full-omni-cnt2.log`
- 所有张量 NaN=0 Inf=0 ✅
- LLM 正确描述图片 ✅

### K2: synchronize=OFF A/B (单图 grid 1×1)
日志: `results/vision-nan/v3/k2-sync-off-cnt2.log`
- 与 K1 无差异 ✅ → 原始 NaN 非异步同步问题

### K3: CPU Vision 对照 (单图 grid 1×1)
日志: `results/vision-nan/v3/k3-cpu-vision-cnt2.log`
- CPU 路径 NaN=0 Inf=0 ✅，LLM 输出正确 ✅
- CPU 编码 ~16.7s vs CANN ~3.5s (约 4.7× 慢，正常)

### K4: Debug slice 诊断
日志: `results/vision-nan/v3/k4-debug-slice.log`
- 确认根因: `max_slice_nums=0 override=-1` → best_grid=1×1
- 已修复: MiniCPM_o case 添加 `hparams.minicpmv_max_slice_nums = 9`

### K5: Multi-slice (grid 2×1, CANN Vision)
日志: `results/vision-nan/v3/k5-multislice-cann.log`
- 3 chunks (1 overview + 2 slices), 192 tokens ✅
- 所有边界 NaN=0 Inf=0 ✅
- LLM 输出正确 ✅
- TTS 正常 ✅

## 代码变更汇总 (git diff HEAD)

```
vision.cpp:
  - MiniCPM_o case: +hparams.minicpmv_max_slice_nums = 9;  (修复)
  - NaN cb 增强 (norm/patch_conv/learned_pos_embd/final_projection/kq_pre/post)
  
omni.cpp:
  - +nan_check_embed() 边界检查 (overview/serial/batch_slice/prefill)

omni-cli.cpp:
  - OMNI_VISION_CPU=1 环境变量
```

## 未完成的任务

### P1
1. **BatchMatMulV3 内核缺失** — CANN 内核编译问题，独立于 NaN
2. **debug_print_tensors 为空问题** — Full Omni 路径下 cb 输出 header 但无 tensor 数据
3. **补全 prefill 路径边界检查** — omni.cpp stream_prefill index>0 处 prefill_with_emb 调用点

### P2
4. **不同图片测试** — 多尺寸/内容图片
5. **环境差异调查** — 确认用户 NaN 条件的具体差异

## 快速命令

```bash
# 重建
cd /workspace/llama.cpp-omni/build && cmake --build . -j$(nproc) --target llama-omni-cli

# F16 Full Omni (CANN Vision)
Omni_DEBUG_GRAPH=1 /workspace/llama.cpp-omni/build/bin/llama-omni-cli \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf \
  --omni -ngl 99 \
  --test /workspace/llama.cpp-omni/tools/omni/assets/test_case/omni_test_case/omni_test_case_ 2 \
  2>&1 | tee /workspace/llama.cpp-omni/results/vision-nan/v3/run.log

# CPU Vision 对照
OMNI_VISION_CPU=1 Omni_DEBUG_GRAPH=1 /workspace/llama.cpp-omni/build/bin/llama-omni-cli \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf \
  --omni -ngl 99 \
  --test /workspace/llama.cpp-omni/tools/omni/assets/test_case/omni_test_case/omni_test_case_ 2 \
  2>&1 | tee /workspace/llama.cpp-omni/results/vision-nan/v3/run-cpu.log

# 查看 git diff
cd /workspace/llama.cpp-omni && git diff HEAD
```
