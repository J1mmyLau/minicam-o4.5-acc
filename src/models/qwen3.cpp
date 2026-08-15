#include "models.h"

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


// ============================================================================
// TileLang fused RoPE (OMNI_TL_ROPE=1): CUSTOM 节点替换 Q/K rope 链
// (RoPE+Cos+Sin+Mul+Cast+Tile ~400 微算子/token, launch-bound 32ms/token 主因).
// qwen3 特点: rope 前有 per-head q/k RMSNorm, 其输出连续 [D,H,T],
// token 步长 = H*D 元素 (Q:4096 / K:1024).
// ============================================================================
#include <dlfcn.h>
#include <cmath>
#include <mutex>
#include <unordered_map>
#include <vector>
#include <atomic>

extern "C" void * ggml_cann_custom_current_stream();
extern "C" int aclrtMalloc(void **, size_t, int);
extern "C" int aclrtMemcpy(void *, size_t, void *, size_t, int);

namespace tlrope {

typedef void (*rope_fn)(void * x, void * cs, void * sn, void * pos, void * y, void * stream);

static bool enabled() {
    static int e = [] { const char * v = getenv("OMNI_TL_ROPE"); return v && atoi(v); }();
    return e;
}

struct Tables { void * cs = nullptr; void * sn = nullptr; int maxp = 0; };
static Tables g_tbl;

static void init_tables(int maxp) {
    if (g_tbl.cs && g_tbl.maxp >= maxp) return;
    const int half = 64;
    std::vector<float> cs(maxp * half), sn(maxp * half);
    const double theta = 1e6;
    for (int p = 0; p < maxp; p++)
        for (int i = 0; i < half; i++) {
            double ang = p * pow(theta, -(2.0 * i) / 128.0);
            cs[p * half + i] = cos(ang);
            sn[p * half + i] = sin(ang);
        }
    void * dcs = nullptr, * dsn = nullptr;
    aclrtMalloc(&dcs, cs.size() * 4, 0);
    aclrtMalloc(&dsn, sn.size() * 4, 0);
    aclrtMemcpy(dcs, cs.size() * 4, cs.data(), cs.size() * 4, 1);
    aclrtMemcpy(dsn, sn.size() * 4, sn.data(), sn.size() * 4, 1);
    g_tbl = { dcs, dsn, maxp };
    (void) 0;
}

static std::unordered_map<uint64_t, rope_fn> g_cache;
static std::mutex g_mtx;

static rope_fn lookup(int64_t H, int64_t D, int64_t ROW, int64_t T) {
    uint64_t key = (uint64_t(H) << 48) | (uint64_t(D) << 32) | (uint64_t(ROW) << 12) | uint64_t(T);
    std::lock_guard<std::mutex> lk(g_mtx);
    auto it = g_cache.find(key);
    if (it != g_cache.end()) return it->second;
    const char * dir = getenv("OMNI_TL_ROPE_DIR");
    std::string d = dir ? dir : "/workspace/t2w-tilelang/aot";
    char name[180];
    snprintf(name, sizeof(name), "%s/tlrope_H%lld_D%lld_R%lld_T%lld_F32.so", d.c_str(),
             (long long)H, (long long)D, (long long)ROW, (long long)T);
    void * h = dlopen(name, RTLD_NOW);
    rope_fn fn = h ? (rope_fn)dlsym(h, "call") : nullptr;
    if (fn) fprintf(stderr, "[TL_ROPE] loaded %s\n", name);
    else if (enabled()) fprintf(stderr, "[TL_ROPE] MISS H=%lld ROW=%lld T=%lld\n",
                                (long long)H, (long long)ROW, (long long)T);
    g_cache[key] = fn;
    return fn;
}

struct RopeKey { int64_t h, d, row, t; };
static std::unordered_map<const void *, RopeKey> g_key_by_dst;

static std::atomic<int64_t> g_exec{0};
static std::atomic<int64_t> g_nolook{0};

static void rope_cb(ggml_tensor * dst, int, int, void *) {
    auto it = g_key_by_dst.find(dst);
    if (it == g_key_by_dst.end()) {
        int64_t n = ++g_nolook;
        if (n <= 3) fprintf(stderr, "[TL_ROPE] cb NO-KEY dst=%p\n", (void *)dst);
        return;
    }
    const RopeKey & k = it->second;
    rope_fn fn = lookup(k.h, k.d, k.row, k.t);
    if (!fn) return;
    {
        int64_t n = ++g_exec;
        if (n == 1 || n % 144 == 0)
            fprintf(stderr, "[TL_ROPE] cb exec#%lld (H=%lld T=%lld)\n",
                    (long long)n, (long long)k.h, (long long)k.t);
    }
    fn(dst->src[0]->data, g_tbl.cs, g_tbl.sn, dst->src[3]->data, dst->data,
       ggml_cann_custom_current_stream());
}

// 构图期入口: qwen3 q/k-norm 输出连续 [D,H,T] (token 步长 H*D)。
// 返回 [D,H,T] 同形张量; 未命中回退 nullptr。
static ggml_tensor * try_rope(ggml_context * ctx, ggml_tensor * x, ggml_tensor * pos,
                              int64_t n_ctx) {
    if (!enabled() || !x) return nullptr;
    static int diag = [] { const char * v = getenv("OMNI_TL_ROPE_DIAG"); return v && atoi(v); }();
    if (diag) fprintf(stderr, "[TL_ROPE][diag] type=%d ne=[%lld,%lld,%lld] nb=[%zu,%zu,%zu]\n",
                      (int)x->type, (long long)x->ne[0], (long long)x->ne[1], (long long)x->ne[2],
                      x->nb[0], x->nb[1], x->nb[2]);
    if (x->type != GGML_TYPE_F32) return nullptr;      // q/k-norm 输出 F32
    const int64_t D = x->ne[0];
    if (D != 128) return nullptr;
    if (x->nb[0] != 4 || x->nb[1] != D * 4) return nullptr;
    const int64_t T = x->ne[2];
    const int64_t H = x->ne[1];
    const int64_t row_elems = x->nb[2] / 4;
    if (row_elems != H * D) return nullptr;            // 连续 (norm 输出)
    if (!lookup(H, D, row_elems, T)) return nullptr;
    init_tables((int) n_ctx + 8);

    ggml_tensor * y = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, H * D, T);
    struct { ggml_custom_op_t fun; int n_tasks; void * userdata; } p = { rope_cb, 1, nullptr };
    GGML_ASSERT(sizeof(p) <= GGML_MAX_OP_PARAMS);
    memcpy(y->op_params, &p, sizeof(p));
    y->op = GGML_OP_CUSTOM;
    y->src[0] = x;
    y->src[3] = pos;
    g_key_by_dst[y] = { H, D, row_elems, T };
    return ggml_reshape_3d(ctx, y, D, H, T);
}

}  // namespace tlrope

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

            if (ggml_tensor * q_t = tlrope::try_rope(ctx0, Qcur, inp_pos, n_ctx)) Qcur = q_t;
            else Qcur = ggml_rope_ext(
                    ctx0, Qcur, inp_pos, nullptr,
                    n_rot, rope_type, n_ctx_orig, freq_base, freq_scale,
                    ext_factor, attn_factor, beta_fast, beta_slow
                    );

            Kcur = build_norm(Kcur, model.layers[il].attn_k_norm, NULL, LLM_NORM_RMS, il);
            cb(Kcur, "Kcur_normed", il);

            if (ggml_tensor * k_t = tlrope::try_rope(ctx0, Kcur, inp_pos, n_ctx)) Kcur = k_t;
            else Kcur = ggml_rope_ext(
                    ctx0, Kcur, inp_pos, nullptr,
                    n_rot, rope_type, n_ctx_orig, freq_base, freq_scale,
                    ext_factor, attn_factor, beta_fast, beta_slow
                    );

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
