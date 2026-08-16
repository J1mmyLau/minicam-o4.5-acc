// TileLang conv1d 桥接: dlopen AOT .so 注册表 + ggml CUSTOM 回调
// env: OMNI_TL_CONV=1 启用; OMNI_TL_CONV_DIR=.so 目录; OMNI_TL_CONV_LOG=1 打印形状
#include "tl_conv_bridge.h"
#include "ggml-alloc.h"

#include <dlfcn.h>
#include <cstdio>
#include <cstring>
#include <string>
#include <unordered_map>
#include <mutex>
#include <vector>
#include <cstdlib>
#include <cmath>
extern "C" int aclrtMemcpy(void *, size_t, void *, size_t, int);
extern "C" int aclrtMalloc(void **, size_t, int);
extern "C" int aclrtSynchronizeStream(void *);

extern "C" void * ggml_cann_custom_current_stream();  // ggml-cann.cpp 提供

static inline float __fp16h_to_f(short h) {
    unsigned u = (unsigned)(h & 0x8000) << 16;
    unsigned e = ((h >> 10) & 0x1f), m = (h & 0x3ff);
    if (e == 0) return (m / 1024.0f) * (1.0f / 16384.0f) * (u ? -1 : 1);
    u |= (e - 15 + 127) << 23 | m << 13;
    float f; memcpy(&f, &u, 4); return u & 0x80000000 ? -f : f;
}

namespace tlconv {

struct Entry {
    void *     handle = nullptr;
    tl_call_fn call = nullptr;
};

static std::unordered_map<uint64_t, Entry> g_registry;
static std::mutex                          g_mutex;
static bool                                g_inited = false;
static bool                                g_enabled = false;
static bool                                g_log = false;

// key: (Cin<<52)|(Cout<<36)|(K<<28)|(dil<<24)|T
static uint64_t make_key(int64_t cin, int64_t cout, int64_t k, int64_t dil, int64_t t) {
    return (uint64_t(cin) << 52) | (uint64_t(cout) << 36) | (uint64_t(k) << 28) |
           (uint64_t(dil) << 24) | uint64_t(t);
}

static void init() {
    const char * en = getenv("OMNI_TL_CONV");
    g_enabled = en && std::string(en) == "1";
    const char * lg = getenv("OMNI_TL_CONV_LOG");
    g_log = lg && std::string(lg) == "1";
    g_inited = true;
}

static tl_call_fn lookup_or_load(int64_t cin, int64_t cout, int64_t k, int64_t dil, int64_t t);

bool maybe_log(int64_t cin, int64_t cout, int64_t k, int64_t dil, int64_t t) {
    if (!g_inited) init();
    if (g_log) {
        std::fprintf(stderr, "[TL_CONV] shape Cin=%lld Cout=%lld K=%lld D=%lld T=%lld\n",
                     (long long) cin, (long long) cout, (long long) k,
                     (long long) dil, (long long) t);
    }
    if (!g_enabled) return false;
    // 构图期直接尝试 dlopen（含负缓存），回调期同 key 直接命中
    return lookup_or_load(cin, cout, k, dil, t) != nullptr;
}

// .so 命名: tlconv_C{cin}_O{cout}_K{k}_D{dil}_T{t}.so，暴露 void call(x, w, y, stream)
static tl_call_fn lookup_or_load(int64_t cin, int64_t cout, int64_t k, int64_t dil, int64_t t) {
    uint64_t key = make_key(cin, cout, k, dil, t);
    std::lock_guard<std::mutex> lk(g_mutex);
    auto it = g_registry.find(key);
    if (it != g_registry.end()) return it->second.call;

    const char * dir = getenv("OMNI_TL_CONV_DIR");
    std::string d = dir ? dir : "tilelang-aot";  // 相对 cwd=仓库根; 可用 OMNI_TL_CONV_DIR 覆盖
    char name[300];
    std::snprintf(name, sizeof(name), "%s/tlconv_C%lld_O%lld_K%lld_D%lld_T%lld.so",
                  d.c_str(), (long long) cin, (long long) cout, (long long) k,
                  (long long) dil, (long long) t);
    void * h = dlopen(name, RTLD_NOW);
    if (!h) {
        g_registry[key] = {nullptr, nullptr};  // 负缓存
        return nullptr;
    }
    auto fn = (tl_call_fn) dlsym(h, "call");
    if (!fn) {
        dlclose(h);
        g_registry[key] = {nullptr, nullptr};
        return nullptr;
    }
    g_registry[key] = {h, fn};
    std::fprintf(stderr, "[TL_CONV] loaded %s\n", name);
    return fn;
}

static ggml_tensor * g_pc_y32 = nullptr;  // try_conv1d 每次构图刷新
static int           g_pc_hits = 0;


void track_y32(ggml_tensor * y32) { g_pc_y32 = y32; }

void verify_after_compute() {
    if (!g_pc_y32) return;
    // y32 = CUSTOM 输出经 cast 的 F32 [T, Cout, 1]——记录首尾 16 个 float
    const size_t n = ggml_nelements(g_pc_y32);
    static std::vector<float> gold;
    static size_t gold_n = 0;
    if (g_pc_hits == 1) {  // 第一次 verify 时存金标（compute 刚完成）
        gold.resize(n);
        aclrtMemcpy(gold.data(), n * 4, g_pc_y32->data, n * 4, 2);
        gold_n = n;
        std::fprintf(stderr, "[TL_CONV][POSTCHECK] gold saved n=%zu mean=%.4f\n",
                     gold_n, gold.empty() ? 0.f : gold[0]);
    } else if (g_pc_hits == 2 && gold_n == n) {
        std::vector<float> now(n);
        aclrtMemcpy(now.data(), n * 4, g_pc_y32->data, n * 4, 2);
        double d = 0;
        for (size_t i = 0; i < n; i++) d += std::fabs(now[i] - gold[i]);
        std::fprintf(stderr, "[TL_CONV][POSTCHECK] recheck n=%zu mean_abs_diff=%.6f %s\n",
                     n, d / n, d / n > 1e-3 ? "*** Y32 CHANGED BETWEEN WINDOWS ***" : "y32 stable");
    }
    g_pc_y32 = nullptr;
}

// w 重排缓存: 从 w16 沿 src 链回溯到 F32 根权重(模型权重, 地址稳定, 无流依赖),
// host 一次完成 F32读取 -> K连→Cout连重排 -> F16转换 -> 上传, 按根指针+签名缓存
struct WRewrite {
    void * src_root; void * dst; int64_t k, cin, cout;
    std::vector<unsigned short> sig;   // F32 根的头/中/尾采样(bit 级)
};
static std::vector<WRewrite> g_wcache;

static inline unsigned short f32_to_f16_bits(float f) {
    unsigned x; memcpy(&x, &f, 4);
    unsigned sign = (x >> 16) & 0x8000;
    int exp = (int)((x >> 23) & 0xff) - 127 + 15;
    unsigned man = x & 0x7fffff;
    if (((x >> 23) & 0xff) == 0xff) return sign | 0x7c00 | (man ? 1 : 0);  // inf/nan
    if (((x >> 23) & 0xff) == 0) {                                          // denorm->0
        if (man < 0x2000) return sign;                                      // 太小截 0
        // 粗略 denorm 处理: 转规格化
        int e = -1; unsigned m = man;
        while (!(m & 0x800000)) { m <<= 1; e--; }
        exp = 15 - 127 + (127 - 127) + e + 1 - 1;  // 简化路径(权重无 denorm)
        return sign;
    }
    if (exp >= 0x1f) return sign | 0x7c00;                                  // overflow->inf
    if (exp <= 0) {                                                         // subnormal
        unsigned short r = sign;
        if (exp >= -10) { man |= 0x800000; unsigned sh = (unsigned)(14 - exp);
            r |= (unsigned short)((man >> sh) & 0x3ff);
            unsigned rem = man & ((1u << sh) - 1), half = 1u << (sh - 1);
            if (rem > half || (rem == half && (r & 1))) r++; }
        return r;
    }
    unsigned short r = sign | ((unsigned short)exp << 10) | (unsigned short)(man >> 13);
    unsigned rem = man & 0x1fff, half = 0x1000;                             // RN
    if (rem > half || (rem == half && (r & 1))) r++;
    return r;
}

static void take_sig_f32(const void * dev, size_t n, std::vector<unsigned short> & sig) {
    sig.clear();
    size_t idx[4] = {0, n / 3, n / 2, n - 8};
    float buf[8];
    sig.reserve(32);
    for (size_t i = 0; i < 4; i++) {
        size_t off = idx[i], cnt = (off + 8 <= n) ? 8 : (n > off ? n - off : 0);
        if (!cnt) continue;
        aclrtMemcpy(buf, cnt * 4, (char *)dev + off * 4, cnt * 4, 2);
        for (size_t j = 0; j < cnt; j++) {
            unsigned b; memcpy(&b, &buf[j], 4);
            sig.push_back((unsigned short)(b & 0xffff));
            sig.push_back((unsigned short)(b >> 16));
        }
    }
}

static void * rewrite_w(const ggml_tensor * w16, int64_t K, int64_t Cin, int64_t Cout) {
    // 沿 src[0] 回溯到 F32 根权重 (cast <- cont <- permute <- F32 w)
    const ggml_tensor * root = w16;
    while (root->src[0]) root = root->src[0];
    const void * src = root->data;               // F32, 稳定
    const size_t n = (size_t)K * Cin * Cout;

    std::vector<unsigned short> sig;
    take_sig_f32(src, n, sig);

    for (auto & e : g_wcache)
        if (e.src_root == (void *)src && e.k == K && e.cin == Cin && e.cout == Cout &&
            e.sig == sig)
            return e.dst;                         // 命中(权重静态, 每层一次)

    std::vector<float> h(n);
    aclrtMemcpy(h.data(), n * 4, (void *)src, n * 4, 2);
    // 数据实际 [Cout][Cin][K](K连, 官方 PyTorch 序) -> kernel 序 [K][Cin][Cout](Cout连)
    std::vector<unsigned short> out(n);
    for (int64_t c = 0; c < Cout; c++)
        for (int64_t ci = 0; ci < Cin; ci++)
            for (int64_t k = 0; k < K; k++)
                out[(size_t)(k * Cin + ci) * Cout + c] = f32_to_f16_bits(h[(size_t)(c * Cin + ci) * K + k]);

    void * dev = nullptr;
    aclrtMalloc(&dev, n * 2, 0);
    aclrtMemcpy(dev, n * 2, out.data(), n * 2, 1);
    g_wcache.push_back({(void *)src, dev, K, Cin, Cout, sig});
    std::fprintf(stderr, "[TL_CONV] w-rewrite(root-f32) K=%lld C=%lld->%lld\n",
                 (long long)K, (long long)Cin, (long long)Cout);
    return dev;
}

void conv1d_cb(ggml_tensor * dst, int /*ith*/, int /*nth*/, void * /*userdata*/) {
    static int exec_count = 0;
    if (exec_count++ < 3) std::fprintf(stderr, "[TL_CONV] CB EXECUTED #%d dst=%p op=%d\n", exec_count, (void*)dst, (int)dst->op);
    // dst = CUSTOM(x_f16, w_f16): x [TP, Cin] T-fast, w [K, Cin, Cout], y [T, Cout] T-fast
    const ggml_tensor * x = dst->src[0];
    const ggml_tensor * w = dst->src[1];
    const int64_t TP   = x->ne[0];
    const int64_t Cin  = x->ne[1];
    const int64_t K    = w->ne[0];
    const int64_t Cout = w->ne[2];
    const int64_t T    = dst->ne[0];
    const int64_t dil  = (K > 1) ? ((TP - T) / (K - 1)) : 1;  // 由 pad 反推

    tl_call_fn fn = lookup_or_load(Cin, Cout, K, dil, T);
    if (!fn) {
        std::fprintf(stderr, "[TL_CONV] MISS Cin=%lld Cout=%lld K=%lld D=%lld T=%lld\n",
                     (long long) Cin, (long long) Cout, (long long) K,
                     (long long) dil, (long long) T);
        return;
    }
    void * stream = ggml_cann_custom_current_stream();
    void * w_dev = rewrite_w(w, K, Cin, Cout);
    fn(x->data, w_dev, dst->data, stream);
    if (exec_count == 1) {
        aclrtSynchronizeStream(stream);
        auto rd = [&](void * p, int n) {
            std::vector<short> buf(n);
            aclrtMemcpy(buf.data(), n * 2, p, n * 2, 2);
            std::fprintf(stderr, "[TL_CONV] dump:");
            for (int i = 0; i < n && i < 8; i++)
                std::fprintf(stderr, " %.4f", __fp16h_to_f(buf[i]));
            std::fprintf(stderr, "\n");
        };
        rd(x->data, 8); rd(w->data, 8); rd(dst->data, 8);
    }
    // 调试: OMNI_TL_CONV_DUMP=1 时 dump 首次调用的 x/w/y 全量
    static int dump_count = -1;
    if (getenv("OMNI_TL_CONV_DUMP")) {
        if (dump_count < 0) dump_count = atoi(getenv("OMNI_TL_CONV_DUMP"));
        if (dump_count-- > 0) {
            
            FILE * f = fopen("/tmp/tl_dump.bin", "ab");
            if (f) {
                uint64_t hdr[7] = {(uint64_t)TP, (uint64_t)Cin, (uint64_t)K, (uint64_t)Cout,
                                   (uint64_t)T, (uint64_t)dil, (uint64_t)dst->ne[1]};
                fwrite(hdr, 8, 7, f);
                aclrtSynchronizeStream(stream);  // 等 compute 流上 cast 等前置节点完成
                auto dumpdev = [&](void * p, size_t bytes) {
                    std::vector<char> buf(bytes);
                    aclrtMemcpy(buf.data(), bytes, p, bytes, 2 /*D2H*/);
                    fwrite(buf.data(), 1, bytes, f);
                };
                dumpdev(x->data, (size_t)TP * Cin * 2);
                dumpdev(w->data, (size_t)K * Cin * Cout * 2);
                dumpdev(dst->data, (size_t)T * Cout * 2);
                fclose(f);
            }
        }
    }
}

ggml_tensor * try_conv1d(ggml_context * ctx, ggml_tensor * w_kic_oc, ggml_tensor * x_tcb,
                         int padding, int dilation) {
    if (!ctx || !w_kic_oc || !x_tcb) return nullptr;
    if (x_tcb->type != GGML_TYPE_F32 || w_kic_oc->type != GGML_TYPE_F32) return nullptr;
    if (x_tcb->ne[2] != 1) return nullptr;  // 仅 B==1
    // 输入必须内存连续（view/permute 的 strided 张量不能直接当 [TP,Cin] 连续内存读）
    if (!ggml_is_contiguous(x_tcb) || !ggml_is_contiguous(w_kic_oc)) return nullptr;

    const int64_t K    = w_kic_oc->ne[0];
    const int64_t Cin  = w_kic_oc->ne[1];
    const int64_t Cout = w_kic_oc->ne[2];
    const int64_t T    = x_tcb->ne[0];

    if (!maybe_log(Cin, Cout, K, dilation, T)) return nullptr;

    // CANN pad 路径在大张量上输出未初始化（pad 区垃圾/NaN，实测 320/320 非零）——
    // 改用生产验证过的 zero-concat：[zeros(p) | x | zeros(p)] 沿 T 维（ne0）
    ggml_tensor * x_pad = x_tcb;
    if (padding > 0) {
        ggml_tensor * zero_scalar = ggml_arange(ctx, 0.0f, 1.0f, 1.0f);
        ggml_tensor * l4 = ggml_repeat_4d(ctx, zero_scalar, padding, Cin, 1, 1);
        ggml_tensor * l3 = ggml_cont(ctx, ggml_reshape_3d(ctx, l4, padding, Cin, 1));
        ggml_tensor * r4 = ggml_repeat_4d(ctx, zero_scalar, padding, Cin, 1, 1);
        ggml_tensor * r3 = ggml_cont(ctx, ggml_reshape_3d(ctx, r4, padding, Cin, 1));
        x_pad = ggml_cont(ctx, ggml_concat(ctx, ggml_concat(ctx, l3, x_tcb, 0), r3, 0));
    }
    ggml_tensor * x16   = ggml_cast(ctx, x_pad, GGML_TYPE_F16);
    ggml_tensor * w16   = ggml_cast(ctx, w_kic_oc, GGML_TYPE_F16);

    ggml_tensor * y16 = ggml_new_tensor_2d(ctx, GGML_TYPE_F16, T, Cout);
    // 与 ggml_custom_op_params 同布局（ggml-cann.cpp 侧按其读取）
    struct { ggml_custom_op_t fun; int n_tasks; void * userdata; } p = { conv1d_cb, 1, nullptr };
    GGML_ASSERT(sizeof(p) <= GGML_MAX_OP_PARAMS);
    memcpy(y16->op_params, &p, sizeof(p));
    y16->op     = GGML_OP_CUSTOM;
    y16->src[0] = x16;
    y16->src[1] = w16;

    if (getenv("OMNI_TL_CONV_RAW")) return y16;   // 调试: 直接暴露 kernel 输出
    ggml_tensor * y32 = ggml_cast(ctx, y16, GGML_TYPE_F32);
    y32 = ggml_cont(ctx, ggml_reshape_3d(ctx, y32, T, Cout, 1));
    if (getenv("OMNI_TL_CONV_PC")) { g_pc_hits++; track_y32(y32); }
    return y32;
}


// ---------------- flow LayerNorm (LN(x)*w+b) ----------------
static tl_call_fn ln_lookup(int64_t n, int64_t rows, int eps_tier);

// eps 分档: conformer 1e-6 / qk-norm+conv-block 1e-5 —— 编两套 .so, fn 按 dst 指针索引
// (构图完成后才执行, map 始终反映最新构图, galloc 地址复用天然安全)
static std::unordered_map<const void *, tl_call_fn> g_ln_fn_by_dst;

void layernorm_cb(ggml_tensor * dst, int /*ith*/, int /*nth*/, void * /*userdata*/) {
    auto it = g_ln_fn_by_dst.find(dst);
    if (it == g_ln_fn_by_dst.end() || !it->second) return;
    void * stream = ggml_cann_custom_current_stream();
    ((void (*)(void *, void *, void *, void *, void *))it->second)(
        dst->src[0]->data, dst->src[1]->data, dst->src[2]->data, dst->data, stream);
}

static tl_call_fn ln_lookup(int64_t n, int64_t rows, int eps_tier) {
    static std::unordered_map<uint64_t, tl_call_fn> cache;
    uint64_t key = (uint64_t(n) << 40) | (uint64_t(rows) << 4) | uint64_t(eps_tier);
    auto it = cache.find(key);
    if (it != cache.end()) return it->second;
    const char * dir = getenv("OMNI_TL_CONV_DIR");
    std::string d = dir ? dir : "tilelang-aot";  // 相对 cwd=仓库根; 可用 OMNI_TL_CONV_DIR 覆盖
    char name[160];
    std::snprintf(name, sizeof(name), "%s/tlnorm_N%lld_R%lld_E%d.so", d.c_str(),
                  (long long)n, (long long)rows, eps_tier);
    void * h = dlopen(name, RTLD_NOW);
    tl_call_fn fn = h ? (tl_call_fn)dlsym(h, "call") : nullptr;
    if (fn) std::fprintf(stderr, "[TL_LN] loaded %s\n", name);
    else if (getenv("OMNI_TL_LN_LOG") || getenv("OMNI_TL_CONV"))
        std::fprintf(stderr, "[TL_LN] shape N=%lld rows=%lld E%d (no .so)\n",
                     (long long)n, (long long)rows, eps_tier);
    cache[key] = fn;
    return fn;
}

ggml_tensor * try_layernorm(ggml_context * ctx, ggml_tensor * x, ggml_tensor * w,
                            ggml_tensor * b, float eps) {
    if (!ctx || !x || !w) return nullptr;
    if (x->type != GGML_TYPE_F32 || w->type != GGML_TYPE_F32) return nullptr;
    if (!b || b->type != GGML_TYPE_F32) return nullptr;
    if (!ggml_is_contiguous(x)) return nullptr;
    (void) eps;  // AOT 时编译进 kernel (1e-5 固定，flow/ue 两处相同)

    const int64_t N = x->ne[0];
    const int64_t rows = ggml_nelements(x) / N;
    const int tier = (eps < 5e-6f) ? 6 : 5;   // 1e-6 -> E6, 1e-5 -> E5
    tl_call_fn fn = ln_lookup(N, rows, tier);
    if (!fn) return nullptr;

    // F32 直传（零 cast 真融合）
    ggml_tensor * x16 = x;
    ggml_tensor * w16 = w;
    ggml_tensor * b16 = b;
    int y16_nd = (x->ne[3] > 1) ? 4 : (x->ne[2] > 1) ? 3 : (x->ne[1] > 1) ? 2 : 1;
    ggml_tensor * y16 = ggml_new_tensor(ctx, GGML_TYPE_F32, y16_nd, x->ne);
    struct { ggml_custom_op_t fun; int n_tasks; void * userdata; } p = { layernorm_cb, 1, nullptr };
    GGML_ASSERT(sizeof(p) <= GGML_MAX_OP_PARAMS);
    memcpy(y16->op_params, &p, sizeof(p));
    y16->op = GGML_OP_CUSTOM;
    y16->src[0] = x16;
    y16->src[1] = w16;
    y16->src[2] = b16;
    g_ln_fn_by_dst[y16] = fn;
    return y16;
}

}  // namespace tlconv
