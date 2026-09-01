#!/usr/bin/env python3
"""AOT 编译 rope/rmsnorm kernel -> .so，并按 C++ 口径（预分配 buffer + ctypes call）重测延迟"""
import ctypes
import shutil
import time
import sys

import torch
import torch_npu  # noqa: F401
import tilelang
import tilelang.language as T
from tilelang.jit.adapter.libgen import LibraryGenerator
from tilelang.utils.target import determine_platform

sys.path.insert(0, '/workspace/t2w-tilelang')
from llm_fused_kernels import fused_rope_tbl, fused_rmsnorm  # noqa: E402

dev = 'npu:0'


def aot_build(kernel_factory, name):
    """kernel_factory() -> (prim_func, params...)；这里直接复用 jit 内部 lower 路径"""
    raise NotImplementedError


def aot_from_jit(kern, out_so):
    """从 JITKernel 拿 prim_func 并编 .so（与 gemm_aot 同路径）"""
    platform = determine_platform('auto')
    platform = determine_platform('auto')
    artifact = kern.artifact if hasattr(kern, 'artifact') else None
    src = kern.get_kernel_source() if hasattr(kern, 'get_kernel_source') else None
    lg = LibraryGenerator(target='ascendc', platform=platform)
    lg.update_lib_code(src)
    lg.compile_lib()
    shutil.copy(lg.get_lib_path(), out_so)
    return out_so


if __name__ == '__main__':
    H, D, MAXP, T, N = 32, 128, 4096, 5, 4096
    half = D // 2

    # --- rope ---
    from tilelang.jit.kernel import JITKernel
    rk = fused_rope_tbl(H, D, T)
    # JITKernel 构造后 .func 可能有；gemm_aot 用独立函数定义。这里尝试直接 lower:
    so = aot_from_jit(rk, '/workspace/t2w-tilelang/rope_t5.so')

    lib = ctypes.CDLL(so)
    stream = torch.npu.current_stream()._as_parameter_
    x = torch.randn(T, H * D, device=dev, dtype=torch.float16) * 0.3
    y = torch.empty_like(x)
    theta = 1_000_000.0
    freq = (theta ** (-torch.arange(0, half, dtype=torch.float32) * 2 / D)).to(dev)
    ang = torch.arange(MAXP, device=dev, dtype=torch.float32).unsqueeze(1) * freq.unsqueeze(0)
    cs_tbl, sn_tbl = ang.cos().half(), ang.sin().half()
    pos = torch.tensor([990 + i for i in range(T)], device=dev, dtype=torch.int32)
    cs, sn = cs_tbl[pos.long()], sn_tbl[pos.long()]

    lib.call(ctypes.c_void_p(x.data_ptr()), ctypes.c_void_p(cs.data_ptr()),
             ctypes.c_void_p(sn.data_ptr()), ctypes.c_void_p(y.data_ptr()), stream)
    torch.npu.synchronize()

    # 数值
    from llm_fused_kernels import ref_rope
    y_ref = ref_rope(x, freq, pos, H, D).reshape(T, H * D)
    d = (y.float() - y_ref.float()).abs()
    rel = d.mean().item() / (y_ref.float().abs().mean() + 1e-9)
    print(f'AOT rope 数值: rel={rel:.2e} {"PASS" if rel < 3e-3 else "FAIL"}')

    # 延迟（预分配 + 纯 ctypes）
    for _ in range(50):
        lib.call(ctypes.c_void_p(x.data_ptr()), ctypes.c_void_p(cs.data_ptr()),
                 ctypes.c_void_p(sn.data_ptr()), ctypes.c_void_p(y.data_ptr()), stream)
    torch.npu.synchronize()
    t0 = time.perf_counter()
    for _ in range(1000):
        lib.call(ctypes.c_void_p(x.data_ptr()), ctypes.c_void_p(cs.data_ptr()),
                 ctypes.c_void_p(sn.data_ptr()), ctypes.c_void_p(y.data_ptr()), stream)
    torch.npu.synchronize()
    us = (time.perf_counter() - t0) / 1000 * 1e6
    print(f'AOT rope 延迟: {us:.1f} us/call（C++ 侧同量级）×73/step = {us*73/1000:.3f} ms/step')
