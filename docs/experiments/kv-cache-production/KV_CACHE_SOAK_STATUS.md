# KV Cache Soak Status

**Date:** 2026-07-26
**Soak started:** 2026-07-26 03:33 UTC
**Current stage:** P3 — Stage A (1h) PASS ✅ → Stage B (6h) launching

---

## Gates Passed Before Soak

- **P1**: Production-grade cache storage (b2e45ce) — FNV-1a key, CRC32 integrity, atomic rename, OMKC header
- **P2**: 8 boundary condition gates (58c1fd9) — 20/20 PASS
  - Cache key: G1-G6 all PASS or CODE_VERIFIED
  - Corruption safety: G7a-G7e all PASS (truncate/bitflip/bad_magic/version/crc)
  - Concurrency: G8a-G8h all PASS or DESIGN_VERIFIED

---

## Stage Progress

| Stage | Duration | Status | Started | Completed | Pass/Fail | Evidence |
|-------|----------|--------|---------|-----------|-----------|----------|
| A | 1h | **PASS** ✅ | 2026-07-26 03:33 UTC | 2026-07-26 04:33 UTC | PASS | p3-soak/stage_a_20260726_033330/ |
| B | 6h | **RUNNING** | 2026-07-26 ~04:40 UTC | — | — | p3-soak/stage_b_*/ |
| C | 24h | PENDING | — | — | — | — |
| D | 72h | PENDING | — | — | — | — |
| E | 168h | PENDING | — | — | — | — |

## Stage A Test Design

- **Method**: Repeated cache HIT runs (30+ iterations in 1 hour)
- **Each iteration**: Full omni inference with --test 1, verifying KV cache HIT
- **Metrics collected every 60s**: RSS, FD count, thread count, cache file size
- **Error detection**: cache file size changes, timeouts, crash detection
- **Prime**: One MISS→SAVE at start, then all subsequent runs should HIT

---

## Gate Checks Per Stage

Each stage gate:
- crash = 0
- CANN error = 0
- rc0_without_audio = 0
- semantic corruption = 0
- cache key错误命中 = 0
- temporary file leak = 0
- thread/process leak = 0
- RSS/HBM无持续单调增长
- cache hit路径性能收益保持
- cache miss路径与baseline一致

---

**最后更新:** 2026-07-26 03:35 UTC (Stage A launched)
