/**
 * Phase 1c: W8A8 vs V2 vs F16 Performance A/B benchmark.
 *
 * Process isolation: one {path,shape} per invocation.
 *
 * CANN tensor conventions (verified against ggml-cann + debug tests):
 *   Inner-major: shape {inner, outer}, strides {1, inner}
 *     → data[i + o*inner], used for V2 weight/scales, W8A8 weight/input/output
 *   Outer-major: shape {outer, inner}, strides {inner, 1}
 *     → data[o*inner + i], used for V2 input/output, F16 input/output
 *   Both describe the SAME memory layout (col-major fill).
 *   The difference is which dim the operator interprets as reduction vs batch.
 *
 * Build:
 *   g++ -std=c++17 -O2 -fopenmp \
 *       -I/usr/local/Ascend/cann-9.1.0-beta.1/aarch64-linux/include \
 *       -I/usr/local/Ascend/cann-9.1.0-beta.1/include \
 *       phase1c_w8a8_bench.cpp \
 *       -L/usr/local/Ascend/cann-9.1.0-beta.1/lib64 \
 *       -lascendcl -lnnopbase -lopapi -lacl_rt -lpthread -ldl \
 *       -Wl,-rpath,/usr/local/Ascend/cann-9.1.0-beta.1/lib64 \
 *       -o phase1c_w8a8_bench
 */
#include <acl/acl.h>
#include <aclnn/aclnn_base.h>
#include <aclnnop/aclnn_mm.h>
#include <aclnnop/aclnn_quant_matmul_v3.h>
#include <aclnnop/aclnn_quantize.h>
#include <aclnnop/aclnn_weight_quant_batch_matmul_v2.h>

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <ctime>
#include <vector>

#define ACL_CHECK(cmd) do { \
    aclError err = (cmd); \
    if (err != ACL_SUCCESS) { \
        fprintf(stderr, "ACL error %d at %s:%d: %s\n", err, __FILE__, __LINE__, #cmd); \
        exit(1); \
    } \
} while(0)

// ── Shape definitions ──
struct ShapeConfig {
    const char *id, *name, *category;
    int64_t K, N, batch;
};

static const ShapeConfig SHAPES[] = {
    {"S1",  "Q-proj",       "PRIMARY_REAL_MODEL",     4096,  4096, 1},
    {"S2",  "K-proj",       "PRIMARY_REAL_MODEL",     4096,  1024, 1},
    {"S3",  "V-proj",       "PRIMARY_REAL_MODEL",     4096,  1024, 1},
    {"S4",  "O-proj",       "PRIMARY_REAL_MODEL",     4096,  4096, 1},
    {"S5",  "FFN-gate",     "PRIMARY_REAL_MODEL",     4096, 12288, 1},
    {"S6",  "FFN-up",       "PRIMARY_REAL_MODEL",     4096, 12288, 1},
    {"S7",  "FFN-down",     "PRIMARY_REAL_MODEL",    12288,  4096, 1},
    {"S8",  "FFN-gate-n2",  "BATCH_SCALING",          4096, 12288, 2},
    {"S9",  "FFN-gate-n4",  "BATCH_SCALING",          4096, 12288, 4},
    {"S10", "FFN-gate-n8",  "BATCH_SCALING",          4096, 12288, 8},
    {"S11", "FFN-up-14336",  "LEGACY_REFERENCE",      4096, 14336, 1},
    {"S12", "FFN-down-14336","LEGACY_REFERENCE",     14336,  4096, 1},
    {"S13", "QKV-combined",  "SYNTHETIC_FUSION_ONLY", 4096, 12288, 1},
    {"S14", "All-proj",      "SYNTHETIC_FUSION_ONLY", 4096, 18432, 1},
};

static const ShapeConfig* find_shape(const char* id) {
    for (auto& s : SHAPES) if (strcmp(s.id, id) == 0) return &s;
    fprintf(stderr, "Unknown shape: %s\n", id); exit(1);
}

// ── RNG ──
static uint32_t xorshift32(uint32_t &s) { s ^= s << 13; s ^= s >> 17; s ^= s << 5; return s; }

// Fill column-major [inner, outer]: data[i + o*inner] in [-range, range]
static void fill_fp16_cm(uint16_t *d, int64_t inner, int64_t outer, float range, uint32_t &rng) {
    for (int64_t o = 0; o < outer; o++)
        for (int64_t i = 0; i < inner; i++) {
            float v = ((float)(int32_t)xorshift32(rng) / 2147483648.0f) * range;
            uint32_t bits; memcpy(&bits, &v, 4);
            uint16_t sign = (bits >> 16) & 0x8000;
            int32_t  exp  = ((bits >> 23) & 0xFF) - 127;
            uint32_t mant = bits & 0x7FFFFF;
            if (exp > 15) exp = 15;
            if (exp < -14) { sign = 0; exp = 0; mant = 0; }
            d[i + o*inner] = sign | ((exp + 15) << 10) | (mant >> 13);
        }
}

static void fill_i8_cm(int8_t *d, int64_t inner, int64_t outer, uint32_t &rng) {
    for (int64_t o = 0; o < outer; o++)
        for (int64_t i = 0; i < inner; i++)
            d[i + o*inner] = (int8_t)(xorshift32(rng) & 0xFF);
}

static float fp16_to_f32(uint16_t v) {
    uint32_t sign = (v >> 15) & 1, exp = (v >> 10) & 0x1F, mant = v & 0x3FF, f32;
    if (exp == 0) {
        if (mant == 0) f32 = sign << 31;
        else { int e = 1; while ((mant & 0x400) == 0) { mant <<= 1; e--; } mant &= 0x3FF; f32 = (sign << 31) | ((e - 15 + 127) << 23) | (mant << 13); }
    } else if (exp == 31) { f32 = (sign << 31) | (0xFF << 23) | (mant << 13); }
    else { f32 = (sign << 31) | ((exp - 15 + 127) << 23) | (mant << 13); }
    float ret; memcpy(&ret, &f32, 4); return ret;
}

// ── Timer ──
static double now_us() { struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts); return ts.tv_sec*1e6 + ts.tv_nsec*1e-3; }

// ── Statistics ──
struct Stats { double mean, p50, p90, p99, stddev, cv; };
static Stats compute_stats(std::vector<double> &v) {
    std::sort(v.begin(), v.end());
    Stats s; double sum = 0;
    for (auto x : v) sum += x;
    s.mean = sum / v.size();
    double sq = 0; for (auto x : v) sq += (x - s.mean)*(x - s.mean);
    s.stddev = std::sqrt(sq / (v.size() - 1));
    s.cv = s.stddev / s.mean;
    s.p50 = v[v.size()*50/100]; s.p90 = v[v.size()*90/100]; s.p99 = v[v.size()*99/100];
    return s;
}

static constexpr int QK8_0 = 32;

// ═══════════════════════════════════════════════════════════════
// CANN tensor helpers.
// Data is ALWAYS column-major: data[inner + outer*inner_dim].
// Two conventions describe the same memory:
//   inner_major: shape {inner, outer}, strides {1, inner}
//   outer_major: shape {outer, inner}, strides {inner, 1}
// Which one to use depends on what the operator interprets as
// reduction dim vs batch dim.
// ═══════════════════════════════════════════════════════════════

static aclTensor* tensor_inner_major(void *data, aclDataType dtype,
                                      int64_t inner, int64_t outer) {
    int64_t shape[] = {inner, outer};
    int64_t strd[]  = {1, inner};
    int64_t slen    = inner * outer;
    return aclCreateTensor(shape, 2, dtype, strd, 0, ACL_FORMAT_ND, &slen, 1, data);
}

static aclTensor* tensor_outer_major(void *data, aclDataType dtype,
                                      int64_t outer, int64_t inner) {
    int64_t shape[] = {outer, inner};
    int64_t strd[]  = {inner, 1};
    int64_t slen    = outer * inner;
    return aclCreateTensor(shape, 2, dtype, strd, 0, ACL_FORMAT_ND, &slen, 1, data);
}

static aclTensor* tensor_scalar(void *data, aclDataType dtype) {
    int64_t sh[] = {1}, st[] = {1}, sl = 1;
    return aclCreateTensor(sh, 1, dtype, st, 0, ACL_FORMAT_ND, &sl, 1, data);
}

// ═══════════════════════════════════════════════════════════════
// Validation: CPU reference + NMSE comparison against device output
// Criterion: NMSE ≤ 5e-4 (matching test-backend-ops MUL_MAT threshold)
// ═══════════════════════════════════════════════════════════════

static constexpr double NMSE_THRESHOLD = 5e-4;

struct ValidationResult {
    bool   pass;
    double max_abs_err;
    double mean_abs_err;
    double nmse;
};

// CPU reference FP32 matmul: C[outer, inner] = sum_k A[outer, k] * B[k, inner]
// A is col-major [K, S] (input), B is col-major [K, N] (weight), C is [S, N]
static void cpu_matmul_fp32(const float* A, const float* B,
                             float* C, int64_t K, int64_t N, int64_t S) {
    for (int64_t s = 0; s < S; s++) {
        for (int64_t n = 0; n < N; n++) {
            float sum = 0.0f;
            for (int64_t k = 0; k < K; k++)
                sum += A[k + s*K] * B[k + n*K];
            C[s*N + n] = sum;
        }
    }
}

// Read device output [S,N] FP16 → host float, compute NMSE vs reference
static ValidationResult compute_nmse(void* dout, const float* ref,
                                      int64_t N, int64_t S) {
    ValidationResult r = {false, 0.0, 0.0, 0.0};
    size_t out_elems = (size_t)N * S;
    std::vector<uint16_t> h_out(out_elems);
    ACL_CHECK(aclrtMemcpy(h_out.data(), out_elems * sizeof(uint16_t),
                          dout, out_elems * sizeof(uint16_t),
                          ACL_MEMCPY_DEVICE_TO_HOST));

    double sum_sq_diff = 0.0, sum_sq_ref = 0.0, sum_abs_diff = 0.0;
    r.max_abs_err = 0.0;
    for (size_t i = 0; i < out_elems; i++) {
        float dev_val = fp16_to_f32(h_out[i]);
        float ref_val = ref[i];

        // NaN/Inf guard
        if (!std::isfinite(dev_val) || !std::isfinite(ref_val)) {
            r.nmse = INFINITY;
            return r;
        }

        float abs_diff = std::abs(dev_val - ref_val);
        sum_sq_diff  += (double)(dev_val - ref_val) * (dev_val - ref_val);
        sum_sq_ref   += (double)ref_val * ref_val;
        sum_abs_diff += abs_diff;
        if (abs_diff > r.max_abs_err) r.max_abs_err = abs_diff;
    }
    r.mean_abs_err = sum_abs_diff / (double)out_elems;
    r.nmse = (sum_sq_ref > 0.0) ? sum_sq_diff / sum_sq_ref : sum_sq_diff;
    r.pass = (r.nmse <= NMSE_THRESHOLD);
    return r;
}

// Validate F16 path: weight [K,N] FP16 × input [K,S] FP16 → output [S,N]
static ValidationResult validate_f16(const ShapeConfig& sh,
                                      const std::vector<uint16_t>& h_w,
                                      const std::vector<uint16_t>& h_in,
                                      void* dout) {
    int64_t K = sh.K, N = sh.N, S = sh.batch;
    size_t w_elems = (size_t)K * N, in_elems = (size_t)K * S;

    std::vector<float> w_f32(w_elems), in_f32(in_elems);
    for (size_t i = 0; i < w_elems; i++) w_f32[i] = fp16_to_f32(h_w[i]);
    for (size_t i = 0; i < in_elems; i++) in_f32[i] = fp16_to_f32(h_in[i]);

    std::vector<float> ref((size_t)N * S);
    cpu_matmul_fp32(in_f32.data(), w_f32.data(), ref.data(), K, N, S);
    return compute_nmse(dout, ref.data(), N, S);
}

// Validate V2 path: dequant Q8_0 weight × input → output
static ValidationResult validate_v2(const ShapeConfig& sh,
                                     const std::vector<uint8_t>& h_wq,
                                     const std::vector<uint16_t>& h_wsc,
                                     const std::vector<uint16_t>& h_in,
                                     void* dout) {
    int64_t K = sh.K, N = sh.N, S = sh.batch, Kg = K / QK8_0;
    size_t w_elems = (size_t)K * N, in_elems = (size_t)K * S;

    // Dequant Q8_0 weight: w_fp32[i] = (int8_t)w_q[i] * fp16_to_f32(scale[group])
    std::vector<float> w_f32(w_elems);
    for (size_t i = 0; i < w_elems; i++) {
        size_t gi = i / QK8_0;
        w_f32[i] = (float)(int8_t)h_wq[i] * fp16_to_f32(h_wsc[gi]);
    }

    std::vector<float> in_f32(in_elems);
    for (size_t i = 0; i < in_elems; i++) in_f32[i] = fp16_to_f32(h_in[i]);

    std::vector<float> ref((size_t)N * S);
    cpu_matmul_fp32(in_f32.data(), w_f32.data(), ref.data(), K, N, S);
    return compute_nmse(dout, ref.data(), N, S);
}

// Validate W8A8 path: full CPU pipeline matching Quantize+QuantMatmulV3
static ValidationResult validate_w8a8(const ShapeConfig& sh,
                                       const std::vector<uint8_t>& h_wq,
                                       const std::vector<uint16_t>& h_wsc,
                                       const std::vector<uint16_t>& h_in,
                                       void* dout) {
    int64_t K = sh.K, N = sh.N, S = sh.batch, Kg = K / QK8_0;
    size_t w_elems = (size_t)K * N, in_elems = (size_t)K * S;

    // Step 1: Dequant Q8_0 weight → FP32
    std::vector<float> w_f32(w_elems);
    float w_max = 0.0f;
    for (size_t i = 0; i < w_elems; i++) {
        float gs = fp16_to_f32(h_wsc[i / QK8_0]);
        float v = (float)(int8_t)h_wq[i] * gs;
        w_f32[i] = v;
        if (std::abs(v) > w_max) w_max = std::abs(v);
    }

    // Step 2: Per-tensor weight scale
    float w_scale = w_max / 127.0f;
    if (w_scale == 0.0f) w_scale = 1.0f;

    // Step 3: Requant weight → per-tensor INT8
    std::vector<int8_t> w_i8(w_elems);
    for (size_t i = 0; i < w_elems; i++)
        w_i8[i] = (int8_t)std::max(-128.0f, std::min(127.0f,
                                    std::round(w_f32[i] / w_scale)));

    // Step 4: Input FP16 → FP32 + compute act_scale
    std::vector<float> in_f32(in_elems);
    float a_max = 0.0f;
    for (size_t i = 0; i < in_elems; i++) {
        float v = fp16_to_f32(h_in[i]);
        in_f32[i] = v;
        if (std::abs(v) > a_max) a_max = std::abs(v);
    }
    float a_scale = a_max / 127.0f;
    if (a_scale == 0.0f) a_scale = 1.0f;

    // Step 5: Quantize input → INT8
    std::vector<int8_t> a_i8(in_elems);
    for (size_t i = 0; i < in_elems; i++)
        a_i8[i] = (int8_t)std::max(-128.0f, std::min(127.0f,
                                   std::round(in_f32[i] / a_scale)));

    // Step 6: INT32 matmul: [K,N]^T × [K,S] = [N,S]
    // w_i8 is [K,N] col-major, a_i8 is [K,S] col-major
    // ref[n,s] = sum_k w_i8[k+n*K] * a_i8[k+s*K] (INT32 accumulation)
    float combined_scale = w_scale * a_scale;
    size_t out_elems = (size_t)N * S;
    std::vector<float> ref(out_elems);
    for (int64_t n = 0; n < N; n++) {
        for (int64_t s = 0; s < S; s++) {
            int32_t sum = 0;
            for (int64_t k = 0; k < K; k++)
                sum += (int32_t)w_i8[k + n*K] * (int32_t)a_i8[k + s*K];
            ref[n + s*N] = (float)sum * combined_scale;  // W8A8 output is [N,S] inner-major
        }
    }

    // W8A8 device output is [N,S] inner-major: dout[n + s*N]
    return compute_nmse(dout, ref.data(), N, S);
}

// ═══════════════════════════════════════════════════════════════
// PATH: V2 (WeightQuantBatchmatmulV2)
// Weight: inner_major {K, N} — q[k + n*K], s[g + n*Kg]
// Input:  outer_major {S, K} — din[s*K + k]
// Output: outer_major {S, N} — dout[s*N + n]
// ═══════════════════════════════════════════════════════════════
static void bench_v2(const ShapeConfig &sh, uint32_t seed,
                     int warmup, int measure, bool validate, FILE *csv_out) {
    int64_t K = sh.K, N = sh.N, S = sh.batch, Kg = K / QK8_0;
    aclrtStream st; ACL_CHECK(aclrtCreateStream(&st));

    size_t w_q_sz  = (size_t)K * N;
    size_t w_sc_sz = (size_t)Kg * N * sizeof(uint16_t);
    std::vector<uint8_t>  h_wq(w_q_sz);
    std::vector<uint16_t> h_wsc(w_sc_sz / 2);
    uint32_t rng = seed;
    fill_i8_cm((int8_t*)h_wq.data(), K, N, rng);
    for (size_t i = 0; i < h_wsc.size(); i++) {
        float s = 0.001f + ((float)xorshift32(rng)/4294967296.0f)*0.099f;
        uint32_t bits; memcpy(&bits, &s, 4);
        h_wsc[i] = (uint16_t)((bits>>16) | ((bits>>31)<<15));
    }
    size_t in_sz = (size_t)K * S * sizeof(uint16_t);
    std::vector<uint16_t> h_in(in_sz / 2);
    rng = seed ^ 0xDEADBEEF;
    fill_fp16_cm(h_in.data(), K, S, 1.0f, rng);

    void *dw, *din, *dout;
    ACL_CHECK(aclrtMalloc(&dw, w_q_sz + w_sc_sz, ACL_MEM_MALLOC_HUGE_FIRST));
    ACL_CHECK(aclrtMalloc(&din, in_sz, ACL_MEM_MALLOC_HUGE_FIRST));
    ACL_CHECK(aclrtMalloc(&dout, (size_t)N*S*sizeof(uint16_t), ACL_MEM_MALLOC_HUGE_FIRST));
    ACL_CHECK(aclrtMemcpy(dw, w_q_sz, h_wq.data(), w_q_sz, ACL_MEMCPY_HOST_TO_DEVICE));
    ACL_CHECK(aclrtMemcpy((char*)dw + w_q_sz, w_sc_sz, h_wsc.data(), w_sc_sz, ACL_MEMCPY_HOST_TO_DEVICE));
    ACL_CHECK(aclrtMemcpy(din, in_sz, h_in.data(), in_sz, ACL_MEMCPY_HOST_TO_DEVICE));

    // Q8_0 weight: inner_major {K_inner, N_outer}
    aclTensor* tw  = tensor_inner_major(dw, ACL_INT8, K, N);
    // Scales: inner_major {Kg_inner, N_outer}
    aclTensor* tsc = tensor_inner_major((char*)dw + w_q_sz, ACL_FLOAT16, Kg, N);
    // Input: outer_major {S_outer, K_inner}
    aclTensor* tin = tensor_outer_major(din, ACL_FLOAT16, S, K);
    // Output: outer_major {S_outer, N_inner}
    aclTensor* tout = tensor_outer_major(dout, ACL_FLOAT16, S, N);
    int64_t ags = (K > QK8_0) ? QK8_0 : 0;

    for (int i = 0; i < warmup; i++) {
        uint64_t ws = 0; aclOpExecutor* e = nullptr;
        ACL_CHECK(aclnnWeightQuantBatchMatmulV2GetWorkspaceSize(
            tin, tw, tsc, nullptr, nullptr, nullptr, nullptr, ags, tout, &ws, &e));
        void* w = nullptr; if (ws>0) ACL_CHECK(aclrtMalloc(&w, ws, ACL_MEM_MALLOC_HUGE_FIRST));
        ACL_CHECK(aclnnWeightQuantBatchMatmulV2(w, ws, e, st));
        ACL_CHECK(aclrtSynchronizeStream(st)); if (ws>0) ACL_CHECK(aclrtFree(w));
    }

    std::vector<double> ts; ts.reserve(measure);
    for (int i = 0; i < measure; i++) {
        double t0 = now_us();
        uint64_t ws = 0; aclOpExecutor* e = nullptr;
        ACL_CHECK(aclnnWeightQuantBatchMatmulV2GetWorkspaceSize(
            tin, tw, tsc, nullptr, nullptr, nullptr, nullptr, ags, tout, &ws, &e));
        void* w = nullptr; if (ws>0) ACL_CHECK(aclrtMalloc(&w, ws, ACL_MEM_MALLOC_HUGE_FIRST));
        ACL_CHECK(aclnnWeightQuantBatchMatmulV2(w, ws, e, st));
        ACL_CHECK(aclrtSynchronizeStream(st)); if (ws>0) ACL_CHECK(aclrtFree(w));
        ts.push_back(now_us() - t0);
    }

    Stats s = compute_stats(ts);
    double max_ae = 0, mean_ae = 0, nmse = 0;
    int pass = 0;
    if (validate) {
        auto vr = validate_v2(sh, h_wq, h_wsc, h_in, dout);
        max_ae = vr.max_abs_err; mean_ae = vr.mean_abs_err; nmse = vr.nmse; pass = vr.pass ? 1 : 0;
    }
    fprintf(csv_out, "%s,%s,%ld,%ld,%ld,V2,V2_TOTAL_US,%.3f,%.3f,%.3f,%.3f,%.3f,%.4f,,%.6e,%.6e,%.6e,%d\n",
            sh.id, sh.name, K, N, S, s.mean, s.p50, s.p90, s.p99, s.stddev, s.cv,
            max_ae, mean_ae, nmse, pass);

    aclDestroyTensor(tw); aclDestroyTensor(tsc); aclDestroyTensor(tin); aclDestroyTensor(tout);
    ACL_CHECK(aclrtFree(dw)); ACL_CHECK(aclrtFree(din)); ACL_CHECK(aclrtFree(dout));
    ACL_CHECK(aclrtDestroyStream(st));
}

// ═══════════════════════════════════════════════════════════════
// PATH: F16 (aclnnMm with transposeB=2)
// Weight: inner_major {K, N} — same data layout as V2 weight
// Input:  outer_major {S, K} — din[s*K + k]
// Output: outer_major {S, N} — dout[s*N + n]
// ═══════════════════════════════════════════════════════════════
static void bench_f16(const ShapeConfig &sh, uint32_t seed,
                      int warmup, int measure, bool use_nz, bool validate, FILE *csv_out) {
    int64_t K = sh.K, N = sh.N, S = sh.batch;
    aclrtStream st; ACL_CHECK(aclrtCreateStream(&st));

    size_t w_sz  = (size_t)K * N * sizeof(uint16_t);
    size_t in_sz = (size_t)K * S * sizeof(uint16_t);
    std::vector<uint16_t> h_w(w_sz/2), h_in(in_sz/2);
    uint32_t rng = seed;
    fill_fp16_cm(h_w.data(), K, N, 1.0f, rng);
    rng = seed ^ 0xDEADBEEF;
    fill_fp16_cm(h_in.data(), K, S, 1.0f, rng);

    void *dw, *din, *dout;
    ACL_CHECK(aclrtMalloc(&dw, w_sz, ACL_MEM_MALLOC_HUGE_FIRST));
    ACL_CHECK(aclrtMalloc(&din, in_sz, ACL_MEM_MALLOC_HUGE_FIRST));
    ACL_CHECK(aclrtMalloc(&dout, (size_t)N*S*sizeof(uint16_t), ACL_MEM_MALLOC_HUGE_FIRST));
    ACL_CHECK(aclrtMemcpy(dw, w_sz, h_w.data(), w_sz, ACL_MEMCPY_HOST_TO_DEVICE));
    ACL_CHECK(aclrtMemcpy(din, in_sz, h_in.data(), in_sz, ACL_MEMCPY_HOST_TO_DEVICE));

    // Weight: inner_major {K, N} + optional NZ format
    // Input:  outer_major {S, K}
    // Output: outer_major {S, N}
    int64_t w_sh[] = {K, N}, w_st[] = {1, K}, w_sl = K*N;
    int64_t in_sh[] = {S, K}, in_st[] = {K, 1}, in_sl_v = S*K;
    int64_t o_sh[]  = {S, N}, o_st[]  = {N, 1}, o_sl_v  = S*N;

    aclTensor* tw, *tin, *tout;
    if (use_nz) {
        tw = aclCreateTensor(w_sh, 2, ACL_FLOAT16, w_st, 0, ACL_FORMAT_FRACTAL_NZ, &w_sl, 1, dw);
    } else {
        tw = aclCreateTensor(w_sh, 2, ACL_FLOAT16, w_st, 0, ACL_FORMAT_ND, &w_sl, 1, dw);
    }
    tin  = aclCreateTensor(in_sh, 2, ACL_FLOAT16, in_st, 0, ACL_FORMAT_ND, &in_sl_v, 1, din);
    tout = aclCreateTensor(o_sh, 2, ACL_FLOAT16, o_st, 0, ACL_FORMAT_ND, &o_sl_v, 1, dout);

    for (int i = 0; i < warmup; i++) {
        uint64_t ws = 0; aclOpExecutor* e = nullptr;
        ACL_CHECK(aclnnMmGetWorkspaceSize(tin, tw, tout, 2, &ws, &e));
        void* w = nullptr; if (ws>0) ACL_CHECK(aclrtMalloc(&w, ws, ACL_MEM_MALLOC_HUGE_FIRST));
        ACL_CHECK(aclnnMm(w, ws, e, st));
        ACL_CHECK(aclrtSynchronizeStream(st)); if (ws>0) ACL_CHECK(aclrtFree(w));
    }

    std::vector<double> ts; ts.reserve(measure);
    for (int i = 0; i < measure; i++) {
        double t0 = now_us();
        uint64_t ws = 0; aclOpExecutor* e = nullptr;
        ACL_CHECK(aclnnMmGetWorkspaceSize(tin, tw, tout, 2, &ws, &e));
        void* w = nullptr; if (ws>0) ACL_CHECK(aclrtMalloc(&w, ws, ACL_MEM_MALLOC_HUGE_FIRST));
        ACL_CHECK(aclnnMm(w, ws, e, st));
        ACL_CHECK(aclrtSynchronizeStream(st)); if (ws>0) ACL_CHECK(aclrtFree(w));
        ts.push_back(now_us() - t0);
    }

    Stats s = compute_stats(ts);
    double max_ae = 0, mean_ae = 0, nmse = 0;
    int pass = 0;
    if (validate) {
        auto vr = validate_f16(sh, h_w, h_in, dout);
        max_ae = vr.max_abs_err; mean_ae = vr.mean_abs_err; nmse = vr.nmse; pass = vr.pass ? 1 : 0;
    }
    fprintf(csv_out, "%s,%s,%ld,%ld,%ld,%s,F16_TOTAL_US,%.3f,%.3f,%.3f,%.3f,%.3f,%.4f,,%.6e,%.6e,%.6e,%d\n",
            sh.id, sh.name, K, N, S, use_nz?"F16_NZ":"F16_ND",
            s.mean, s.p50, s.p90, s.p99, s.stddev, s.cv,
            max_ae, mean_ae, nmse, pass);

    aclDestroyTensor(tw); aclDestroyTensor(tin); aclDestroyTensor(tout);
    ACL_CHECK(aclrtFree(dw)); ACL_CHECK(aclrtFree(din)); ACL_CHECK(aclrtFree(dout));
    ACL_CHECK(aclrtDestroyStream(st));
}

// ═══════════════════════════════════════════════════════════════
// PATH: W8A8 (aclnnQuantize + aclnnQuantMatmulV3)
// Weight:   inner_major {K, N} — wi8[k + n*K]
// Input:    inner_major {K, S} — din[k + s*K] FP16
// Act INT8: inner_major {K, S} — dai8[k + s*K]
// Output:   inner_major {N, S} — dout[n + s*N]
// ═══════════════════════════════════════════════════════════════
static void bench_w8a8(const ShapeConfig &sh, uint32_t seed,
                       int warmup, int measure, bool validate, FILE *csv_out) {
    int64_t K = sh.K, N = sh.N, S = sh.batch, Kg = K / QK8_0;
    aclrtStream st; ACL_CHECK(aclrtCreateStream(&st));

    size_t w_q_sz  = (size_t)K * N;
    size_t w_sc_sz = (size_t)Kg * N * sizeof(uint16_t);
    size_t in_sz   = (size_t)K * S * sizeof(uint16_t);
    std::vector<uint8_t>  h_wq(w_q_sz);
    std::vector<uint16_t> h_wsc(w_sc_sz/2);
    std::vector<uint16_t> h_in(in_sz/2);
    uint32_t rng = seed;
    fill_i8_cm((int8_t*)h_wq.data(), K, N, rng);
    for (size_t i = 0; i < h_wsc.size(); i++) {
        float s = 0.001f + ((float)xorshift32(rng)/4294967296.0f)*0.099f;
        uint32_t bits; memcpy(&bits, &s, 4);
        h_wsc[i] = (uint16_t)((bits>>16) | ((bits>>31)<<15));
    }
    rng = seed ^ 0xDEADBEEF;
    fill_fp16_cm(h_in.data(), K, S, 1.0f, rng);

    // ═══ WEIGHT PREPROCESS (ONE_TIME_LOAD_COST) ═══
    double t_pre0 = now_us();

    void *dw_qs, *dw_sc, *din, *dout;
    ACL_CHECK(aclrtMalloc(&dw_qs, w_q_sz, ACL_MEM_MALLOC_HUGE_FIRST));
    ACL_CHECK(aclrtMalloc(&dw_sc, w_sc_sz, ACL_MEM_MALLOC_HUGE_FIRST));
    ACL_CHECK(aclrtMalloc(&din, in_sz, ACL_MEM_MALLOC_HUGE_FIRST));
    ACL_CHECK(aclrtMalloc(&dout, (size_t)N*S*sizeof(uint16_t), ACL_MEM_MALLOC_HUGE_FIRST));
    ACL_CHECK(aclrtMemcpy(dw_qs, w_q_sz, h_wq.data(), w_q_sz, ACL_MEMCPY_HOST_TO_DEVICE));
    ACL_CHECK(aclrtMemcpy(dw_sc, w_sc_sz, h_wsc.data(), w_sc_sz, ACL_MEMCPY_HOST_TO_DEVICE));
    ACL_CHECK(aclrtMemcpy(din, in_sz, h_in.data(), in_sz, ACL_MEMCPY_HOST_TO_DEVICE));

    // Dequant Q8_0 → FP32 → requant per-tensor INT8
    size_t w_elems = w_q_sz;
    std::vector<float> h_wf32(w_elems);
    float w_max = 0;
    for (size_t i = 0; i < w_elems; i++) {
        float gs = fp16_to_f32(h_wsc[i/QK8_0]);
        float v  = (float)(int8_t)h_wq[i] * gs;
        h_wf32[i] = v;
        if (std::abs(v) > w_max) w_max = std::abs(v);
    }
    float w_scale = w_max / 127.0f; if (w_scale == 0) w_scale = 1.0f;
    std::vector<int8_t> h_wi8(w_elems);
    for (size_t i = 0; i < w_elems; i++)
        h_wi8[i] = (int8_t)std::max(-128.0f, std::min(127.0f, std::round(h_wf32[i]/w_scale)));

    void *dw_i8;
    ACL_CHECK(aclrtMalloc(&dw_i8, w_elems*sizeof(int8_t), ACL_MEM_MALLOC_HUGE_FIRST));
    ACL_CHECK(aclrtMemcpy(dw_i8, w_elems*sizeof(int8_t), h_wi8.data(), w_elems*sizeof(int8_t), ACL_MEMCPY_HOST_TO_DEVICE));

    double weight_preprocess_ms = (now_us() - t_pre0) / 1000.0;

    // ── Buffers ──
    void *dact_i8;
    ACL_CHECK(aclrtMalloc(&dact_i8, (size_t)K*S*sizeof(int8_t), ACL_MEM_MALLOC_HUGE_FIRST));
    void *dsc_q, *dzp_q, *dsc_comb;
    ACL_CHECK(aclrtMalloc(&dsc_q, sizeof(float), ACL_MEM_MALLOC_HUGE_FIRST));
    ACL_CHECK(aclrtMalloc(&dzp_q, sizeof(int32_t), ACL_MEM_MALLOC_HUGE_FIRST));
    ACL_CHECK(aclrtMalloc(&dsc_comb, sizeof(uint64_t), ACL_MEM_MALLOC_HUGE_FIRST));

    // Tensors: all inner_major
    aclTensor* tw   = tensor_inner_major(dw_i8, ACL_INT8, K, N);
    aclTensor* tin  = tensor_inner_major(din, ACL_FLOAT16, K, S);
    aclTensor* tai  = tensor_inner_major(dact_i8, ACL_INT8, K, S);
    aclTensor* tout = tensor_inner_major(dout, ACL_FLOAT16, N, S);
    aclTensor* tsc_q    = tensor_scalar(dsc_q, ACL_FLOAT);
    aclTensor* tzp_q    = tensor_scalar(dzp_q, ACL_INT32);
    aclTensor* tsc_comb = tensor_scalar(dsc_comb, ACL_UINT64);

    std::vector<uint16_t> h_act((size_t)K*S);

    // Warmup
    for (int i = 0; i < warmup; i++) {
        ACL_CHECK(aclrtMemcpy(h_act.data(), in_sz, din, in_sz, ACL_MEMCPY_DEVICE_TO_HOST));
        float am = 0;
        for (auto v : h_act) am = std::max(am, std::abs(fp16_to_f32(v)));
        float as = am/127.0f; if (as==0) as=1.0f;
        float comb = w_scale*as;
        int32_t zp = 0;
        uint32_t cb; memcpy(&cb, &comb, 4);
        uint64_t cu = (uint64_t)cb;
        ACL_CHECK(aclrtMemcpy(dsc_q, sizeof(float), &as, sizeof(float), ACL_MEMCPY_HOST_TO_DEVICE));
        ACL_CHECK(aclrtMemcpy(dzp_q, sizeof(int32_t), &zp, sizeof(int32_t), ACL_MEMCPY_HOST_TO_DEVICE));
        ACL_CHECK(aclrtMemcpy(dsc_comb, sizeof(uint64_t), &cu, sizeof(uint64_t), ACL_MEMCPY_HOST_TO_DEVICE));
        { uint64_t ws=0; aclOpExecutor* e=nullptr;
          ACL_CHECK(aclnnQuantizeGetWorkspaceSize(tin, tsc_q, tzp_q, ACL_INT8, -1, tai, &ws, &e));
          void* w=nullptr; if(ws>0) ACL_CHECK(aclrtMalloc(&w, ws, ACL_MEM_MALLOC_HUGE_FIRST));
          ACL_CHECK(aclnnQuantize(w, ws, e, st));
          ACL_CHECK(aclrtSynchronizeStream(st)); if(ws>0) ACL_CHECK(aclrtFree(w)); }
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
        { uint64_t ws=0; aclOpExecutor* e=nullptr;
          ACL_CHECK(aclnnQuantMatmulV3GetWorkspaceSize(tw, tai, tsc_comb, nullptr, nullptr, true, false, tout, &ws, &e));
          void* w=nullptr; if(ws>0) ACL_CHECK(aclrtMalloc(&w, ws, ACL_MEM_MALLOC_HUGE_FIRST));
          ACL_CHECK(aclnnQuantMatmulV3(w, ws, e, st));
          ACL_CHECK(aclrtSynchronizeStream(st)); if(ws>0) ACL_CHECK(aclrtFree(w)); }
#pragma GCC diagnostic pop
    }

    std::vector<double> t_as, t_q, t_m, t_t;
    t_as.reserve(measure); t_q.reserve(measure); t_m.reserve(measure); t_t.reserve(measure);

    for (int i = 0; i < measure; i++) {
        double t0 = now_us();
        ACL_CHECK(aclrtMemcpy(h_act.data(), in_sz, din, in_sz, ACL_MEMCPY_DEVICE_TO_HOST));
        float am = 0;
        for (auto v : h_act) am = std::max(am, std::abs(fp16_to_f32(v)));
        float as = am/127.0f; if (as==0) as=1.0f;
        float comb = w_scale*as;
        int32_t zp = 0;
        uint32_t cb; memcpy(&cb, &comb, 4);
        uint64_t cu = (uint64_t)cb;
        ACL_CHECK(aclrtMemcpy(dsc_q, sizeof(float), &as, sizeof(float), ACL_MEMCPY_HOST_TO_DEVICE));
        ACL_CHECK(aclrtMemcpy(dzp_q, sizeof(int32_t), &zp, sizeof(int32_t), ACL_MEMCPY_HOST_TO_DEVICE));
        ACL_CHECK(aclrtMemcpy(dsc_comb, sizeof(uint64_t), &cu, sizeof(uint64_t), ACL_MEMCPY_HOST_TO_DEVICE));
        double t_as1 = now_us();

        { uint64_t ws=0; aclOpExecutor* e=nullptr;
          ACL_CHECK(aclnnQuantizeGetWorkspaceSize(tin, tsc_q, tzp_q, ACL_INT8, -1, tai, &ws, &e));
          void* w=nullptr; if(ws>0) ACL_CHECK(aclrtMalloc(&w, ws, ACL_MEM_MALLOC_HUGE_FIRST));
          ACL_CHECK(aclnnQuantize(w, ws, e, st));
          ACL_CHECK(aclrtSynchronizeStream(st)); if(ws>0) ACL_CHECK(aclrtFree(w)); }
        double t_q1 = now_us();

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
        { uint64_t ws=0; aclOpExecutor* e=nullptr;
          ACL_CHECK(aclnnQuantMatmulV3GetWorkspaceSize(tw, tai, tsc_comb, nullptr, nullptr, true, false, tout, &ws, &e));
          void* w=nullptr; if(ws>0) ACL_CHECK(aclrtMalloc(&w, ws, ACL_MEM_MALLOC_HUGE_FIRST));
          ACL_CHECK(aclnnQuantMatmulV3(w, ws, e, st));
          ACL_CHECK(aclrtSynchronizeStream(st)); if(ws>0) ACL_CHECK(aclrtFree(w)); }
#pragma GCC diagnostic pop
        double t1 = now_us();

        t_as.push_back(t_as1 - t0);
        t_q.push_back(t_q1 - t_as1);
        t_m.push_back(t1 - t_q1);
        t_t.push_back(t1 - t0);
    }

    double max_ae = 0, mean_ae = 0, nmse = 0;
    int pass = 0;
    if (validate) {
        auto vr = validate_w8a8(sh, h_wq, h_wsc, h_in, dout);
        max_ae = vr.max_abs_err; mean_ae = vr.mean_abs_err; nmse = vr.nmse; pass = vr.pass ? 1 : 0;
    }
    auto emit = [&](const char* m, const std::vector<double>& v) {
        auto vc = v;
        Stats s = compute_stats(vc);
        fprintf(csv_out, "%s,%s,%ld,%ld,%ld,W8A8,%s,%.3f,%.3f,%.3f,%.3f,%.3f,%.4f,%.3f,%.6e,%.6e,%.6e,%d\n",
                sh.id, sh.name, K, N, S, m,
                s.mean, s.p50, s.p90, s.p99, s.stddev, s.cv, weight_preprocess_ms,
                max_ae, mean_ae, nmse, pass);
    };
    emit("T_ACT_SCALE_US", t_as);
    emit("T_QUANTIZE_US", t_q);
    emit("T_MATMUL_US", t_m);
    emit("T_W8A8_TOTAL_US", t_t);

    aclDestroyTensor(tw); aclDestroyTensor(tin); aclDestroyTensor(tai);
    aclDestroyTensor(tout); aclDestroyTensor(tsc_q); aclDestroyTensor(tzp_q);
    aclDestroyTensor(tsc_comb);
    ACL_CHECK(aclrtFree(dw_qs)); ACL_CHECK(aclrtFree(dw_sc)); ACL_CHECK(aclrtFree(dw_i8));
    ACL_CHECK(aclrtFree(din)); ACL_CHECK(aclrtFree(dout)); ACL_CHECK(aclrtFree(dact_i8));
    ACL_CHECK(aclrtFree(dsc_q)); ACL_CHECK(aclrtFree(dzp_q)); ACL_CHECK(aclrtFree(dsc_comb));
    ACL_CHECK(aclrtDestroyStream(st));
}

// ═══════════════════════════════════════════════════════════════
int main(int argc, char **argv) {
    const char *shape_id = "S1", *path = "W8A8", *out_file = nullptr;
    uint32_t seed = 42;
    int warmup = 20, measure = 200;
    bool validate = false;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--shape") && i+1<argc)   shape_id = argv[++i];
        else if (!strcmp(argv[i], "--path") && i+1<argc) path = argv[++i];
        else if (!strcmp(argv[i], "--seed") && i+1<argc) seed = (uint32_t)atoi(argv[++i]);
        else if (!strcmp(argv[i], "--warmup") && i+1<argc) warmup = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--measure") && i+1<argc) measure = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--output") && i+1<argc) out_file = argv[++i];
        else if (!strcmp(argv[i], "--validate")) validate = true;
        else { fprintf(stderr, "Usage: %s --shape S1..S14 --path F16_NZ|F16_ND|V2|W8A8 [--seed N] [--warmup N] [--measure N] [--output f] [--validate]\n", argv[0]); return 1; }
    }

    const ShapeConfig *sh = find_shape(shape_id);
    ACL_CHECK(aclInit(nullptr));
    ACL_CHECK(aclrtSetDevice(0));

    FILE *csv = out_file ? fopen(out_file, "a") : stdout;
    if (!csv) { perror(out_file); return 1; }
    if (out_file) { fseek(csv, 0, SEEK_END); if (ftell(csv)==0)
        fprintf(csv, "shape_id,name,K,N,batch,path,metric,mean_us,p50_us,p90_us,p99_us,std_us,cv,weight_preprocess_ms,max_abs_err,mean_abs_err,ggml_err,correctness_pass\n");
    }

    if (!strcmp(path, "V2"))           bench_v2(*sh, seed, warmup, measure, validate, csv);
    else if (!strcmp(path, "F16_NZ"))  bench_f16(*sh, seed, warmup, measure, true, validate, csv);
    else if (!strcmp(path, "F16_ND"))  bench_f16(*sh, seed, warmup, measure, false, validate, csv);
    else if (!strcmp(path, "W8A8"))    bench_w8a8(*sh, seed, warmup, measure, validate, csv);
    else { fprintf(stderr, "Unknown path: %s\n", path); return 1; }

    if (out_file) fclose(csv);
    ACL_CHECK(aclrtResetDevice(0));
    ACL_CHECK(aclFinalize());
    return 0;
}
