# KV Cache Soak Status

**Date:** 2026-07-26
**Soak started:** NOT YET
**Current stage:** P0 — Phase initialization

---

## Stage Progress

| Stage | Duration | Status | Started | Completed | Pass/Fail | Evidence |
|-------|----------|--------|---------|-----------|-----------|----------|
| A | 1h | PENDING | — | — | — | — |
| B | 6h | PENDING | — | — | — | — |
| C | 24h | PENDING | — | — | — | — |
| D | 72h | PENDING | — | — | — | — |
| E | 168h | PENDING | — | — | — | — |

## Soak Metrics Template

```
total_requests:      0
success:             0
cache_hit:           0
cache_miss:          0
cache_rebuild:       0
cache_corruption_detected: 0
fallback_success:    0
request_to_first_audio_p50: 0
RSS_p50:             0
HBM_p50:             0
open_fds_p50:        0
thread_count:        0
CANN_errors:         0
T2W_failures:        0
rc0_without_audio:   0
degeneration:        0
retry:               0
output_block:        0
```

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

**最后更新:** 2026-07-26
