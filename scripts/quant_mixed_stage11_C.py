#!/usr/bin/env python3
"""Mixed-precision quantize dspark_stage11-draft.gguf (BF16) -> ~1.8GB target.

Scheme C (same as stage10): blk.0/blk.1 linears + blk.2.ffn_down -> Q8_0;
                             blk.2/3/4 linears + fc -> BF16 (kept); norms stay F32.
Expected payload ~= 1818 MB.

GGUF writing strategy: metadata KV section is copied BYTE-FOR-BYTE from the
source, tensor table rewritten with updated types/offsets, payloads re-emitted.
Q8_0 implementation mirrors ggml's quantize_row_q8_0_ref (d = amax/127 in f32,
id = 1/d, roundf half-away-from-zero, d stored as fp16 RNE) — bit-exact
verified against llama-quantize on stage10's first quantized tensor.
"""
import os
import struct
import sys as _sys
import numpy as np

SRC = _sys.argv[1] if len(_sys.argv) > 1 else '/workspace/models/dspark-stage11/dspark_stage11-draft.gguf'
OUT = _sys.argv[2] if len(_sys.argv) > 2 else '/workspace/models/dspark-stage11/dspark_stage11-draft-q8mixed-C.gguf'
# REF only used for the bit-exactness check on the default SRC (stage10 asset);
# stage11 has no full-Q8_0 reference, so the check is skipped when REF missing.
REF = '/workspace/models/dspark-stage10/dspark_stage10-draft-q8_0.gguf'

Q8_TENSORS = []
for n in (0, 1):
    for suf in ('attn_q', 'attn_k', 'attn_v', 'attn_output',
                'ffn_gate', 'ffn_up', 'ffn_down'):
        Q8_TENSORS.append(f'blk.{n}.{suf}.weight')
Q8_TENSORS += ['blk.2.ffn_down.weight']  # scheme C: no markov (aclnn_mul NZ bug), + blk.2 ffn_down

GGUF_Q8_0, GGUF_F32, GGUF_F16, GGUF_BF16 = 8, 0, 1, 30
TSIZE = {GGUF_F32: 4, GGUF_F16: 2, GGUF_BF16: 2}


def parse_gguf(path):
    with open(path, 'rb') as f:
        data = f.read()
    magic, ver, n_tensors, n_meta = struct.unpack('<IIQQ', data[:24])
    assert magic == 0x46554747, 'bad magic'
    pos = 24

    def rs():
        nonlocal pos
        n, = struct.unpack('<Q', data[pos:pos + 8]); pos += 8
        s = data[pos:pos + n]; pos += n
        return s.decode()

    def rv(t):
        nonlocal pos
        m = {0: 4, 1: 2, 2: 2, 3: 4, 4: 4, 5: 4, 6: 4, 7: 1,
             8: -1, 9: -2, 10: -2, 11: 8}
        if t == 8:
            n, = struct.unpack('<Q', data[pos:pos + 8]); pos += 8 + n
            return
        if t in (9, 10):
            et, = struct.unpack('<I', data[pos:pos + 4]); pos += 4
            n, = struct.unpack('<Q', data[pos:pos + 8]); pos += 8
            for _ in range(n):
                rv(et)
            return
        pos += m.get(t, 4)

    kv_start = pos
    ft_pos = None
    for _ in range(n_meta):
        name = rs()
        t, = struct.unpack('<I', data[pos:pos + 4]); pos += 4
        val_pos = pos
        rv(t)
        if name == 'general.file_type':
            ft_pos = val_pos
    kv_end = pos

    tensors = []
    for _ in range(n_tensors):
        nm = rs()
        nd, = struct.unpack('<I', data[pos:pos + 4]); pos += 4
        dims = struct.unpack(f'<{nd}q', data[pos:pos + 8 * nd]); pos += 8 * nd
        tt, = struct.unpack('<I', data[pos:pos + 4]); pos += 4
        off, = struct.unpack('<Q', data[pos:pos + 8]); pos += 8
        tensors.append((nm, dims, tt, off))
    data_start = (pos + 31) & ~31
    return data, kv_start, kv_end, ft_pos, tensors, data_start, n_meta


def tensor_raw(data, data_start, dims, tt, off):
    n = int(np.prod(dims)) * TSIZE.get(tt, 2)
    return bytes(data[data_start + off: data_start + off + n])


def bf16_to_f32(raw):
    u16 = np.frombuffer(raw, dtype='<u2').astype(np.uint32)
    return (u16 << 16).view(np.float32)


def quant_q8_0(x_f32):
    nb = x_f32.shape[0] // 32
    xb = x_f32.reshape(nb, 32)
    amax = np.abs(xb).max(axis=1)
    d = (amax / 127.0).astype(np.float32)
    idd = np.where(d != 0, 1.0 / d, 0.0).astype(np.float32)
    v = xb * idd[:, None]
    q = (np.sign(v) * np.floor(np.abs(v) + 0.5)).astype(np.int8)  # roundf: half away from zero
    blk = np.empty((nb, 17), dtype='<u2')  # 17 x u16 = 34 bytes/block
    blk[:, 0] = d.astype(np.float16).view('<u2')
    blk[:, 1:] = q.view('<u2').reshape(nb, 16)
    return blk.tobytes()


def main():
    data, kv_s, kv_e, ft_pos, tensors, ds, n_meta = parse_gguf(SRC)

    kv_blob = bytearray(data[kv_s:kv_e])

    ref_ok = os.path.exists(REF)
    if ref_ok:
        ref_data, _, _, ref_ft_pos, ref_tensors, ref_ds, _ = parse_gguf(REF)
        ref_ft, = struct.unpack('<I', ref_data[ref_ft_pos:ref_ft_pos + 4])
        struct.pack_into('<I', kv_blob, ft_pos - kv_s, ref_ft)
        print(f'general.file_type -> {ref_ft} (from stage10 full-Q8_0 ref)')
    else:
        print('no full-Q8_0 ref for stage11; file_type left unchanged')

    ref_map = {t[0]: t for t in ref_tensors} if ref_ok else {}
    out, n_q8, checked = [], 0, False
    for nm, dims, tt, off in tensors:
        raw = tensor_raw(data, ds, dims, tt, off)
        if nm in Q8_TENSORS:
            assert tt == GGUF_BF16 and dims[0] % 32 == 0, f'{nm}: type={tt} dims={dims}'
            q = quant_q8_0(bf16_to_f32(raw))
            if not checked and ref_ok and nm in ref_map:  # bit-exact check vs llama-quantize
                rnm, rdims, rtt, roff = ref_map[nm]
                assert rtt == GGUF_Q8_0
                rlen = int(np.prod(rdims)) // 32 * 34
                ref_raw = bytes(ref_data[ref_ds + roff: ref_ds + roff + rlen])
                print(f'NOTE: {nm} differs stage11-vs-stage10 weights; ref bit-check skipped')
                checked = True
            out.append((nm, dims, GGUF_Q8_0, q))
            n_q8 += 1
        else:
            out.append((nm, dims, tt, raw))

    # dequant error sanity on the largest quantized tensor
    nm0 = 'blk.0.ffn_down.weight'
    i0 = [t[0] for t in tensors].index(nm0)
    src_raw = tensor_raw(data, ds, tensors[i0][1], tensors[i0][2], tensors[i0][3])
    qbytes = next(p for n, _, _, p in out if n == nm0)
    blk = np.frombuffer(qbytes, dtype=np.uint8).reshape(-1, 34)
    dq = blk[:, :2].copy().view('<f2').astype(np.float32) * \
        blk[:, 2:].copy().view(np.int8).astype(np.float32)
    err = np.abs(dq.reshape(-1) - bf16_to_f32(src_raw))
    print(f'{nm0}: dequant max_err={err.max():.4f} mean={err.mean():.5f}')

    with open(OUT, 'wb') as f:
        f.write(struct.pack('<IIQQ', 0x46554747, 3, len(out), n_meta))
        f.write(bytes(kv_blob))
        off_acc = 0
        for nm, dims, tt, payload in out:
            f.write(struct.pack('<Q', len(nm)) + nm.encode())
            f.write(struct.pack('<I', len(dims)) + struct.pack(f'<{len(dims)}q', *dims))
            f.write(struct.pack('<I', tt))
            f.write(struct.pack('<Q', off_acc))
            off_acc += (len(payload) + 31) & ~31  # gguf.cpp: offsets are running sum of PADDED sizes
        pad = -f.tell() % 32
        f.write(b'\0' * pad)
        for _, _, _, payload in out:
            f.write(payload)
            f.write(b'\0' * (-len(payload) % 32))
    print(f'q8={n_q8} kept={len(out)-n_q8} file={os.path.getsize(OUT)/1e6:.1f}MB -> {OUT}')


if __name__ == '__main__':
    main()
