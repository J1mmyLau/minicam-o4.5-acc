# Vision CANN NaN 定位 — 任务清单

## Phase A: FUNCTIONAL PASS ✅

| 任务 | 状态 | 结论 |
|------|------|------|
| 环境与 F16 模型确认 | DONE | |
| llama.cpp-omni CANN 构建 | DONE | `feat/ascend-cann@6eeeb4d` |
| Audio-only | DONE | |
| TTS + Token2Wav | DONE | TTS 退 CPU (RTF ~3.9) |
| Vision 单图 | DONE | CANN NaN=0 |
| Vision CPU/CANN 对照 | DONE | 均 NaN=0 |
| 同步开关 A/B | DONE | 无差异 |
| 多切片参数 Bug 修复 | DONE | `minicpmv_max_slice_nums=9` |
| Vision 多切片 | DONE | grid=2×1, 3 chunks, NaN=0 |
| Vision → LLM | DONE | LLM 正确描述图片 |
| 原始 NaN 根因 | UNRESOLVED | NOT REPRODUCED |
| Full Omni + TTS 完整验收 | READY | |
| Reference Baseline | READY | 2 warmup + 5 measured |

## Phase B: 待复现 NaN

- [ ] 获取用户实际图片和命令
- [ ] 修复 CANN BatchMatMulV3 内核缺失
- [ ] 不同图像尺寸/内容测试

## Phase C: 剩余待办

- [ ] debug_print_tensors 在 Full Omni 路径下为空
- [ ] 补全 stream_prefill index>0 prefill 边界检查
