// Fused zero-cat layout 桥接接口
#pragma once
#include "ggml.h"

namespace tllayout {

// concat(x, scale(x,0), dim=2) 的单节点等价替换 ([C,T,B] -> [C,T,2B], 纯布局)。
// 需 OMNI_TL_LAYOUT=1; 形状/类型不满足时返回 nullptr, 调用点回落到原 ggml 链。
ggml_tensor * try_zerocat2(ggml_context * ctx, ggml_tensor * x);

}  // namespace tllayout
