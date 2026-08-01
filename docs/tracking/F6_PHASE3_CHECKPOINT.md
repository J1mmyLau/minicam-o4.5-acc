# F6 Phase 3 Checkpoint — 2026-08-01

**HEAD:** `f4133d0` (P0-P6 documentation commit)
**Branch:** `perf/f6-decode-to-speak`
**Worktree:** `/workspace/llama.cpp-omni-f6`

## Binary/Model Identity

| Artifact | SHA256 |
|----------|--------|
| Server binary | `42c97f40c0738366e076f6e3352f8f4931e2e8898e29f1a688ad571e794398a3` |
| FP16 model | `d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de` |

## Frozen Decisions

- B6B_TRUE_E2E_FP16_GATE = REJECT_NO_MEANINGFUL_GAIN
- B6B_FEATURE_STATUS = EXPERIMENTAL_KNOB / DEFAULT_OFF
- B6B_PRODUCTION_RECOMMENDATION = DO_NOT_ENABLE
- B6b MUST be OFF: OMNI_TTS_FIRST_CHUNK_STEP=10
- CHUNK_SIZE=25 FROZEN
- Do NOT train DSpark
- Do NOT write AscendC kernels
- Tag `fp16-f6-early-tts-dispatch-internal-20260731` @ `00a2755` preserved

## Data Location

- 120 pairs: `/tmp/f6_fp16_w10/` (60 ABBA blocks)
- Canonical CSV: `/tmp/f6_fp16_w10/F6_B6B_FP16_CANONICAL_120_PAIRS.csv`
- Raw profiles: split JSON (e2e_XXXX.json + e2e_XXXX_audio.json)
- Timing resolution: integer milliseconds (server-side `ggml_time_ms()`)

## Phase 3 Goal

Decompose G0→T2W Dequeue (~621ms undecomposed region) by adding:
- Talker per-step instrumentation (T5-T7, A0-A1)
- T2W submit/dequeue events (Q0-Q1)
- Flow/Vocoder fine-grained events (F0-F1, V0-V1)
- All request-scoped (no global fallback)

## Next Action

C1: Canonical raw data audit → C2: D0→D2 resolution artifact → C3: D2→G0 bimodal analysis
