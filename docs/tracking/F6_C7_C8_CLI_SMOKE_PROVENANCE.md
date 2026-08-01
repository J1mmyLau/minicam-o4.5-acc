# F6 C7/C8 CLI Smoke Provenance

**Date:** 2026-08-01
**Build Type:** Debug (cmake default)

## Binary Provenance

### CLI (used for C7/C8 smoke tests)
| Field | Value |
|-------|-------|
| Path | `/workspace/llama.cpp-omni-f6/build/bin/llama-omni-cli` |
| SHA256 | `fbda1fb024827c4795f8a4f0b5f58481645837194cd9c3af3c632ece8aa5c2a1` |
| Size | 57,928 bytes |

### Server (compiled, NOT yet smoke-tested)
| Field | Value |
|-------|-------|
| Path | `/workspace/llama.cpp-omni-f6/build/bin/llama-omni-server` |
| SHA256 | `74d0ca312a1434f2eaab556af65069d676c454beeb8eef41a600162b67ce69d6` |
| Size | 1,162,960 bytes |

### libomni (shared library)
| Field | Value |
|-------|-------|
| Path | `/workspace/llama.cpp-omni-f6/build/bin/libomni.so` |
| SHA256 | `57ba8602bed0e2a563d3c313de714ecca309b76e7383d653511fbe9a6745cf71` |

### Source
| Field | Value |
|-------|-------|
| HEAD | `0377adef4b938127d780c942f8b9ba0bbd1c8b09` |
| Branch | `perf/f6-decode-to-speak` |
| Uncommitted | 5 files, +215/-45 lines (N2-N6 fixes) |

### CANN
| Field | Value |
|-------|-------|
| Version | `cann-9.1.0-beta.1` |
| Driver path | `/usr/local/Ascend/driver/lib64/driver/libascend_hal.so` |

## Previous Session Binary (commit 0377ade, pre-fix)
| Binary | SHA256 |
|--------|--------|
| Server (old) | `50e6ee05ff837745fd71bf7c9b92f136e98001daadc156dc5b3923a31d8bc405` |

This old SHA256 was recorded as the "tested binary" in the previous session's smoke test,
but the actual smoke test used the CLI tool, not the server. The CLI binary's SHA256 from
that session was NOT recorded.

## Warning
The previous session's smoke test recorded only the server binary SHA256 but actually ran
the CLI tool. The CLI binary from that session was never hashed. The current build
produces DIFFERENT binaries than the 0377ade baseline due to N2-N6 uncommitted fixes.
