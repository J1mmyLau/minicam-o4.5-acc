# 09 · 踩坑与经验（接手必读）

> 全部来自实测撞墙，按「坑 → 后果 → 对策」记录。分四类。

## A. 环境与设备

| # | 坑 | 对策 |
|---|---|---|
| A1 | **EZ1002**：终端 ASCEND_OPP_PATH 未设置/未 export/失效，任一都让首个 aclnn 算子 init 崩（server 首个 prefill 死，客户端只看到 RemoteProtocolError） | 启动脚本**无条件** source `set_env.sh` + 显式 export + 硬校验 OPP 含 `built-in` **或** `builtin`（真实目录叫 built-in） |
| A2 | 910C dual-die 跨 die 拿垃圾数值 | 永远 `ASCEND_RT_VISIBLE_DEVICES` pin 单 die |
| A3 | **FA NaN**：Q≥435 @ KV≥768 触发（FusedInferAttentionScoreV2）；`aclnnMm` 也能从有限输入产 NaN | 精度路径 MAX_UBATCH=16 + Q-split 0；media embd decode 在 KV≥768 必须 batch≤16 |
| A4 | 冷热模型加载 160s vs 7s | **对照必须归一化模型加载**，否则冷启动会假扮 40% 增益 |

## B. 测量与口径

| # | 坑 | 对策 |
|---|---|---|
| B1 | `run_eval.sh` 的 `set -a; source $EVAL_CONFIG` **覆盖 launch env**（两次回归：NFE5 杀 NFE2→0 WAV；perf 全关块误入→RTF 0.62） | config 文件不写与 launch 注入同名的变量；**精度隔离唯一载体 = config-accuracy.env** |
| B2 | perf env 混入精度 CLI → 30k-token prefill logits 污染（VideoMME 69.8→8%） | 双 env 严格分离（server.env vs config-accuracy.env） |
| B3 | 单 run RTF 方差 ±0.04（token2wav 抖动主导） | 结论只看 4-run mean±stdev |
| B4 | `pkill -f llama-omni-server` 自杀（-f 匹配到自身命令行，exit 144） | `ps aux \| grep "[l]lama-omni-server" \| awk '{print $2}' \| xargs -r kill` |
| B5 | **acceptance ≠ TPS**；旧「图像 40-73%」是回声假象（裸 prompt 无 chat template，target 复读指令） | acceptance 测量必须带 ChatML template；加速只认 k-sweep 实测 |
| B6 | zombie NPU 进程污染 bisect（假阳性回归） | 对照前清干净 NPU 进程 |

## C. 模型与数据

| # | 坑 | 对策 |
|---|---|---|
| C1 | ffmpeg `scale=448:448` 拉伸帧 → vision embedding 内容坏（多帧 MM acceptance 0% 根因之一） | 帧抽取保持**原生分辨率** |
| C2 | B300/transformers 4.51：`torch_dtype=` 不是 `dtype=`；复合多模态 target 必须 `AutoModel + trust_remote_code` 取 `.llm` | 按此加载；上游代码对着 5.x 写的 |
| C3 | 8 个 `training_state.rank*.pt` 不是 8 个模型（99.9994% 是 optimizer state） | 拷推理权重时 exclude；LR schedule 从 next_micro_step 重算 |
| C4 | `llama-mtmd-cli` 不可作对照（single-turn 再包模板+默认历史） | 用自家 harness；llama-speculative example 不填 20480 维条件张量勿用 |
| C5 | dspark 树 `-md` CLI 被 arg 解析接受但 **omni_init 不消费** | 开关是 env `OMNI_SPEC_DRAFT`；判别=日志找 loading DSpark draft model |

## D. 开发与内核

| # | 坑 | 对策 |
|---|---|---|
| D1 | **必须编 `llama-server` target**，否则 so 不更新（stage8 先例：以为改了代码其实跑的旧库） | 改 omni 代码后定向编 server |
| D2 | TileLang 桥初版**双重 RoPE + view_3d 步长错**；dump 越界+变长记录定长解析制造流竞态幻影 | 桥接层先做位级对拍再谈性能 |
| D3 | tile-op 元素赋值写法退化 927µs（向量化差 6.5×）；tir.cos 不支持须 host 预取 | 用 tile.fill/reduce 范式写法 |
| D4 | CUSTOM 回调**禁自同步当前流**（segfault） | 异步 D2D + memset |
| D5 | ggml 输入存储会被临时复用 → 多 shape 图缓存命中必须**按 entry 重传常量**（否则全幅噪声静默通过） | parity 测试要覆盖命中路径 |
| D6 | cast 流竞态 + galloc 地址复用制造「conv 语义错」假象 | 根 F32 回溯重排缓存；host 读图节点须 SynchronizeStream |
| D7 | GGUF writer：`<Q` 前缀 + 32 字节对齐 offset；Q8 用 roundf 非 rint；torch (out,in) 即 ggml ne=(K,N) **不转置** | 量化器与 llama-quantize 位级对拍后再用 |
| D8 | markov/全 Q8 崩 `aclnn_mul` NZ-offset | 方案 C：markov_w1/w2 保持不量化 |
| D9 | `llama_batch_get_one().pos == nullptr` 写 pos 前必须显式 init | rollout_dump 教训 |
| D10 | huggingface.co 直连不通、GitHub 22 端口超时 | `ssh.github.com:443` + deploy key；push URL `ssh://git@ssh.github.com:443/<owner>/<repo>.git` |

## 术语约定

- 禁用「门禁」；用 infra 术语「准入标准 / 验收 / 达标线」。
- 提交文档不得出现不符合要求的自我否定表述（如实申报类措辞已合规化）。
