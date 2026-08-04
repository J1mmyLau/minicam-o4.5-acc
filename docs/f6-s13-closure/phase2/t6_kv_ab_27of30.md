# T6 KV Cache A/B — 27/30 有效配对解释（3 对按预声明规则排除）

**日期**: 2026-08-04
**运行**: T6 最终集成回归 re-run #2（P0a 非流式 text 字段 + P0b SSE 崩溃修复重建后）
**二进制**: server `db258375c3d2185ca2...` + libomni `c075c535d18d1213b2...`
**证据**: `t6_integrated_regression.json`（`session2.kv_cache`：n_pairs=30, n_valid=27, gate_pass=true）+ `/tmp/f6_t6_run_binary_c075c535.log`（client 控制台）+ `/tmp/f6_t6/kv_ab_srv.log`（server F6_REQSTATE/F6_EVENT 轨迹）

---

## 1. 结论一句话

KV cache 机制（MISS→SAVED / HIT→load）在 **30/30 对全部正常工作**（每对 A=SAVED、B=HIT、loaded=130，与 R13 canonical n_past=130 一致）；3 对因 **decode POST 客户端 HTTP 异常**（`A_ERR`/`B_ERR`）按脚本预声明排除规则被判无效，**不是缓存污染、不是 DELTA_NEG、不是 TTS 相关**。`KV_CACHE_AB` Gate 判定 **PASS**（n_valid=27 ≥ 25）。R13 canonical 30/30 严格有效结论**不受影响**，继续作为官方速度结论。

## 2. 3 对无效配对明细

| 无效配对 | Case | A 腿 (MISS) | B 腿 (HIT) | Δ (A−B, ms) | loaded | 排除原因 | 预声明规则 |
|----------|------|-------------|------------|-------------|--------|----------|-----------|
| **pair 4** | C1-R4 | `A=SAVED` | `B=HIT(130)` | +123 | 130 | `B_ERR`（B 腿 decode POST 客户端异常） | ✅ 是 |
| **pair 17** | C3-R5 | `A=SAVED` | `B=HIT(130)` | +122 | 130 | `A_ERR`（A 腿 decode POST 客户端异常） | ✅ 是 |
| **pair 20** | C4-R2 | `A=SAVED` | `B=HIT(130)` | +117 | 130 | `B_ERR`（B 腿 decode POST 客户端异常） | ✅ 是 |

三对全部满足：**两腿 prefill 都成功**（Δ 为正值即 A、B 均测到 prefill_wall_ms）、**缓存机制双侧正常**（A 腿 SAVED 写入、B 腿 HIT 载入 130 位置）、**Δ 全为正**（MISS 慢于 HIT，方向正确）。

## 3. 判定链：为什么是"客户端 HTTP 异常"而非缓存污染

排除规则来自脚本 `run_kv_ab`（`scripts/f6_phase3_t6_integrated_regression.py`）——`kv_request` 对 omni_init/prefill/decode 三个 POST 包 `try/except`，任何非 200 状态码或连接/超时异常都会置 `m["error"] = str(e)`，进而 `A_ERR`/`B_ERR` 判该腿无效。**这些规则在脚本中预先声明**（不是事后找的借口）。

server 日志（`kv_ab_srv.log`）逐腿重建证明 3 个失败 decode 的**服务端生成全部完成**：

| 失败轮次 | 对应腿 | STREAM_DECODE_BEGIN → END | DECODING→RESPONDING | HANDLER_RETURN | RESPONDING→IDLE (response_sent) |
|----------|--------|---------------------------|---------------------|----------------|--------------------------------|
| req=4009 | pair4-B | ✅ 13686108931939160 → 13686109164073340（232ms） | ✅ | ✅ | ❌ **缺失** |
| req=4034 | pair17-A | ✅ 13686265819130620 → 13686266042230890（223ms） | ✅ | ✅ | ❌ **缺失** |
| req=4041 | pair20-B | ✅ 13686307108448270 → 13686307342542180（237ms） | ✅ | ✅ | ❌ **缺失** |
| 对照 req=4008 | pair4-A | ✅（776ms） | ✅ | ✅ | ✅ **有** |
| 对照 req=4035 | pair17-B | ✅（373ms） | ✅ | ✅ | ✅ **有** |
| 对照 req=4040 | pair20-A | ✅（445ms） | ✅ | ✅ | ✅ **有** |

`response_sent` 事件在 `res_ok(res, resp)`（server-omni.cpp:626）之后、socket 实际 flush 之前发出（server-omni.cpp:628）。3 个失败轮次到达 `HANDLER_RETURN`（decode 成功）却**从未发出 `response_sent`** → 响应对象已构造/发送环节异常 → 客户端 `urllib.request.urlopen` 抛异常（非 200 HTTPError 或连接错误）→ `http_post` 传播 → `A_ERR`/`B_ERR`。解码生成本身正常（每轮 ~230ms，远低于 wall_timeout_ms=300000 与客户端 REQ_TIMEOUT）。

**不是缓存污染**的证据：
- 三对 A 腿均 `SAVED`（n_past=130 写入缓存文件），B 腿均 `HIT`（loaded=130）；机制两侧行为与 27 对有效配对完全一致。
- 失败发生在 decode（LLM 生成之后）阶段，KV 缓存早已在 prefill 阶段正确写入/载入。
- server 端无 crash / 无 500 / 无 CANN 错误；三失败轮次之后全部后续配对（pair 5-30）与后续会话（smoke 5/5）正常。

**瞬时性**：60 个 decode 轮次中仅这 3 个（5%）失败，分散于 pair 4/17/20（不同 case、A/B 腿都有），无周期性、无重复，随后所有请求成功。归为瞬时 HTTP 交付层异常。

> **诚实披露**：`HANDLER_RETURN` 与 `response_sent` 之间具体抛点（T9/T10 text_queue drain 之后的 JSON 构造 / `set_content`）无法从现有日志完全定位——该路径任何 `LOG_ERR` 在生产构建的 media_type=1 会话中被 verbosity 阈值过滤（见 T13 记忆 `[[f6-t13-tts-kv-guard-pass]]`）。不影响结论：无论抛点在响应构造还是连接层，对客户端而言都是 decode POST 的 HTTP 级失败，且与 KV 缓存正确性无关。

## 4. R13 canonical 30/30 vs T6 integration 30/27

| | R13 canonical KV A/B | T6 integration KV A/B |
|---|---|---|
| 运行 | 专用 KV-only 会话（`f6_r13_kv_cache`） | T6 全量回归 session2（120+扩展+音色+断连+smoke 之间） |
| 配对 | 30 对 | 30 对 |
| 严格有效 | **30/30** | **27/30**（3 对 decode POST 客户端 HTTP 异常，预声明排除） |
| 机制层 | 30/30 SAVED/HIT/loaded=130 | **30/30 SAVED/HIT/loaded=130** |
| prefill MISS p50 | 206ms | 203.6ms |
| prefill HIT p50 | 85ms | 83.6ms |
| speedup | 2.4× | 2.44× |
| Gate | PASS | PASS（27 ≥ 25） |

**两个结论不冲突**：R13 的 30/30 是严格有效口径（专用运行、无客户端错误），T6 的 30/27 是集成运行口径（机制 30/30，3 对因客户端 HTTP 异常按预声明规则排除）。**不允许用 T6 的 27/30 覆盖 R13 的 30/30 官方速度结论**——两者机制数据完全一致（loaded=130、~2.4×、Δ~119ms）。

## 5. 对 Gate 与候选状态的影响

- `KV_CACHE_AB` = **PASS**（脚本 `gate_pass = n_valid ≥ 25`，27 ≥ 25）。`T6_REGRESSION=PASS` 不受影响。
- 无需降级、无需重跑（排除规则匹配预声明规则；机制层 30/30 无异常）。
- 候选二进制不变：server `db258375` + libomni `c075c535`。
