/**
 * Micro-benchmark: F16 vs Q8_0 MatMul on CANN backend.
 *
 * Tests the key structural differences found in static audit:
 *   - F16:  aclnnMm/BatchMatMul with ACL_FORMAT_FRACTAL_NZ  (NZ=on default)
 *   - F16:  aclnnMm/BatchMatMul with ACL_FORMAT_ND           (NZ=off)
 *   - Q8_0: aclnnWeightQuantBatchMatmulV2 with ACL_FORMAT_ND (always ND)
 *
 * Usage:
 *   ./micro_matmul_bench [--nz-off] [--n-iter 500] [--hidden 4096] [--ffn 14336]
 *
 * Build:
 *   g++ -std=c++17 -O2 -Iggml/include -Iggml/src \
 *       micro_matmul_bench.cpp \
 *       -Lbuild/ggml/src -lggml -Lbuild/ggml/src/ggml-cann -lggml-cann \
 *       -Wl,-rpath,build/ggml/src:build/ggml/src/ggml-cann \
 *       -o micro_matmul_bench
 */

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <numeric>
#include <algorithm>
#include <cmath>

#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"

// ─── Statistics ──────────────────────────────────────────────────────────────

static double median(std::vector<double>& v) {
    if (v.empty()) return 0.0;
    std::sort(v.begin(), v.end());
    size_t n = v.size();
    if (n % 2 == 0) return (v[n/2 - 1] + v[n/2]) / 2.0;
    return v[n/2];
}

static double mean(const std::vector<double>& v) {
    if (v.empty()) return 0.0;
    return std::accumulate(v.begin(), v.end(), 0.0) / (double)v.size();
}

static double p90(const std::vector<double>& v) {
    if (v.empty()) return 0.0;
    auto sorted = v;
    std::sort(sorted.begin(), sorted.end());
    return sorted[(size_t)(sorted.size() * 0.90)];
}

static double p99(const std::vector<double>& v) {
    if (v.empty()) return 0.0;
    auto sorted = v;
    std::sort(sorted.begin(), sorted.end());
    return sorted[(size_t)(sorted.size() * 0.99)];
}

// ─── Benchmark core ──────────────────────────────────────────────────────────
//
// Weight layout:  [ne0=K, ne1=N]  — K columns, N rows
// Input layout:   [ne0=K, ne1=seq_len]
// MUL_MAT(weight, input):
//   weight [K, N] is src0
//   input  [K, S] is src1
//   output = weight^T * input → [N, K] * [K, S] → [N, S]
//   → output shape [ne0=N, ne1=S]

static void bench_mul_mat(ggml_backend_t backend, ggml_type weight_type,
                          int K, int N, int seq_len,
                          int n_iter, bool verbose) {

    // --- Build compute graph on CPU-side context ---
    struct ggml_init_params params = {
        /*.mem_size   =*/ 256 * 1024 * 1024,
        /*.mem_buffer =*/ nullptr,
        /*.no_alloc   =*/ true,
    };
    struct ggml_context* ctx = ggml_init(params);
    if (!ctx) { fprintf(stderr, "ggml_init failed\n"); return; }

    // src0 = weight [ne0=K, ne1=N]
    const int64_t ne_w[] = {static_cast<int64_t>(K), static_cast<int64_t>(N), 1, 1};
    struct ggml_tensor* weight = ggml_new_tensor(ctx, weight_type, 2, ne_w);

    // src1 = input [ne0=K, ne1=seq_len]
    const int64_t ne_in[] = {static_cast<int64_t>(K), static_cast<int64_t>(seq_len), 1, 1};
    struct ggml_tensor* input = ggml_new_tensor(ctx, GGML_TYPE_F16, 2, ne_in);

    // MUL_MAT: dst = src0^T * src1  → shape [ne0=N, ne1=seq_len]
    struct ggml_tensor* output = ggml_mul_mat(ctx, weight, input);

    struct ggml_cgraph* cgraph = ggml_new_graph(ctx);
    ggml_build_forward_expand(cgraph, output);

    // --- Allocate all tensors on CANN backend (single call) ---
    ggml_backend_buffer_t buf = ggml_backend_alloc_ctx_tensors(ctx, backend);
    if (!buf) { fprintf(stderr, "ggml_backend_alloc_ctx_tensors failed\n"); ggml_free(ctx); return; }

    // --- Upload data (random — correctness irrelevant for kernel timing) ---
    // Q8_0 block: 34 bytes per 32 elements → round up nbytes
    {
        size_t wsize = ggml_nbytes(weight);
        std::vector<uint8_t> wdata(wsize);
        for (size_t i = 0; i < wsize; i++) wdata[i] = (uint8_t)(rand() & 0xFF);
        ggml_backend_tensor_set(weight, wdata.data(), 0, wsize);
    }
    {
        size_t isize = ggml_nbytes(input);
        std::vector<uint8_t> idata(isize);
        for (size_t i = 0; i < isize; i++) idata[i] = (uint8_t)(rand() & 0xFF);
        ggml_backend_tensor_set(input, idata.data(), 0, isize);
    }

    // --- Warmup ---
    for (int i = 0; i < 10; i++) {
        ggml_backend_graph_compute(backend, cgraph);
    }
    ggml_backend_synchronize(backend);

    // --- Measure ---
    std::vector<double> times_us;
    times_us.reserve(n_iter);
    for (int i = 0; i < n_iter; i++) {
        auto t0 = std::chrono::steady_clock::now();
        ggml_backend_graph_compute(backend, cgraph);
        ggml_backend_synchronize(backend);
        auto t1 = std::chrono::steady_clock::now();
        double us = std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count();
        times_us.push_back(us);
    }

    double p50v  = median(times_us);
    double meanv = mean(times_us);
    double p90v  = p90(times_us);
    double p99v  = p99(times_us);

    // Compute GFLOPS: 2*K*N*seq_len FLOP per MatMul
    double gflops = (2.0 * K * N * seq_len) / (p50v * 1e3);  // us→ms→s: ÷1e6, then ×1e9 → ÷1e3

    if (verbose) {
        const char* type_str = (weight_type == GGML_TYPE_Q8_0) ? "Q8_0" : "F16";
        printf("  [%4s  K=%5d N=%5d S=%d]  p50=%8.1f us  mean=%8.1f us  "
               "p90=%8.1f us  p99=%8.1f us  GFLOPS=%6.1f\n",
               type_str, K, N, seq_len, p50v, meanv, p90v, p99v, gflops);
    }

    // --- Cleanup ---
    ggml_backend_buffer_free(buf);
    ggml_free(ctx);
}

// ─── Main ────────────────────────────────────────────────────────────────────

int main(int argc, char** argv) {
    // Parse args
    bool nz_off    = false;
    int  n_iter    = 500;
    int  hidden    = 4096;
    int  ffn       = 14336;
    int  seq_len   = 1;
    bool test_both = true;

    for (int i = 1; i < argc; i++) {
        if      (!strcmp(argv[i], "--nz-off"))   { nz_off = true; }
        else if (!strcmp(argv[i], "--n-iter"))   { n_iter = atoi(argv[++i]); }
        else if (!strcmp(argv[i], "--hidden"))   { hidden = atoi(argv[++i]); }
        else if (!strcmp(argv[i], "--ffn"))      { ffn = atoi(argv[++i]); }
        else if (!strcmp(argv[i], "--seq-len"))  { seq_len = atoi(argv[++i]); }
        else if (!strcmp(argv[i], "--f16-only")) { test_both = false; }
    }

    // Apply NZ setting BEFORE backend init (read once at static init time)
    if (nz_off) {
        setenv("GGML_CANN_WEIGHT_NZ", "off", 1);
        printf("GGML_CANN_WEIGHT_NZ=off  (F16 will use ND layout)\n\n");
    } else {
        printf("GGML_CANN_WEIGHT_NZ=on   (F16 will use Fractal NZ layout)\n\n");
    }

    // --- Init CANN backend ---
    size_t n_dev = ggml_backend_dev_count();
    printf("GGML backends: %zu device(s)\n", n_dev);

    ggml_backend_t backend = nullptr;
    for (size_t i = 0; i < n_dev; i++) {
        ggml_backend_dev_t dev = ggml_backend_dev_get(i);
        const char* name = ggml_backend_dev_name(dev);
        printf("  dev[%zu]: %s\n", i, name);
        if (strstr(name, "CANN") || strstr(name, "ASCEND")) {
            printf("  → Using: %s\n", name);
            backend = ggml_backend_dev_init(dev, nullptr);
            break;
        }
    }
    if (!backend) {
        fprintf(stderr, "ERROR: No CANN/ASCEND backend found!\n");
        return 1;
    }

    printf("\n");

    // Shape table — matching Qwen3-8B linear layer dimensions
    struct { int K; int N; const char* desc; } shapes[] = {
        {hidden, hidden,          "Q/K/V proj"},
        {hidden, hidden * 2,      "Q+K combined"},
        {hidden, ffn,             "FFN up (gate+up)"},
        {ffn,    hidden,          "FFN down"},
        {hidden, hidden + ffn,    "QKV+FFN combined"},  // ~full block
    };

    // ─── Q8_0 ─────────────────────────────────────────────────────────────
    printf("═══ Q8_0 (always ND layout) ═══\n");
    for (auto& s : shapes) {
        bench_mul_mat(backend, GGML_TYPE_Q8_0, s.K, s.N, seq_len, n_iter, true);
    }

    // ─── F16 ──────────────────────────────────────────────────────────────
    if (test_both) {
        const char* layout = nz_off ? "ND" : "NZ";
        printf("\n═══ F16 (%s layout) ═══\n", layout);
        for (auto& s : shapes) {
            bench_mul_mat(backend, GGML_TYPE_F16, s.K, s.N, seq_len, n_iter, true);
        }
    }

    printf("\nConfig: GGML_CANN_WEIGHT_NZ=%s  n_iter=%d  seq_len=%d\n",
           nz_off ? "off" : "on", n_iter, seq_len);

    ggml_backend_free(backend);
    return 0;
}
