# G5: Official Benchmark Harness Audit

**Date:** 2026-07-29
**Status:** PARTIAL — internal test cases available, external harnesses missing

---

## Internal Test Cases

| Type | Path | Files | Coverage |
|------|------|-------|----------|
| Omni (vision+audio) | `tools/omni/assets/test_case/omni_test_case/` | 18 (9 pairs) | 9 test cases, .jpg + .wav pairs |
| Audio only | `tools/omni/assets/test_case/audio_test_case/` | 2 | 1 pair |
| Duplex omni | `tools/omni/assets/test_case/duplex_omni_test_case/` | 72 | 36 pairs |

## Binary Capabilities

| Flag | Function |
|------|----------|
| `--omni` | Vision + audio mode |
| `--test <prefix> <n>` | Run n test cases from prefix |
| `--test-start <n>` | Start from specific test case index |
| `--bench-vision <img>` | Benchmark serial vs batched vision encoding |
| `OMNI_T2W_PROFILE=2` | Enable per-chunk profiling output |
| `OMNI_T2W_DEVICE` | Flow model backend (cann-flow-only/cpu) |
| `OMNI_VOC_DEVICE` | Vocoder backend (gpu/cpu) |

## External Benchmark Harnesses

| Harness | Available | Notes |
|---------|-----------|-------|
| Daily-Omni | ❌ NOT FOUND | Not in workspace |
| TTS-Seed | ❌ NOT FOUND | Not in workspace |
| Video-MME | ❌ NOT FOUND | Not in workspace |

## Verdict

```
BENCHMARK_GATE = BLOCKED_BY_EXTERNAL_HARNESS
```

Missing: Daily-Omni, TTS-Seed, Video-MME harnesses and datasets.

**Mitigation:** Continue with internal test cases for:
- G6: Demo (9 omni test cases available)
- G7-G8: Stability (internal test cases sufficient)
- G9-G11: KV cache, multi-prefix, T2W lifecycle (use internal test cases)
- G12: Clean reproduction (internal test cases sufficient)

No blocking — proceed with available resources.
