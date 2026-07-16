# Vision CANN NaN 定位 — 项目状态

## 当前阶段

`Phase A：FUNCTIONAL PASS` — Vision CANN 功能验证通过。原始 NaN 未复现。

## 阶段结论

```text
Vision CANN 功能验证：PASS
原始 Vision NaN：NOT REPRODUCED
多切片参数 Bug：FIXED
Full Omni 基础链路：基本跑通
```

### 已完成验证

| 项目 | 状态 | 结论 |
|------|------|------|
| Vision CANN 单图 | ✅ | 所有检查边界 NaN=0, Inf=0 |
| synchronize ON/OFF | ✅ | 结果一致，排除当前单图路径的异步读取假说 |
| CPU Vision 对照 | ✅ | CPU 同样无 NaN，LLM 输出正常 |
| MiniCPM-o 多切片参数 | ✅ 修复 | 补充 `minicpmv_max_slice_nums=9` |
| 多切片 CANN | ✅ | grid=2×1、3 chunks、192 tokens |
| Vision → LLM | ✅ | LLM 能正确描述图片 |
| 原始 NaN | ⚠️ 未复现 | 当前证据无法确认历史 NaN 根因 |

### 关键 Bug：多切片参数失效（非 NaN 根因）

MiniCPM_o 模型加载分支未初始化 `hparams.minicpmv_max_slice_nums`，默认值 0
导致运行时切片上限为 0，图像被错误限制为 grid 1×1，无法进入多切片路径。

修复：
```cpp
case MiniCPM_o:
    hparams.minicpmv_max_slice_nums = 9;  // 新增
    break;
```

修复效果：
```
修复前：max_slice_nums=0 → grid=1×1 → 单图路径
修复后：max_slice_nums=9 → grid=2×1 → 3 chunks, 192 tokens, CANN 全路径 NaN=0
```

### 原始 NaN 正式结论

> 在 Ascend 910、CANN 9.0.0、MiniCPM-o 4.5 F16 和 `feat/ascend-cann@6eeeb4d` 环境下，
> 通过单图、CPU/CANN 对照、同步开关对照以及多切片输入测试，均未能重新复现此前观察到的
> Vision Embedding 全 NaN 问题。各边界 Tensor 的 NaN 和 Inf 计数均为 0，Vision Embedding
> 可被 LLM 正常消费并输出合理的图片描述。因此，目前没有证据证明原始 NaN 来源于 CANN
> Vision 算子、异步同步或多切片路径。后续若该问题再次出现，应保存完整输入图片、运行命令、
> 环境变量、模型哈希及逐边界 Tensor 统计，以便精确复现。

## 验证矩阵

| 测试 | 日志 | 结果 |
|------|------|------|
| K1: sync=ON 单图 | v2/k1-f16-full-omni-cnt2.log | NaN=0 ✅ |
| K2: sync=OFF 单图 | v3/k2-sync-off-cnt2.log | NaN=0 ✅ |
| K3: CPU 单图 | v3/k3-cpu-vision-cnt2.log | NaN=0 ✅ |
| K4: slice 调试 | v3/k4-debug-slice.log | 诊断用 |
| K5: 多切片 CANN | v3/k5-multislice-cann.log | NaN=0 ✅ |

## 下一阶段

```
A-final：Full Omni + TTS 验收
    ↓
固定 patch 和源码 commit
    ↓
Reference Baseline (2 warmup + 5 measured)
    ↓
30 分钟稳定性
    ↓
官方 Harness 对齐
    ↓
Profiling 和性能优化
```

## 待办

| 任务 | 状态 |
|------|------|
| BatchMatMulV3 内核缺失 | BLOCKED (CANN 内核编译) |
| debug_print_tensors Full Omni 下为空 | TODO |
| 补全 prefill 边界检查 | TODO |
