#include "models.h"

// ============================================================================
// TileLang talker 桥 (TTS 热路径): OMNI_TL_TTS=1 时把 MiniCPM-o talker (llama arch,
// 20L/768/12H*64/theta=1e4) 的 41 个 rms_norm 位点 + 40 个 Q/K rope 换成
// GGML_OP_CUSTOM 节点 (tltsnorm_N768_T{t}.so / tltsrope_H12_D64_R768_T{t}.so)。
// talker 前向 ~5ms/token 全是 launch 税 (20L * ~18 op), 与主模型 QKR 融合同范式。
// 指纹: 仅当 n_embd==768 && n_head==12 生效, 避免误伤其他 llama-arch 模型。
// 数值: norm rel~1.5e-3 (与主模型 kernel 同量级), rope 位级一致 (theta=1e4 表)。
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

namespace tltts {

typedef void (*nr_fn)(void *, void *, void *, void *);            // call(x, w, y, stream)
typedef void (*rope_fn)(void *, void *, void *, void *, void *, void *);  // call(x, cs, sn, pos, y, stream)

static std::mutex g_mu;

static bool enabled() {
    static const bool e = [] { const char * s = getenv("OMNI_TL_TTS"); return s && s[0] == '1'; }();
    return e;
}

static void * (*cur_stream)() = nullptr;

static void * get_stream() {
    if (!cur_stream) cur_stream = (void * (*)()) dlsym(RTLD_DEFAULT, "ggml_cann_custom_current_stream");
    return cur_stream ? cur_stream() : nullptr;
}

// ---------------- 行级 RMSNorm N=768 ----------------
static nr_fn lookup_nr(int64_t T) {
    static std::unordered_map<int64_t, nr_fn> cache;
    std::lock_guard<std::mutex> lk(g_mu);
    auto it = cache.find(T);
    if (it != cache.end()) return it->second;
    const char * dir = getenv("OMNI_TL_ROPE_DIR");
    std::string d = dir ? dir : "tilelang-aot";
    char name[256];
    snprintf(name, sizeof(name), "%s/tltsnorm_N768_T%lld_F32.so", d.c_str(), (long long)T);
    void * h = dlopen(name, RTLD_NOW);
    nr_fn fn = h ? (nr_fn) dlsym(h, "call") : nullptr;
    static bool logged = false;
    if (fn && !logged) { fprintf(stderr, "[TL_TTS] loaded %s\n", name); logged = true; }
    cache[T] = fn;
    return fn;
}

static void norm_cb(ggml_tensor * dst, int, int, void *) {
    const ggml_tensor * x = dst->src[0];
    const ggml_tensor * w = dst->src[1];
    if (!x || !x->data || !w || !w->data || !dst->data) return;
    nr_fn fn = lookup_nr(dst->ne[1]);
    if (!fn) return;
    void * s = get_stream();
    if (!s) return;
    fn(x->data, (void *) w->data, dst->data, s);
}

// x: [768, T] F32 连续; w: [768] F32。成功返回 CUSTOM 节点, 否则 nullptr。
ggml_tensor * try_norm(ggml_context * ctx, ggml_tensor * x, ggml_tensor * w) {
    if (!enabled() || !ctx || !x || !w) return nullptr;
    if (x->type != GGML_TYPE_F32 || !ggml_is_contiguous(x)) return nullptr;
    if (x->ne[0] != 768 || x->ne[2] != 1) return nullptr;
    const int64_t T = x->ne[1];
    if (T < 1 || T > 16) return nullptr;
    if (!lookup_nr(T)) return nullptr;
    ggml_tensor * w32 = (w->type == GGML_TYPE_F32) ? w : ggml_cast(ctx, w, GGML_TYPE_F32);
    ggml_tensor * y = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, 768, T);
    struct { ggml_custom_op_t fun; int n_tasks; void * userdata; } p = { norm_cb, 1, nullptr };
    memcpy(y->op_params, &p, sizeof(p));
    y->op = GGML_OP_CUSTOM;
    y->src[0] = x;
    y->src[1] = w32;
    return y;
}

// ---------------- RoPE H=12 D=64 theta=1e4 (NEOX) ----------------
static rope_fn lookup_rope(int64_t T) {
    static std::unordered_map<int64_t, rope_fn> cache;
    std::lock_guard<std::mutex> lk(g_mu);
    auto it = cache.find(T);
    if (it != cache.end()) return it->second;
    const char * dir = getenv("OMNI_TL_ROPE_DIR");
    std::string d = dir ? dir : "tilelang-aot";
    char name[256];
    snprintf(name, sizeof(name), "%s/tltsrope_H12_D64_R768_T%lld_F32.so", d.c_str(), (long long)T);
    void * h = dlopen(name, RTLD_NOW);
    rope_fn fn = h ? (rope_fn) dlsym(h, "call") : nullptr;
    static bool logged = false;
    if (fn && !logged) { fprintf(stderr, "[TL_TTS] loaded %s\n", name); logged = true; }
    cache[T] = fn;
    return fn;
}

static void * g_cs = nullptr, * g_sn = nullptr;

static void ensure_tables(float theta) {
    static double cached = -1.0;
    if (g_cs && cached == (double) theta) return;
    const int rows = 4096 + 8, half = 32;
    std::vector<float> cs(rows * half), sn(rows * half);
    for (int i = 0; i < half; i++) {
        float freq = powf(theta, -2.0f * (float) i / 64.0f);
        for (int p = 0; p < rows; p++) {
            float ang = (float) p * freq;
            cs[(size_t) p * half + i] = cosf(ang);
            sn[(size_t) p * half + i] = sinf(ang);
        }
    }
    size_t bytes = (size_t) rows * half * 4;
    aclrtMalloc(&g_cs, bytes, 0);
    aclrtMalloc(&g_sn, bytes, 0);
    aclrtMemcpy(g_cs, bytes, cs.data(), bytes, 1);
    aclrtMemcpy(g_sn, bytes, sn.data(), bytes, 1);
    cached = (double) theta;
    fprintf(stderr, "[TL_TTS] cos/sin table %dx%d theta=%.1f uploaded\n", rows, half, theta);
}

static void rope_cb(ggml_tensor * dst, int, int, void *) {
    const ggml_tensor * x   = dst->src[0];
    const ggml_tensor * pos = dst->src[1];
    if (!x || !x->data || !pos || !pos->data || !dst->data) return;
    rope_fn fn = lookup_rope(dst->ne[1]);
    if (!fn || !g_cs) return;
    void * s = get_stream();
    if (!s) return;
    fn(x->data, g_cs, g_sn, pos->data, dst->data, s);
}

// x: Q/K 投影输出 [768, T] F32 连续; pos: I32 [T]。指纹 D==64&&H==12。
ggml_tensor * try_rope(ggml_context * ctx, ggml_tensor * x, ggml_tensor * pos,
                       int64_t n_head, float theta) {
    static const bool dbg = getenv("OMNI_TL_TTS_LOG") != nullptr;
    if (dbg) fprintf(stderr, "[TL_TTS][rope-dbg] ne=[%lld,%lld,%lld] type=%d cont=%d H=%lld\n",
                     (long long)x->ne[0], (long long)x->ne[1], (long long)x->ne[2],
                     (int)x->type, (int)ggml_is_contiguous(x), (long long)n_head);
    if (!enabled() || !ctx || !x || !pos) return nullptr;
    if (x->ne[3] != 1 || !ggml_is_contiguous(x)) return nullptr;
    if (x->type != GGML_TYPE_F32) return nullptr;
    if (n_head != 12) return nullptr;                      // talker 指纹
    // 两种形态 (内存布局等价: 元素 t*768 + h*64 + d):
    //   3-D [64, 12, T] (build_qkv 输出 view)  或  2-D [768, T]
    int64_t T; int nd;
    if (x->ne[0] == 64 && x->ne[1] == 12)      { T = x->ne[2]; nd = 3; }
    else if (x->ne[0] == 768 && x->ne[2] == 1) { T = x->ne[1]; nd = 2; }
    else return nullptr;
    if (T < 1 || T > 16) return nullptr;
    if (!lookup_rope(T)) return nullptr;
    ensure_tables(theta);
    if (!g_cs) return nullptr;
    ggml_tensor * y = ggml_new_tensor(ctx, x->type, nd, x->ne);
    struct { ggml_custom_op_t fun; int n_tasks; void * userdata; } p = { rope_cb, 1, nullptr };
    memcpy(y->op_params, &p, sizeof(p));
    y->op = GGML_OP_CUSTOM;
    y->src[0] = x;
    y->src[1] = pos;
    return y;
}

}  // namespace tltts

void llama_model_llama::load_arch_hparams(llama_model_loader & ml) {
    uint32_t n_vocab = 0;
    ml.get_key(LLM_KV_VOCAB_SIZE, n_vocab, false) || ml.get_arr_n(LLM_KV_TOKENIZER_LIST, n_vocab, false);

    ml.get_key(LLM_KV_ATTENTION_LAYERNORM_RMS_EPS, hparams.f_norm_rms_eps);

    if (hparams.n_expert == 8) {
        switch (hparams.n_layer) {
            case 32: type = LLM_TYPE_8x7B; break;
            case 56: type = LLM_TYPE_8x22B; break;
            default: type = LLM_TYPE_UNKNOWN;
        }
    } else {
        switch (hparams.n_layer) {
            case 16: type = LLM_TYPE_1B; break; // Llama 3.2 1B
            case 22: type = LLM_TYPE_1B; break;
            case 26: type = LLM_TYPE_3B; break;
            case 28: type = LLM_TYPE_3B; break; // Llama 3.2 3B
            case 30: type = LLM_TYPE_256M; break; // smoldocling 256M
            // granite uses a vocab with len 49152
            case 32: type = n_vocab == 49152 ? LLM_TYPE_3B : (n_vocab < 40000 ? LLM_TYPE_7B : LLM_TYPE_8B); break;
            case 36: type = LLM_TYPE_8B; break; // granite
            case 40: type = LLM_TYPE_13B; break;
            case 48: type = LLM_TYPE_34B; break;
            case 60: type = LLM_TYPE_30B; break;
            case 80: type = hparams.n_head() == hparams.n_head_kv() ? LLM_TYPE_65B : LLM_TYPE_70B; break;
            default: type = LLM_TYPE_UNKNOWN;
        }
    }
}

void llama_model_llama::load_arch_tensors(llama_model_loader &) {
    LLAMA_LOAD_LOCALS;

    tok_embd = create_tensor(tn(LLM_TENSOR_TOKEN_EMBD, "weight"), {n_embd, n_vocab}, 0);

    // output
    output_norm = create_tensor(tn(LLM_TENSOR_OUTPUT_NORM, "weight"), {n_embd}, 0);
    output      = create_tensor(tn(LLM_TENSOR_OUTPUT,      "weight"), {n_embd, n_vocab}, TENSOR_NOT_REQUIRED);

    // if output is NULL, init from the input tok embed
    if (output == NULL) {
        output = create_tensor(tn(LLM_TENSOR_TOKEN_EMBD, "weight"), {n_embd, n_vocab}, TENSOR_DUPLICATED);
    }

    for (int i = 0; i < n_layer; ++i) {
        auto & layer = layers[i];

        layer.attn_norm = create_tensor(tn(LLM_TENSOR_ATTN_NORM, "weight", i), {n_embd}, 0);

        create_tensor_qkv(layer, i, n_embd, n_embd_head_k * n_head, n_embd_k_gqa, n_embd_v_gqa, 0);
        layer.wo = create_tensor(tn(LLM_TENSOR_ATTN_OUT, "weight", i), {n_embd_head_k * n_head, n_embd}, 0);

        // optional bias tensors
        layer.wo_b = create_tensor(tn(LLM_TENSOR_ATTN_OUT, "bias", i), {n_embd}, TENSOR_NOT_REQUIRED);

        layer.ffn_norm = create_tensor(tn(LLM_TENSOR_FFN_NORM, "weight", i), {n_embd}, 0);

        if (hparams.rope_scaling_type_train == LLAMA_ROPE_SCALING_TYPE_LONGROPE) {
            layer.rope_long  = create_tensor(tn(LLM_TENSOR_ROPE_FACTORS_LONG,  "weight", i), {n_rot/2}, TENSOR_NOT_REQUIRED | (i != 0 ? TENSOR_DUPLICATED : 0));
            layer.rope_short = create_tensor(tn(LLM_TENSOR_ROPE_FACTORS_SHORT, "weight", i), {n_rot/2}, TENSOR_NOT_REQUIRED | (i != 0 ? TENSOR_DUPLICATED : 0));
        }
        else {
            layer.rope_freqs = create_tensor(tn(LLM_TENSOR_ROPE_FREQS, "weight", i), {n_rot/2}, TENSOR_NOT_REQUIRED | (i != 0 ? TENSOR_DUPLICATED : 0));
        }

        if (n_expert == 0) {
            layer.ffn_gate = create_tensor(tn(LLM_TENSOR_FFN_GATE, "weight", i), {n_embd,   n_ff}, 0);
            layer.ffn_down = create_tensor(tn(LLM_TENSOR_FFN_DOWN, "weight", i), {  n_ff, n_embd}, 0);
            layer.ffn_up   = create_tensor(tn(LLM_TENSOR_FFN_UP,   "weight", i), {n_embd,   n_ff}, 0);

            // optional MLP bias
            layer.ffn_gate_b = create_tensor(tn(LLM_TENSOR_FFN_GATE, "bias", i), {n_ff}, TENSOR_NOT_REQUIRED);
            layer.ffn_down_b = create_tensor(tn(LLM_TENSOR_FFN_DOWN, "bias", i), {n_embd}, TENSOR_NOT_REQUIRED);
            layer.ffn_up_b   = create_tensor(tn(LLM_TENSOR_FFN_UP,   "bias", i), {n_ff}, TENSOR_NOT_REQUIRED);
        } else {
            layer.ffn_gate_inp  = create_tensor(tn(LLM_TENSOR_FFN_GATE_INP,  "weight", i), {n_embd, n_expert}, 0);
            layer.ffn_gate_exps = create_tensor(tn(LLM_TENSOR_FFN_GATE_EXPS, "weight", i), {n_embd,   n_ff, n_expert}, TENSOR_NOT_REQUIRED);
            layer.ffn_down_exps = create_tensor(tn(LLM_TENSOR_FFN_DOWN_EXPS, "weight", i), {  n_ff, n_embd, n_expert}, 0);
            layer.ffn_up_exps   = create_tensor(tn(LLM_TENSOR_FFN_UP_EXPS,   "weight", i), {n_embd,   n_ff, n_expert}, 0);

            // For Granite MoE Shared
            if (hparams.n_ff_shexp > 0) {
                layer.ffn_gate_shexp = create_tensor(tn(LLM_TENSOR_FFN_GATE_SHEXP, "weight", i), {n_embd, hparams.n_ff_shexp}, 0);
                layer.ffn_up_shexp   = create_tensor(tn(LLM_TENSOR_FFN_UP_SHEXP,   "weight", i), {n_embd, hparams.n_ff_shexp}, 0);
                layer.ffn_down_shexp = create_tensor(tn(LLM_TENSOR_FFN_DOWN_SHEXP, "weight", i), {hparams.n_ff_shexp, n_embd}, 0);
            }
        }
    }
}

std::unique_ptr<llm_graph_context> llama_model_llama::build_arch_graph(const llm_graph_params & params) const {
    return std::make_unique<graph<false>>(*this, params);
}

template <bool embed>
llama_model_llama::graph<embed>::graph(const llama_model & model, const llm_graph_params & params) : llm_graph_context(params) {
    const int64_t n_embd_head = hparams.n_embd_head_v();

    GGML_ASSERT(n_embd_head == hparams.n_embd_head_k());
    GGML_ASSERT(n_embd_head == n_rot);

    ggml_tensor * cur;
    ggml_tensor * inpL;

    inpL = build_inp_embd(model.tok_embd);

    // inp_pos - contains the positions
    ggml_tensor * inp_pos = build_inp_pos();

    using inp_attn_type = std::conditional_t<embed, llm_graph_input_attn_no_cache, llm_graph_input_attn_kv>;

    inp_attn_type * inp_attn = nullptr;
    if constexpr (embed) {
        inp_attn = build_attn_inp_no_cache();
    } else {
        inp_attn = build_attn_inp_kv();
    }

    const float kq_scale = hparams.f_attention_scale == 0.0f ? 1.0f/sqrtf(float(n_embd_head)) : hparams.f_attention_scale;

    ggml_tensor * inp_out_ids = build_inp_out_ids();

    for (int il = 0; il < n_layer; ++il) {
        ggml_tensor * inpSA = inpL;

        // norm
        ggml_tensor * fused_norm = tltts::try_norm(ctx0, inpL, model.layers[il].attn_norm);
        if (fused_norm) {
            cur = fused_norm;
        } else {
            cur = build_norm(inpL,
                    model.layers[il].attn_norm, NULL,
                    LLM_NORM_RMS, il);
        }
        cb(cur, "attn_norm", il);

        // self-attention
        {
            // rope freq factors for llama3; may return nullptr for llama2 and other models
            ggml_tensor * rope_factors = model.get_rope_factors(cparams, il);

            // compute Q and K and RoPE them
            auto [Qcur, Kcur, Vcur] = build_qkv(model.layers[il], cur,
                    n_embd_head, n_head, n_head_kv, il);

            // TileLang 融合 rope (互斥: 命中则不再走 ggml_rope_ext)
            ggml_tensor * Qf = tltts::try_rope(ctx0, Qcur, inp_pos, n_head, freq_base);
            ggml_tensor * Kf = tltts::try_rope(ctx0, Kcur, inp_pos, n_head, freq_base);
            Qcur = Qf ? Qf : ggml_rope_ext(
                    ctx0, Qcur, inp_pos, rope_factors,
                    n_rot, rope_type, n_ctx_orig, freq_base, freq_scale,
                    ext_factor, attn_factor, beta_fast, beta_slow
                    );

            Kcur = Kf ? Kf : ggml_rope_ext(
                    ctx0, Kcur, inp_pos, rope_factors,
                    n_rot, rope_type, n_ctx_orig, freq_base, freq_scale,
                    ext_factor, attn_factor, beta_fast, beta_slow
                    );

            cb(Qcur, "Qcur", il);
            cb(Kcur, "Kcur", il);
            cb(Vcur, "Vcur", il);

            if (hparams.use_kq_norm) {
                // Llama4TextL2Norm
                Qcur = ggml_rms_norm(ctx0, Qcur, hparams.f_norm_rms_eps);
                Kcur = ggml_rms_norm(ctx0, Kcur, hparams.f_norm_rms_eps);
                cb(Qcur, "Qcur_normed", il);
                cb(Kcur, "Kcur_normed", il);
            }
            cur = build_attn(inp_attn,
                    model.layers[il].wo, model.layers[il].wo_b, model.layers[il].wo_s,
                    Qcur, Kcur, Vcur, nullptr, nullptr, nullptr, kq_scale, il);
            cb(cur, "attn_out", il);
        }
        if (il == n_layer - 1 && inp_out_ids) {
            cur   = ggml_get_rows(ctx0,   cur, inp_out_ids);
            inpSA = ggml_get_rows(ctx0, inpSA, inp_out_ids);
        }
        ggml_tensor * ffn_inp = ggml_add(ctx0, cur, inpSA);
        cb(ffn_inp, "ffn_inp", il);

        // feed-forward network (non-MoE)
        if (model.layers[il].ffn_gate_inp == nullptr) {

            ggml_tensor * ffn_fused = tltts::try_norm(ctx0, ffn_inp, model.layers[il].ffn_norm);
            cur = ffn_fused ? ffn_fused : build_norm(ffn_inp,
                    model.layers[il].ffn_norm, NULL,
                    LLM_NORM_RMS, il);
            cb(cur, "ffn_norm", il);

            cur = build_ffn(cur,
                    model.layers[il].ffn_up,   model.layers[il].ffn_up_b,   model.layers[il].ffn_up_s,
                    model.layers[il].ffn_gate, model.layers[il].ffn_gate_b, model.layers[il].ffn_gate_s,
                    model.layers[il].ffn_down, model.layers[il].ffn_down_b, model.layers[il].ffn_down_s,
                    NULL,
                    LLM_FFN_SILU, LLM_FFN_PAR, il);
            cb(cur, "ffn_out", il);
        } else {
            // MoE branch
            ggml_tensor * ffn_fused = tltts::try_norm(ctx0, ffn_inp, model.layers[il].ffn_norm);
            cur = ffn_fused ? ffn_fused : build_norm(ffn_inp,
                    model.layers[il].ffn_norm, NULL,
                    LLM_NORM_RMS, il);
            cb(cur, "ffn_norm", il);

            cur = build_moe_ffn(cur,
                    model.layers[il].ffn_gate_inp,
                    model.layers[il].ffn_up_exps,
                    model.layers[il].ffn_gate_exps,
                    model.layers[il].ffn_down_exps,
                    nullptr,
                    n_expert, n_expert_used,
                    LLM_FFN_SILU, true,
                    hparams.expert_weights_scale,
                    LLAMA_EXPERT_GATING_FUNC_TYPE_SOFTMAX,
                    il,
                    nullptr, nullptr,
                    model.layers[il].ffn_up_exps_s,
                    model.layers[il].ffn_gate_exps_s,
                    model.layers[il].ffn_down_exps_s);
            cb(cur, "ffn_moe_out", il);
        }
        cur = ggml_add(ctx0, cur, ffn_inp);
        cb(cur, "ffn_out", il);

        cur = build_cvec(cur, il);
        cb(cur, "l_out", il);

        // input for next layer
        inpL = cur;
    }
    cur = inpL;

    ggml_tensor * out_fused = tltts::try_norm(ctx0, cur, model.output_norm);
    cur = out_fused ? out_fused : build_norm(cur,
            model.output_norm, NULL,
            LLM_NORM_RMS, -1);

    cb(cur, "result_norm", -1);
    res->t_embd = cur;

    if constexpr (!embed) {
        // lm_head
        cur = build_lora_mm(model.output, cur, model.output_s);

        cb(cur, "result_output", -1);
        res->t_logits = cur;
    }

    ggml_build_forward_expand(gf, cur);
}

template struct llama_model_llama::graph<false>;
template struct llama_model_llama::graph<true>;
