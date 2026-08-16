#include "models.h"

// ============================================================================
// TileLang RoPE 桥 (decode 热路径): OMNI_TL_ROPE=1 时把 Q/K 的 ggml_rope_ext 换成
// 单个 GGML_OP_CUSTOM 节点, 回调内 dlopen AOT kernel (tlrope_H{H}_D128_R{H*128}_T{1..8}.so,
// ABI: call(x, cs_tbl, sn_tbl, pos, y, stream))。cos/sin 表 host 预计算一次上传
// (tir.cos 不支持, 与 /workspace/t2w-tilelang/llm_fused_kernels.py 的 fused_rope_view
// 数值口径一致: neox 半分旋转, freq = theta^(-2i/D))。
// 约束: T<=8 (AOT 覆盖), pos < 4104 (表行数 4096+8), x 连续 F16/F32, D==128。
// 流序: kernel 在当前 compute stream 上发射, 上下游同流保序 (与已认证 conv 桥同模型);
// 禁止回调内同步当前流 (自同步 UB, 见 tl_layout_bridge 教训)。
// ============================================================================
#include <dlfcn.h>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

extern "C" int aclrtMemcpy(void *, size_t, void *, size_t, int);
extern "C" int aclrtMalloc(void **, size_t, int);

namespace tlrope {

typedef void (*rope_call_fn)(void *, void *, void *, void *, void *, void *);

static std::unordered_map<uint64_t, rope_call_fn> g_so_cache;  // key: (H<<8)|T|(f32?1<<16)
static std::mutex g_mu;

static bool enabled() {
    static const bool e = [] { const char * s = getenv("OMNI_TL_ROPE"); return s && s[0] == '1'; }();
    return e;
}

static rope_call_fn lookup(int64_t H, int64_t T, bool f32) {
    uint64_t key = (uint64_t(H) << 8) | uint64_t(T) | (f32 ? (1ull << 16) : 0);
    std::lock_guard<std::mutex> lk(g_mu);
    auto it = g_so_cache.find(key);
    if (it != g_so_cache.end()) return it->second;
    const char * dir = getenv("OMNI_TL_ROPE_DIR");
    std::string d = dir ? dir : "tilelang-aot";  // 相对 cwd=仓库根; 可用 OMNI_TL_ROPE_DIR 覆盖
    char name[256];
    snprintf(name, sizeof(name), "%s/tlrope_H%lld_D128_R%lld_T%lld%s.so", d.c_str(),
             (long long)H, (long long)(H * 128), (long long)T, f32 ? "_F32" : "");
    void * h = dlopen(name, RTLD_NOW);
    rope_call_fn fn = h ? (rope_call_fn) dlsym(h, "call") : nullptr;
    static bool logged = false;
    if (fn && !logged) { fprintf(stderr, "[TL_ROPE] loaded %s\n", name); logged = true; }
    g_so_cache[key] = fn;
    return fn;
}

// cos/sin 表: [4104, half] 上传一次; theta 每模型固定
static void * g_cs = nullptr, * g_sn = nullptr;
static double g_theta_cached = -1.0;

static inline unsigned short f32_to_f16_bits(float f) {
    unsigned x; memcpy(&x, &f, 4);
    unsigned sign = (x >> 16) & 0x8000;
    unsigned e = (x >> 23) & 0xff, m = x & 0x7fffff;
    if (e == 0xff) return sign | 0x7c00 | (m ? 1 : 0);
    if (e == 0) return sign;
    int ee = (int)e - 127 + 15;
    if (ee >= 0x1f) return sign | 0x7c00;
    if (ee <= 0) return sign;
    unsigned short r = sign | ((unsigned short)ee << 10) | (unsigned short)(m >> 13);
    unsigned rem = m & 0x1fff;
    if (rem > 0x1000 || (rem == 0x1000 && (r & 1))) r++;
    return r;
}

static void ensure_tables(int half, float theta, bool f32) {
    const int rows = 4096 + 8;
    if (g_cs && g_theta_cached == (double)theta) return;
    std::vector<float> cs(rows * half), sn(rows * half);
    for (int i = 0; i < half; i++) {
        float freq = powf(theta, -2.0f * (float)i / (float)(2 * half));
        for (int p = 0; p < rows; p++) {
            float ang = (float)p * freq;
            cs[(size_t)p * half + i] = cosf(ang);
            sn[(size_t)p * half + i] = sinf(ang);
        }
    }
    size_t bytes = (size_t)rows * half * (f32 ? 4 : 2);
    aclrtMalloc(&g_cs, bytes, 0);
    aclrtMalloc(&g_sn, bytes, 0);
    if (f32) {
        aclrtMemcpy(g_cs, bytes, cs.data(), bytes, 1);
        aclrtMemcpy(g_sn, bytes, sn.data(), bytes, 1);
    } else {
        std::vector<unsigned short> c16(rows * half), s16(rows * half);
        for (size_t i = 0; i < cs.size(); i++) {
            c16[i] = f32_to_f16_bits(cs[i]);
            s16[i] = f32_to_f16_bits(sn[i]);
        }
        aclrtMemcpy(g_cs, bytes, c16.data(), bytes, 1);
        aclrtMemcpy(g_sn, bytes, s16.data(), bytes, 1);
    }
    g_theta_cached = (double)theta;
    fprintf(stderr, "[TL_ROPE] cos/sin table %dx%d theta=%.1f dtype=%s uploaded\n",
            rows, half, theta, f32 ? "F32" : "F16");
}

static void rope_cb(ggml_tensor * dst, int /*ith*/, int /*nth*/, void * /*userdata*/) {
    const ggml_tensor * x   = dst->src[0];
    const ggml_tensor * pos = dst->src[1];
    if (!x || !x->data || !dst->data || !pos || !pos->data) return;
    const bool    f32 = x->type == GGML_TYPE_F32;
    const int64_t H   = (x->ne[0] == 128) ? x->ne[1] : x->ne[0] / 128;
    const int64_t T   = (x->ne[0] == 128) ? x->ne[2] : x->ne[1];
    rope_call_fn fn = lookup(H, T, f32);
    if (!fn) return;
    // 表按 (half=64, theta) 缓存; 回调在 CANN dispatch 内, thread_local stream 已设好
    static void * (*cur_stream)() = nullptr;
    if (!cur_stream) cur_stream = (void * (*)()) dlsym(RTLD_DEFAULT, "ggml_cann_custom_current_stream");
    if (!cur_stream) return;
    fn(x->data, g_cs, g_sn, pos->data, dst->data, cur_stream());
}

// x: q/k-norm 输出, 连续; 两种形态 (内存布局等价: 元素 t*H*D + h*D + d):
//   2-D [H*D, T] (separate wq/wk 路径)  或  3-D [D, H, T] (wqkv 融合 view 路径, norm 后连续)
// pos: I32 [T] (inp_pos)
ggml_tensor * try_rope(ggml_context * ctx, ggml_tensor * x, ggml_tensor * pos,
                       int64_t n_head, float theta) {
    static const bool dbg = getenv("OMNI_TL_ROPE_LOG") != nullptr;
    if (!enabled() || !ctx || !x || !pos) return nullptr;
    if (dbg) fprintf(stderr, "[TL_ROPE][dbg] try ne=[%lld,%lld,%lld,%lld] type=%d cont=%d n_head=%lld\n",
                     (long long)x->ne[0], (long long)x->ne[1], (long long)x->ne[2], (long long)x->ne[3],
                     (int)x->type, (int)ggml_is_contiguous(x), (long long)n_head);
    if (x->ne[3] != 1) return nullptr;
    if (!ggml_is_contiguous(x)) return nullptr;
    if (x->type != GGML_TYPE_F16 && x->type != GGML_TYPE_F32) return nullptr;
    int64_t D, H, T;
    if (x->ne[0] == 128 && x->ne[1] == n_head) { D = 128; H = n_head; T = x->ne[2]; }  // 3-D [D,H,T]
    else                                       { D = x->ne[0] / n_head; H = n_head; T = x->ne[1]; }  // 2-D [H*D,T]
    if (D != 128) { if (dbg) fprintf(stderr, "[TL_ROPE][dbg] reject D=%lld\n", (long long)D); return nullptr; }
    if (H != n_head) { if (dbg) fprintf(stderr, "[TL_ROPE][dbg] reject H=%lld!=%lld\n", (long long)H, (long long)n_head); return nullptr; }
    if (T < 1 || T > 8) { if (dbg) fprintf(stderr, "[TL_ROPE][dbg] reject T=%lld\n", (long long)T); return nullptr; }
    if (!lookup(H, T, x->type == GGML_TYPE_F32)) { if (dbg) fprintf(stderr, "[TL_ROPE][dbg] reject no-so H=%lld T=%lld\n", (long long)H, (long long)T); return nullptr; }
    ensure_tables(D / 2, theta, x->type == GGML_TYPE_F32);
    if (!g_cs) return nullptr;

    const int nd = (x->ne[2] > 1) ? 3 : 2;
    ggml_tensor * y = ggml_new_tensor(ctx, x->type, nd, x->ne);
    struct { ggml_custom_op_t fun; int n_tasks; void * userdata; } p = { rope_cb, 1, nullptr };
    GGML_ASSERT(sizeof(p) <= GGML_MAX_OP_PARAMS);
    memcpy(y->op_params, &p, sizeof(p));
    y->op     = GGML_OP_CUSTOM;
    y->src[0] = x;
    y->src[1] = pos;
    return y;
}

}  // namespace tlrope


void llama_model_qwen3::load_arch_hparams(llama_model_loader & ml) {
    ml.get_key(LLM_KV_ATTENTION_LAYERNORM_RMS_EPS, hparams.f_norm_rms_eps);
    switch (hparams.n_layer) {
        case 28: type = hparams.n_embd == 1024 ? LLM_TYPE_0_6B : LLM_TYPE_1_7B; break;
        case 36: type = hparams.n_embd == 2560 ? LLM_TYPE_4B : LLM_TYPE_8B; break;
        case 40: type = LLM_TYPE_14B; break;
        case 64: type = LLM_TYPE_32B; break;
        default: type = LLM_TYPE_UNKNOWN;
    }
}

void llama_model_qwen3::load_arch_tensors(llama_model_loader &) {
    LLAMA_LOAD_LOCALS;

    tok_embd = create_tensor(tn(LLM_TENSOR_TOKEN_EMBD, "weight"), {n_embd, n_vocab}, 0);

    // output
    output_norm = create_tensor(tn(LLM_TENSOR_OUTPUT_NORM, "weight"), {n_embd}, 0);
    output      = create_tensor(tn(LLM_TENSOR_OUTPUT,      "weight"), {n_embd, n_vocab}, TENSOR_NOT_REQUIRED);
    // if output is NULL, init from the input tok embed
    if (output == NULL) {
        output = create_tensor(tn(LLM_TENSOR_TOKEN_EMBD, "weight"), {n_embd, n_vocab}, TENSOR_DUPLICATED);
    }

    // output rerank head
    cls_out = create_tensor(tn(LLM_TENSOR_CLS_OUT, "weight"), {n_embd, hparams.n_cls_out}, TENSOR_NOT_REQUIRED);

    for (int i = 0; i < n_layer; ++i) {
        auto & layer = layers[i];

        layer.attn_norm = create_tensor(tn(LLM_TENSOR_ATTN_NORM, "weight", i), {n_embd}, 0);

        create_tensor_qkv(layer, i, n_embd, n_embd_head_k * n_head, n_embd_gqa, n_embd_gqa, 0);
        layer.wo = create_tensor(tn(LLM_TENSOR_ATTN_OUT, "weight", i), {n_embd_head_k * n_head, n_embd}, 0);

        layer.attn_k_norm = create_tensor(tn(LLM_TENSOR_ATTN_K_NORM, "weight", i), {n_embd_head_k}, 0);
        layer.attn_q_norm = create_tensor(tn(LLM_TENSOR_ATTN_Q_NORM, "weight", i), {n_embd_head_k}, 0);

        layer.ffn_norm = create_tensor(tn(LLM_TENSOR_FFN_NORM, "weight", i), {n_embd}, 0);
        layer.ffn_gate = create_tensor(tn(LLM_TENSOR_FFN_GATE, "weight", i), {n_embd,   n_ff}, 0);
        layer.ffn_down = create_tensor(tn(LLM_TENSOR_FFN_DOWN, "weight", i), {  n_ff, n_embd}, 0);
        layer.ffn_up   = create_tensor(tn(LLM_TENSOR_FFN_UP,   "weight", i), {n_embd,   n_ff}, 0);
    }
}

std::unique_ptr<llm_graph_context> llama_model_qwen3::build_arch_graph(const llm_graph_params & params) const {
    return std::make_unique<graph>(*this, params);
}

llama_model_qwen3::graph::graph(const llama_model & model, const llm_graph_params & params) : llm_graph_context(params) {
    const int64_t n_embd_head = hparams.n_embd_head_v();

    GGML_ASSERT(n_embd_head == hparams.n_embd_head_k());
    GGML_ASSERT(n_embd_head == n_rot);

    ggml_tensor * cur;
    ggml_tensor * inpL;

    inpL = build_inp_embd(model.tok_embd);

    // inp_pos - contains the positions
    ggml_tensor * inp_pos = build_inp_pos();

    auto * inp_attn = build_attn_inp_kv();

    ggml_tensor * inp_out_ids = build_inp_out_ids();

    for (int il = 0; il < n_layer; ++il) {
        ggml_tensor * inpSA = inpL;

        // norm
        cur = build_norm(inpL,
                model.layers[il].attn_norm, NULL,
                LLM_NORM_RMS, il);
        cb(cur, "attn_norm", il);

        // self-attention
        {
            // compute Q and K and RoPE them
            auto [Qcur, Kcur, Vcur] = build_qkv(model.layers[il], cur,
                    n_embd_head, n_head, n_head_kv, il);

            Qcur = build_norm(Qcur, model.layers[il].attn_q_norm, NULL, LLM_NORM_RMS, il);
            cb(Qcur, "Qcur_normed", il);

            if (ggml_tensor * qr = tlrope::try_rope(ctx0, Qcur, inp_pos, n_head, freq_base)) {
                Qcur = qr;
            } else {
                Qcur = ggml_rope_ext(
                        ctx0, Qcur, inp_pos, nullptr,
                        n_rot, rope_type, n_ctx_orig, freq_base, freq_scale,
                        ext_factor, attn_factor, beta_fast, beta_slow
                        );
            }

            Kcur = build_norm(Kcur, model.layers[il].attn_k_norm, NULL, LLM_NORM_RMS, il);
            cb(Kcur, "Kcur_normed", il);

            if (ggml_tensor * kr = tlrope::try_rope(ctx0, Kcur, inp_pos, n_head_kv, freq_base)) {
                Kcur = kr;
            } else {
                Kcur = ggml_rope_ext(
                        ctx0, Kcur, inp_pos, nullptr,
                        n_rot, rope_type, n_ctx_orig, freq_base, freq_scale,
                        ext_factor, attn_factor, beta_fast, beta_slow
                        );
            }

            cb(Qcur, "Qcur", il);
            cb(Kcur, "Kcur", il);
            cb(Vcur, "Vcur", il);

            cur = build_attn(inp_attn,
                    model.layers[il].wo, model.layers[il].wo_b, model.layers[il].wo_s,
                    Qcur, Kcur, Vcur, nullptr, nullptr, nullptr, 1.0f/sqrtf(float(n_embd_head)), il);
        }
        if (il == n_layer - 1 && inp_out_ids) {
            cur   = ggml_get_rows(ctx0,   cur, inp_out_ids);
            inpSA = ggml_get_rows(ctx0, inpSA, inp_out_ids);
        }
        ggml_tensor * ffn_inp = ggml_add(ctx0, cur, inpSA);
        cb(ffn_inp, "ffn_inp", il);

        // feed-forward network
        cur = build_norm(ffn_inp,
                model.layers[il].ffn_norm, NULL,
                LLM_NORM_RMS, il);
        cb(cur, "ffn_norm", il);

        cur = build_ffn(cur,
                model.layers[il].ffn_up,   NULL, model.layers[il].ffn_up_s,
                model.layers[il].ffn_gate, NULL, model.layers[il].ffn_gate_s,
                model.layers[il].ffn_down, NULL, model.layers[il].ffn_down_s,
                NULL,
                LLM_FFN_SILU, LLM_FFN_PAR, il);
        cb(cur, "ffn_out", il);

        cur = ggml_add(ctx0, cur, ffn_inp);

        cur = build_cvec(cur, il);
        cb(cur, "l_out", il);

        // input for next layer
        inpL = cur;
    }
    cur = inpL;

    cur = build_norm(cur,
            model.output_norm, NULL,
            LLM_NORM_RMS, -1);

    cb(cur, "result_norm", -1);
    res->t_embd = cur;

    // lm_head
    cur = build_lora_mm(model.output, cur, model.output_s);

    cb(cur, "result_output", -1);
    res->t_logits = cur;

    ggml_build_forward_expand(gf, cur);
}
