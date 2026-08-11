# F6 R6: Audio Quality Gate Split

**Date:** 2026-07-31
**Replaces:** "B6B_AUDIO_QUALITY_GATE = ADVISORY_PENDING" with 4 separate gates

---

## Gate Split

| Gate | Status | Evidence | What It Covers |
|------|--------|----------|----------------|
| **AUDIO_FORMAT_GATE** | **PASS** | Z8: 120 WAVs, 24000 Hz, mono, valid headers, no corruption | WAV container validity, sample rate, channel count, codec |
| **AUDIO_BASIC_QC_GATE** | **PASS** | Z8: duration 0.44-1.00s, consistent baseline/candidate, no silent files | File size, duration, non-silence, basic signal presence |
| **HUMAN_LISTENING_GATE** | **PENDING** | Z9: 20-sample blind A/B manifest prepared (`/tmp/f6_z9_listening/LISTENING_MANIFEST.csv`) | First-word articulation, prosody, voice timbre, chunk boundary smoothness |
| **OBJECTIVE_WER_SIM_GATE** | **PENDING_EXTERNAL** | Requires: ASR engine + speaker embedding model | Word Error Rate, Speaker SIMilarity, objective acoustic metrics |

## What Each Gate Proves (and Doesn't)

### AUDIO_FORMAT_GATE = PASS
- ✅ WAV files are valid containers
- ✅ Consistent sample rate (24000 Hz)
- ✅ Consistent channel count (mono)
- ✅ Files are non-empty
- ❌ Does NOT prove audio sounds correct
- ❌ Does NOT prove speech content is accurate
- ❌ Does NOT prove voice quality is maintained

### AUDIO_BASIC_QC_GATE = PASS
- ✅ Files have reasonable duration (0.44-1.00s)
- ✅ Baseline and candidate produce similar file sizes
- ✅ No completely silent files detected
- ✅ No truncated headers
- ❌ Does NOT prove pronunciation is correct
- ❌ Does NOT prove prosody is natural
- ❌ Does NOT prove chunk boundary is seamless

### HUMAN_LISTENING_GATE = PENDING
- 20-sample blind A/B manifest prepared
- Requires human evaluator to:
  - Compare baseline (step=10) vs candidate (step=5)
  - Judge: first word articulation, prosody, voice consistency
  - Identify which is which (blind)
- ⚠️ 5-token first chunk has less TTS context (theoretical risk)
- ⚠️ No evidence of degradation from automated checks

### OBJECTIVE_WER_SIM_GATE = PENDING_EXTERNAL
- Requires external tools:
  - ASR engine (e.g., Whisper) for transcription → WER computation
  - Speaker embedding model for SIM score
- Not in scope for F6 internal candidate
- Recommended before DEFAULT_ON consideration

## Why 24000Hz Mono ≠ Audio Quality PASS

The format checks prove the pipeline produces valid audio containers. They do not prove:
1. **First word isn't truncated**: 5-token context might be insufficient for TTS to correctly pronounce the first word
2. **First phoneme isn't anomalous**: Less context could cause mispronunciation of initial phonemes
3. **Prosody across chunk boundary**: First→second chunk transition might have discontinuity
4. **Voice timbre stability**: Shorter first chunk could affect voice conditioning
5. **WER/SIM regression**: Without ASR, we can't quantify speech accuracy

## Recommendation

```
B6B_DEFAULT_ENABLEMENT = NO
  (pending HUMAN_LISTENING or OBJECTIVE_WER_SIM)

B6B_OPT_IN_STATUS = READY
  (format + basic QC + stability + performance all PASS)
  (env var OMNI_TTS_FIRST_CHUNK_STEP allows opt-in)
```

The 24000Hz/mono format check is a **necessary** condition for audio quality, not a **sufficient** one. The tag correctly remains DEFAULT_OFF until perceptual or objective audio evaluation confirms no regression.
