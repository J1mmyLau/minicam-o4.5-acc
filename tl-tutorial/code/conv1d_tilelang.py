#!/usr/bin/env python3
"""T2W vocoder conv1d — TileLang-Ascend kernel v2

布局（与 ggml tcb 完全一致，集成零转换）:
  x: [Cin, T]  (已含零 pad 的 host 侧张量)
  w: [K, Cin, Cout]  (ggml 原生)
  b: [Cout]
  y: [Cout, T]

计算: y[c, t] = b[c] + Σ_{k,ci} w[k, ci, c] · x[ci, t + k]
  （host 已 pad，kernel 内 t 范围 [0, T)，读 xp[ci, t+k]）
  —— xp 传入的是 pad 后张量，kernel 对称 [pad, pad+T) 内部窗口

tile: 输出 [BLOCK_COUT, BLOCK_T]，reduction 逐 (k, cin_block) gemm_v0 累加
"""
import torch
import torch_npu  # noqa: F401
import tilelang
import tilelang.language as T

pass_configs = {
    tilelang.PassConfigKey.TL_ASCEND_AUTO_CV_COMBINE: True,
    tilelang.PassConfigKey.TL_ASCEND_AUTO_SYNC: True,
    tilelang.PassConfigKey.TL_ASCEND_MEMORY_PLANNING: True,
}

_kernel_cache = {}


@tilelang.jit(out_idx=[-1], pass_configs=pass_configs)
def conv1d_kernel(Cin, Cout, K, T_len, TP, DIL, BLOCK_CIN, BLOCK_COUT, BLOCK_T,
                  dtype="float16"):

    @T.prim_func
    def main(
        xp: T.Tensor((Cin, TP), dtype),  # pad 后输入
        w: T.Tensor((K, Cin, Cout), dtype),   # Cout 连续
        y: T.Tensor((Cout, T_len), dtype),
    ):
        n_t_blocks = T.ceildiv(T_len, BLOCK_T)
        n_cout_blocks = T.ceildiv(Cout, BLOCK_COUT)
        with T.Kernel(n_t_blocks * n_cout_blocks, is_npu=True) as (bid, vid):
            tb = bid // n_cout_blocks
            cb_out = bid % n_cout_blocks
            t0 = tb * BLOCK_T

            x_L1 = T.alloc_L1((BLOCK_CIN, BLOCK_T), dtype)
            w_L1 = T.alloc_L1((BLOCK_CIN, BLOCK_COUT), dtype)
            y_L0C = T.alloc_L0C((BLOCK_COUT, BLOCK_T), "float")

            with T.Scope("C"):
                for cb_in in T.serial(T.ceildiv(Cin, BLOCK_CIN)):
                    for k in T.serial(K):
                        T.copy(xp[cb_in * BLOCK_CIN, t0 + k * DIL], x_L1)
                        T.copy(w[k, cb_in * BLOCK_CIN, cb_out * BLOCK_COUT], w_L1)
                        T.barrier_all()   # 拷贝落 L1 后再进 cube（官方 GEMM 模式）
                        T.gemm_v0(w_L1, x_L1, y_L0C, transpose_A=True,
                                  init=((cb_in == 0) & (k == 0)))
                        T.barrier_all()   # gemm 读完 L1 才允许下一步覆盖

                T.copy(y_L0C, y[cb_out * BLOCK_COUT, t0])
    return main


def get_kernel(Cin, Cout, K, T_len, TP, DIL=1, BLOCK_CIN=64, BLOCK_COUT=128, BLOCK_T=128):
    key = (Cin, Cout, K, T_len, TP, DIL, BLOCK_CIN, BLOCK_COUT, BLOCK_T)
    if key not in _kernel_cache:
        _kernel_cache[key] = conv1d_kernel(
            Cin, Cout, K, T_len, TP, DIL, BLOCK_CIN, BLOCK_COUT, BLOCK_T)
    return _kernel_cache[key]


def conv1d_tl(x, w, b, pad, dil=1):
    """x [1,Cin,T] torch npu, w [Cout,Cin,K], b [Cout] -> [1,Cout,T]"""
    import torch.nn.functional as F
    Cin, Tt = x.shape[1], x.shape[2]
    K = w.shape[2]
    Tout = Tt + 2 * pad - dil * (K - 1)             # stride=1 dilated 卷积输出长度
    xp = F.pad(x, (pad, pad))                       # [1, Cin, T+2p]
    w_k = w.permute(2, 1, 0).contiguous()           # [K, Cin, Cout] Cout连续
    kern = get_kernel(Cin, w.shape[0], K, Tout, xp.shape[2], DIL=dil)
    y = kern(xp[0], w_k)                            # [Cout, T]
    y = y + b[:, None]                              # host 侧 bias
    return y.unsqueeze(0)


def run(Cin, Cout, K, pad, T_len, seed=42, check=True, bench=False):
    torch.manual_seed(seed)
    dev = 'npu:0'
    x = (torch.randn(1, Cin, T_len, device=dev, dtype=torch.float16) * 0.5)
    w = (torch.randn(Cout, Cin, K, device=dev, dtype=torch.float16) * 0.05)
    b = torch.randn(Cout, device=dev, dtype=torch.float16) * 0.1

    y = conv1d_tl(x, w, b, pad)
    torch.npu.synchronize()

    if check:
        import torch.nn.functional as F
        y_ref = F.conv1d(x, w, b, stride=1, padding=pad)
        d = (y.float() - y_ref.float()).abs()
        rel = d.mean().item() / (y_ref.float().abs().mean().item() + 1e-9)
        status = 'PASS' if rel < 5e-3 else 'FAIL'
        print(f'C={Cin}->{Cout} K={K} pad={pad} T={T_len}: rel={rel:.2e} '
              f'max={d.max().item():.3e} {status}')
        return rel < 5e-3
    return True


if __name__ == '__main__':
    shapes = [
        (64, 64, 11, 5, 20883),
        (64, 64, 7, 3, 20883),
        (64, 64, 3, 1, 20883),
        (128, 128, 11, 5, 6961),
        (128, 128, 7, 3, 6961),
        (128, 128, 3, 1, 6961),
        (256, 256, 7, 3, 2320),
        (256, 256, 3, 1, 2320),
        (512, 512, 16, 7, 174),
    ]
    ok = 0
    for s in shapes:
        try:
            if run(*s):
                ok += 1
        except Exception as e:
            print(f'{s}: EXC {type(e).__name__}: {str(e)[:160]}')
    print(f'== {ok}/{len(shapes)} PASS ==')
