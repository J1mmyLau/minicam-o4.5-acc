import torch, sys
sys.path.insert(0, '/workspace/t2w-tilelang')
import tilelang
from tilelang.jit.adapter.libgen import LibraryGenerator
from tilelang.utils.target import determine_platform
import shutil
from llm_fused_kernels import fused_qknorm_rope

dev = "npu:0"
def run_case(H, D, ROW, T, dtype, eps=1e-6, seed=7):
    torch.manual_seed(seed)
    half = D // 2
    td = torch.float32 if dtype == "float" else torch.float16
    theta = 1_000_000.0
    freq = (theta ** (-torch.arange(0, half, dtype=torch.float32) * 2 / D)).to(dev)
    ang = torch.arange(4104, device=dev, dtype=torch.float32).unsqueeze(1) * freq.unsqueeze(0)
    cs_tbl, sn_tbl = ang.cos().to(td), ang.sin().to(td)
    x = (torch.randn(T, ROW, device=dev) * 0.3).to(td)          # wqkv 行
    w = (torch.randn(D, device=dev) * 0.2 + 1.0).to(td)          # q/k-norm 权重
    pos = torch.tensor([7, 101, 999, 4095, 1234, 5, 88, 3000][:T], device=dev, dtype=torch.int32)
    kern = fused_qknorm_rope(H, D, ROW, T, eps=eps, dtype=dtype)
    y = kern(x.reshape(-1), cs_tbl, sn_tbl, w, pos)
    torch.npu.synchronize()
    # ref: rmsnorm(per head) -> rope
    xv = x[:, :H * D].float().view(T, H, D)
    var = (xv * xv).mean(-1, keepdim=True) + eps
    nv = (xv * torch.rsqrt(var)) * w.float().view(1, 1, D)
    cs, sn = cs_tbl[pos.long()].float().unsqueeze(1), sn_tbl[pos.long()].float().unsqueeze(1)
    yv = torch.zeros_like(nv)
    yv[:, :, :half] = nv[:, :, :half] * cs - nv[:, :, half:] * sn
    yv[:, :, half:] = nv[:, :, half:] * cs + nv[:, :, :half] * sn
    y_ref = yv.reshape(T, H * D).to(td)
    d = (y.float() - y_ref.float()).abs()
    rel = d.mean().item() / (y_ref.float().abs().mean() + 1e-9)
    mx = d.max().item()
    print(f'H{H} D{D} R{ROW} T{T} {dtype}: rel={rel:.2e} max={mx:.2e} {"PASS" if rel < 3e-3 else "FAIL"}')
    return rel < 3e-3

ok = True
for H, ROW in [(32, 6144), (8, 6144)]:
    for T in (1, 3, 8):
        ok &= run_case(H, 128, ROW, T, "float")
print("ALL", "PASS" if ok else "FAIL")

# AOT 编释 .so
OUT = '/workspace/t2w-tilelang/aot'
built = 0
for H in (32, 8):
    for T in range(1, 9):
        try:
            kern = fused_qknorm_rope(H, 128, H * 128, T, eps=1e-6, dtype="float")
            lg = LibraryGenerator(target='ascendc', platform=determine_platform('auto'))
            lg.update_lib_code(kern.get_kernel_source())
            lg.compile_lib()
            so = f'{OUT}/tlqkr_H{H}_D128_R{H*128}_T{T}_F32.so'
            shutil.copy(lg.get_lib_path(), so)
            built += 1
        except Exception as e:
            print(f'H{H} T{T}: EXC {type(e).__name__}: {str(e)[:100]}')
print(f'AOT built {built}/16')
