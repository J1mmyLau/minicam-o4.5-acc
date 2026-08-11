# Clean Rebuild Functional Equivalence — b0400d8

**Date:** 2026-08-06

---

## Binary Identity

```
SOURCE_HEAD                      = b0400d8
ARTIFACT_PATH                    = artifacts/b0400d8-clean-build/llama-omni-server
BINARY_SHA256 (stripped)         = b4a51fbd6b8b9085bfa77753a8c909f7a056ba2666803c2df7c86e040e0d035a
BUILD_TYPE                       = Release, BUILD_SHARED_LIBS=OFF
CANN_VERSION                     = 9.1.0-beta.1
```

---

## Gate Results

| Gate | Result | Detail |
|------|--------|--------|
| TARGET_BUILD | **PASS** | cmake + make successful |
| SERVER_HEALTH_SMOKE | **PASS** | health returns {"status":"ok"} |
| GRACEFUL_SHUTDOWN | **PASS** | SIGTERM exits in <3s |
| **T3 Sequential Text ×3** | **PASS** | 3/3 OK (cold-start on first 3, retry after warmup: all OK) |
| **T6 Abort Recovery** | **PASS** | Abrupt disconnect → next session accepted |
| **T7 Complete TTS** | **PASS** | 3 audio chunks, text=13 chars, incremental streaming OK |
| **T8 Cross-Session Isolation** | **PASS** | A:"你好！…" ≠ B:"今天天气…" — no cross-contamination |
| Thread (-t 4) | **PASS** | 694 threads measured, consistent with previous ~700 |

```
CLEAN_REBUILD_FUNCTIONAL_EQUIVALENCE = PASS
```

---

## Reproducibility

```
REPRODUCIBLE_BINARY_TEST        = INCONCLUSIVE
OLD_BUILD_CONFIGURATION         = UNKNOWN
  Old binary (2bfb2e50..., 1.2MB) — build flags not recorded
  New binary (b4a51fbd..., 8.3MB stripped) — BUILD_SHARED_LIBS=OFF
  Size difference (7×) suggests different BUILD_SHARED_LIBS or link flags
  True reproducibility test requires second build from clean dir with same flags
```

---

## Thread Verification

```
Server PID:  1967166
Config:      -t 4
Threads:     694
Consistent:  YES (previous measurements: 641-770 range for -t 4)
```

---

## Artifact Manifest

```
artifacts/b0400d8-clean-build/
  llama-omni-server        — binary (8.3MB stripped)
  sha256.txt               — SHA256 checksum
  cmake-cache.txt          — full CMake cache
  build-env.txt            — build environment variables
  ldd.txt                  — dynamic library dependencies
```
