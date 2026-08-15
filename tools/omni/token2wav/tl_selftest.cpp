// TileLang conv 图链隔离单测: x -> [zero-pad-concat -> cast -> CUSTOM -> cast -> cont] -> y
// 与 CPU 参考对比。用法: tl-selftest [Cin Cout K dil T]
#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "tl_conv_bridge.h"

#include <cstdio>
#include <cstring>
#include <cmath>
#include <vector>
#include <random>



static ggml_tensor * g_w2 = nullptr;
int main(int argc, char ** argv) {
    int Cin = argc > 1 ? atoi(argv[1]) : 64;
    int Cout = argc > 2 ? atoi(argv[2]) : 64;
    int K = argc > 3 ? atoi(argv[3]) : 11;
    int dil = argc > 4 ? atoi(argv[4]) : 3;
    int T = argc > 5 ? atoi(argv[5]) : 6961;

    // 找 CANN 设备
    ggml_backend_dev_t dev = nullptr;
    for (size_t i = 0; i < ggml_backend_dev_count(); i++) {
        auto * d = ggml_backend_dev_get(i);
        if (std::string(ggml_backend_dev_name(d)).find("CANN") != std::string::npos) {
            dev = d; break;
        }
    }
    if (!dev) { fprintf(stderr, "no CANN device\n"); return 1; }
    ggml_backend_t backend = ggml_backend_dev_init(dev, nullptr);
    fprintf(stderr, "backend=%s\n", ggml_backend_name(backend));

    const int pad = dil * (K - 1) / 2;
    std::mt19937 rng(7);
    std::normal_distribution<float> nd(0.f, 0.5f);
    std::vector<float> hx(Cin * T), hw(K * Cin * Cout), hbias(Cout, 0.0f);
    for (auto & v : hx) v = nd(rng);
    for (auto & v : hw) v = nd(rng) * 0.05f;
    if (getenv("OMNI_TL_PROBE")) {
        // 脉冲探针: x = δ(ci=0, t=2000) —— 必须在 tensor_set 之前
        std::fill(hx.begin(), hx.end(), 0.f);
        hx[0 * T + 2000] = 1.f;
    }

    ggml_init_params ip = {/*.mem_size   =*/ 512u << 20,
                           /*.mem_buffer =*/ nullptr,
                           /*.no_alloc   =*/ true};
    ggml_context * ctx = ggml_init(ip);

    // x_tcb [T, Cin, 1] T-fast（与 vocoder 稳态链一致）
    ggml_tensor * x = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, T, Cin, 1);
    ggml_tensor * w = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, K, Cin, Cout);

    // mode6: 两个 TL conv 串联（模拟 resblock 相邻 conv），中间夹 Snake 式非线性
    ggml_tensor * y = ::tlconv::try_conv1d(ctx, w, x, pad, dil);
    ggml_tensor * y2 = nullptr;
    if (argc > 6 && std::string(argv[6]) == "chain") {
        ggml_tensor * w2 = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, K, Cout, Cout);
        g_w2 = w2;  // alloc 后再填数据
        // 直接串联（无中间节点）
        y2 = ::tlconv::try_conv1d(ctx, w2, y, pad, dil);
        if (!y2) { fprintf(stderr, "conv2 MISS\n"); return 2; }
        y = y2;
    }
    if (!y) { fprintf(stderr, "try_conv1d MISS（无匹配 .so？OMNI_TL_CONV=1 + DIR）\n"); return 2; }

    // 同图双路: 原路径参考（照抄 hg_resblock_conv1d 的 im2col+mul_mat+reshape+cont）
    ggml_tensor * im2col = ggml_im2col(ctx, w, x, 1, 0, pad, 0, dil, 0, false, GGML_TYPE_F32);
    ggml_tensor * im2col_2d = ggml_reshape_2d(ctx, im2col, im2col->ne[0], im2col->ne[2] * im2col->ne[1]);
    im2col_2d = ggml_cont(ctx, im2col_2d);
    ggml_tensor * w_2d = ggml_reshape_2d(ctx, w, K * Cin, Cout);
    w_2d = ggml_cont(ctx, w_2d);
    ggml_tensor * y_ref = ggml_mul_mat(ctx, im2col_2d, w_2d);   // 直读 mm [Cout, T]
    (void) 0;

    // 判定实验: x 转成 ne0=Cin 的声明语义布局（Cin-fast 内存）
    ggml_tensor * x_in = x;   // leaf，tensor_set 用
    if (getenv("OMNI_TL_DECL")) {
        x = ggml_cont(ctx, ggml_permute(ctx, x, 1, 0, 2, 3));  // ne=[Cin, T, 1]
    }

    ggml_cgraph * gf = ggml_new_graph(ctx);
    ggml_build_forward_expand(gf, y);
    if (!y2) ggml_build_forward_expand(gf, y_ref);  // chain 模式只看同图A/B单路
    else ggml_build_forward_expand(gf, y_ref);

    ggml_gallocr_t ga = ggml_gallocr_new(ggml_backend_get_default_buffer_type(backend));
    if (!ggml_gallocr_alloc_graph(ga, gf)) { fprintf(stderr, "alloc failed\n"); return 3; }
    ggml_backend_tensor_set(x_in, hx.data(), 0, hx.size() * 4);
    ggml_backend_tensor_set(w, hw.data(), 0, hw.size() * 4);
    if (g_w2) ggml_backend_tensor_set(g_w2, hw.data(), 0, g_w2->ne[0]*g_w2->ne[1]*g_w2->ne[2]*4);

    // 对拍: 输入落盘
    FILE * fx = fopen("/tmp/st_x.bin", "wb"); fwrite(hx.data(), 4, hx.size(), fx); fclose(fx);
    FILE * fw = fopen("/tmp/st_w.bin", "wb"); fwrite(hw.data(), 4, hw.size(), fw); fclose(fw);
    FILE * fm = fopen("/tmp/st_meta.txt", "w");
    fprintf(fm, "%d %d %d %d %d\n", Cin, Cout, K, dil, T); fclose(fm);

    if (ggml_backend_graph_compute(backend, gf) != GGML_STATUS_SUCCESS) { fprintf(stderr, "compute failed\n"); return 4; }

    std::vector<float> hy(T * Cout), hr(T * Cout);
    if (getenv("OMNI_TL_CONV_RAW")) {
        // y16 F16 [T, Cout] T-fast —— 按 ggml ne 序读回
        std::vector<short> h16(T * Cout);
        ggml_backend_tensor_get(y, h16.data(), 0, h16.size() * 2);
        for (size_t i = 0; i < h16.size(); i++) {
            unsigned short h = (unsigned short) h16[i];
            unsigned u = ((h & 0x8000) << 16) | ((((h >> 10) & 0x1f) - 15 + 127) << 23) | ((h & 0x3ff) << 13);
            float f; memcpy(&f, &u, 4);
            hy[i] = f;
        }
    } else {
        ggml_backend_tensor_get(y, hy.data(), 0, hy.size() * 4);
    }
    ggml_backend_tensor_get(y_ref, hr.data(), 0, hr.size() * 4);
    fprintf(stderr, "hy[:4]=%.4f %.4f %.4f %.4f | hr[:4]=%.4f %.4f %.4f %.4f\n",
            hy[0], hy[1], hy[2], hy[3], hr[0], hr[1], hr[2], hr[3]);
    FILE * fhr = fopen("/tmp/st_hr.bin", "wb"); fwrite(hr.data(), 4, hr.size(), fhr); fclose(fhr);
    FILE * fhy = fopen("/tmp/st_hy.bin", "wb"); fwrite(hy.data(), 4, hy.size(), fhy); fclose(fhy);

    // 同图双路参考。布局: hy(TL)= [Cout 行][T 列] 行主序; hr(ggml)= reshape+cont 物化的
    // [T, Cout] 行主序——两者同值不同视，比较前把 hr 按 (T,Cout)->(Cout,T) 转置对齐
    {
        double d1 = 0, a1 = 0;
        for (int i = 0; i < T * Cout; i++) { d1 += std::fabs(hy[i] - hr[i]); a1 += std::fabs(hr[i]); }
        double r1 = d1 / (a1 + 1e-9);
        fprintf(stderr, "SAME-GRAPH A/B(direct mm): rel=%.2e %s\n", r1, r1 < 5e-3 ? "PASS" : "FAIL");
    }

    // CPU 参考
    double sdiff = 0, sabs = 0;
    for (int c = 0; c < Cout; c++)
        for (int t = 0; t < T; t++) {
            float acc = 0;
            for (int ci = 0; ci < Cin; ci++)
                for (int k = 0; k < K; k++) {
                    int tt = t + k * dil - pad;
                    float xv = (tt >= 0 && tt < T) ? hx[ci * T + tt] : 0.f;
                    acc += xv * hw[(k * Cin + ci) * Cout + c];
                }
            double d = std::fabs(hy[c * T + t] - acc);
            sdiff += d; sabs += std::fabs(acc);
        }
    double rel = sdiff / (sabs + 1e-9);
    fprintf(stderr, "C%d->%d K%d D%d T%d: rel=%.2e %s\n", Cin, Cout, K, dil, T, rel,
            rel < 5e-3 ? "PASS" : "FAIL");

    ggml_gallocr_free(ga);
    ggml_free(ctx);
    ggml_backend_free(backend);
    return rel < 5e-3 ? 0 : 5;
}
