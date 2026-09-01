import torch, sys
sys.path.insert(0, '/workspace/t2w-tilelang')
from llm_fused_kernels import fused_rope_view
dev = "npu:0"
H, D, ROW, T = 32, 128, 6144, 1
half = D // 2
torch.manual_seed(7)
theta = 1_000_000.0
freq = (theta ** (-torch.arange(0, half, dtype=torch.float32) * 2 / D)).to(dev)
ang = torch.arange(4104, device=dev, dtype=torch.float32).unsqueeze(1) * freq.unsqueeze(0)
cs_tbl, sn_tbl = ang.cos(), ang.sin()
x = torch.randn(T, ROW, device=dev) * 0.3
pos = torch.tensor([7], device=dev, dtype=torch.int32)
kern = fused_rope_view(H, D, ROW, T, dtype="float")
y = kern(x.reshape(-1), cs_tbl, sn_tbl, pos)
torch.npu.synchronize()
xv = x[:, :H*D].float().view(T, H, D)
cs, sn = cs_tbl[pos.long()].unsqueeze(1), sn_tbl[pos.long()].unsqueeze(1)
yv = torch.zeros_like(xv)
yv[:, :, :half] = xv[:, :, :half]*cs - xv[:, :, half:]*sn
yv[:, :, half:] = xv[:, :, half:]*cs + xv[:, :, :half]*sn
d = (y.float() - yv.reshape(T, H*D)).abs()
print("rope_view harness check rel =", (d.mean()/yv.abs().mean()).item())
