/**
 * W8A8 micro-benchmark: QuantMatmulV5 (INT8×INT8) vs WeightQuantBatchmatmulV2 (W8A16).
 *
 * Calls CANN ACLNN API directly (no ggml dependency for the CANN part).
 * Uses random data — correctness is irrelevant; only kernel timing matters.
 *
 * Build:
 *   g++ -std=c++17 -O2 -fopenmp \
 *       -I/usr/local/Ascend/cann-9.1.0-beta.1/aarch64-linux/include \
 *       -I/usr/local/Ascend/cann-9.1.0-beta.1/include \
 *       micro_w8a8_bench.cpp \
 *       -L/usr/local/Ascend/cann-9.1.0-beta.1/lib64 \
 *       -lascendcl -lnnopbase -lopapi -lacl_rt -lpthread -ldl \
 *       -Wl,-rpath,/usr/local/Ascend/cann-9.1.0-beta.1/lib64 \
 *       -o micro_w8a8_bench
 */

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <numeric>
#include <algorithm>
#include <cmath>

#include <acl/acl.h>
#include <aclnn/aclnn_base.h>
#include <aclnnop/aclnn_util.h>
#include <aclnnop/level2/aclnn_quant_matmul_v5.h>
#include <aclnnop/level2/aclnn_weight_quant_batch_matmul_v2.h>
#include <aclnnop/level2/aclnn_cast.h>
#include <aclnnop/level2/aclnn_dynamic_quant.h>

#define ACL_CHECK(cmd) do {                              \
    aclError err = (cmd);                                \
    if (err != ACL_SUCCESS) {                            \
        fprintf(stderr, "ACL error %d at %s:%d: %s\n",  \
                err, __FILE__, __LINE__, #cmd);          \
        exit(1);                                         \
    }                                                    \
} while(0)

static double median(std::vector<double>& v) {
    if (v.empty()) return 0.0;
    std::sort(v.begin(), v.end());
    size_t n = v.size();
    return (n % 2 == 0) ? (v[n/2-1] + v[n/2])/2.0 : v[n/2];
}
static double mean(const std::vector<double>& v) {
    if (v.empty()) return 0.0;
    return std::accumulate(v.begin(), v.end(), 0.0) / (double)v.size();
}

// ─── Helper: aclTensor lifetime ─────────────────────────────────────────
struct AclTensorWrap {
    aclTensor* t;
    AclTensorWrap() : t(nullptr) {}
    explicit AclTensorWrap(aclTensor* p) : t(p) {}
    ~AclTensorWrap() { if (t) aclDestroyTensor(t); }
    aclTensor* get() { return t; }
    aclTensor* release() { auto p = t; t = nullptr; return p; }
};

// ─── Helper: device memory ──────────────────────────────────────────────
struct DevMem { void* ptr; size_t size; DevMem() : ptr(nullptr), size(0) {} };
static DevMem dev_alloc(size_t size) {
    DevMem m; m.size = size;
    ACL_CHECK(aclrtMalloc(&m.ptr, size, ACL_MEM_MALLOC_HUGE_FIRST));
    return m;
}
static void dev_free(DevMem& m) {
    if (m.ptr) { ACL_CHECK(aclrtFree(m.ptr)); m.ptr = nullptr; }
}
static void h2d_copy(void* dst, const void* src, size_t size) {
    ACL_CHECK(aclrtMemcpy(dst, size, src, size, ACL_MEMCPY_HOST_TO_DEVICE));
}

// ─── Timer ──────────────────────────────────────────────────────────────
struct Timer {
    std::vector<double> us;
    aclrtStream stream;
    void warmup(int n, const std::function<void()>& fn) {
        for (int i = 0; i < n; i++) fn();
        ACL_CHECK(aclrtSynchronizeStream(stream));
    }
    void measure(int n_iter, const std::function<void()>& fn) {
        us.reserve(n_iter);
        for (int i = 0; i < n_iter; i++) {
            ACL_CHECK(aclrtSynchronizeStream(stream));
            auto t0 = std::chrono::steady_clock::now();
            fn();
            ACL_CHECK(aclrtSynchronizeStream(stream));
            auto t1 = std::chrono::steady_clock::now();
            us.push_back(std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count());
        }
    }
};

// ─── Create simple 2D tensor ─────────────────────────────────────────────
static AclTensorWrap make_tensor(const int64_t* shape, int ndim, aclDataType dtype,
                                  aclFormat fmt, void* dev_data, size_t data_len) {
    int64_t strides[ndim];
    strides[ndim-1] = aclDataTypeSize(dtype);
    for (int i = ndim-2; i >= 0; i--) strides[i] = strides[i+1] * shape[i+1];
    int64_t storage_len = data_len;
    return AclTensorWrap(aclCreateTensor(shape, ndim, dtype, strides, 0, fmt,
                                          &storage_len, 1, dev_data));
}

// ─── Run single op (get workspace → alloc → call → free) ─────────────────
typedef aclnnStatus (*GetWorkspaceFn)(const aclTensor*, const aclTensor*,
    const aclTensor*, const aclTensor*, const aclTensor*, const aclTensor*,
    const aclTensor*, const aclTensor*, const aclTensor*, bool, bool,
    int64_t, aclTensor*, uint64_t*, aclOpExecutor**);

static void run_quant_matmul_v5(aclrtStream stream,
    aclTensor* x1, aclTensor* x2,
    aclTensor* x1Scale, aclTensor* x2Scale,
    aclTensor* bias, bool transposeX1, bool transposeX2,
    int64_t groupSize, aclTensor* out)
{
    uint64_t wsSize = 0;
    aclOpExecutor* exec = nullptr;
    ACL_CHECK(aclnnQuantMatmulV5GetWorkspaceSize(
        x1, x2, x1Scale, x2Scale, nullptr, nullptr, nullptr, nullptr,
        bias, transposeX1, transposeX2, groupSize, out, &wsSize, &exec));
    DevMem ws;
    if (wsSize > 0) ws = dev_alloc(wsSize);
    ACL_CHECK(aclnnQuantMatmulV5(ws.ptr, wsSize, exec, stream));
    if (wsSize > 0) dev_free(ws);
}

// ─── WeightQuantBatchmatmulV2 benchmark (current W8A16 path) ─────────────
static void run_weight_quant_bmm_v2(aclrtStream stream,
    aclTensor* x, aclTensor* weight, aclTensor* antiquantScale,
    int64_t antiquantGroupSize, aclTensor* out)
{
    uint64_t wsSize = 0;
    aclOpExecutor* exec = nullptr;
    ACL_CHECK(aclnnWeightQuantBatchMatmulV2GetWorkspaceSize(
        x, weight, antiquantScale,
        nullptr, nullptr, nullptr, nullptr, // quantOpt, quantScale, quantOffset, bias
        antiquantGroupSize, out, &wsSize, &exec));
    DevMem ws;
    if (wsSize > 0) ws = dev_alloc(wsSize);
    ACL_CHECK(aclnnWeightQuantBatchMatmulV2(ws.ptr, wsSize, exec, stream));
    if (wsSize > 0) dev_free(ws);
}

// ─── Main ────────────────────────────────────────────────────────────────
int main(int argc, char** argv) {
    int n_iter  = 200;
    int K       = 4096;
    int N       = 4096;
    int seq_len = 1;
    int group   = 32;  // QK8_0 = 32

    for (int i = 1; i < argc; i++) {
        if      (!strcmp(argv[i], "--n-iter")) { n_iter = atoi(argv[++i]); }
        else if (!strcmp(argv[i], "--K"))      { K = atoi(argv[++i]); }
        else if (!strcmp(argv[i], "--N"))      { N = atoi(argv[++i]); }
        else if (!strcmp(argv[i], "--group"))  { group = atoi(argv[++i]); }
        else if (!strcmp(argv[i], "--seq-len")){ seq_len = atoi(argv[++i]); }
    }

    // ── Init CANN ──────────────────────────────────────────────────────
    ACL_CHECK(aclInit(nullptr));
    ACL_CHECK(aclrtSetDevice(0));
    aclrtStream stream;
    ACL_CHECK(aclrtCreateStream(&stream));

    int K_groups = (K + group - 1) / group;

    // ── Allocate host data ─────────────────────────────────────────────
    // Weight (INT8): [K, N]  — in ggml memory layout: [ne0=K, ne1=N]
    size_t weight_sz    = (size_t)K * N * sizeof(int8_t);
    size_t wscale_sz    = (size_t)K_groups * N * sizeof(float);    // x1Scale MUST be float32
    // Activation (FP16 → INT8): [K, seq_len]
    size_t act_fp16_sz  = (size_t)K * seq_len * sizeof(uint16_t);
    size_t act_int8_sz  = (size_t)K * seq_len * sizeof(int8_t);
    size_t ascale_sz    = (size_t)K_groups * seq_len * sizeof(float); // x2Scale as float32
    // Output: [N, seq_len] FP16
    size_t out_sz       = (size_t)N * seq_len * sizeof(uint16_t);

    std::vector<int8_t>   h_weight(K * N);
    std::vector<float>    h_wscale(K_groups * N);
    std::vector<uint16_t> h_act_fp16(K * seq_len);
    std::vector<int8_t>   h_act_int8(K * seq_len);
    std::vector<float>    h_ascale(K_groups * seq_len);
    std::vector<uint16_t> h_out(N * seq_len);

    // Fill with random data
    for (auto& v : h_weight)  v = (int8_t)(rand() % 255 - 127);
    for (auto& v : h_wscale)  v = (float)(rand() % 1000) / 1000.0f + 0.001f;  // small positive fp32
    for (auto& v : h_act_fp16) { uint16_t bits; *(uint16_t*)&bits = (uint16_t)(rand() % 0xFFFF); v = bits; }
    // h_act_int8 and h_ascale computed below

    // ── Device memory ──────────────────────────────────────────────────
    auto d_weight  = dev_alloc(weight_sz);
    auto d_wscale  = dev_alloc(wscale_sz);
    auto d_act_fp  = dev_alloc(act_fp16_sz);
    auto d_act_i8  = dev_alloc(act_int8_sz);
    auto d_ascale  = dev_alloc(ascale_sz);
    auto d_out     = dev_alloc(out_sz);

    h2d_copy(d_weight.ptr, h_weight.data(), weight_sz);
    h2d_copy(d_wscale.ptr, h_wscale.data(), wscale_sz);
    h2d_copy(d_act_fp.ptr, h_act_fp16.data(), act_fp16_sz);

    // ── Tensor descriptors (ND layout) ──────────────────────────────────

    // Weight [K, N] INT8
    int64_t w_shape[] = {K, N};
    auto t_weight = make_tensor(w_shape, 2, ACL_INT8, ACL_FORMAT_ND, d_weight.ptr, weight_sz);

    // Weight scale [K/group, N] — x1Scale MUST be float32 per API
    int64_t ws_shape[] = {K_groups, N};
    auto t_wscale = make_tensor(ws_shape, 2, ACL_FLOAT, ACL_FORMAT_ND, d_wscale.ptr, wscale_sz);

    // Activation FP16 [K, seq_len]
    int64_t a_shape[] = {K, seq_len};
    auto t_act_fp = make_tensor(a_shape, 2, ACL_FLOAT16, ACL_FORMAT_ND, d_act_fp.ptr, act_fp16_sz);

    // Activation INT8 [K, seq_len]  (quantized version)
    auto t_act_i8 = make_tensor(a_shape, 2, ACL_INT8, ACL_FORMAT_ND, d_act_i8.ptr, act_int8_sz);

    // Activation scale [K/group, seq_len] — x2Scale as float32
    int64_t as_shape[] = {K_groups, seq_len};
    auto t_ascale = make_tensor(as_shape, 2, ACL_FLOAT, ACL_FORMAT_ND, d_ascale.ptr, ascale_sz);

    // Output [N, seq_len] FP16
    int64_t o_shape[] = {N, seq_len};
    auto t_out = make_tensor(o_shape, 2, ACL_FLOAT16, ACL_FORMAT_ND, d_out.ptr, out_sz);

    // ── DynamicQuant: FP16 activation → INT8 activation + scale ─────────
    // We use aclnnCast to get INT8 (no scale) + manual scale computation,
    // OR use the aclnnDynamicQuantV4 API to get both.
    // For simplicity, use aclnnCast (FP16→INT8 directly, no scale) as a rough quant proxy.
    // The scale is set to random values — kernel timing is independent of scale values.
    // We populate h_ascale with valid-looking scales:
    for (size_t i = 0; i < h_ascale.size(); i++) {
        h_ascale[i] = (float)(rand() % 1000) / 1000.0f + 0.001f;  // small positive fp32
    }
    h2d_copy(d_ascale.ptr, h_ascale.data(), ascale_sz);

    {
        // Quantize activation FP16 → INT8 via aclnnCast (scale-less; good enough for timing)
        uint64_t cast_ws = 0;
        aclOpExecutor* cast_exec = nullptr;
        ACL_CHECK(aclnnCastGetWorkspaceSize(t_act_fp.get(), ACL_INT8, t_act_i8.get(), &cast_ws, &cast_exec));
        DevMem cast_ws_mem;
        if (cast_ws > 0) cast_ws_mem = dev_alloc(cast_ws);
        ACL_CHECK(aclnnCast(cast_ws_mem.ptr, cast_ws, cast_exec, stream));
        ACL_CHECK(aclrtSynchronizeStream(stream));
        if (cast_ws > 0) dev_free(cast_ws_mem);
    }

    Timer timer;
    timer.stream = stream;

    printf("=== W8A8: aclnnQuantMatmulV5 (INT8×INT8, group=%d) ===\n", group);
    printf("  Shape: K=%d N=%d seq=%d  groups=%d\n", K, N, seq_len, K_groups);

    // Warmup
    for (int i = 0; i < 10; i++) {
        run_quant_matmul_v5(stream,
            t_weight.get(), t_act_i8.get(),
            t_wscale.get(), t_ascale.get(),
            nullptr, true, false, group, t_out.get());
    }
    ACL_CHECK(aclrtSynchronizeStream(stream));

    // Measure
    std::vector<double> times_w8a8;
    times_w8a8.reserve(n_iter);
    for (int i = 0; i < n_iter; i++) {
        ACL_CHECK(aclrtSynchronizeStream(stream));
        auto t0 = std::chrono::steady_clock::now();
        run_quant_matmul_v5(stream,
            t_weight.get(), t_act_i8.get(),
            t_wscale.get(), t_ascale.get(),
            nullptr, true, false, group, t_out.get());
        ACL_CHECK(aclrtSynchronizeStream(stream));
        auto t1 = std::chrono::steady_clock::now();
        double us = std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count();
        times_w8a8.push_back(us);
    }

    double w8a8_p50  = median(times_w8a8);
    double w8a8_mean = mean(times_w8a8);
    printf("  W8A8 p50=%.1f us  mean=%.1f us\n", w8a8_p50, w8a8_mean);

    // ── W8A16 comparison: WeightQuantBatchmatmulV2 ──────────────────────
    // WeightQuantBatchmatmulV2: x=FP16 activation, weight=INT8, antiquantScale=FP16
    // weight layout: [K, N] INT8, scale [K/group, N] FP16, antiquantGroupSize=32
    printf("\n=== W8A16: aclnnWeightQuantBatchmatmulV2 (Q8_0 current path) ===\n");

    for (int i = 0; i < 10; i++) {
        run_weight_quant_bmm_v2(stream,
            t_act_fp.get(), t_weight.get(), t_wscale.get(), group, t_out.get());
    }
    ACL_CHECK(aclrtSynchronizeStream(stream));

    std::vector<double> times_w8a16;
    times_w8a16.reserve(n_iter);
    for (int i = 0; i < n_iter; i++) {
        ACL_CHECK(aclrtSynchronizeStream(stream));
        auto t0 = std::chrono::steady_clock::now();
        run_weight_quant_bmm_v2(stream,
            t_act_fp.get(), t_weight.get(), t_wscale.get(), group, t_out.get());
        ACL_CHECK(aclrtSynchronizeStream(stream));
        auto t1 = std::chrono::steady_clock::now();
        double us = std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count();
        times_w8a16.push_back(us);
    }

    double w8a16_p50  = median(times_w8a16);
    double w8a16_mean = mean(times_w8a16);
    printf("  W8A16 p50=%.1f us  mean=%.1f us\n", w8a16_p50, w8a16_mean);

    // ── Summary ─────────────────────────────────────────────────────────
    printf("\n=== Summary (K=%d N=%d seq=%d group=%d) ===\n", K, N, seq_len, group);
    printf("  W8A8  (QuantMatmulV5):            p50=%.1f us  mean=%.1f us\n", w8a8_p50, w8a8_mean);
    printf("  W8A16 (WeightQuantBatchmatmulV2): p50=%.1f us  mean=%.1f us\n", w8a16_p50, w8a16_mean);
    if (w8a8_p50 > 0 && w8a16_p50 > 0) {
        double ratio = w8a8_p50 / w8a16_p50;
        printf("  Ratio (W8A8 / W8A16): %.2fx  %s\n", ratio,
               ratio < 1.0 ? "W8A8 FASTER ✓" : "W8A16 faster ✗");
    }

    // Cleanup (destructors handle aclTensor cleanup)
    dev_free(d_weight);
    dev_free(d_wscale);
    dev_free(d_act_fp);
    dev_free(d_act_i8);
    dev_free(d_ascale);
    dev_free(d_out);
    ACL_CHECK(aclrtDestroyStream(stream));
    ACL_CHECK(aclrtResetDevice(0));
    ACL_CHECK(aclFinalize());

    return 0;
}
