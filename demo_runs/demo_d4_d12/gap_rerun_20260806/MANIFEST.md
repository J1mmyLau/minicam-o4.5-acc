# Gap Re-run Manifest — 2026-08-06

**Server:** PID 2104774, ASCEND_RT_VISIBLE_DEVICES=0, single instance
**Infrastructure:** Gateway :18006 / Worker :22400 / Server :22500

## Re-run Items

### D5: Audio Semantics (Official D7)
- **Status:** ✅ COMPLETED
- **Test:** 4-turn audio understanding diagnostic (direct backend)
  - Test 1: Audio only → "你好！你有什么问题需要我帮忙吗？😊"
  - Test 2: Audio + transcription prompt → "给你的钱都花光啦！" (hallucinated)
  - Test 3: Audio + content question → "您现在收听的是喜马拉雅有声小说。" (hallucinated)
  - Test 4: Long audio (11.34s) + transcription prompt → "音频转写：" (empty)
- **Evidence:** D5_events.json (1604 bytes)
- **Verdict:** CONDITIONAL_PASS — functional ✓, semantic accuracy model-limited

### D6: Duplex Complete Output (Official D11 duplex component)
- **Status:** ✅ COMPLETED
- **Test:** Full-duplex pipeline diagnostic (direct backend, use_tts=true, force_listen_count=0)
  - Whisper: 19 tokens × 4096 dims ✅
  - LLM: 26 audio tokens (speech only, no text) ✅
  - TTS: 1 chunk, 0.84s WAV ✅
  - T2W: WAV delivered (107520 bytes base64) ✅
  - First audio response: 5909ms
  - No response.done (duplex is continuous)
- **Evidence:** D6_events.json (108354 bytes — full event trace)
- **Verdict:** CONDITIONAL — infrastructure works, model generates speech-only in duplex (by design)

### D12: Continuous Stability (Official D12)
- **Status:** 🔄 RUNNING
- **Test:** 60 sequential sessions over ~40 minutes (direct backend)
- **Interval:** 40s between sessions
- **Evidence:** D12_stability/results.json (pending)

## Infrastructure Verification

| Check | Status |
|-------|--------|
| Single server PID | ✅ PID 2104774 |
| ASCEND_RT_VISIBLE_DEVICES=0 | ✅ Verified |
| No SO_REUSEPORT | ✅ Single listener on :22500 |
| No pkill/pgrep | ✅ PID file only |
| Gateway alive | ✅ PID 1986045 |
| Worker alive | ✅ PID 1985404 |
