# TileLang 教学 — 以本项目真实 kernel 为教材

> 这是给本项目（MiniCPM-o 4.5 / Ascend 910C 实时语音对话，RTF 1.087→0.4829）
> 写的 TileLang 教程。**所有代码都摘自项目真实生产 kernel 或官方模板**，
> 没有虚构示例。学完你能读懂、修改、并写出下一个融合 kernel。

## 为什么值得学：它在本项目赚了多少

| Kernel | 收益 | 位置 |
|---|---|---|
| QK-norm+RoPE 整段融合 | **decode 吞吐 +66%**（0.47→0.78 t/s） | 03 讲 |
| RMSNorm 行融合（单开/叠加） | +25% / **+55~65%** | 03 讲 |
| vocoder conv1d（消 im2col） | t2w −21%，WAV corr 0.9993 | 04 讲 |

对照组（同样重要）：用现成算子做单点替换（RoPE 换装、sel-emb、OP_FUSION）
**实测全部为零**——因为 decode 的墙是每步 ~1027 次 launch × ~30µs host 税，
只有「一串算子 → 一个 kernel」能跨过去。这就是 TileLang 的定位。

## 一句话心智模型

TileLang 是 **TVM 之上的 tile 级 kernel DSL**。你不写"每个元素怎么算"，
你写"**一块数据怎么搬进来、在片上算、再搬出去**"。编译成 Ascend CCE，
AOT 成 `.so` 纯 C ABI（本项目单核 15.3µs/call）。

```
GM（HBM，大而慢）──T.copy──► UB（片上 Unified Buffer，小而快）
                                │ 全部计算发生在这里（T.tile.*）
```

**所有 kernel 都是这个骨架的三拍子：搬进 → 算 → 搬回。**

## 课程表

| 讲 | 内容 | 代码 |
|---|---|---|
| [01-mental-model.md](01-mental-model.md) | 内存层级 + 七个核心原语 + Hello World 逐行 | `code/elementwise_add.py` |
| [02-two-pass-walkthrough.md](02-two-pass-walkthrough.md) | 官方 RMSNorm 模板：分块/ping-pong/归约/dtype 纪律 | `code/rms_norm.py` |
| [03-production-kernels.md](03-production-kernels.md) | **本项目生产 kernel 精读**：RoPE 三版演进 + fused_rmsnorm | `code/llm_fused_kernels.py` |
| [04-conv1d.md](04-conv1d.md) | vocoder conv1d：布局即集成、bucket 化 | `code/conv1d_tilelang.py` |
| [05-pitfalls.md](05-pitfalls.md) | 血泪规则 10 条（全部实测撞过） | — |
| [06-integration.md](06-integration.md) | 怎么进生产：AOT → 桥接 → env 开关 → 位级 parity | `code/aot_llm_kernels.py`、`code/bridge_parity_probe.py` |
| [07-exercises.md](07-exercises.md) | 练习路线（本机可直接跑） | — |

## 环境与跑法（910C 本机）

```bash
# 依赖：tilelang-ascend 源码树（我们用的是打 TVM 补丁 6 处的版本，
#       团队工作区路径为 /workspace/tilelang-ascend——外部读者请换成
#       自己的 tilelang-ascend 检出路径）
#       另需 torch-npu、CANN 9.1.0-beta.1、ASCEND_RT_VISIBLE_DEVICES pin 单 die
export PYTHONPATH=/path/to/tilelang-ascend

python code/elementwise_add.py          # 第一个 kernel，~秒级编译
python code/rms_norm.py                 # 官方模板 + 自带对拍
python code/test_qknorm_rope.py         # 生产 kernel 的正确性测试
```

每个示例自带 torch 参考对拍（`torch.testing.assert_close`）——
**这是本项目的铁律：先位级 parity，再看性能。**

## 代码目录索引

| 文件 | 是什么 |
|---|---|
| `code/llm_fused_kernels.py` | **生产 kernel 源**：fused RoPE（3 版演进）/ fused RMSNorm+残差 / fused LayerNorm+残差 / TTS 侧 norm_row、fused_rope_view，含参考实现与测试（827 行） |
| `code/conv1d_tilelang.py` | 生产 vocoder conv1d kernel（t2w −21% 那个） |
| `code/test_qknorm_rope.py` | QKR kernel 正确性测试 |
| `code/aot_llm_kernels.py` | AOT 编译脚本：kernel → `.so`（_LIBRARY_GENERATOR 用法） |
| `code/bridge_parity_probe.py` | 桥接层位级对拍 harness（debug 神器） |
| `code/elementwise_add.py` | 官方 Hello World（教学） |
| `code/rms_norm.py` | 官方 two-pass 模板（教学，也是我们行融合的模板来源） |

## 与工程归档的关系

性能数据链、被否决路线、A/B 口径见同分支根目录的
[../06-kernel-runtime-optimization.md](../06-kernel-runtime-optimization.md) 与
[../05-profiling.md](../05-profiling.md)（本分支基于冻结的
`docs/engineering-log`@858ad30 切出，工程日志全量随分支携带，
总览见 [../README-engineering-log.md](../README-engineering-log.md)）。
本教程专注「怎么写」，工程日志那边专注「为什么值 / 为什么不值」。

生产接线侧（side-loading 桥接、ggml-cann 集成）的真源在
`perf/tilelang-bridge` 分支。
