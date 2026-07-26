# CANNBot Skills Installation Audit

**Date:** 2026-07-26 06:55 UTC
**Auditor:** Claude Code (read-only, no modifications)
**Scope:** `~/.claude` skills/plugins/agents, `install-helper`, `/root/.cannbot/repo/`

---

## 1. Executive Summary

| Attribute | Status |
|-----------|--------|
| `install-helper` version | **v1.1.3** ✅ (npm global, symlinked into Trae) |
| CANNBot repo cloned | **YES** — `/root/.cannbot/repo/` (HEAD: `86b6a7f`, 2026-07-26 clone) |
| Old repo copies | `/workspace/llama.cpp-omni/third_party/cannbot-skills/` (HEAD: `5b1802b`, Jul 16) |
| Skills installed to `~/.claude/` | **ZERO** ❌ |
| Plugins registered | **ZERO** ❌ |
| Agents installed | **ZERO** ❌ |
| Claude Code version | v2.1.197 ✅ |
| CANN toolkit | CANN 9.1.0-beta.1 ✅ |

**Root Cause**: The previous `bootstrap_cannbot.sh` (at `minicpmo45-ascend-cc-harness/scripts/`) is a **prepare-only script** — it clones the repository but **never calls `install-helper install`** to register skills/plugins/agents with Claude Code. The repo content is fully present on disk (95+ skills, 12 official plugins, 14 community plugins), but Claude Code cannot discover any of them because nothing was linked into `~/.claude/skills/`, `~/.claude/plugins/`, or `~/.claude/agents/`.

---

## 2. Detailed Findings

### 2.1 install-helper

```
Path:      /root/.trae-cn-server/binaries/node/versions/20.20.2/bin/install-helper
Target:    ../lib/node_modules/@cannbot-ai/install-helper/bin/install-helper.js
Version:   1.1.3
Commands:  init, list, doctor, status, install, uninstall, update, info, lang
```

### 2.2 `install-helper doctor` Result

All 10 official plugins report **未安装** (not installed):

| Plugin | Status |
|--------|--------|
| ops-direct-invoke | 未安装 |
| ops-direct-invoke-flash | 未安装 |
| ops-registry-invoke | 未安装 |
| catlass-op-generator | 未安装 |
| model-infer-optimize | 未安装 |
| pypto-op-orchestrator | 未安装 |
| tilelang-op-orchestrator | 未安装 |
| triton-op-generator | 未安装 |
| torch-compile | 未安装 |
| ops-code-reviewer | 未安装 |

Doctor also **repaired** two issues:
- Created `~/.claude/skills/` (was missing)
- Created `~/.claude/agents/` (was missing)

### 2.3 `~/.claude/` Directory State

```
~/.claude/
├── plugins/
│   ├── known_marketplaces.json    ← only Anthropic official marketplace
│   └── marketplaces/
│       └── claude-plugins-official/
├── skills/                        ← EMPTY (created by doctor)
├── agents/                        ← EMPTY (created by doctor)
└── (no SKILL.md, no AGENTS.md, no plugin.json from CANNBot)
```

**Zero CANNBot skills, agents, workflows, or plugins are discoverable by Claude Code.**

### 2.4 Repository Content (on disk, NOT installed)

The repo at `/root/.cannbot/repo/` (HEAD: `86b6a7f`) contains:

#### Official Plugins (12)
| Plugin | `.claude-plugin` | agents/ | skills/ | workflows/ | hooks/ |
|--------|:---:|:---:|:---:|:---:|:---:|
| model-infer-optimize | ✅ | ✅ | — | ✅ | ✅ |
| model-infer-sota-approach | ✅ | ✅ | — | ✅ | — |
| ops-direct-invoke | ✅ | ✅ | — | ✅ | ✅ |
| ops-direct-invoke-flash | ✅ | ✅ | ✅ | — | — |
| ops-registry-invoke | ✅ | ✅ | ✅ | — | ✅ |
| catlass-op-generator | ✅ | ✅ | — | ✅ | ✅ |
| pypto-op-orchestrator | ✅ | ✅ | — | — | ✅ |
| tilelang-op-orchestrator | ✅ | ✅ | — | — | ✅ |
| triton-op-generator | ✅ | — | — | — | — |
| torch-compile | ✅ | ✅ | — | — | ✅ |
| ops-code-reviewer | ✅ | ✅ | — | — | ✅ |

#### Community Plugins (14)
| Plugin | Type |
|--------|------|
| autoresearch | plugin |
| cannbot-insight | plugin |
| cannbot-knowledge | plugin |
| collaborative-agent-kernel-evolution | plugin |
| cuda2ascend | plugin |
| install-helper | tooling |
| ops-easyasc-dsl | plugin |
| ops-perf-evolution | plugin |
| ops-perf-optimize | plugin |
| ops-qa-suite | plugin |
| science-model-npu-migration | plugin |
| tilelang2ascendc-ops-generator | plugin |
| triton-optimizer | plugin |

#### Skills by Category (repo directories)

| Category | Count | Key Skills |
|----------|-------|------------|
| **model/** | 19 | infer-profiling, infer-perf-breakdown, infer-kvcache, infer-fusion, infer-multi-stream, infer-parallel-analysis, infer-parallel-impl, infer-quantization, infer-prefetch, infer-superkernel, infer-precision-debug, infer-runtime-debug, infer-migrator, infer-graph-mode, infer-harmony, train-oom-analysis, train-accuracy-debug, train-log-visualization |
| **ops/** | 62 | ascendc-env-check, ascendc-tiling-design, ascendc-code-review, ascendc-precision-debug, ascendc-runtime-debug, ascendc-perf-optimize, ascendc-performance-best-practices, ascendc-api-best-practices, ascendc-direct-invoke-template, ascendc-st-design, ascendc-ut-develop, ascenc-simt-*, npu-arch, ops-profiling, ops-spec-gen, ops-simulator, ops-precision-standard, tilelang-*, triton-*, catlass-*, pypto-*, cann-env-setup, torch-ops-profiler, torch-ascendc-op-extension |
| **graph/** | 8 | torch-npugraph-ex-* (compile, template, compile-error-diagnosis, dfx-triage, knowledge, performance-diagnosis, runtime-error-diagnosis), torch-custom-ops-guide |
| **infra/** | 6 | cannbot-skill-reviewer, gitcode-issue-gen, gitcode-issue-handler, gitcode-pr-handler, gitcode-toolkit |
| **runtime/** | 1 | runtime_migration |

---

## 3. Capability Checklist

### 3.1 Model Inference (requested)

| Capability | Repo Exists | Installed to ~/.claude | Classification |
|------------|:-----------:|:----------------------:|----------------|
| model-infer-profiling | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| model-infer-perf-breakdown | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| model-infer-sota-approach | ✅ (plugin) | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| model-infer-fusion | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| model-infer-kvcache | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| model-infer-multi-stream | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| model-infer-parallel-analysis | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| model-infer-parallel-impl | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| model-infer-quantization | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| model-infer-superkernel | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| model-infer-migrator | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |

### 3.2 AscendC (requested)

| Capability | Repo Exists | Installed | Classification |
|------------|:-----------:|:---------:|----------------|
| ascendc-env-check | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| npu-arch | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| ascendc-tiling-design | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| ascendc-performance-best-practices | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| ascendc-precision-debug | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| ascendc-runtime-debug | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| ascendc-code-review | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| ascendc-direct-invoke-template | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| ops-profiling | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |

### 3.3 TileLang (requested)

| Capability | Repo Exists | Installed | Classification |
|------------|:-----------:|:---------:|----------------|
| tilelang-env-check | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| tilelang-submodule-pull | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| tilelang-op-design | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| tilelang-op-develop | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| tilelang-perf-optimization | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| tilelang-op-test-design | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| tilelang-api-best-practices | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| tilelang-programming-model-guide | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| tilelang-review | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |

### 3.4 Triton (requested)

| Capability | Repo Exists | Installed | Classification |
|------------|:-----------:|:---------:|----------------|
| triton-task-extractor | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| triton-op-designer | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| triton-op-coding | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| triton-op-verifier | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| triton-latency-optimizer | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |
| triton-simulator-optimizer | ✅ | ❌ | FILES_PRESENT_BUT_NOT_REGISTERED |

---

## 4. External Dependencies

| Dependency | Status | Path |
|-----------|--------|------|
| CANN 9.1.0-beta.1 | ✅ INSTALLED | `/usr/local/Ascend/cann-9.1.0-beta.1` |
| CANN ascend-toolkit/latest | ✅ INSTALLED | `/usr/local/Ascend/ascend-toolkit/latest` |
| NPU driver | ✅ INSTALLED | `/usr/local/Ascend/driver` |
| ATB (nnal) | ✅ INSTALLED | `/usr/local/Ascend/nnal/atb` |
| GCC toolchain | ✅ | `Ascend/cann-9.1.0-beta.1/toolkit` |
| Python 3.12 | ✅ | `/usr/local/python3.12.13/bin` |
| AscendPyTorch (torch_npu) | ⚠️ UNKNOWN | `PYTHONPATH` includes CANN python |
| tilelang-ascend | ❌ NOT_FOUND | Required for TileLang path |
| asc-devkit | ❌ NOT_FOUND | Required for AscendC dev |
| cann-samples | ❌ NOT_FOUND | Reference code |
| PyPTO runtime | ❌ NOT_FOUND | Only templates in repo, no installed runtime |

### Environment Variables (already configured)

```
ASCEND_HOME_PATH=/usr/local/Ascend/cann-9.1.0-beta.1
ASCEND_TOOLKIT_HOME=/usr/local/Ascend/cann-9.1.0-beta.1
LD_LIBRARY_PATH=...cann-9.1.0-beta.1/lib64...
PYTHONPATH=...cann-9.1.0-beta.1/python/site-packages...
```

---

## 5. Gap Analysis

### What's Working
- `install-helper` v1.1.3 functional, can `list`/`install`/`doctor`
- CANN 9.1.0-beta.1 toolchain complete with drivers
- Repo cloned with latest content (86b6a7f, "A5 ascend/triton skills")
- Claude Code v2.1.197 detected and supported
- All 95+ skills present in repo on disk

### What's NOT Working
1. **Zero skills linked to `~/.claude/skills/`** — Claude Code cannot discover any CANNBot skill
2. **Zero plugins registered** — no `.claude-plugin` manifests linked; `install-helper doctor` confirms all 10 as "未安装"
3. **Zero agents in `~/.claude/agents/`** — no CANNBot agents available
4. **Old bootstrap script incomplete** — `minicpmo45-ascend-cc-harness/scripts/bootstrap_cannbot.sh` only clones repo, never installs
5. **External deps missing**: `tilelang-ascend`, `asc-devkit`, `cann-samples`, PyPTO runtime

### Classification Summary

| Classification | Count |
|----------------|-------|
| INSTALLED_AND_DISCOVERABLE | 0 |
| FILES_PRESENT_BUT_NOT_REGISTERED | 95+ skills, 26 plugins |
| OUTDATED | 0 (repo is fresh) |
| MISSING | 4 external deps |
| BROKEN_SYMLINK | 0 |
| EXTERNAL_DEPENDENCY_MISSING | tilelang-ascend, asc-devkit, cann-samples, PyPTO |

---

## 6. Recommended Minimal Install Set

For the `llama.cpp-omni` operator optimization project, install these first:

```bash
# Model inference profiling (phase 1: find hotspots)
install-helper install model-infer-profiling model-infer-perf-breakdown

# SOTA approach orchestrator (phase 2: profiling-driven optimization)
install-helper install model-infer-sota-approach

# AscendC path (phase 3: kernel development)
install-helper install ops-direct-invoke ops-profiling ascendc-env-check npu-arch

# TileLang path (alternative to AscendC)
install-helper install tilelang-env-check tilelang-op-design tilelang-op-develop

# Triton path (alternative to AscendC)
install-helper install triton-task-extractor triton-op-designer triton-op-coding
```

**After install, restart Claude Code** to pick up new skills.

---

## 7. Recommended Complete Install

```bash
# Full model inference suite
install-helper install model-infer-optimize model-infer-sota-approach

# Full AscendC suite
install-helper install ops-direct-invoke ops-direct-invoke-flash

# Full TileLang suite
install-helper install tilelang-op-orchestrator

# Full Triton suite
install-helper install triton-op-generator

# Support
install-helper install ops-code-reviewer cannbot-knowledge
```

### External Dependencies to Install Separately

```bash
# tilelang-ascend (required for TileLang path)
# git clone <tilelang-ascend-repo> /workspace/tilelang-ascend

# asc-devkit (required for AscendC dev)
# Check with: install-helper doctor

# cann-samples (reference code)
# Check CANN installation: /usr/local/Ascend/cann-9.1.0-beta.1/samples/
```

---

## 8. Bootstrap Script Deficiency

The existing bootstrap script at `/workspace/minicpmo45-ascend-cc-harness/scripts/bootstrap_cannbot.sh` only implements a `prepare` mode:

```bash
prepare() {
  git clone .../cannbot-skills.git "${THIRD_PARTY}"
  git checkout "${REF}"
  # Records version info → STOP. Never calls install-helper install.
}
```

**Missing step**: After cloning, it should run:
```bash
install-helper install --tool claude --level project -y <skill-names>
```

This is why everything is on disk but nothing is registered with Claude Code.

---

## 9. Phased Install Plan (DECIDED)

**Decision**: Do NOT install now. Stage B is running. Install after Stage B gate completes.

### Phase 1: Profiling Core (install immediately after Stage B gate)

```bash
install-helper install \
  model-infer-profiling \
  model-infer-perf-breakdown \
  model-infer-sota-approach \
  ops-profiling \
  ascendc-env-check \
  npu-arch
```

Then:
```bash
install-helper doctor --fix
# Exit Claude Code: /exit
# Restart Claude Code: claude
# Verify: list discoverable plugins and skills
```

Purpose: model-level profiling → module/op breakdown → hotspot identification → decide AscendC/TileLang/Triton.

### Phase 2: Operator Dev Stack (only after profiling identifies hotspots)

Pick ONE based on hotspot characteristics:

**AscendC** (best performance control, highest dev cost):
```bash
install-helper install \
  ascendc-tiling-design \
  ascendc-performance-best-practices \
  ascendc-precision-debug \
  ascendc-runtime-debug \
  ascendc-code-review
```

**TileLang** (higher-level, structured ops):
```bash
install-helper install \
  tilelang-env-check \
  tilelang-op-design \
  tilelang-op-develop \
  tilelang-perf-optimization
# + external dep: tilelang-ascend
```

**Triton** (fast dev, block-level parallelism):
```bash
install-helper install \
  triton-task-extractor \
  triton-op-designer \
  triton-op-coding \
  triton-op-verifier \
  triton-latency-optimizer
```

### Rationale

- Do NOT install all three stacks at once — let profiling data decide
- Phase 1 alone is sufficient to identify Top-K hotspots and choose the right stack
- Each additional stack may pull large external deps (tilelang-ascend, asc-devkit, PyPTO)
- Installing mid-soak risks environment changes affecting the runner

---

## 10. Claude Code Restart Required

After running `install-helper install`, Claude Code **must be restarted** to discover new skills, plugins, and agents. The current session will not see newly installed capabilities until restart.

---

## 11. Production Status Unchanged

```
KV_CACHE_PRODUCTION: OPT_IN_READY / DEFAULT_OFF
Stage B (6h): RUNNING (PID 160616, 175 iters at 07:05 UTC, ETA ~11:08 UTC)
```

This audit is read-only. No files modified. No experiments interrupted.

---

**报告路径:** `docs/experiments/operator-optimization/CANNBOT_INSTALL_AUDIT.md`
**最后更新:** 2026-07-26 07:05 UTC (added phased install plan)
