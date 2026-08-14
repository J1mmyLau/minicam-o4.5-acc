# 工程复现审计（干净环境）

> ⚠️ **已作废（SUPERSEDED）**：本文件是 2026-08-05 前序冻结（source `bdd4550` / server `db258375…` /
> libomni `c4b16937…`）的审计模板，其中 SHA 与 commit **不再**是提交身份。权威复现步骤见
> **`REPRODUCTION.md`**；权威 SHA 见 **`BINARY_PROVENANCE.md`**（当前 = `fd3dd36` / `4694cb58…` / `3f3e1e63…`）。

> 主办方会在官方环境重新部署并测试。本文件定义复现清单与审计流程。
> 目标：**一条命令从 checkout 到启动成功 → health → 冒烟 → Benchmark 小流量 → Demo → 性能采集**。
> 现状：构建侧已证 `REPRODUCIBLE_BINARY=PASS`（bdd4550 两次干净重建 SHA 逐字节一致）；干净环境完整时间线待官方环境验证。

---

## 1. 固定版本（不得漂移）

| 项 | 值 |
|---|---|
| 源码 | `bdd4550de931407ff5c1536fef50847e6c8332eb`（分支 `perf/f6-decode-to-speak`） |
| 证据文档 | `adb9bb6…` + `d5cc978…` + `f26323f…` |
| server SHA256 | `db258375c3d2185ca2181da2a5c8f99a95d381413fcb7ab92a771850ba3a4a21` |
| libomni SHA256 | `c4b169376bced6bc3107cfda2f77abf35a634c1e146eed313a193e99e3739ea1` |
| model SHA256 | `d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de` |
| CANN | 9.1.0-beta.1 |
| driver / OS / NPU | 记录于 `submission/environment/system_info.txt`（env_check.sh 采集） |

## 2. 干净环境步骤序列

```text
[自动] 1. env_check.sh        → 环境依赖、NPU、端口
[自动] 2. git clone + checkout bdd4550
[自动] 3. build.sh            → 目标构建（libomni.so + llama-omni-server）
[自动] 4. 重建 SHA 比对        → 与 db258375… / c4b16937… 一致（REPRODUCIBLE_BINARY）
[自动] 5. start_server.sh     → 启动冻结 env 服务
[自动] 6. health_check.sh     → /health OK
[自动] 7. smoke 小流量         → 最小 TTS 请求 + text 请求
[自动] 8. Benchmark 小流量     → 各 run_*.sh --smoke（官方口径就绪后全量）
[自动] 9. run_performance.sh  → chunk RTF 采集
[人工] 10. Demo 录像           → DEMO_VIDEO_SCRIPT.md
[人工] 11. 数据回填与报告
```

## 3. 审计记录字段（每次复现一份 JSON）

```text
source commit | docs commit | server SHA | libomni SHA | model SHA
CANN | driver | OS | NPU 拓扑 | CANN/OPP env
构建命令 | 启动命令 | 环境变量全集 | 数据版本
端口占用检查 | NPU 占用检查 | 时间戳 | run_id
```

## 4. 从零复现时间线（待官方环境验证后回填）

| 阶段 | 自动/人工 | 外部资产 | 预计时间 | 磁盘 | NPU 占用 | 已知失败恢复 |
|---|---|---|---|---|---|---|
| env_check | 自动 | 无 | — | — | 0 | 缺 env → 提示安装 |
| checkout | 自动 | git 可达 | — | ~1GB 源码 | 0 | 网络失败重试 |
| build | 自动 | CANN 工具链 | — | +几 GB | 编译期短暂 | 按编译日志修复 |
| SHA 比对 | 自动 | 无 | — | 0 | 0 | 不一致→检查源码/工具链 |
| 启动 | 自动 | model 文件 | — | +~50GB | 常驻 | 端口占用→换端口 |
| smoke/perf | 自动 | 无 | — | wav 输出 | 常驻 | 超时重试 |
| Demo | 人工 | 浏览器/录像 | — | 视频 | 常驻 | — |

## 5. 防复现失败清单（提交前逐项自检）

- [ ] 无脚本依赖本地私有绝对路径作为唯一默认值
- [ ] 不依赖 `/tmp` 持久化（重启即失）
- [ ] 源码 commit 与二进制 SHA 一一对应（manifest）
- [ ] 模型文件有 SHA + 获取方式说明
- [ ] 环境变量全集显式声明（含 ASCEND_RT_VISIBLE_DEVICES）
- [ ] 每条结果可一条命令复现，禁止手工改源码
- [ ] 启动/停止/健康脚本幂等

## 6. 当前结论
- `REPRODUCIBLE_BINARY = PASS`（本机两次重建一致）
- `OFFICIAL_REPRODUCTION_REVIEW = NOT_RUN`（官方环境复现待执行）
