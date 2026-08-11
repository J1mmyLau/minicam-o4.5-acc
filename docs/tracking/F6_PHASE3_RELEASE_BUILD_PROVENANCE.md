# F6 Phase 3 — RelWithDebInfo Build Provenance (S5)

**Date:** 2026-08-01
**HEAD:** `7c9ef72`
**Build dir:** `build-f6-phase3-relwithdebinfo/`

## Binary Provenance

| Binary | SHA256 |
|--------|--------|
| llama-omni-server | `c13c04a081850c2eb46fb828775603672acd86518c6ecd9de324635831ed04bc` |
| llama-omni-cli | `54999244edf4a2edb0fb42a5797007a7d9671ed3e592665b49de5a9488479658` |

## Build Configuration

| Setting | Value |
|---------|-------|
| CMAKE_BUILD_TYPE | RelWithDebInfo |
| CXX Flags | `-O2 -g -DNDEBUG` |
| C Flags | `-O2 -g -DNDEBUG` |
| GGML_CANN | ON |
| GGML_CUDA | OFF |
| CANN dir | `/usr/local/Ascend/cann-9.1.0-beta.1` |

## Environment

| Component | Version / Info |
|-----------|---------------|
| CANN | 9.1.0-beta.1 |
| npu-smi | 25.5.1 |
| NPU | Ascend910 (2 chips, 0 and 1) |
| Chip Phy-ID 0 | 0000:9D:00.0 |
| Chip Phy-ID 1 | 0000:9F:00.0 |
| HBM per chip | 65536 MB |
| SOC_VERSION (auto-detected) | ascendascend910 |

## Linked CANN Libraries

```
libascendcl.so → /usr/local/Ascend/cann-9.1.0-beta.1/lib64/
libnnopbase.so → /usr/local/Ascend/cann-9.1.0-beta.1/lib64/
libopapi.so → /usr/local/Ascend/cann-9.1.0-beta.1/lib64/
libmsprofiler.so → /usr/local/Ascend/cann-9.1.0-beta.1/lib64/
libruntime.so → /usr/local/Ascend/cann-9.1.0-beta.1/lib64/
libacl_rt.so → /usr/local/Ascend/cann-9.1.0-beta.1/lib64/
libascend_hal.so → /usr/local/Ascend/driver/lib64/driver/
```

## Build Command

```bash
cmake -B build-f6-phase3-relwithdebinfo \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DGGML_CANN=ON \
    -DGGML_CUDA=OFF

cmake --build build-f6-phase3-relwithdebinfo -j$(nproc) \
    --target llama-omni-server llama-omni-cli
```

## Git State

```
HEAD: 7c9ef72 docs(f6-phase3): TalkerStepBuffer memory model — formal happens-before proof (S4)
Branch: perf/f6-decode-to-speak
Working tree: clean
```

## Build Artifacts Saved

- `F6_PHASE3_RELWITHDEBINFO_CMakeCache.txt` — full CMakeCache.txt
- `F6_PHASE3_RELWITHDEBINFO_compile_commands.json` — 2166 compile commands
- This document: `F6_PHASE3_RELEASE_BUILD_PROVENANCE.md`

## Freeze Rule

**All subsequent N8/N9/C9/C10/120-baseline MUST use this same binary.**
If a rebuild is needed, a new provenance document must be created and the old
binary SHA256s must be archived as deprecated.

The binary path is:
- Server: `/workspace/llama.cpp-omni-f6/build-f6-phase3-relwithdebinfo/bin/llama-omni-server`
- CLI: `/workspace/llama.cpp-omni-f6/build-f6-phase3-relwithdebinfo/bin/llama-omni-cli`
