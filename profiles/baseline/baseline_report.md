# Baseline Report: Decode-to-Speak Wall-Clock Timing
## 2026-07-28 06:45 UTC
## Binary: 6913c972b30177fd
## Model: MiniCPM-o-4_5-Q4_K_M.gguf

## Test Case 0 (SHORT)

| Run | Wall (ms) | Exit | stderr lines |
|-----|-----------|------|-------------|
| 1 | 183228 | 0 | 74 |
| 2 | 187952 | 0 | 74 |
| 3 | 86998 | 0 | 60 |
| 4 | 156006 | 0 | 71 |
| 5 | 82000 | 0 | 67 |

**Summary (SHORT):**

| Stat | Value |
|------|-------|
| n | 5 |
| min | 82000ms |
| p50 | 156006ms |
| p95 | 187952ms |
| max | 187952ms |
| mean | 139236ms |

## Test Case 4 (MEDIUM)

| Run | Wall (ms) | Exit | stderr lines |
|-----|-----------|------|-------------|
| 1 | 34981 | 0 | 54 |
| 2 | 31010 | 0 | 51 |
| 3 | 34006 | 0 | 54 |
| 4 | 218004 | 0 | 73 |
| 5 | 167007 | 0 | 70 |

**Summary (MEDIUM):**

| Stat | Value |
|------|-------|
| n | 5 |
| min | 31010ms |
| p50 | 34981ms |
| p95 | 218004ms |
| max | 218004ms |
| mean | 97001ms |

## Test Case 7 (LONG)

| Run | Wall (ms) | Exit | stderr lines |
|-----|-----------|------|-------------|
| 1 | 114006 | 0 | 61 |
| 2 | 1573175 | 0 | 1575 |
| 3 | 58828 | 0 | 65 |
| 4 | 127044 | 0 | 70 |
| 5 | 37965 | 0 | 54 |

**Summary (LONG):**

| Stat | Value |
|------|-------|
| n | 5 |
| min | 37965ms |
| p50 | 114006ms |
| p95 | 1573175ms |
| max | 1573175ms |
| mean | 382203ms |

## Raw data: /workspace/llama.cpp-omni-operator/profiles/baseline/baseline_tc*_r*.{stdout,stderr}
