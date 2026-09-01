# 07 · 练习路线（本机 910C 直接跑）

> 顺序做。每个练习都有明确的"你能观察到什么"——观察不到就说明环境或
> 理解出了问题，先解决再往下走。

## 环境准备

```bash
export PYTHONPATH=/path/to/tilelang-ascend   # 换成你的 tilelang-ascend 检出路径
export ASCEND_RT_VISIBLE_DEVICES=1        # pin 单 die，跨 die 拿垃圾数值
# 检查：python -c "import tilelang, torch_npu; print('ok')"
```

## Level 1：跑通与观察（01 讲配套）

**E1. Hello World**
```bash
python code/elementwise_add.py --m 1024 --n 1024
```
改 `block_M, block_N` 为 `(8, 4096)` / `(1024, 32)`，观察编译成败与耗时
变化。**观察点**：UB 面积守恒——块太大编译期就报，块太碎性能差。

**E2. 模板对拍**
```bash
python code/rms_norm.py
```
官方模板自带 6 组形状对拍。**观察点**：N=51200 的用例为什么必须横切。

## Level 2：亲手制造一次退化（05 讲规则 1）

**E3. 向量化对比实验**
复制 `code/rms_norm.py` 为 `my_rms_norm.py`，把两处
```python
T.tile.mul(a_ub_cast_0, a_ub_cast_0, a_ub_cast_0)
T.tile.add(sum_sq_acc, sum_sq_acc, a_ub_cast_0)
```
换成元素写法（`T.Parallel` 逐元素循环 + `sum_sq_acc[i] += ...`），
重跑 N=16384 的 bf16 用例计时。**观察点**：数量级级别的变慢——
这就是"必须用 tile-op"的体感。

**E4. dtype 纪律实验**
把 `acc_dtype` 强制改成输入 dtype（删掉 cast 分支），对拍看误差。
**观察点**：bf16 直接累加 51200 长度的误差爆炸。

## Level 3：读懂生产代码（03 讲配套）

**E5. RoPE 分法实验**
把 `fused_rope_tbl` 的 `T.Kernel(1)` 改成 `T.Kernel(T_len)`（一核一
token，cs/sn 按 cid 行取），对拍。**思考题**：T=1 的 decode 场景哪个赢？
T=4096 的 prefill 呢？（答案方向：小 T 单核少 launch 赢；大 T 并行度赢。）

**E6. 生产 kernel 测试**
```bash
python code/test_qknorm_rope.py
```
读懂它的断言，然后给它加一个 T=8、pos 不连续的用例。

**E7. AOT 上手**
照 `code/aot_llm_kernels.py` 的模式，把你 E5 改的 kernel 编成一个
`myrope_*.so`。**观察点**：`k.get_kernel_source()` 打出来看一眼——
那就是生成的 CCE 代码。

## Level 4：桥接视角（06 讲配套）

**E8. parity 探针**
```bash
python code/bridge_parity_probe.py
```
**观察点**：rel 应该在 1e-7 量级。改大 T 到 4104 以上再跑——
表上限（我们踩过的 4104 坑）会在哪里报错？

**E9.（进阶）端到端 A/B**
在有 submission 环境的机器上：
```bash
./submission/scripts/run_rts.sh 1001    # OMNI_TL_* 全开
OMNI_TL_QKR=0 OMNI_TL_NORM=0 ./submission/scripts/run_rts.sh 1001
```
对比 core RTF。**观察点**：单 run 方差 ±0.04——这就是为什么结论必须
4-run。**注意**：这个练习动真实服务，做完把 env 恢复。

## 自测清单（全部能答出来就毕业）

- [ ] tile-op 和元素循环差多少倍？为什么？
- [ ] cos/sin 表为什么必须在 host 预取？
- [ ] two-pass 为什么要读两遍输入？
- [ ] `T.tile.rsqrt` 什么时候不能用？替代写法？
- [ ] 我们的单算子替换为什么全零，整段融合为什么 +66%？
- [ ] bucket 化是为了解决什么问题？没命中 bucket 会怎样？
- [ ] kernel 输出噪声，你的排查顺序是什么？
- [ ] 性能结论的最低证据标准是什么？（同 seed / 归一化加载 / 4-run / 位级 parity）

能答出最后一题，你就已经掌握了这个项目里最值钱的方法论：
**evidence-driven performance engineering**。
