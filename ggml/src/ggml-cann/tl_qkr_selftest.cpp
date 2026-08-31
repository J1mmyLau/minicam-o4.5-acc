// qknorm CUSTOM 单测: root[ROW,T] F32 -> CUSTOM(x,w) -> y1, 与 CPU rmsnorm*w 对照
#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include <cstdio>
#include <cstring>
#include <cmath>
#include <vector>
#include <random>
#include <string>
#include <dlfcn.h>

extern "C" void * ggml_cann_custom_current_stream();

typedef void (*qkn_fn)(void *, void *, void *, void *);
typedef void (*ggml_custom_op_t)(struct ggml_tensor *, int, int, void *);

static void qknorm_cb(ggml_tensor * dst, int, int, void *) {
    const ggml_tensor * x = dst->src[0];
    const ggml_tensor * w = dst->src[1];
    const int64_t H = dst->ne[0] / 128, T = dst->ne[1];
    static qkn_fn fn = nullptr;
    if (!fn) {
        void * h = dlopen("tilelang-aot/tlqkn_H32_R4096_T1_F32.so", RTLD_NOW);
        if (!h) { fprintf(stderr, "dlopen fail: %s\n", dlerror()); return; }
        fn = (qkn_fn) dlsym(h, "call");
    }
    fn(x->data, (void*)w->data, dst->data, ggml_cann_custom_current_stream());
}

int main() {
    ggml_backend_dev_t dev = nullptr;
    for (size_t i = 0; i < ggml_backend_dev_count(); i++) {
        auto * d = ggml_backend_dev_get(i);
        if (std::string(ggml_backend_dev_name(d)).find("CANN") != std::string::npos) { dev = d; break; }
    }
    ggml_backend_t backend = ggml_backend_dev_init(dev, nullptr);
    const int H = 32, D = 128, ROW = H * D, T = 1;
    std::mt19937 rng(7);
    std::normal_distribution<float> nd(0.f, 0.3f);
    std::vector<float> hx(ROW * T), hw16(D);
    for (auto & v : hx) v = nd(rng);
    for (auto & v : hw16) v = nd(rng) * 0.2f + 1.0f;

    ggml_init_params ip = {512u << 20, nullptr, true};
    ggml_context * ctx = ggml_init(ip);
    ggml_tensor * qkv = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, 6144, T);   // 模拟 wqkv
    ggml_tensor * x = ggml_view_2d(ctx, qkv, ROW, T, qkv->nb[1], 0);        // Q 段裁剪 view
    ggml_tensor * wh = ggml_new_tensor_1d(ctx, GGML_TYPE_F16, D);           // F16 权重
    ggml_tensor * wf = ggml_cast(ctx, wh, GGML_TYPE_F32);                   // cast 节点
    ggml_tensor * y  = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, ROW, T);
    struct { ggml_custom_op_t fun; int n_tasks; void * ud; } p = { qknorm_cb, 1, nullptr };
    memcpy(y->op_params, &p, sizeof(p));
    y->op = GGML_OP_CUSTOM;
    y->src[0] = x; y->src[1] = wf;

    ggml_cgraph * graph = ggml_new_graph(ctx);
    ggml_build_forward_expand(graph, y);
    ggml_gallocr_t ga = ggml_gallocr_new(ggml_backend_get_default_buffer_type(backend));
    ggml_gallocr_alloc_graph(ga, graph);
    std::vector<float> hq(6144 * T, 0.f);
    memcpy(hq.data(), hx.data(), hx.size() * 4);
    ggml_backend_tensor_set(qkv, hq.data(), 0, hq.size() * 4);
    std::vector<uint16_t> hw_f16(D); for (int i = 0; i < D; i++) { float f = hw16[i]; uint32_t u; memcpy(&u, &f, 4); uint16_t h = ((u >> 16) & 0x8000) | (((((u >> 23) & 0xff) - 127 + 15) & 0x1f) << 10) | ((u >> 13) & 0x3ff); hw_f16[i] = h; }
    ggml_backend_tensor_set(wh, hw_f16.data(), 0, hw_f16.size() * 2);
    ggml_backend_graph_compute(backend, graph);
    ggml_backend_synchronize(backend);
    std::vector<float> hy(ROW * T);
    ggml_backend_tensor_get(y, hy.data(), 0, hy.size() * 4);

    // CPU 参考
    double maxrel = 0;
    for (int t = 0; t < T; t++)
        for (int h = 0; h < H; h++) {
            double s = 0;
            for (int d = 0; d < D; d++) { double v = hx[t*ROW + h*D + d]; s += v * v; }
            double inv = 1.0 / sqrt(s / D + 1e-6);
            for (int d = 0; d < D; d++) {
                double ref = hx[t*ROW + h*D + d] * inv * hw16[d];
                double got = hy[t*ROW + h*D + d];
                double rel = fabs(ref - got) / (fabs(ref) + 1e-9);
                if (rel > maxrel) maxrel = rel;
            }
        }
    printf("qkr-selftest maxrel=%.3e %s\n", maxrel, maxrel < 3e-3 ? "PASS" : "FAIL");
    return 0;
}
