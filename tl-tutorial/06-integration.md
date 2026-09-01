# 06 · 从 kernel 到生产（本项目接线全流程）

> 写对 kernel 只是一半；让它跑进 llama.cpp 服务、可回滚、可验证是另一半。
> 本项目全链路：**kernel.py → AOT .so → ggml-cann 桥接 → env 开关 →
> 位级 parity → NPU A/B → 提交**。

## 1. AOT 编译：kernel → `.so`（纯 C ABI）

`code/aot_llm_kernels.py`（生产脚本，节选模式）：

```python
from tilelang.jit.adapter.libgen import LibraryGenerator
from tilelang.utils.target import determine_platform
from llm_fused_kernels import norm_row, fused_rope_view

for T in [1, 2, 3, 4, 5, 6, 7, 8, 16]:          # 形状特化 → 每个一编
    k = norm_row(T, 768, block_N_in=768, dtype="float")
    lg = LibraryGenerator(target='ascendc', platform=determine_platform('auto'))
    lg.update_lib_code(k.get_kernel_source())     # 拿 CCE 源
    lg.compile_lib()                              # 编 .so
    shutil.copy(lg.get_lib_path(), f'{OUT}/tltsnorm_N768_T{T}_F32.so')
```

命名即形状（`tltsnorm_N768_T5_F32.so`、`tlconv_C128_O128_K11_D3_T1280.so`），
提交包里 `tilelang-aot/` 有 224 个。dlopen 直接调用，单核 15.3µs/call，
没有 Python 开销。

## 2. 桥接进 ggml-cann（side-loading）

问题：ggml-cann 的 CMakeLists 是冻结的，不能改构建。
解法：**桥以独立源码挂进 `ggml/src/ggml-cann/`**（`tl_conv_bridge.cpp`、
`tl_layout_bridge.cpp` 等 + `patch_ggml_cann_custom.diff`），在算子分发处
拦截特定 pattern 调 dlopen 的 .so。输出与原生路径位相等。

## 3. env 开关：一切可回滚

```
OMNI_TL_QKR=1     # QK-norm+RoPE 融合核
OMNI_TL_NORM=1    # RMSNorm 行融合
OMNI_TL_TTS=1     # TTS 生成链融合
OMNI_TL_CONV=1    # vocoder conv1d
```

launch-only：关掉就走原生路径，A/B 就是改一个 env。
（精度任务走 `config-accuracy.env` 全关——见 07 练习 4。）

## 4. 验证金字塔（自下而上，缺一不可）

```
① kernel 级：ref 实现 + torch.testing.assert_close
      （llm_fused_kernels.py / test_qknorm_rope.py 自带）
② 桥接级：bridge_parity_probe.py —— 同输入过桥 vs 直调，
      rel 误差必须 ~1e-7 级（位级）
③ 服务级：NPU A/B —— 同 seed 同 harness，4-run mean±stdev，
      位级一致才计时；对照归一化模型加载
④ 精度级：四项指标（videomme/daily/WER/SIM）在隔离口径下过线
```

`code/bridge_parity_probe.py` 是 ② 的活例子（30 行）：

```python
kern = fused_rope_view(H, D, ROW, T, dtype="float")
y = kern(x.reshape(-1), cs_tbl, sn_tbl, pos)
# 手写 NeoX 参考实现 yv，比较
print("rope_view harness check rel =", (d.mean()/yv.abs().mean()).item())
```

## 5. 全链路一图

```
profile 定热点（msprof：RoPE 35% / Norm 30%）
   ↓
写 kernel（llm_fused_kernels.py）+ ref + 单测
   ↓
AOT 编 .so（aot_llm_kernels.py，形状特化 + bucket）
   ↓
桥接（tl_*_bridge.cpp + diff，side-loading）
   ↓
env 开关 + parity 探针 + 4-run A/B
   ↓
精度隔离验证 → 提交
```

**顺序不能乱**：没 profile 不写 kernel；没 parity 不计时；没 A/B 不下结论。
