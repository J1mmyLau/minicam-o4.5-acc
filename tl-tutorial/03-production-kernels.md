# 03 · 生产 Kernel 精读（llm_fused_kernels.py）

> `code/llm_fused_kernels.py`（827 行）——**本项目 decode 侧融合 kernel 的真源**，
> 直接服务于 QK-norm+RoPE 融合（+66%）与 RMSNorm 行融合（+25%~65%）。
> 文件头就写着动机（msprof 实测）：

```
RoPE 全链 ≈35%: RotaryPositionEmbedding 12.1 + Mul 12.7 + Cos 3.4 + Sin 3.3 + Cast/Tile
RMSNorm 链 ≈30%: RmsNorm 19.3 + Add(残差) + Mul + Cast
```

**先 profile 再写 kernel**——35%+30% ≈ 65% 的 decode 时间在这两条链上，
这就是为什么融合它们能拿到 +66%。

## 1. fused_rope 的三版演进（这个文件最有教学价值的部分）

文件里**完整保留了三次尝试**，是一个真实的"试错现场"：

### v1 `rope_kernel`：占位失败

```python
with T.Kernel(n_t, is_npu=True) as (bid, vid):
    pass  # 占位——改用 Parallel 版本
```
教训：按 token 分块的写法没想清楚就动不了手，先跳出来。

### v2 `fused_rope`：Parallel 逐元素 + 在线算 power —— 写不动

```python
for h in T.serial(H):
    for i in T.Parallel(half):
        p = T.if_then_else(cid < sym_T, T.Cast("float32", pos[cid]), 0.0)
        inv_freq = T.power(theta_base, ...)  # placeholder
```
教训：**在 kernel 里在线算 `theta^(-2i/d)` 不好写也不划算**（`tir` 里
power/cos/sin 支持有限，且逐元素算浪费）。

### v3 `fused_rope_tbl`：**host 预取表 + 纯 tile-op** —— 生产版

```python
@tilelang.jit(out_idx=[-1], pass_configs=pass_configs)
def fused_rope_tbl(H, D, T_len, dtype="float16"):
    """cs/sn 由 host 按 pos 预取成 [T, half] 行传入
       y_lo = x_lo*cs - x_hi*sn;  y_hi = x_hi*cs + x_lo*sn (NeoX)"""
    half = D // 2

    @T.prim_func
    def main(x:  T.Tensor((T_len, H * D), dtype),   # [T, H*D]
             cs: T.Tensor((T_len, half), dtype),    # host 算好的 cos 行
             sn: T.Tensor((T_len, half), dtype),
             y:  T.Tensor((T_len, H * D), dtype)):
        with T.Kernel(1, is_npu=True) as (bid, vid):
            cs_ub = T.alloc_ub((T_len, half), dtype)
            sn_ub = T.alloc_ub((T_len, half), dtype)
            x_lo  = T.alloc_ub((T_len, half), dtype)
            x_hi  = T.alloc_ub((T_len, half), dtype)
            t1 = T.alloc_ub((T_len, half), dtype); t2 = T.alloc_ub((T_len, half), dtype)
            y_lo = T.alloc_ub((T_len, half), dtype); y_hi = T.alloc_ub((T_len, half), dtype)
            T.copy(cs, cs_ub); T.copy(sn, sn_ub)
            for h in T.serial(H):                    # 每个 head 一轮
                T.copy(x[0, h * D], x_lo)            # strided 区段 [T, half]
                T.copy(x[0, h * D + half], x_hi)
                T.tile.mul(t1, x_lo, cs_ub)          # y_lo = x_lo*cs − x_hi*sn
                T.tile.mul(t2, x_hi, sn_ub)
                T.tile.sub(y_lo, t1, t2)
                T.tile.mul(t1, x_hi, cs_ub)          # y_hi = x_hi*cs + x_lo*sn
                T.tile.mul(t2, x_lo, sn_ub)
                T.tile.add(y_hi, t1, t2)
                T.copy(y_lo, y[0, h * D])
                T.copy(y_hi, y[0, h * D + half])
    return main
```

**三个关键设计**：

1. **cos/sin 表 host 预取**：CPU 上按 pos 算好 `[T, half]` 的表作为常量
   传入，kernel 里只剩乘加。decode 时 T 很小（1~8），表几乎免费。
   —— 这就是 05 讲规则 2 的出处。
2. **布局即接口**：`x` 是 `[T, H*D]` 行主序打平——**llama.cpp 的 xqd
   口径**，桥接零转换。kernel 的输入布局跟着调用方走，别让调用方迁就你。
3. **一个核包全部**：`T.Kernel(1, ...)` 单核循环所有 head——decode 的
   T 很小，launch 并行度不重要，**少 launch 才重要**。

## 2. fused_rmsnorm：一核一行 + 精确 rsqrt

```python
@tilelang.jit(out_idx=[3, 4], pass_configs=pass_configs)   # 两个输出：s 和 y
def fused_rmsnorm(N, T_len, eps=1e-6, dtype="float16"):
    # x/res: [T, N] -> s: 残差和(供下一层), y: w ⊙ rmsnorm(s)

    @T.prim_func
    def main(x, res, w, s, y):
        with T.Kernel(T_len, is_npu=True) as (cid, vid):   # ← 一核一行！
            x_ub  = T.alloc_ub((N,), dtype); r_ub = T.alloc_ub((N,), dtype)
            w_ub  = T.alloc_ub((N,), dtype); s_ub = T.alloc_ub((N,), dtype)
            s32   = T.alloc_ub((N,), "float32")            # fp32 主拷贝
            ...
            T.copy(x[cid, 0], x_ub); T.copy(res[cid, 0], r_ub); T.copy(w, w_ub)
            # s = x + r（逐元素 Parallel，fp32 算、fp16 存双写）
            for i in T.Parallel(N):
                a = T.Cast("float32", x_ub[i]) + T.Cast("float32", r_ub[i])
                s32[i] = a
                s_ub[i] = T.Cast(dtype, a)
            # var = mean(s²) + eps
            T.tile.mul(sq32, s32, s32)
            T.reduce_sum(sq32, var_ub, dim=0, clear=True)
            for i in T.Parallel(1):
                var_ub[i] = var_ub[i] / N + eps
            # ★ 精确 1/sqrt：不用 T.tile.rsqrt（快速近似 ~3e-3 误差）
            T.tile.fill(ones_ub, 1.0)
            T.tile.sqrt(sqrt_ub, var_ub)
            T.tile.div(rms_ub, ones_ub, sqrt_ub)
            for i in T.Parallel(N):
                y_ub[i] = T.Cast(dtype, s32[i] * rms_ub[0] * T.Cast("float32", w_ub[i]))
            T.copy(s_ub, s[cid, 0]); T.copy(y_ub, y[cid, 0])
```

**四个要点**：

1. **一核一行**：`T.Kernel(T_len)`，`cid` 直接就是行号。N=4096 的 fp32
   主拷贝刚好放得下 UB，decode 的 T 又小——这是 decode 场景的正确分法，
   和 02 讲的"每核多行"互补（那边是大 M 场景）。
2. **融合残差**：`s = x + res` 和 rmsnorm 在一个核里，输出两份（s 给下一
   层做残差、y 是本层输出）——原生要 3 个算子 2 次 GM 往返。
3. **精确 rsqrt 的写法**：`fill(1.0) → sqrt → div`，绕开 `T.tile.rsqrt`
   的 ~3e-3 近似误差。**位级 parity 时这就是过不过的区别**。
4. **`clear=True`**：`reduce_sum` 前清零目标，否则累加到残留值上。

## 3. 文件里还有什么

- `fused_layernorm`：同构的 LayerNorm+残差版（flow 段 LayerNormV3 链用），
  结构 = fused_rmsnorm + 先减 mean（两次 reduce：mean 和 var）。
- `norm_row` / `fused_rope_view`：**TTS 侧**（768 维 talker）的行融合与
  RoPE，喂 `tltsnorm_N768_T*` / `tltsrope_H12_D64_R768_T*` 系列 AOT so。
- `ref_rope / ref_rmsnorm / test_*`：每个 kernel 的参考实现 + 测试，
  和官方模板同一个纪律。

## 4. 练习

1. 把 `fused_rope_tbl` 的 `T.Kernel(1)` 改成 `T.Kernel(T_len)`（一核一
   token），对拍过了之后想：哪个形状下这个版本才划算？
2. 给 `fused_rmsnorm` 加 `VEC_NUM=2` 向量化（参照 02 讲的做法），对拍。
3. 读 `fused_layernorm`，画出它的数据流（两次 reduce 的顺序为什么不能换）。
