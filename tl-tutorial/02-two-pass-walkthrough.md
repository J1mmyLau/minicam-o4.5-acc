# 02 · Two-Pass 模板精读（官方 rms_norm.py）

> `code/rms_norm.py`（tilelang-ascend 官方模板）。
> RMSNorm 数学：`y = x / sqrt(mean(x²) + eps)`——三步：求均方 → rsqrt → 逐元素乘。
> 原生实现是 3 次 launch + 2 次完整 GM 往返；TileLang 版 1 个 kernel、数据只进 UB 一次。
> **这也是我们行融合 kernel 的模板来源**（+25%/+55~65% 那条线的起点）。

## 1. 为什么这个例子值得精读

它一次展示了四个进阶结构，后面所有归约类 kernel（norm/softmax/attention
的统计量部分）都是它的变体：

- **分块策略在外层**（`_get_optimized_tiling`）
- **流式两遍扫描**（two-pass：先累加统计量，再归一化写回）
- **Ping-pong 双缓冲**（搬运和计算重叠）
- **dtype 纪律**（bf16 进、fp32 累加、bf16 出）

## 2. 分块：UB 面积守恒下的自适应

```python
def _get_optimized_tiling(M, N, block_M_in, block_N_in, vec_num):
    budget = block_M_in * block_N_in        # 面积预算固定
    ideal_n = budget // 16
    block_N = min(N // 2, ideal_n)
    if block_N < 128:
        block_N = 128 if N >= 256 else N
    while N % block_N != 0:                 # 必须整除，护边界
        block_N -= 1
    block_M = budget // block_N
    if M % block_M != 0:                    # M 不整除时退到 vec_num
        block_M = block_M_in if M % block_M_in == 0 else vec_num
    return block_M, block_N
```

两个要点：
- **行长超过 UB 时横着切**：N=51200（DeepSeek 级）一行都放不下，切成
  `n_num` 块循环——这是后面 two-pass 循环的来源。
- **M 不整除会崩**：官方 tiling 对 M<2 / 非整除形状敏感，必须在外层
  护住（这是踩过的坑，见 05 讲规则 3）。

## 3. Kernel 主体骨架

```python
@tilelang.jit(out_idx=[1], pass_configs=pass_configs)
def _rms_norm(M, N, block_M_in, block_N_in, eps=1e-5, dtype="float"):
    block_M, block_N = _get_optimized_tiling(...)
    m_num = M // block_M      # 行块数
    n_num = N // block_N      # 列块数（行长放不下 UB 时 >1）
    ROWS = block_M // VEC_NUM # 本核实际处理的行数
    need_cast = dtype not in ("float", "float32")
    acc_dtype = "float32" if need_cast else dtype   # ← dtype 纪律

    @T.prim_func
    def tilelang_rms_norm(A: T.Tensor((M, N), dtype), B: T.Tensor((M, N), dtype)):
        with T.Kernel(m_num, is_npu=True) as (cid, vid):
            # ... 一堆 T.alloc_ub，见下
            row_start = cid * block_M + vid * ROWS     # 本核负责的行
```

注意 grid 只有 `m_num`（不是 m_num×n_num）——**每个核负责固定的几行，
行内所有列块在这个核里循环**。这是归约类 kernel 的标准分法：归约维
（列）必须在核内做完。

## 4. 第一遍：流式累加 + ping-pong

```python
# 单一累加器：不用双缓冲累加器，省 UB
sum_sq_acc = T.alloc_ub([ROWS, block_N], acc_dtype)

T.tile.fill(sum_sq_acc, 0.0)

for by in T.serial(n_num // 2):
    # 偶数块
    T.copy(A[row_start:+ROWS, (by*2)*block_N:...], a_ub_0)
    T.tile.cast(a_ub_cast_0, a_ub_0, "CAST_NONE", tile_elements)  # bf16→fp32
    T.tile.mul(a_ub_cast_0, a_ub_cast_0, a_ub_cast_0)             # x²
    T.tile.add(sum_sq_acc, sum_sq_acc, a_ub_cast_0)               # 累加
    # 奇数块（a_ub_1 同理）
...
if n_num % 2 != 0:   # 奇数尾巴单独处理
    ...
```

- **ping-pong**：`a_ub_0`/`a_ub_1` 交替——搬第 i+1 块的同时算第 i 块。
- **cast 后再算**：bf16 先 `CAST_NONE` 成 fp32，乘加全在 fp32 做。
- **尾巴处理**：`n_num` 是奇数时最后一块单独来一遍。这个 `if` 在 kernel
  体内是编译期常量展开，不亏性能。

## 5. 归约 + 广播 + 第二遍

```python
# 每行一个数
T.reduce_sum(sum_sq_acc, sum_sq_row, dim=-1)        # [ROWS, block_N] → [ROWS, 1]

# inv_rms = rsqrt(mean+eps)，标量算术在 tile 上完成
inv_n  = T.cast(1.0 / N, acc_dtype)
T.tile.mul(sum_sq_row, sum_sq_row, inv_n)
T.tile.add(sum_sq_row, sum_sq_row, eps_val)
T.tile.rsqrt(inv_rms_ub, sum_sq_row)
T.tile.broadcast(inv_rms_tile, inv_rms_ub)          # [ROWS,1] → [ROWS,block_N]

# 第二遍：重新流式过一遍 x，乘 inv_rms 写回
for by in T.serial(n_num // 2):
    T.copy(A[..., col_off_0:...], a_ub_0); T.tile.cast(...)
    T.tile.mul(a_ub_cast_0, a_ub_cast_0, inv_rms_tile)
    T.tile.cast(a_ub_0, a_ub_cast_0, "CAST_RINT", tile_elements)   # fp32→bf16
    T.copy(a_ub_0, B[..., col_off_0:...])
```

**为什么读两遍输入？** 因为第一遍只存了累加器，没存原数据；行太长 UB
放不下整行。GM 读两遍 ≪ 多两次 kernel launch + 中间结果落 GM，所以
two-pass 是对的。（顺带：这里的 `T.tile.rsqrt` 是快速近似版，精度敏感
场合见 03 讲 fused_rmsnorm 的精确写法。）

## 6. 自带对拍（学它的测试姿势）

文件末尾：

```python
for M, N, block_M, block_N, dtype in test_configs:      # 6 组形状含 bf16
    func = _rms_norm(M, N, block_M, block_N, dtype=dtype)
    b = func(a)
    ref_b = torch.rms_norm(a.float(), normalized_shape=[N]).to(a.dtype)
    torch.testing.assert_close(b.cpu(), ref_b.cpu(), rtol=1e-2, atol=1e-2)
```

**每个 kernel 配一个参考实现 + 对拍**，这是官方模板自带的纪律，
也是我们项目的铁律（先 parity 再性能）。

## 7. 练习

1. 把 ping-pong 两缓冲改成单缓冲，跑 `N=51200` 用例，观察慢多少。
2. 把 `acc_dtype` 强制改成 bf16（删掉 cast），对拍看误差——理解 dtype 纪律。
3. 照抄结构写一个 "mean + variance"（LayerNorm 统计量）kernel。
