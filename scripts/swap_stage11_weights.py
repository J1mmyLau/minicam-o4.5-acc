#!/usr/bin/env python3
"""Stage11 GGUF = stage8 GGUF with tensor payloads swapped in place.

Same provenance as swap_stage10_weights.py (bit-exact method, validated via
dspark_align_ref_text.pt cross-check on stage10): both checkpoints share
identical tensor names/shapes/dtypes, so the stage8 file's header, KV
(tokenizer, chat template, hyperparams incl. dflash.target_layers
[2,10,18,26,34]) and tensor table are byte-preserved; only data blobs are
overwritten (F32 norms/biases, bf16 bit-patterns for big linears, NO transpose).
"""
import struct
import numpy as np
import torch
from safetensors import safe_open

TPL = '/workspace/models/dspark-draft/dspark_stage8-draft.gguf'
import sys as _sys
SRC = _sys.argv[1] if len(_sys.argv) > 1 else '/workspace/models/dspark-stage11/model.safetensors'
OUT = _sys.argv[2] if len(_sys.argv) > 2 else '/workspace/models/dspark-stage11/dspark_stage11-draft.gguf'

MAP = {
    'fc.weight': ('fc.weight', True),
    'confidence_head.proj.weight': ('conf_proj.weight', True),
    'confidence_head.proj.bias': ('conf_proj.bias', False),
    'hidden_norm.weight': ('enc.output_norm.weight', False),
    'norm.weight': ('output_norm.weight', False),
    'markov_head.markov_w1.weight': ('markov_w1.weight', True),
    'markov_head.markov_w2.weight': ('markov_w2.weight', True),
}
for n in range(5):
    MAP[f'layers.{n}.input_layernorm.weight'] = (f'blk.{n}.attn_norm.weight', False)
    MAP[f'layers.{n}.post_attention_layernorm.weight'] = (f'blk.{n}.ffn_norm.weight', False)
    MAP[f'layers.{n}.self_attn.q_proj.weight'] = (f'blk.{n}.attn_q.weight', True)
    MAP[f'layers.{n}.self_attn.k_proj.weight'] = (f'blk.{n}.attn_k.weight', True)
    MAP[f'layers.{n}.self_attn.v_proj.weight'] = (f'blk.{n}.attn_v.weight', True)
    MAP[f'layers.{n}.self_attn.o_proj.weight'] = (f'blk.{n}.attn_output.weight', True)
    MAP[f'layers.{n}.self_attn.q_norm.weight'] = (f'blk.{n}.attn_q_norm.weight', False)
    MAP[f'layers.{n}.self_attn.k_norm.weight'] = (f'blk.{n}.attn_k_norm.weight', False)
    MAP[f'layers.{n}.mlp.gate_proj.weight'] = (f'blk.{n}.ffn_gate.weight', True)
    MAP[f'layers.{n}.mlp.up_proj.weight'] = (f'blk.{n}.ffn_up.weight', True)
    MAP[f'layers.{n}.mlp.down_proj.weight'] = (f'blk.{n}.ffn_down.weight', True)

# parse the template's tensor table
with open(TPL, 'rb') as f:
    data = bytearray(f.read())
magic, ver, n_tensors, n_meta = struct.unpack('<IIQQ', data[:24])
pos = 24


def rs():
    global pos
    n, = struct.unpack('<Q', data[pos:pos + 8]); pos += 8
    s = data[pos:pos + n]; pos += n
    return s.decode()


def rv(t):
    global pos
    m = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 8: -1, 9: -2, 10: -2, 11: 8}
    sz = m.get(t, 1)
    if t == 8:
        n, = struct.unpack('<Q', data[pos:pos + 8]); pos += 8
        pos += n
        return
    if t in (9, 10):
        et, = struct.unpack('<I', data[pos:pos + 4]); pos += 4
        n, = struct.unpack('<Q', data[pos:pos + 8]); pos += 8
        for _ in range(n):
            rv(et)
        return
    pos += sz if sz > 0 else 0


for _ in range(n_meta):
    rs(); t, = struct.unpack('<I', data[pos:pos + 4]); pos += 4
    rv(t)

gguf_tensors = {}
for _ in range(n_tensors):
    nm = rs()
    nd, = struct.unpack('<I', data[pos:pos + 4]); pos += 4
    dims = struct.unpack(f'<{nd}q', data[pos:pos + 8 * nd]); pos += 8 * nd
    tt, = struct.unpack('<I', data[pos:pos + 4]); pos += 4
    off, = struct.unpack('<Q', data[pos:pos + 8]); pos += 8
    gguf_tensors[nm] = (dims, tt, off)

# alignment: offsets are relative to start of the data section
data_start = (pos + 31) & ~31
nbytes = {0: 4, 1: 2, 30: 2}  # F32, F16, BF16

n_swapped = 0
with safe_open(SRC, framework='pt') as sf:
    for src_name, (dst_name, transpose) in MAP.items():
        dims, tt, off = gguf_tensors[dst_name]
        ne = np.prod(dims)
        esz = nbytes[tt]
        blob_off = data_start + off
        w_t = sf.get_tensor(src_name)                      # torch (out, in)
        # NOTE: ggml mul_mat weight ne=(K,N) memory = N rows x K = torch raw
        # contiguous DIRECTLY - NO transpose. The earlier .t() scrambled every
        # linear weight (fc cos -0.001 vs ref; raw layout gives cos 1.0000,
        # verified against dspark_align_ref_text.pt fc_out_prenorm).
        w32 = w_t.float().numpy().astype(np.float32)
        assert w_t.numel() == ne, f'{dst_name}: torch {tuple(w_t.shape)} numel {w_t.numel()} != gguf {dims} ({ne})'  # (out,in) vs ne=(K,N): same memory, tuple order differs
        if tt == 0:      # F32
            blob = w32.tobytes()
        else:            # BF16: round-trip via torch bf16
            blob = torch.from_numpy(w32).to(torch.bfloat16).view(torch.uint16).numpy().tobytes()
        assert len(blob) == ne * esz, f'{dst_name}: {len(blob)} != {ne * esz}'
        data[blob_off:blob_off + len(blob)] = blob
        n_swapped += 1

with open(OUT, 'wb') as f:
    f.write(data)
print(f'swapped {n_swapped}/{len(gguf_tensors)} tensors -> {OUT}')
