// TileLang conv1d 桥接接口
#pragma once
#include "ggml.h"

namespace tlconv {

typedef void (*tl_call_fn)(void * x, void * w, void * y, void * stream);

// 返回 true = 该形状可用 TileLang（或仅日志模式打印形状）
// key: (Cin, Cout, K, dilation, T_out)
bool maybe_log(int64_t cin, int64_t cout, int64_t k, int64_t dil, int64_t t);

// ggml CUSTOM 回调: dst = CUSTOM(x_f16 [TP,Cin] T-fast, w_f16 [K,Cin,Cout]) -> y_f16 [T,Cout] T-fast
void conv1d_cb(ggml_tensor * dst, int ith, int nth, void * userdata);

// 统一接入: 命中注册形状时构建 [pad -> cast -> CUSTOM -> cast -> cont -> reshape] 链，
// 返回 y_tcb [T, Cout, B]（T-fast，含 pad 使 L_out==T 的调用约定）；未命中返回 nullptr。
// 仅支持 stride==1 / B==1 / F32 输入（vocoder resblock/f0/hift conv 形态）。
ggml_tensor * try_conv1d(ggml_context * ctx, ggml_tensor * w_kic_oc, ggml_tensor * x_tcb,
                         int padding, int dilation);

// graph_compute 全部完成后调用：校验首个 CUSTOM 输出是否被后续节点覆盖
void verify_after_compute();
void track_y32(ggml_tensor * y32);

// flow LayerNorm 融合: y = LN(x)*w + b，CUSTOM(x16,w16,b16)->y16->F32
ggml_tensor * try_layernorm(ggml_context * ctx, ggml_tensor * x, ggml_tensor * w,
                            ggml_tensor * b, float eps);

}  // namespace tlconv
