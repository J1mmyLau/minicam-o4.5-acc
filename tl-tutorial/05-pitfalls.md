# 05 · 血泪规则（10 条，全部实测撞过）

> 每条都是用 debug 时间换的。写 kernel 前过一遍，能省掉我们付过的学费。

## 性能类

### 1. 永远用 `T.tile.*`，不要写元素级循环

元素赋值写法退化到 **927µs**，tile 写法 **15.3µs**——差 6.5 倍。
不是风格问题，是能不能进向量指令的问题。`T.Parallel` 逐元素循环只在
tile op 覆盖不到的场合用（如 fused_rmsnorm 的残差双写）。

### 2. cos/sin / power 必须 host 预取

`tir` 里 `cos/sin/power` 支持有限，且在 kernel 里逐元素算三角函数
浪费算力。CPU 上按 pos 算好 `[T, half]` 表作为常量传入
（03 讲 fused_rope_tbl 的 v3 演进就是这条教训的现场）。

### 3. M < 2 / 非整除形状，官方 tiling 会崩

分块参数必须在外层 Python 护边界（`while N % block_N != 0`、
`if M % block_M != 0: block_M = vec_num`）。kernel 体内写不了这些逻辑。

### 4. 一个 kernel 能装下的一串算子，别拆开

decode 的墙是 launch 税（每步 ~1027 次 × ~30µs），不是算力。我们的
数据点：单算子换装全零收益；整段融合（norm+rope × 36 层）+66%。
**量级才是关键**——"墙不可动"的单点结论都是错的，错在没融合够长。

## 正确性类

### 5. `T.tile.rsqrt` 是快速近似（~3e-3 误差）

位级 parity 过不了就用 `fill(1.0) → sqrt → div` 三连精确实现
（03 讲 fused_rmsnorm 现场示范）。

### 6. dtype 纪律：fp32 累加，边界转换

bf16 直接乘加累加会崩精度。进 UB 先 `CAST_NONE` 到 fp32，算完
`CAST_RINT` 回去。和 GGUF 量化里 roundf/rint 的教训同族。

### 7. 1-D copy 进 2-D tile 是垃圾数据

形状必须先对齐（`T.tile.broadcast` 把 `[ROWS,1]` 广播成 `[ROWS,block_N]`），
不能指望隐式广播。

### 8. kernel 输出错了，先查数据依赖，再怀疑数学

真实案例（04 讲）：conv1d 输出噪声，看着像卷积写错，实际是
**cast 流竞态 + galloc 地址复用**。修复 = 根 F32 回溯重排缓存。
配套：host 读图节点必须 `SynchronizeStream`；自定义回调**禁止自同步
当前流**（会 segfault），用异步 D2D + memset。

## 流程类

### 9. 桥接层先做位级对拍，再看性能

我们 QKR 第一版 +66% 变成"输出错"：桥接**双重 RoPE + `view_3d` 步长错**，
TileLang 无辜。流程永远是：参考实现 → `bridge_parity_probe.py` 对拍 →
过了才准计时。dump 对拍数据时还要小心：越界 dump + 变长记录定长解析
会制造流竞态幻影。

### 10. 对照必须归一化模型加载（冷热缓存 160s vs 7s 会假扮 40% 增益）

性能结论只认配对 A/B：同 seed、同 harness、4-run mean±stdev；
单 run 方差 ±0.04 什么都证明不了。
