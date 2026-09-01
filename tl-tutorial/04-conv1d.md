# 04 · vocoder conv1d（t2w −21% 那条线）

> `code/conv1d_tilelang.py`——生产 vocoder conv1d kernel。
> 背景：profiling 发现 **im2col 占 vocoder 85%（351ms/chunk）**，原生
> 实现要先把卷积展开成大矩阵再 GEMM。TileLang 版直接在原布局上算卷积，
> 免掉 im2col。结果：t2w stage −21%，WAV 相关系数 0.9993（音频质量保持）。

## 1. 接口设计：布局即集成

文件头的布局声明就是最好的教材：

```
布局（与 ggml tcb 完全一致，集成零转换）:
  x: [Cin, T]           （host 侧已 pad 的张量）
  w: [K, Cin, Cout]     （ggml 原生）
  y: [Cout, T]

计算: y[c, t] = b[c] + Σ_{k,ci} w[k, ci, c] · x[ci, t + k]
  —— xp 传入的是 pad 后张量，kernel 对称 [pad, pad+T) 内部窗口
```

**两个设计决策**：

1. **完全沿用调用方（ggml）的布局**——`w [K, Cin, Cout]` 是 ggml 原生
   排布，kernel 直接吃，不做任何 transpose。反例教训：stage10 转换器
   曾因为一个 `.t()` 多余转置踩坑（ggml mul_mat 的 ne=(K,N) 原生布局
   就是 torch (out,in) 连续内存）。
2. **pad 放 host 侧**：kernel 只管算，边界处理（左右补零）在 CPU/框架侧
   完成，kernel 读到的 `xp` 永远是合法窗口。简化 kernel 换 host 一点
   小工作——decode 场景下稳赚。

## 2. kernel 骨架

```python
@tilelang.jit(out_idx=[-1], pass_configs=pass_configs)
def conv1d_kernel(Cin, Cout, K, T_len, TP, DIL, BLOCK_CIN, BLOCK_COUT, BLOCK_T,
                  dtype="float16"):
    @T.prim_func
    def main(xp: T.Tensor((Cin, TP), dtype),     # pad 后输入（TP = T+2*pad）
             w:   T.Tensor((K, Cin, Cout), dtype),
             y:   T.Tensor((Cout, T_len), dtype)):
        n_t_blocks = T.ceildiv(T_len, BLOCK_T)
        ...
```

tile 形状 = 输出块 `[BLOCK_COUT, BLOCK_T]`；reduction 沿 `(k, cin_block)`
**以 gemm_v0 累加**的方式做——即卷积被组织成"输出块 × (K×Cin 分块)"
的一串小 GEMM 累加，天然适配向量核的矩阵乘单元，这正是它打得过
im2col+GEMM 的原因：**不物化展开矩阵，把展开折叠进 tile 循环**。

参数里的 `DIL`（dilation）和 `TP`（padded 长度）都是编译期常量——
每个 (C, K, DIL, T) 组合一个特化 kernel。

## 3. Bucket 化：形状特化的代价与解法

TileLang kernel 是**形状特化**的，而 vocoder 每个音频 chunk 的 T 都在变。
解法（生产口径，72 个 kernel + 桥回落）：

```python
# 按 T 分桶，每桶编一个特化 kernel（C128_O128_K11_D1_T1280.so 就是这么来的）
for T in [640, 1280, 2320, 2560, ...]:
    for K, DIL in [(11,1),(11,3),(11,5),...]:
        k = conv1d_kernel(Cin, Cout, K, T, TP, DIL, ...)
        # AOT 编译成 tlconv_C{C}_O{O}_K{K}_D{D}_T{T}.so
```

运行时桥按 (K, DIL, T) 查表命中 bucket；**没命中的形状回落到原生
ggml 路径**——性能优化必须带回落，不能让没覆盖的形状直接崩。
（`aot_conv_buckets.py` / `aot_conv_all.py` 在 `/workspace/t2w-tilelang/`
是生成脚本，命名即形状。）

## 4. 调试往事（真实根因，别再踩）

初版 kernel 输出噪声，看起来像"卷积语义写错"，实际根因有两个，**都不在
conv 语义**：

1. **cast 流竞态**：fp16/fp32 转换和计算在不同流上，没同步就消费。
2. **galloc 地址复用**：编译器临时缓冲复用了还在被读的地址。

修复 = 根 F32 回溯重排缓存。教训：**kernel 输出错了，先查数据依赖和
缓冲生命周期，再怀疑数学**。另外 host 读图节点必须 `SynchronizeStream`。

## 5. 收益的边界（诚实账）

t2w stage −21%，但 **E2E 只 −0.01~0.02**——因为 vocoder 只占 t2w 的
~1/3，flow 的 NFE 才是大头。这是本项目反复出现的模式：
**段内大赢 ≠ 端到端大赢，Amdahl 管着一切**。写 kernel 前先看这段在
E2E 里占多少。
