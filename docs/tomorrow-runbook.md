# Tomorrow Runbook — Official Unified Eval Branch Arrival

**Date:** 2026-08-11 (expected)
**State:** WAIT_OFFICIAL_UNIFIED_EVAL_BRANCH
**Frozen candidate:** `051e993` (`main` on private remote)

## Overview

Official organizer confirmed a unified evaluation branch will be provided.
This runbook covers the end-to-end workflow from branch pull to final re-evaluation.

## Phase 1: Pull & Record (≤15 min)

```bash
# 1. Fetch official branch
git fetch origin
git checkout -b eval/official-$(date +%Y%m%d) origin/<official-branch-name>

# 2. Record
OFFICIAL_BRANCH=$(git branch --show-current)
OFFICIAL_SHA=$(git rev-parse HEAD)
echo "OFFICIAL_BRANCH=$OFFICIAL_BRANCH" >> docs/tomorrow-runbook.log
echo "OFFICIAL_SHA=$OFFICIAL_SHA" >> docs/tomorrow-runbook.log
echo "DATE=$(date -Iseconds)" >> docs/tomorrow-runbook.log

# 3. Diff against our frozen candidate (informational only)
git diff 051e993 --stat > docs/official-branch-diff-stat.txt
```

**Deliverable:** `docs/tomorrow-runbook.log` with OFFICIAL_SHA recorded.

## Phase 2: F16 Accuracy Baseline (≤2h estimate)

Run all 4 accuracy benchmarks against the official branch with F16 weights:

```bash
# Build (CANN 9.1.0-beta1, -t4)
cmake -B build -DGGML_CANN=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc) --target llama-omni-server

# Launch server (F16, CANN0, ngl 999)
OMNI_T2W_PIPELINE_OVERLAP=1 \
./build/bin/llama-omni-server \
  -m /path/to/model-F16.gguf \
  --device CANN0 -ngl 999 -t 4 \
  --port 8080
```

### G2: Daily-Omni Accuracy
```bash
python scripts/f6_daily_omni_eval.py --url http://localhost:8080 --output results/daily-omni-f16.json
```

### G3: TTS-Seed Accuracy
```bash
# ASV
python scripts/f6_tts_seed_eval.py --metric asv --url http://localhost:8080 --output results/tts-seed-asv-f16.json
# WER
python scripts/f6_tts_seed_eval.py --metric wer --url http://localhost:8080 --output results/tts-seed-wer-f16.json
```

### G4: VideoMME Accuracy
```bash
python scripts/f6_videomme_eval.py --url http://localhost:8080 --output results/videomme-f16.json
```

### Compare Against Thresholds
| Benchmark | Threshold | F16 Result | Δ | Pass? |
|-----------|-----------|-----------|-----|------|
| Daily-Omni | ≥ 77.5 | TBD | TBD | TBD |
| TTS-Seed ASV | ≥ 0.689 | TBD | TBD | TBD |
| TTS-Seed WER | ≤ 1.56 | TBD | TBD | TBD |
| VideoMME | ≥ 67.0 | TBD | TBD | TBD |

**Deliverable:** `results/accuracy-f16-<date>.json` with all 4 benchmark results.

**Decision gate:** If F16 fails any threshold → BLOCKED, report to organizer.
If F16 passes all → proceed to Phase 3.

## Phase 3: Q8_0 Accuracy (≤2h estimate)

Convert model to Q8_0 and re-run all 4 benchmarks:

```bash
# Quantize
./build/bin/llama-quantize /path/to/model-F16.gguf /path/to/model-Q8_0.gguf Q8_0

# Launch server with Q8_0
./build/bin/llama-omni-server -m /path/to/model-Q8_0.gguf --device CANN0 -ngl 999 -t 4 --port 8080

# Re-run all 4 benchmarks (same commands as Phase 2)
```

**Deliverable:** `results/accuracy-q8_0-<date>.json`.

## Phase 4: Bug Re-Evaluation

Only bugs that reproduce on the official branch are submission blockers.

### P0-1: WS Multimodal NaN (audio/video → all `?`)
1. Start server with `OMNI_NAN_DIAG=1`
2. Run `scripts/f6_nan_repro_matrix.py` (text, image, audio, video)
3. Reproduce on official branch? → If YES: fix. If NO: de-prioritize.

### P0-2: Q8_0 contiguous-y constraint ([4096,17] multi-token crash)
1. Run multi-token decode with Q8_0 weights on official branch
2. Reproduce? → If YES: fix or fallback. If NO: de-prioritize.

### P0-3: Thread exhaustion (libgomp × httplib, 319 threads/session)
1. Run 10-session sequential test
2. Monitor thread count: `watch -n 1 'ps aux | wc -l'`
3. If official branch uses different server impl → may not apply.

**Deliverable:** `docs/bug-triage-<date>.md` with reproduce/not-reproduce per bug.

## Phase 5: Performance RTF (≤1h)

```bash
# Run official SPEAK→WAV RTF measurement
python submission/scripts/benchmark_client.py \
  --url http://localhost:8080 \
  --video /path/to/omni_duplex1.mp4 \
  --warmup 0 \
  --rounds 30 \
  --output results/rtf-official-f16-<date>.json
```

Compare against official F16 baseline (1.087).

**Deliverable:** `results/rtf-official-<date>.json`.

## Phase 6: Final Decision

After all 5 phases complete:

| Decision | Condition |
|----------|-----------|
| SUBMIT F16 | All accuracy gates pass, RTF improves or within noise |
| SUBMIT Q8_0 | Q8_0 accuracy passes AND RTF is better than F16 |
| FIX FIRST | Any P0 bug reproduces on official branch |
| BLOCKED | Official branch won't build/run, or accuracy threshold failed |

## Quick Reference: Key Files

| File | Purpose |
|------|---------|
| `docs/competition-submission/OFFICIAL_EVALUATION_SPEC.md` | Official spec (thresholds, RTF definition) |
| `docs/competition-submission/OFFICIAL_GATE_MATRIX.md` | Full gate matrix |
| `submission/scripts/benchmark_client.py` | Official RTF harness (if available) |
| `scripts/f6_nan_repro_matrix.py` | NaN repro script |
| `scripts/f6_daily_omni_eval.py` | Daily-Omni eval |
| `STATUS.md` | Update after each phase |

## Rollback

If official branch has issues, fall back to frozen candidate `051e993`:

```bash
git checkout 051e993
# Binary SHA: 768614abd68f93ff5b57a3eb99cb79ad14d2a839f0fcb7ebf0990c88f39d189e
```
