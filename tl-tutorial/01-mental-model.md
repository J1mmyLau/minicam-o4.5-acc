# 01 · 心智模型 + Hello World

## 1. 为什么需要 tile 抽象

Ascend NPU 的向量核**不能直接吃 HBM 上的数据**——必须先搬进片上
Unified Buffer（UB）。UB 很小（~256KB 级），所以一次只能装一个"块"
（tile）。TileLang 的工作就是让你用 Python 描述这个搬进-算-搬回的循环，
它负责生成 CCE 代码、调度 DMA、管理 UB。

和 CUDA 的区别：CUDA 你管 thread；TileLang 你管 **tile**。
和 torch 的区别：torch 一个算子一次 launch；TileLang 一个 kernel
里可以塞一整串算子（这就是融合收益的来源）。

## 2. 七个核心原语（读完这节就能看懂任何 TileLang 代码）

| 原语 | 作用 | 类比 |
|---|---|---|
| `@tilelang.jit(out_idx=[...])` | 编译入口；`out_idx` 声明哪些参数是输出 | `torch.compile` 的装饰器 |
| `T.Tensor((M,N), dtype)` | GM 上的张量参数 | 函数签名 |
| `T.Kernel(grid, is_npu=True)` | 启动 grid 个核，拿到 `(cid, vid)` 编号 | CUDA grid，但 cid 是"块编号" |
| `T.alloc_ub(shape, dtype)` | 在 UB 上开缓冲 | `torch.empty`，但容量极贵 |
| `T.copy(gm_slice, ub)` / `T.copy(ub, gm_slice)` | GM↔UB 搬运（DMA） | 显式 memcpy |
| `T.tile.add/mul/sub/div/rsqrt/...` | **整块**算术，就地写第一个参数 | 批量 torch 运算 |
| `T.reduce_sum(tile, out, dim=-1)` / `T.tile.broadcast(dst, src)` | 归约 / 广播 | `sum(dim)` / `expand` |

辅助件：`T.serial(n)`（串行循环）、`T.Parallel(n)`（向量核逐元素）、
`T.barrier_all()`（核内同步）、`T.tile.fill(t, v)`（整块填充）、
`T.tile.cast(dst, src, mode, n)`（dtype 转换）。

## 3. Hello World 逐行（`code/elementwise_add.py`）

```python
@tilelang.jit(out_idx=[-1])              # -1 = 最后一个参数是输出
def vec_add(M, N, block_M, block_N, dtype="float"):
    m_num = M // block_M                  # 外层 Python：先算好分块数
    n_num = N // block_N
    VEC_NUM = 2                           # 一个核吃 2 份（向量化系数）

    @T.prim_func                          # TVM 函数式 IR 入口
    def main(A: T.Tensor((M, N), dtype),
             B: T.Tensor((M, N), dtype),
             C: T.Tensor((M, N), dtype)):
        with T.Kernel(m_num * n_num, is_npu=True) as (cid, vid):
            bx = cid // n_num             # 线性 id → 二维块坐标
            by = cid % n_num

            a_ub = T.alloc_ub((block_M // VEC_NUM, block_N), dtype)
            b_ub = T.alloc_ub((block_M // VEC_NUM, block_N), dtype)
            c_ub = T.alloc_ub((block_M // VEC_NUM, block_N), dtype)
            with T.Scope("V"):            # "V" = 向量化作用域
                # 搬进（行起点偏移 vid*block_M//VEC_NUM ← VEC_NUM 的含义）
                T.copy(A[bx*block_M + vid*block_M//VEC_NUM, by*block_N], a_ub)
                T.copy(B[bx*block_M + vid*block_M//VEC_NUM, by*block_N], b_ub)
                T.barrier_all()
                T.tile.add(c_ub, a_ub, b_ub)     # 算：整块加
                T.barrier_all()
                T.copy(c_ub, C[bx*block_M + vid*block_M//VEC_NUM, by*block_N])
    return main
```

使用：

```python
func = vec_add(1024, 1024, 128, 256)   # 编译（形状特化！）
a, b = torch.randn(1024,1024).npu(), torch.randn(1024,1024).npu()
c = func(a, b)                          # 直接喂 torch-npu 张量
```

**四个必懂细节**：

1. **形状特化**：`vec_add(1024, 1024, ...)` 编出的 kernel 只吃这个形状
   （或 `T.symbolic` 的动态维）。这就是我们 vocoder 要做 72 个 bucket
   kernel 的原因——每个 T 一个 shape。
2. **分块在外层 Python 算**：`block_M/block_N` 是普通 Python 变量，
   可以做 `while N % block_N != 0` 这种护边界逻辑——kernel 体内写不了这些。
3. **UB 面积守恒**：`block_M × block_N` 受 UB 容量约束，这是所有 tiling
   设计的第一约束。
4. **切片即搬运范围**：`A[row_start : row_start+ROWS, col : col+N]` 这种
   切片表达式同时定义了 GM 源区域和 UB 形状，`T.copy` 会生成对应 DMA。

## 4. 跑起来

```bash
export PYTHONPATH=/path/to/tilelang-ascend   # 你的 tilelang-ascend 检出路径
python code/elementwise_add.py --m 1024 --n 1024
```

练习：把 `block_M, block_N` 从 `(128, 256)` 改成 `(8, 4096)` 和
`(1024, 32)`，观察编译是否成功、耗时怎么变——体会 UB 预算和形状约束。
