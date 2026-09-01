#!/usr/bin/env python3
"""LLM decode 融合 kernel（DSpark verify 口径 bs≈5，qwen3 4096/32h/128d）

依据 msprof（MiniCPM-o Q4_K_M decode 128 tok）：
  RoPE 全链 ≈35%: RotaryPositionEmbedding 12.1 + Mul 12.7 + Cos 3.4 + Sin 3.3 + Cast/Tile
  RMSNorm 链 ≈30%: RmsNorm 19.3 + Add(残差) + Mul + Cast

kernel1 fused_rope:     NeoX half-rotate，cos/sin 由 theta^(-2i/d) 在线计算（UB 缓存 64 对）
kernel2 fused_rmsnorm:  y = w ⊙ rmsnorm(x + res)，fp32 累加

布局: x [T, H*D] 行主序（llama.cpp 的 xqd 打平口径）
"""
import math
import torch
import torch_npu  # noqa: F401
import tilelang
import tilelang.language as T

pass_configs = {
    tilelang.PassConfigKey.TL_ASCEND_AUTO_CV_COMBINE: True,
    tilelang.PassConfigKey.TL_ASCEND_AUTO_SYNC: True,
    tilelang.PassConfigKey.TL_ASCEND_MEMORY_PLANNING: True,
}


# ---------------- fused RoPE (NeoX half-rotate, 在线 cos/sin) ----------------
@tilelang.jit(out_idx=[-1], pass_configs=pass_configs)
def rope_kernel(H, D, theta_base, BLOCK_T, dtype="float16"):
    # x: [T, H*D], pos: [T] int32 -> y: [T, H*D]
    @T.prim_func
    def main(x: T.Tensor((T.symbolic("T"), H * D), dtype),
             pos: T.Tensor((T.symbolic("T"),), "int32"),
             y: T.Tensor((T.symbolic("T"), H * D), dtype)):
        half = D // 2
        n_t = T.ceildiv(T.symbolic("T"), BLOCK_T)
        with T.Kernel(n_t, is_npu=True) as (bid, vid):
            pass  # 占位——改用 Parallel 版本
    return main


# Parallel 版本（vector core 逐元素，T.Parallel 向量化）
@tilelang.jit(out_idx=[-1], pass_configs=pass_configs)
def fused_rope(H, D, theta_base, dtype="float16"):
    sym_T = T.symbolic("T")

    @T.prim_func
    def main(
        x: T.Tensor((sym_T, H * D), dtype),
        pos: T.Tensor((sym_T,), "int32"),
        y: T.Tensor((sym_T, H * D), dtype),
    ):
        with T.Kernel(sym_T, is_npu=True) as (cid, vid):
            half = D // 2
            for h in T.serial(H):
                for i in T.Parallel(half):
                    p = T.if_then_else(cid < sym_T, T.Cast("float32", pos[cid]), 0.0)
                    inv_freq = T.power(theta_base, T.Cast("float32", -2 * (i % half)) / D * (-2.0) if False else 0.0)  # placeholder
    return main


# ---- 上面的在线 power 不好写；改用 freq 表输入（host 一次算好 [half] 表，常驻）----
@tilelang.jit(out_idx=[-1], pass_configs=pass_configs)
def fused_rope_tbl(H, D, T_len, dtype="float16"):
    """纯 tile-op 版：cs/sn 由 host 按 pos 预取成 [T, half] 行传入
       y_lo = x_lo*cs - x_hi*sn;  y_hi = x_hi*cs + x_lo*sn (NeoX)"""
    half = D // 2

    @T.prim_func
    def main(
        x: T.Tensor((T_len, H * D), dtype),       # [T, H*D]
        cs: T.Tensor((T_len, half), dtype),       # host 预取的 cos 行
        sn: T.Tensor((T_len, half), dtype),
        y: T.Tensor((T_len, H * D), dtype),
    ):
        with T.Kernel(1, is_npu=True) as (bid, vid):
            cs_ub = T.alloc_ub((T_len, half), dtype)
            sn_ub = T.alloc_ub((T_len, half), dtype)
            x_lo = T.alloc_ub((T_len, half), dtype)
            x_hi = T.alloc_ub((T_len, half), dtype)
            t1 = T.alloc_ub((T_len, half), dtype)
            t2 = T.alloc_ub((T_len, half), dtype)
            y_lo = T.alloc_ub((T_len, half), dtype)
            y_hi = T.alloc_ub((T_len, half), dtype)
            T.copy(cs, cs_ub)
            T.copy(sn, sn_ub)
            for h in T.serial(H):
                T.copy(x[0, h * D], x_lo)                  # [T, half] strided 区域
                T.copy(x[0, h * D + half], x_hi)
                T.tile.mul(t1, x_lo, cs_ub)
                T.tile.mul(t2, x_hi, sn_ub)
                T.tile.sub(y_lo, t1, t2)
                T.tile.mul(t1, x_hi, cs_ub)
                T.tile.mul(t2, x_lo, sn_ub)
                T.tile.add(y_hi, t1, t2)
                T.copy(y_lo, y[0, h * D])
                T.copy(y_hi, y[0, h * D + half])
    return main


# ---------------- fused RMSNorm + residual ----------------
@tilelang.jit(out_idx=[3, 4], pass_configs=pass_configs)
def fused_rmsnorm(N, T_len, eps=1e-6, dtype="float16"):
    # x/res: [T, N] -> sum: [T, N]（残差和，供下一层）, y: w ⊙ rmsnorm(sum)

    @T.prim_func
    def main(
        x: T.Tensor((T_len, N), dtype),
        res: T.Tensor((T_len, N), dtype),
        w: T.Tensor((N,), dtype),
        s: T.Tensor((T_len, N), dtype),
        y: T.Tensor((T_len, N), dtype),
    ):
        with T.Kernel(T_len, is_npu=True) as (cid, vid):
            x_ub = T.alloc_ub((N,), dtype)
            r_ub = T.alloc_ub((N,), dtype)
            w_ub = T.alloc_ub((N,), dtype)
            s_ub = T.alloc_ub((N,), dtype)
            s32 = T.alloc_ub((N,), "float32")
            sq32 = T.alloc_ub((N,), "float32")
            y_ub = T.alloc_ub((N,), dtype)
            var_ub = T.alloc_ub((1,), "float32")
            ones_ub = T.alloc_ub((1,), "float32")
            sqrt_ub = T.alloc_ub((1,), "float32")
            rms_ub = T.alloc_ub((1,), "float32")
            T.copy(x[cid, 0], x_ub)
            T.copy(res[cid, 0], r_ub)
            T.copy(w, w_ub)
            # s = x + r（fp32 主拷贝 + fp16 输出）
            for i in T.Parallel(N):
                a = T.Cast("float32", x_ub[i]) + T.Cast("float32", r_ub[i])
                s32[i] = a
                s_ub[i] = T.Cast(dtype, a)
            # var = mean(s^2) + eps;  rms = rsqrt(var)
            T.tile.mul(sq32, s32, s32)
            T.reduce_sum(sq32, var_ub, dim=0, clear=True)
            for i in T.Parallel(1):
                var_ub[i] = var_ub[i] / N + eps
            # precise 1/sqrt (T.tile.rsqrt is fast-approx ~3e-3)
            T.tile.fill(ones_ub, 1.0)
            T.tile.sqrt(sqrt_ub, var_ub)
            T.tile.div(rms_ub, ones_ub, sqrt_ub)
            for i in T.Parallel(N):
                y_ub[i] = T.Cast(dtype, s32[i] * rms_ub[0] * T.Cast("float32", w_ub[i]))
            T.copy(s_ub, s[cid, 0])
            T.copy(y_ub, y[cid, 0])
    return main


# ---------------- fused LayerNorm + residual（flow 段 LayerNormV3 链） ----------------
@tilelang.jit(out_idx=[3, 4], pass_configs=pass_configs)
def fused_layernorm(N, T_len, eps=1e-5, dtype="float16"):
    # x/res: [T, N] -> s: x+res, y: (s-mean)/std * w + b

    @T.prim_func
    def main(
        x: T.Tensor((T_len, N), dtype),
        res: T.Tensor((T_len, N), dtype),
        w: T.Tensor((N,), dtype),
        s: T.Tensor((T_len, N), dtype),
        y: T.Tensor((T_len, N), dtype),
    ):
        with T.Kernel(T_len, is_npu=True) as (cid, vid):
            x_ub = T.alloc_ub((N,), dtype)
            r_ub = T.alloc_ub((N,), dtype)
            w_ub = T.alloc_ub((N,), dtype)
            s_ub = T.alloc_ub((N,), dtype)
            s32 = T.alloc_ub((N,), "float32")
            d32 = T.alloc_ub((N,), "float32")
            y_ub = T.alloc_ub((N,), dtype)
            mean_ub = T.alloc_ub((1,), "float32")
            var_ub = T.alloc_ub((1,), "float32")
            ones_ub = T.alloc_ub((1,), "float32")
            sqrt_ub = T.alloc_ub((1,), "float32")
            rstd_ub = T.alloc_ub((1,), "float32")
            T.copy(x[cid, 0], x_ub)
            T.copy(res[cid, 0], r_ub)
            T.copy(w, w_ub)
            for i in T.Parallel(N):
                a = T.Cast("float32", x_ub[i]) + T.Cast("float32", r_ub[i])
                s32[i] = a
                s_ub[i] = T.Cast(dtype, a)
            T.reduce_sum(s32, mean_ub, dim=0, clear=True)
            for i in T.Parallel(1):
                mean_ub[i] = mean_ub[i] / N
            T.copy(s32, d32)
            for i in T.Parallel(N):
                d32[i] = d32[i] - mean_ub[0]
            # var = mean(d^2): 平方再 reduce
            sq = T.alloc_ub((N,), "float32")
            T.tile.mul(sq, d32, d32)
            T.reduce_sum(sq, var_ub, dim=0, clear=True)
            for i in T.Parallel(1):
                var_ub[i] = var_ub[i] / N + eps
            # precise 1/sqrt (T.tile.rsqrt is fast-approx ~3e-3)
            T.tile.fill(ones_ub, 1.0)
            T.tile.sqrt(sqrt_ub, var_ub)
            T.tile.div(rstd_ub, ones_ub, sqrt_ub)
            for i in T.Parallel(N):
                y_ub[i] = T.Cast(dtype, d32[i] * rstd_ub[0] * T.Cast("float32", w_ub[i]))
            T.copy(s_ub, s[cid, 0])
            T.copy(y_ub, y[cid, 0])
    return main


# ---------------- 参考实现 & 测试 ----------------
def ref_rope(x, freq, pos, H, D):
    """NeoX half-rotate 参考: x [T, H*D]"""
    half = D // 2
    T_len = x.shape[0]
    ang = pos.float().unsqueeze(1) * freq.unsqueeze(0)      # [T, half]
    cs, sn = ang.cos(), ang.sin()
    y = torch.zeros_like(x)
    xv = x.float().view(T_len, H, D)
    yv = y.float().view(T_len, H, D)
    yv[:, :, :half] = xv[:, :, :half] * cs.unsqueeze(1) - xv[:, :, half:] * sn.unsqueeze(1)
    yv[:, :, half:] = xv[:, :, half:] * cs.unsqueeze(1) + xv[:, :, :half] * sn.unsqueeze(1)
    return yv.to(x.dtype)


def ref_rmsnorm(x, res, w, eps=1e-6):
    s = x + res
    var = s.float().pow(2).mean(-1, keepdim=True)
    y = (s.float() * torch.rsqrt(var + eps) * w.float()).to(x.dtype)
    return s, y


def test_rope(H=32, D=128, T=5, seed=0):
    torch.manual_seed(seed)
    dev = 'npu:0'
    theta = 1_000_000.0
    half = D // 2
    freq = (theta ** (-torch.arange(0, half, dtype=torch.float32) * 2 / D)).to(dev)
    x = (torch.randn(T, H * D, device=dev, dtype=torch.float16) * 0.3)
    pos = torch.tensor([990 + i for i in range(T)], device=dev, dtype=torch.int32)
    MAXP = 4096
    ang = torch.arange(MAXP, device=dev, dtype=torch.float32).unsqueeze(1) * freq.unsqueeze(0)
    cs_tbl, sn_tbl = ang.cos().half(), ang.sin().half()
    cs, sn = cs_tbl[pos.long()], sn_tbl[pos.long()]        # host 预取行
    kern = fused_rope_tbl(H, D, T)
    y = kern(x, cs, sn)
    torch.npu.synchronize()
    y_ref = ref_rope(x, freq, pos, H, D).reshape(T, H * D)
    d = (y.float() - y_ref.float()).abs()
    rel = d.mean().item() / (y_ref.float().abs().mean() + 1e-9)
    print(f'rope H={H} D={D} T={T}: rel={rel:.2e} max={d.max().item():.3e} '
          f'{"PASS" if rel < 3e-3 else "FAIL"}')
    return rel < 3e-3


def test_layernorm(N=4096, T=5, seed=0):
    torch.manual_seed(seed)
    dev = 'npu:0'
    x = (torch.randn(T, N, device=dev, dtype=torch.float16) * 0.5)
    res = (torch.randn(T, N, device=dev, dtype=torch.float16) * 0.5)
    w = (torch.randn(N, device=dev, dtype=torch.float16) * 0.2 + 1.0)
    kern = fused_layernorm(N, T)
    s, y = kern(x, res, w)
    torch.npu.synchronize()
    s_ref = x + res
    import torch.nn.functional as F
    y_ref = F.layer_norm(s_ref.float(), (N,), weight=w.float(), eps=1e-5).to(x.dtype)
    for name, a, b in (('sum', s, s_ref), ('y', y, y_ref)):
        d = (a.float() - b.float()).abs()
        rel = d.mean().item() / (b.float().abs().mean() + 1e-9)
        print(f'layernorm {name} N={N} T={T}: rel={rel:.2e} {"PASS" if rel < 5e-3 else "FAIL"}')
        if rel >= 5e-3:
            return False
    return True


def test_rmsnorm(N=4096, T=5, seed=0):
    torch.manual_seed(seed)
    dev = 'npu:0'
    x = (torch.randn(T, N, device=dev, dtype=torch.float16) * 0.5)
    res = (torch.randn(T, N, device=dev, dtype=torch.float16) * 0.5)
    w = (torch.randn(N, device=dev, dtype=torch.float16) * 0.2 + 1.0)
    kern = fused_rmsnorm(N, T)
    s, y = kern(x, res, w)
    torch.npu.synchronize()
    s_ref, y_ref = ref_rmsnorm(x, res, w)
    for name, a, b in (('sum', s, s_ref), ('y', y, y_ref)):
        d = (a.float() - b.float()).abs()
        rel = d.mean().item() / (b.float().abs().mean() + 1e-9)
        print(f'rmsnorm {name} N={N} T={T}: rel={rel:.2e} '
              f'{"PASS" if rel < 3e-3 else "FAIL"}')
        if rel >= 3e-3:
            return False
    return True




# ---------------- pure LayerNorm F32 版 (flow: LN(x)*w+b, 免 cast 真融合) ----------------
@tilelang.jit(out_idx=[-1], pass_configs=pass_configs)
def layernorm_pure_f32(N, T_len, eps=1e-5, dtype="float"):
    @T.prim_func
    def main(
        x: T.Tensor((T_len, N), dtype),
        w: T.Tensor((N,), dtype),
        b: T.Tensor((N,), dtype),
        y: T.Tensor((T_len, N), dtype),
    ):
        with T.Kernel(T_len, is_npu=True) as (cid, vid):
            x_ub = T.alloc_ub((N,), dtype)
            w_ub = T.alloc_ub((N,), dtype)
            b_ub = T.alloc_ub((N,), dtype)
            mean_ub = T.alloc_ub((1,), dtype)
            var_ub = T.alloc_ub((1,), dtype)
            ones_ub = T.alloc_ub((1,), "float32")
            sqrt_ub = T.alloc_ub((1,), "float32")
            rstd_ub = T.alloc_ub((1,), dtype)
            y_ub = T.alloc_ub((N,), dtype)
            T.copy(x[cid, 0], x_ub)
            T.copy(w, w_ub)
            T.copy(b, b_ub)
            T.reduce_sum(x_ub, mean_ub, dim=0, clear=True)
            for i in T.Parallel(1):
                mean_ub[i] = mean_ub[i] / N
            for i in T.Parallel(N):
                x_ub[i] = x_ub[i] - mean_ub[0]
            # var = mean(x^2) after centering
            sq = T.alloc_ub((N,), dtype)
            T.tile.mul(sq, x_ub, x_ub)
            T.reduce_sum(sq, var_ub, dim=0, clear=True)
            for i in T.Parallel(1):
                var_ub[i] = var_ub[i] / N + eps
            # precise 1/sqrt (T.tile.rsqrt is fast-approx ~3e-3)
            T.tile.fill(ones_ub, 1.0)
            T.tile.sqrt(sqrt_ub, var_ub)
            T.tile.div(rstd_ub, ones_ub, sqrt_ub)
            for i in T.Parallel(N):
                y_ub[i] = x_ub[i] * rstd_ub[0] * w_ub[i] + b_ub[i]
            T.copy(y_ub, y[cid, 0])
    return main


# ---------------- pure LayerNorm (flow 段 build_layer_norm: LN(x)*w+b) ----------------
@tilelang.jit(out_idx=[-1], pass_configs=pass_configs)
def layernorm_pure(N, T_len, eps=1e-5, dtype="float16"):
    # x: [T, N] N 连续 (ggml ne0=N) -> y = LN(x)*w + b
    @T.prim_func
    def main(
        x: T.Tensor((T_len, N), dtype),
        w: T.Tensor((N,), dtype),
        b: T.Tensor((N,), dtype),
        y: T.Tensor((T_len, N), dtype),
    ):
        with T.Kernel(T_len, is_npu=True) as (cid, vid):
            x_ub = T.alloc_ub((N,), dtype)
            w_ub = T.alloc_ub((N,), dtype)
            b_ub = T.alloc_ub((N,), dtype)
            x32 = T.alloc_ub((N,), "float32")
            d32 = T.alloc_ub((N,), "float32")
            sq = T.alloc_ub((N,), "float32")
            y_ub = T.alloc_ub((N,), dtype)
            mean_ub = T.alloc_ub((1,), "float32")
            var_ub = T.alloc_ub((1,), "float32")
            ones_ub = T.alloc_ub((1,), "float32")
            sqrt_ub = T.alloc_ub((1,), "float32")
            rstd_ub = T.alloc_ub((1,), "float32")
            T.copy(x[cid, 0], x_ub)
            T.copy(w, w_ub)
            T.copy(b, b_ub)
            T.copy(x_ub, x32)
            T.reduce_sum(x32, mean_ub, dim=0, clear=True)
            for i in T.Parallel(1):
                mean_ub[i] = mean_ub[i] / N
            T.copy(x32, d32)
            for i in T.Parallel(N):
                d32[i] = d32[i] - mean_ub[0]
            T.tile.mul(sq, d32, d32)
            T.reduce_sum(sq, var_ub, dim=0, clear=True)
            for i in T.Parallel(1):
                var_ub[i] = var_ub[i] / N + eps
            # precise 1/sqrt (T.tile.rsqrt is fast-approx ~3e-3)
            T.tile.fill(ones_ub, 1.0)
            T.tile.sqrt(sqrt_ub, var_ub)
            T.tile.div(rstd_ub, ones_ub, sqrt_ub)
            for i in T.Parallel(N):
                y_ub[i] = T.Cast(dtype,
                    d32[i] * rstd_ub[0] * T.Cast("float32", w_ub[i]) + T.Cast("float32", b_ub[i]))
            T.copy(y_ub, y[cid, 0])
    return main


def test_layernorm_pure(N=128, T=32, seed=1):
    import torch.nn.functional as F
    torch.manual_seed(seed)
    dev = "npu:0"
    x = (torch.randn(T, N, device=dev, dtype=torch.float16) * 0.5)
    w = (torch.randn(N, device=dev, dtype=torch.float16) * 0.2 + 1.0)
    b = (torch.randn(N, device=dev, dtype=torch.float16) * 0.1)
    kern = layernorm_pure(N, T)
    y = kern(x, w, b)
    torch.npu.synchronize()
    y_ref = F.layer_norm(x.float(), (N,), weight=w.float(), bias=b.float(), eps=1e-5).to(x.dtype)
    d = (y.float() - y_ref.float()).abs()
    rel = d.mean().item() / (y_ref.float().abs().mean() + 1e-9)
    print("layernorm_pure N=%d T=%d: rel=%.2e %s" % (N, T, rel, "PASS" if rel < 5e-3 else "FAIL"))
    return rel < 5e-3


if __name__ == '__main__':
    ok1 = test_rope()
    ok2 = test_rmsnorm()
    ok3 = test_layernorm()
    ok4 = test_layernorm_pure()
    ok5 = test_layernorm_pure(N=512, T=64)
    print(f'== {"ALL PASS" if all([ok1, ok2, ok3, ok4, ok5]) else "FAIL"} ==')

# ---------------- fused RoPE (view 兼容版: 扁平 + token 行步长, 多 bs) ----------------
@tilelang.jit(out_idx=[-1], pass_configs=pass_configs)
def fused_rope_view(H, D, ROW_ELEMS, T_len, dtype="float16"):
    """x = qkv 输出 view: 扁平 [T*ROW_ELEMS], token t 头 h 维 d -> x[t*ROW_ELEMS + h*D + d]
    cs/sn [MAXP_GLOBAL 由外部保证, D/2] 表; pos [T] i32; y [T, H*D] 连续输出"""
    half = D // 2
    @T.prim_func
    def main(
        x: T.Tensor((T_len * ROW_ELEMS,), dtype),
        cs: T.Tensor((4096 + 8, half), dtype),
        sn: T.Tensor((4096 + 8, half), dtype),
        pos: T.Tensor((T_len,), "int32"),
        y: T.Tensor((T_len, H * D), dtype),
    ):
        with T.Kernel(T_len, is_npu=True) as (cid, vid):
            c_ub = T.alloc_ub((half,), dtype)
            s_ub = T.alloc_ub((half,), dtype)
            x_lo = T.alloc_ub((half,), dtype)
            x_hi = T.alloc_ub((half,), dtype)
            t1 = T.alloc_ub((half,), dtype)
            t2 = T.alloc_ub((half,), dtype)
            y_lo = T.alloc_ub((half,), dtype)
            y_hi = T.alloc_ub((half,), dtype)
            p0 = pos[cid]
            T.copy(cs[p0, 0], c_ub)
            T.copy(sn[p0, 0], s_ub)
            base = cid * ROW_ELEMS
            for h in T.serial(H):
                T.copy(x[base + h * D], x_lo)
                T.copy(x[base + h * D + half], x_hi)
                T.tile.mul(t1, x_lo, c_ub)
                T.tile.mul(t2, x_hi, s_ub)
                T.tile.sub(y_lo, t1, t2)
                T.tile.mul(t1, x_hi, c_ub)
                T.tile.mul(t2, x_lo, s_ub)
                T.tile.add(y_hi, t1, t2)
                T.copy(y_lo, y[cid, h * D])
                T.copy(y_hi, y[cid, h * D + half])
    return main


def test_rope_view(H=32, D=128, ROW_ELEMS=6144, T=5, seed=3, dtype="float16"):
    torch.manual_seed(seed)
    dev = "npu:0"
    theta = 1_000_000.0
    half = D // 2
    freq = (theta ** (-torch.arange(0, half, dtype=torch.float32) * 2 / D)).to(dev)
    ang = torch.arange(4104, device=dev, dtype=torch.float32).unsqueeze(1) * freq.unsqueeze(0)
    td = torch.float16 if dtype == "float16" else torch.float32
    cs_tbl, sn_tbl = ang.cos().to(td), ang.sin().to(td)
    qkv = torch.randn(T, ROW_ELEMS, device=dev, dtype=td) * 0.3
    x = qkv[:, :H*D].contiguous().reshape(-1)   # 模拟 view: 实际 kernel 吃整块 qkv 扁平
    pos = torch.tensor(([7, 101, 999, 4095, 1234] * 3)[:T], device=dev, dtype=torch.int32)
    kern = fused_rope_view(H, D, ROW_ELEMS, T, dtype=dtype)
    y = kern(qkv.reshape(-1), cs_tbl, sn_tbl, pos)
    torch.npu.synchronize()
    cs, sn = cs_tbl[pos.long()], sn_tbl[pos.long()]
    xv = qkv[:, :H*D].float().view(T, H, D); yv = torch.zeros_like(xv)
    yv[:, :, :half] = xv[:, :, :half] * cs.unsqueeze(1) - xv[:, :, half:] * sn.unsqueeze(1)
    yv[:, :, half:] = xv[:, :, half:] * cs.unsqueeze(1) + xv[:, :, :half] * sn.unsqueeze(1)
    y_ref = yv.reshape(T, H * D).to(td)
    d = (y.float() - y_ref.float()).abs()
    rel = d.mean().item() / (y_ref.float().abs().mean() + 1e-9)
    print("rope_view H=%d T=%d dt=%s: rel=%.2e %s" % (H, T, dtype, rel, "PASS" if rel < 3e-3 else "FAIL"))
    return rel < 3e-3


# ---------------- fused per-head RMSNorm + NeoX RoPE (qwen3 q/k-norm 链一体) ----------------
# 替换 qwen3 每层的 [rms_norm(Q) + rope(Q)] 与 [rms_norm(K) + rope(K)] 两条 aclnn 链
# (每层 ~8-12 个 launch, 36 层 ≈ 全图 30-40% launch 税)。
@tilelang.jit(out_idx=[-1], pass_configs=pass_configs)
def fused_qknorm_rope(H, D, ROW_ELEMS, T_len, eps=1e-6, dtype="float"):
    """x: 扁平 [T*ROW_ELEMS] —— wqkv 原始输出 view, 元素 (t,h,d) = x[t*ROW + h*D + d]
       (ROW=整行 6144 融合路径 / 4096,1024 分离路径, 布局等价)
    w: [D] q/k-norm 权重; cs/sn: [4104, D/2] F32 表; pos: [T] i32
    y: [T, H*D] 连续输出; 语义 = rope(rms_norm(x) * w), 与 ggml 链逐位等价"""
    half = D // 2
    @T.prim_func
    def main(
        x: T.Tensor((T_len * ROW_ELEMS,), dtype),
        cs: T.Tensor((4096 + 8, half), dtype),
        sn: T.Tensor((4096 + 8, half), dtype),
        w: T.Tensor((D,), dtype),
        pos: T.Tensor((T_len,), "int32"),
        y: T.Tensor((T_len, H * D), dtype),
    ):
        with T.Kernel(T_len, is_npu=True) as (cid, vid):
            c_ub = T.alloc_ub((half,), dtype)
            s_ub = T.alloc_ub((half,), dtype)
            w_lo = T.alloc_ub((half,), dtype)
            w_hi = T.alloc_ub((half,), dtype)
            x_lo = T.alloc_ub((half,), dtype)
            x_hi = T.alloc_ub((half,), dtype)
            n_lo = T.alloc_ub((half,), dtype)
            n_hi = T.alloc_ub((half,), dtype)
            t1 = T.alloc_ub((half,), dtype)
            t2 = T.alloc_ub((half,), dtype)
            var_ub = T.alloc_ub((1,), dtype)
            ones_ub = T.alloc_ub((1,), "float32")
            sqrt_ub = T.alloc_ub((1,), "float32")
            rms_ub = T.alloc_ub((1,), dtype)
            rms_v = T.alloc_ub((half,), dtype)   # 标量广播向量
            p0 = pos[cid]
            T.copy(cs[p0, 0], c_ub)
            T.copy(sn[p0, 0], s_ub)
            T.copy(w[0], w_lo)
            T.copy(w[half], w_hi)
            base = cid * ROW_ELEMS
            for h in T.serial(H):
                T.copy(x[base + h * D], x_lo)
                T.copy(x[base + h * D + half], x_hi)
                # var = (Σ x_lo² + Σ x_hi²)/D + eps
                T.tile.mul(t1, x_lo, x_lo)
                T.reduce_sum(t1, var_ub, dim=0, clear=True)
                T.tile.mul(t2, x_hi, x_hi)
                T.reduce_sum(t2, var_ub, dim=0, clear=False)
                for i in T.Parallel(1):
                    var_ub[i] = var_ub[i] / D + eps
                # precise 1/sqrt (T.tile.rsqrt is fast-approx ~3e-3)
                T.tile.fill(ones_ub, 1.0)
                T.tile.sqrt(sqrt_ub, var_ub)
                T.tile.div(rms_ub, ones_ub, sqrt_ub)
                for i in T.Parallel(half):
                    rms_v[i] = rms_ub[0]
                # n = x * rms * w  (norm); 全程独立 dst, 不用就地别名
                T.tile.mul(n_lo, x_lo, rms_v)
                T.tile.mul(t1, n_lo, w_lo)     # t1 = norm_lo
                T.tile.mul(n_hi, x_hi, rms_v)
                T.tile.mul(t2, n_hi, w_hi)     # t2 = norm_hi
                # rope: y_lo = norm_lo*cs − norm_hi*sn; y_hi = norm_hi*cs + norm_lo*sn
                T.tile.mul(n_lo, t1, c_ub)     # n_lo = norm_lo*cs
                T.tile.mul(n_hi, t2, s_ub)     # n_hi = norm_hi*sn
                T.tile.mul(t2, t2, c_ub)       # t2 = norm_hi*cs
                T.tile.mul(t1, t1, s_ub)       # t1 = norm_lo*sn
                T.tile.sub(n_lo, n_lo, n_hi)   # n_lo = y_lo
                T.tile.add(t2, t2, t1)         # t2 = y_hi
                T.copy(n_lo, y[cid, h * D])
                T.copy(t2, y[cid, h * D + half])
    return main


# ---------------- strided-row RMSNorm (qwen3 q/k-norm: wqkv view 直读, 无 res) ----------------
# fused_rmsnorm 的归约路径逐字保留; 仅载入改为 rope_view 已验证的带步长偏移。
# x: 扁平 [ROWS*ROW_ELEMS], 行 r 元素 d = x[r*ROW_ELEMS + r0 + d] (r0=Q/K 段偏移)
# y: [ROWS, N] 连续输出 = x_per_row * rsqrt(mean(x²)+eps) * w
@tilelang.jit(out_idx=[-1], pass_configs=pass_configs)
def rmsnorm_strided(N, ROW_ELEMS, ROWS, r0=0, eps=1e-6, dtype="float"):
    @T.prim_func
    def main(
        x: T.Tensor((ROWS * ROW_ELEMS,), dtype),
        w: T.Tensor((N,), dtype),
        y: T.Tensor((ROWS, N), dtype),
    ):
        with T.Kernel(ROWS, is_npu=True) as (cid, vid):
            x_ub = T.alloc_ub((N,), dtype)
            w_ub = T.alloc_ub((N,), dtype)
            s32 = T.alloc_ub((N,), "float32")
            sq32 = T.alloc_ub((N,), "float32")
            y_ub = T.alloc_ub((N,), dtype)
            var_ub = T.alloc_ub((1,), "float32")
            ones_ub = T.alloc_ub((1,), "float32")
            sqrt_ub = T.alloc_ub((1,), "float32")
            rms_ub = T.alloc_ub((1,), "float32")
            T.copy(x[cid * ROW_ELEMS + r0], x_ub)
            T.copy(w, w_ub)
            for i in T.Parallel(N):
                s32[i] = T.Cast("float32", x_ub[i])
            T.tile.mul(sq32, s32, s32)
            T.reduce_sum(sq32, var_ub, dim=0, clear=True)
            for i in T.Parallel(1):
                var_ub[i] = var_ub[i] / N + eps
            # precise 1/sqrt (T.tile.rsqrt is fast-approx ~3e-3)
            T.tile.fill(ones_ub, 1.0)
            T.tile.sqrt(sqrt_ub, var_ub)
            T.tile.div(rms_ub, ones_ub, sqrt_ub)
            for i in T.Parallel(N):
                y_ub[i] = T.Cast(dtype, s32[i] * rms_ub[0] * T.Cast("float32", w_ub[i]))
            T.copy(y_ub, y[cid, 0])
    return main


def test_rmsnorm_strided(N=128, ROW=6144, ROWS=3, r0=0, seed=5):
    torch.manual_seed(seed)
    dev = 'npu:0'
    x = (torch.randn(ROWS, ROW, device=dev) * 0.3)
    w = (torch.randn(N, device=dev) * 0.2 + 1.0)
    kern = rmsnorm_strided(N, ROW, ROWS, r0=r0, dtype="float")
    y = kern(x.reshape(-1), w)
    torch.npu.synchronize()
    xv = x[:, r0:r0+N].float()
    ref = xv * torch.rsqrt((xv*xv).mean(-1, keepdim=True) + 1e-6) * w.float().view(1, N)
    d = (y.float() - ref).abs()
    rel = d.mean().item() / (ref.abs().mean() + 1e-9)
    print(f'rmsnorm_strided N={N} ROW={ROW} r0={r0}: rel={rel:.2e} {"PASS" if rel < 3e-3 else "FAIL"}')
    return rel < 3e-3


# qwen3 Q/K-norm 整段版: grid=T, 每块串行处理 H 个头, 直接从 wqkv 行读 (r0=Q/K 段偏移)
# y: [T, H*N] 连续 —— 恰为 fused_rope_view 的输入布局 (ROW_ELEMS=H*D)
@tilelang.jit(out_idx=[-1], pass_configs=pass_configs)
def qknorm_strided(N, H, ROW_ELEMS, T_len, r0=0, eps=1e-6, dtype="float"):
    @T.prim_func
    def main(
        x: T.Tensor((T_len * ROW_ELEMS,), dtype),
        w: T.Tensor((N,), dtype),
        y: T.Tensor((T_len, H * N), dtype),
    ):
        with T.Kernel(T_len, is_npu=True) as (cid, vid):
            x_ub = T.alloc_ub((N,), dtype)
            w_ub = T.alloc_ub((N,), dtype)
            s32 = T.alloc_ub((N,), "float32")
            sq32 = T.alloc_ub((N,), "float32")
            y_ub = T.alloc_ub((N,), dtype)
            var_ub = T.alloc_ub((1,), "float32")
            ones_ub = T.alloc_ub((1,), "float32")
            sqrt_ub = T.alloc_ub((1,), "float32")
            rms_ub = T.alloc_ub((1,), "float32")
            T.copy(w, w_ub)
            for h in T.serial(H):
                T.copy(x[cid * ROW_ELEMS + r0 + h * N], x_ub)
                for i in T.Parallel(N):
                    s32[i] = T.Cast("float32", x_ub[i])
                T.tile.mul(sq32, s32, s32)
                T.reduce_sum(sq32, var_ub, dim=0, clear=True)
                for i in T.Parallel(1):
                    var_ub[i] = var_ub[i] / N + eps
                # precise 1/sqrt (T.tile.rsqrt is fast-approx ~3e-3)
                T.tile.fill(ones_ub, 1.0)
                T.tile.sqrt(sqrt_ub, var_ub)
                T.tile.div(rms_ub, ones_ub, sqrt_ub)
                for i in T.Parallel(N):
                    y_ub[i] = T.Cast(dtype, s32[i] * rms_ub[0] * T.Cast("float32", w_ub[i]))
                T.copy(y_ub, y[cid, h * N])
    return main


def test_qknorm_strided(H=32, N=128, ROW=6144, T=2, r0=0, seed=5):
    torch.manual_seed(seed)
    dev = 'npu:0'
    x = (torch.randn(T, ROW, device=dev) * 0.3)
    w = (torch.randn(N, device=dev) * 0.2 + 1.0)
    kern = qknorm_strided(N, H, ROW, T, r0=r0, dtype="float")
    y = kern(x.reshape(-1), w)
    torch.npu.synchronize()
    xv = x[:, r0:r0+H*N].float().view(T, H, N)
    ref = (xv * torch.rsqrt((xv*xv).mean(-1, keepdim=True) + 1e-6) * w.float().view(1,1,N)).reshape(T, H*N)
    d = (y.float() - ref).abs()
    rel = d.mean().item() / (ref.abs().mean() + 1e-9)
    print(f'qknorm_strided H={H} r0={r0} T={T}: rel={rel:.2e} {"PASS" if rel < 3e-3 else "FAIL"}')
    return rel < 3e-3


# ---------------- 行级 add+rmsnorm (官方 examples/normalization/rms_norm.py 范式) ----------------
# 2-D tile + tile.fill 累加器 + reduce_sum(dim=-1) + 标量 tile.mul + tile.broadcast, 全向量化。
def _row_tiling(M, N, block_M_in, block_N_in, vec_num=2):
    budget = block_M_in * block_N_in
    ideal_n = budget // 16
    block_N = min(N // 2, ideal_n)
    if block_N < 128:
        block_N = 128 if N >= 256 else N
    while N % block_N != 0:
        block_N -= 1
        if block_N <= 0:
            block_N = 1; break
    block_M = budget // block_N
    if M % block_M != 0:
        block_M = block_M_in if M % block_M_in == 0 else vec_num
    return block_M, block_N


@tilelang.jit(out_idx=[3, 4], pass_configs=pass_configs)
def addnorm_row(M, N, block_N_in=512, eps=1e-6, dtype="float"):
    """x/res: [M, N] -> s = x+res (残差输出), y = rmsnorm(s)*w   (decode 用: M=T<=8 单块)"""
    block_N = min(block_N_in, N)
    while N % block_N != 0:
        block_N -= 128 if block_N > 128 else 1
    n_num = N // block_N
    ROWS = M  # 单块全行 (vid 重复执行同块为幂等写, 无害)
    @T.prim_func
    def main(
        x: T.Tensor((M, N), dtype),
        res: T.Tensor((M, N), dtype),
        w: T.Tensor((N,), dtype),
        s: T.Tensor((M, N), dtype),
        y: T.Tensor((M, N), dtype),
    ):
        with T.Kernel(1, is_npu=True) as (cid, vid):
            s_ub = T.alloc_ub([ROWS, block_N], dtype)
            r_ub = T.alloc_ub([ROWS, block_N], dtype)
            w_row = T.alloc_ub([1, block_N], dtype)
            w_ub = T.alloc_ub([ROWS, block_N], dtype)
            sq = T.alloc_ub([ROWS, block_N], dtype)
            acc = T.alloc_ub([ROWS, block_N], dtype)
            sum_row = T.alloc_ub([ROWS, 1], dtype)
            inv_rms = T.alloc_ub([ROWS, 1], dtype)
            inv_tile = T.alloc_ub([ROWS, block_N], dtype)
            row0 = 0
            T.tile.fill(acc, 0.0)
            # pass1: s = x + res; 累加平方
            for c in T.serial(n_num):
                T.copy(x[row0 : row0 + ROWS, c * block_N : (c + 1) * block_N], s_ub)
                T.copy(res[row0 : row0 + ROWS, c * block_N : (c + 1) * block_N], r_ub)
                T.tile.add(s_ub, s_ub, r_ub)
                T.copy(s_ub, s[row0 : row0 + ROWS, c * block_N : (c + 1) * block_N])
                T.tile.mul(sq, s_ub, s_ub)
                T.tile.add(acc, acc, sq)
            # 行归约 -> inv_rms 广播
            T.reduce_sum(acc, sum_row, dim=-1)
            T.tile.mul(sum_row, sum_row, T.cast(1.0 / N, dtype))
            T.tile.add(sum_row, sum_row, T.cast(eps, dtype))
            # precise 1/sqrt: T.tile.rsqrt is a fast-approx intrinsic (~3e-3 max rel)
            _ones = T.alloc_ub([ROWS, 1], dtype)
            _sqrt = T.alloc_ub([ROWS, 1], dtype)
            T.tile.fill(_ones, 1.0)
            T.tile.sqrt(_sqrt, sum_row)
            T.tile.div(inv_rms, _ones, _sqrt)
            T.tile.broadcast(inv_tile, inv_rms)
            # pass2: y = s * inv_rms * w
            for c in T.serial(n_num):
                T.copy(s[row0 : row0 + ROWS, c * block_N : (c + 1) * block_N], s_ub)
                T.copy(w[c * block_N : (c + 1) * block_N], w_row)
                T.tile.broadcast(w_ub, w_row)
                T.tile.mul(s_ub, s_ub, inv_tile)
                T.tile.mul(s_ub, s_ub, w_ub)
                T.copy(s_ub, y[row0 : row0 + ROWS, c * block_N : (c + 1) * block_N])
    return main


def test_addnorm_row(M=2, N=4096, seed=9):
    import time
    torch.manual_seed(seed)
    dev = 'npu:0'
    x = torch.randn(M, N, device=dev) * 0.3
    r = torch.randn(M, N, device=dev) * 0.3
    w = torch.randn(N, device=dev) * 0.2 + 1.0
    kern = addnorm_row(M, N, dtype="float")
    s, y = kern(x, r, w)
    torch.npu.synchronize()
    s_ref = x + r
    y_ref = s_ref * torch.rsqrt((s_ref*s_ref).mean(-1, keepdim=True) + 1e-6) * w.view(1, N)
    rs = ((s - s_ref).abs().mean() / s_ref.abs().mean()).item()
    ry = ((y - y_ref).abs().mean() / y_ref.abs().mean()).item()
    for _ in range(20): kern(x, r, w)
    torch.npu.synchronize(); t0 = time.perf_counter()
    for _ in range(200): kern(x, r, w)
    torch.npu.synchronize()
    us = (time.perf_counter() - t0) / 200 * 1e6
    ok = rs < 3e-3 and ry < 3e-3
    print(f'addnorm_row M={M} N={N}: rel_s={rs:.2e} rel_y={ry:.2e} {us:.1f}us ' + ('PASS' if ok else 'FAIL'))
    return ok


# no-res 行归一 (官方范式, 单输出): y = rmsnorm(x)*w  —— qwen3 attn_norm/ffn_norm/output_norm
@tilelang.jit(out_idx=[-1], pass_configs=pass_configs)
def norm_row(M, N, block_N_in=512, eps=1e-6, dtype="float"):
    block_N = min(block_N_in, N)
    while N % block_N != 0:
        block_N -= 128 if block_N > 128 else 1
    n_num = N // block_N
    ROWS = M
    @T.prim_func
    def main(
        x: T.Tensor((M, N), dtype),
        w: T.Tensor((N,), dtype),
        y: T.Tensor((M, N), dtype),
    ):
        with T.Kernel(1, is_npu=True) as (cid, vid):
            s_ub = T.alloc_ub([ROWS, block_N], dtype)
            w_row = T.alloc_ub([1, block_N], dtype)
            w_ub = T.alloc_ub([ROWS, block_N], dtype)
            acc = T.alloc_ub([ROWS, block_N], dtype)
            sum_row = T.alloc_ub([ROWS, 1], dtype)
            inv_rms = T.alloc_ub([ROWS, 1], dtype)
            inv_tile = T.alloc_ub([ROWS, block_N], dtype)
            T.tile.fill(acc, 0.0)
            for c in T.serial(n_num):
                T.copy(x[0 : ROWS, c * block_N : (c + 1) * block_N], s_ub)
                T.tile.mul(s_ub, s_ub, s_ub)
                T.tile.add(acc, acc, s_ub)
            T.reduce_sum(acc, sum_row, dim=-1)
            T.tile.mul(sum_row, sum_row, T.cast(1.0 / N, dtype))
            T.tile.add(sum_row, sum_row, T.cast(eps, dtype))
            # precise 1/sqrt: T.tile.rsqrt is a fast-approx intrinsic (~3e-3 max rel)
            _ones = T.alloc_ub([ROWS, 1], dtype)
            _sqrt = T.alloc_ub([ROWS, 1], dtype)
            T.tile.fill(_ones, 1.0)
            T.tile.sqrt(_sqrt, sum_row)
            T.tile.div(inv_rms, _ones, _sqrt)
            T.tile.broadcast(inv_tile, inv_rms)
            for c in T.serial(n_num):
                T.copy(x[0 : ROWS, c * block_N : (c + 1) * block_N], s_ub)
                T.copy(w[c * block_N : (c + 1) * block_N], w_row)
                T.tile.broadcast(w_ub, w_row)
                T.tile.mul(s_ub, s_ub, inv_tile)
                T.tile.mul(s_ub, s_ub, w_ub)
                T.copy(s_ub, y[0 : ROWS, c * block_N : (c + 1) * block_N])
    return main


def test_norm_row(M=2, N=4096, seed=9):
    import time
    torch.manual_seed(seed)
    dev = 'npu:0'
    x = torch.randn(M, N, device=dev) * 0.3
    w = torch.randn(N, device=dev) * 0.2 + 1.0
    kern = norm_row(M, N, dtype="float")
    y = kern(x, w)
    torch.npu.synchronize()
    ref = x * torch.rsqrt((x*x).mean(-1, keepdim=True) + 1e-6) * w.view(1, N)
    rel = ((y - ref).abs().mean() / ref.abs().mean()).item()
    for _ in range(20): kern(x, w)
    torch.npu.synchronize(); t0 = time.perf_counter()
    for _ in range(200): kern(x, w)
    torch.npu.synchronize()
    us = (time.perf_counter() - t0) / 200 * 1e6
    print(f'norm_row M={M} N={N}: rel={rel:.2e} {us:.1f}us ' + ('PASS' if rel < 3e-3 else 'FAIL'))
    return rel < 3e-3
