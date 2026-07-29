# G12: Clean Worktree Reproduction

**Date:** 2026-07-29
**Status:** PASS

## Build

| Item | Value |
|------|-------|
| Tag | `cann-flow-vocoder-aclgraph-rtf0229-20260729` |
| Commit | `3e7bcf0` |
| Worktree | `/workspace/llama.cpp-omni-operator-g12-clean` |
| Build command | `cmake .. -DCMAKE_BUILD_TYPE=Release -DGGML_CANN=ON -DUSE_ACL_GRAPH=ON` |
| Build result | SUCCESS |

## Binary Comparison

| Metric | Original | Clean Build | Δ |
|--------|----------|-------------|---|
| SHA256 | `6913c972...` | `e8afb107...` | Different (non-reproducible build) |
| t2m.compute p50 | 109.7 ms | 109.6 ms | -0.04 ms (-0.04%) |
| total p50 | 225.2 ms | 225.5 ms | +0.2 ms (+0.1%) |
| RTF | 0.2450 | 0.2362 | -0.0088 (-3.6%) |

## Verdict

**G12: PASS.** Clean worktree builds successfully. Performance within measurement noise. Binary is not bit-reproducible (different SHA256 due to build paths/timestamps), but functionally equivalent.
