// TileLang fused zero-cat layout op (纯布局, 无算术, 无精度风险)
// 替换 flow CFM 的 [scale(·,0) -> concat(x,z,2)] 3-op 链: 单 CUSTOM 节点写
// [x | 0_block] (batch 维加倍)。omni 布局为 ne0 最内层连续, 故是两块连续拷贝。
// env: OMNI_TL_LAYOUT=1 启用; 形状/类型不满足返回 nullptr 走原 CANN 链。
//
// 流序: 不可在回调内 aclrtSynchronizeStream 当前 stream (自同步 → UB/死锁/段错误,
// 实测 segfault)。改为全 stream-ordered 异步原语:
//   - D2D: aclrtMemcpyAsync(dst, nbytes, src, nbytes, kind=3, stream)
//   - 零块: aclrtMemsetAsync(dst + row, bytes, 0, bytes, stream)
// 全异步、零同步、零 host staging; 与下游消费者同流保序。
#include "ggml.h"

#include <cstdio>
#include <cstring>
#include <cstdlib>

extern "C" int aclrtMemcpyAsync(void *, size_t, const void *, size_t, int, void *);
extern "C" int aclrtMemsetAsync(void *, size_t, int32_t, size_t, void *);
extern "C" void * ggml_cann_custom_current_stream();  // ggml-cann.cpp 提供

namespace tllayout {

// dst=CUSTOM(src=x): y[c, t, b] = x[c,t,b] (b<B) 或 0.0f (B<=b<2B); 轴序 ne=[C, T, 2B]。
// 纯布局。omni 布局 ne0 最内层连续, 单个 (c,t)-block 是 C*T 连续 floats。
// 禁止 aclrtSynchronizeStream 当前 stream (自同步 = UB，实测 segfault);
// 用两个 stream-ordered 异步原语: D2D memcpy + device memset。
static void zcat2_cb(ggml_tensor * dst, int /*ith*/, int /*nth*/, void * /*userdata*/) {
    const ggml_tensor * x = dst->src[0];
    if (x == nullptr || x->data == nullptr || dst->data == nullptr) return;
    const int64_t C  = x->ne[0];
    const int64_t T  = x->ne[1];
    const int64_t B  = x->ne[2];
    const size_t  nbytes = (size_t)C * T * B * sizeof(float);
    void * stream = ggml_cann_custom_current_stream();
    // 前块: x -> dst[0:B]   (kind 3 = ACL_MEMCPY_DEVICE_TO_DEVICE)
    aclrtMemcpyAsync(dst->data, nbytes, x->data, nbytes, 3, stream);
    // 后块: dst[B:2B] 清零 (device-side memset, stream-ordered)
    aclrtMemsetAsync((char *)dst->data + nbytes, nbytes, 0, nbytes, stream);
}

// 若启用且形状合法, 返回单个 CUSTOM 节点张量 [C, T, 2B]; 否则返回 nullptr。
// 需 OMNI_TL_LAYOUT=1; 形状/类型不满足时返回 nullptr, 调用点回落原 ggml 链。
ggml_tensor * try_zerocat2(ggml_context * ctx, ggml_tensor * x) {
    if (ctx == nullptr || x == nullptr) return nullptr;
    const char * en = getenv("OMNI_TL_LAYOUT");
    if (!(en && en[0] == '1')) return nullptr;
    if (x->type != GGML_TYPE_F32) return nullptr;
    if (x->ne[3] != 1) return nullptr;
    if (!ggml_is_contiguous(x)) return nullptr;
    const int64_t C = x->ne[0];
    const int64_t T = x->ne[1];
    const int64_t B = x->ne[2];
    if (B != 1) return nullptr;
    if (C <= 0 || T <= 0) return nullptr;

    ggml_tensor * y = ggml_new_tensor_4d(ctx, GGML_TYPE_F32, C, T, 2 * B, 1);
    struct { ggml_custom_op_t fun; int n_tasks; void * userdata; } p = { zcat2_cb, 1, nullptr };
    GGML_ASSERT(sizeof(p) <= GGML_MAX_OP_PARAMS);
    memcpy(y->op_params, &p, sizeof(p));
    y->op     = GGML_OP_CUSTOM;
    y->src[0] = x;
    static int hits = 0;
    if (hits < 8) std::fprintf(stderr, "[TL_LAYOUT] zcat2 CUSTOM C=%lld T=%lld B=%lld\n",
                               (long long)C, (long long)T, (long long)B);
    hits++;
    return y;
}

}  // namespace tllayout
