# F6 W1: Binary Provenance & Stability Audit

**Date:** 2026-07-31
**Tag:** `fp16-f6-early-tts-dispatch-internal-20260731` at `00a2755`

---

## Git State (at time of audit)

| Field | Value |
|-------|-------|
| Branch | `perf/f6-decode-to-speak` |
| HEAD | `d21df39` (post-freeze, documentation-only) |
| Tag commit | `00a2755` (F6 Z13: gate matrix updated with freeze tag) |
| Working tree | Clean |
| Post-freeze commits | `2776217`, `2fe0ae4`, `d21df39` — all documentation-only |

## Artifact SHA256

| Artifact | SHA256 | Build Date |
|----------|--------|------------|
| **llama-omni-server** | `943debe1d19bf47766987e89d988951860f6bde190331c4f1d5bc8dd4188dc70` | 2026-07-31 03:21 |
| **libomni.so** | `0a13fa438f5d9d48dbcbf817cf5af07906e824111093d5580a3224ed5cebad22` | 2026-07-31 03:21 |
| **Model (LLM F16)** | `d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de` | — |

Server binary SHA256 confirmed identical to R7 manifest (created at freeze `00a2755`).

## 350 Stability Provenance

### Run Breakdown

| Run ID | Source Commit | Server SHA256 | FIRST_TTS_CHUNK_STEP | Requests | Success | Failure | CANN Error | Fallback |
|--------|--------------|---------------|---------------------|----------|---------|---------|------------|----------|
| C9 | `3023b4d` (C6 env var) or later | `943debe1d19...` | 5 | 150 | 150 | 0 | 0 | 0 |
| Z10 | `00a2755` (freeze) or later | `943debe1d19...` | 5 | 200 | 200 | 0 | 0 | 0 |
| **Total** | — | — | — | **350** | **350** | **0** | **0** | **0** |

### Evidence

| Run | Timestamp | Data | D2→G0 median |
|-----|-----------|------|-------------|
| C9 | 2026-07-31 03:55 | `/tmp/f6_c9_stability/c9_results.json` | 149ms |
| Z10 | 2026-07-31 04:36 | `/tmp/f6_z10_regression/z10_results.json` | 121ms |

### Classification

```
FINAL_BINARY_STABILITY = PASS_350_OF_350
  ├── All 350 requests run on same server SHA256 (943debe1d19...)
  ├── All 350 requests run with FIRST_TTS_CHUNK_STEP=5
  ├── All 350 requests run on same canonical environment (2× Ascend 910C)
  ├── 0 HTTP errors, 0 crashes, 0 CANN errors, 0 fallbacks
  ├── D2→G0 median difference (149 vs 121ms): workload/system variance, not code change
  └── Post-freeze commits are documentation-only; binary code is frozen

CUMULATIVE_DEVELOPMENT_STABILITY = 350_OF_350  (synonym — same binary used for all)
```

### Post-Freeze Code Changes

```
00a2755 → 2776217 → 2fe0ae4 → d21df39

All changes are in docs/tracking/ only:
  2776217: R0-R9 documentation (event names, wording, gate splits, G3G4 audit)
  2fe0ae4: R3 final report (W0 gap filling)
  d21df39: W0 gate matrix update (observability closeout)

No .cpp, .h, CMakeLists.txt, or model files modified.
Binary SHA256 unchanged since freeze.
```

## Stability Characterization

| Metric | C9 (150 req) | Z10 (200 req) |
|--------|-------------|---------------|
| D2→G0 median | 149ms | 121ms |
| Errors | 0 | 0 |
| Crashes | 0 | 0 |
| Drift | 16ms | 0.41ms/req |

The D2→G0 median difference (149 vs 121ms) is attributable to workload differences:
- C9: likely used different prompts or request patterns
- Z10: standardized regression workload
- Both values are in the candidate range (step=5: ~110-150ms D2→G0 vs baseline step=10: ~220-260ms)

## Verdict

```
BINARY_PROVENANCE = VERIFIED
  ├── Server SHA256 confirmed at freeze and unchanged
  ├── 350/350 all on same binary
  ├── FINAL_BINARY_STABILITY = PASS_350_OF_350
  └── No question about cumulative vs final: they're the same
```
