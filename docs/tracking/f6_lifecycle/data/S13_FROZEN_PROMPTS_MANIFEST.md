# S13 Frozen Prompts Manifest

**File**: `docs/tracking/f6_lifecycle/data/S13_FROZEN_PROMPTS.jsonl`
**SHA256**: `027bfc4b13257820f35d438dc125c3d92b93984f9ae5b7007c944633833ddd09`
**Generated**: 2026-08-04, from audit script during S13 Strict Audit
**Source**: Extracted from `/workspace/llama.cpp-omni-f6/scripts/f6_s13_120_baseline.py` prompt lists
**Entries**: 120 (30 short_cn + 30 long_cn + 30 english + 30 number_mix)

## Schema

```json
{
  "case_id": "short_cn-R01",
  "category": "short_cn|long_cn|english|number_mix",
  "prompt": "exact prompt text",
  "prompt_sha256": "SHA256 of prompt text (UTF-8)",
  "expected_max_gen": "variable",
  "stop_policy": "EOS_or_max_tokens",
  "first_attempt": "OK|TIMEOUT|NEVER_REACHED",
  "prompt_modified_for_final_ok": true|false,
  "replacement_prompt": "if modified, the simplified replacement",
  "replacement_prompt_sha256": "if modified, SHA256 of replacement"
}
```

## Integrity

| Category | Entries | First-Attempt OK | First-Attempt TIMEOUT | NEVER_REACHED | Modified |
|----------|---------|------------------|-----------------------|---------------|----------|
| short_cn | 30 | 30 | 0 | 0 | 0 |
| long_cn | 30 | 30 | 0 | 0 | 0 |
| english | 30 | 30 | 0 | 0 | 0 |
| number_mix | 30 | 22 | 1 | 7 | 8 |
| **Total** | **120** | **112** | **1** | **7** | **8** |

## Modified Prompts

| Case ID | Original SHA256 | Replacement | Replacement SHA256 |
|---------|----------------|-------------|-------------------|
| number_mix-R23 | `f30f3b9f...` | 1+1等于几 | `8224f4c8...` |
| number_mix-R24 | `e9d3a7b2...` | 2乘以3是多少 | `3a1b5c7d...` |
| number_mix-R25 | `a4c8f1e5...` | 100除以5等于多少 | `7e2d9a4f...` |
| number_mix-R26 | `c5b2d8f6...` | 一二三，请回答 | `2f8a1c3e...` |
| number_mix-R27 | `b7e1c4a9...` | 10的平方是多少 | `9d5f2b8c...` |
| number_mix-R28 | `d2a6f3e8...` | 说出数字1到5 | `4e7c1a9b...` |
| number_mix-R29 | — | 数一数：1,2,3 | `8f3d6c2a...` |
| number_mix-R30 | — | 用中文数1到10... | `1b5e9f4d...` |

> Full SHA256 values are in the JSONL file.

## Usage

This is the **frozen, immutable** prompt set for S13 strict baseline.
Any re-run must use these exact prompts, verified by SHA256 comparison before execution.
No prompt may be modified, simplified, or replaced — even if it triggers a server bug.
If a prompt triggers a server bug, the bug must be fixed before the baseline can pass.
