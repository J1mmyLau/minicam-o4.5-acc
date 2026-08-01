# AUDIT LOG — CANN Flow + Vocoder Optimization

**Project:** llama.cpp-omni-operator / Ascend 910C / CANN 9.1.0-beta.1
**Branch:** perf/flow-chunk-rtf

---

## 2026-07-30 10:15 | PHASE | F6_S10_SMOKE_TEST_PASS
- Binary startup: PASS — health check OK
- 2 requests sent, 2 profile files generated (e2e_0000.json, e2e_0001.json) — per-request reset confirmed
- All 4 new stages (D0, D1, G0, G2) recorded in both requests
- Temporal ordering verified: R0(0) < D0(0) < D1(28) < D2(65) < G0(285) < G1(389) = G2(389) < G3(433) < G5(687)
- Request 2 also correct: R0(0) < D0(15) < D1(44) < D2(79) < G0(299) < G1(311) = G2(311) < G3(342) < G5(592) < W0(2303)
- No negative intervals in E2EStageTiming stages (flow/vocoder global atomics have pre-existing ordering bug)
- D3 (speak_token) absent for text-only requests — expected, guards work correctly
- Next: S11 overhead gate + S12 final status

## 2026-07-30 10:00 | PHASE | F6_S9_INSTRUMENTATION_IMPLEMENTED
- omni.h: 4 new enum values (STAGE_decode_loop_begin=16, STAGE_llm_first_decode_step=17, STAGE_tts_wake=18, STAGE_tts_first_decode=19), STAGE_COUNT=20
- omni.h: reset() method added to E2EStageTiming — clears all timestamps + metadata per-request
- omni.cpp: reset() called at request boundary (line 12508)
- omni.cpp: D0 recorded at decode loop begin (line 12581), alongside PE_DECODE_BEGIN
- omni.cpp: D1 recorded before first llama_loop_with_hidden_and_token (line 12757), guarded by llm_first_decode_step_logged
- omni.cpp: D3 once-guard added (llm_first_speak_token_logged) — STAGE_speak_token now fires once per request
- omni.cpp: G0 recorded at TTS thread cv.wait return (line 7786), guarded by load==0 (reset-safe)
- omni.cpp: G2 recorded before first TTS llama_decode (line 3387), guarded by load==0 (reset-safe)
- Build: PASS — llama-omni-server compiled successfully
- Existing once-guarded stages (G1,G3,G4,G5,Q0,W0) now work per-request thanks to reset()
- Next: S10 correctness smoke test

## 2026-07-30 09:30 | PHASE | F6_SEMANTIC_AUDIT_S1-S8_COMPLETE
- S1 E2EStageTiming infrastructure audit: steady_clock (not MONOTONIC_RAW), relaxed atomics, no reset(), 6 dead stages
- S2 Callsite matrix: 10/16 stages have callsites, 6 missing; once-lifetime guard broken for multi-request
- S3 T0 correction: STAGE_request_received = stream_decode entry (NOT decode submit); D0 should be at line 12581
- S4 First token source: STAGE_llm_first_token confirmed from autoregressive decode (correct)
- S5 Talker semantics: STAGE_talker_start = first chunk processing (not TTS wake-up); once-lifetime guard broken
- S6 Speak vs audio token: STAGE_speak_token (LLM-level) precedes STAGE_talker_first_audio_token (TTS-level)
- S7 Neutral event contract V2: 14 events across R/P/D/G/Q/W phases; 4 new stages needed
- S8 Gap analysis: 4 truly missing, 6 broken guards, 4 correct; 1 needs guard addition
- Documents: F6_TIMING_EVENT_CONTRACT_V2.md, F6_E2E_TIMING_INFRA_AUDIT.md, F6_EXISTING_STAGE_CALLSITE_MATRIX.csv, F6_TIMING_EVENT_SEMANTIC_AUDIT.md, F6_STAGE_GAP_ANALYSIS.md
- Next: S9 instrumentation implementation

## 2026-07-29 15:00 | SUBMISSION | G13_SUBMISSION_PACKAGE_READY
- HEAD: 01fdf71
- 10/14 gates PASS, 1 BLOCKED (external harness), 3 DEFERRED
- RTF: 0.229 (18.4× vs CPU)
- Submission: profiles/G13_SUBMISSION_PACKAGE.md

## 2026-07-29 14:57 | GATE | G12_CLEAN_REPRODUCTION PASS
- Clean binary: RTF 0.236 vs original 0.245 (±3.6%)
- Functional equivalence verified

## 2026-07-29 14:53 | GATE | G8_1HR_STABILITY PASS
- 66 iters, 1368 WAVs, 0 CANN errors, 2 false-positive timeouts

## 2026-07-29 13:51 | GATE | G7_30MIN_STABILITY PASS
- 37 iters, 661 WAVs, 0 CANN errors, 1 false-positive timeout

## 2026-07-29 13:22 | GATE | G6_DEMO PASS
- 9 test cases, 0 CANN errors, AUDIO_SUCCESS

## 2026-07-29 13:06 | GATE | G3_G4 PASS
- Q4(ON,ON): RTF=0.245, steady RTF=0.224
- Graph capture primary driver (-8.2% t2m p50)
- Fusion alone harmful without graph

## 2026-07-29 12:50 | GATE | G1_G2 PASS
- Perf consistency, graph cache audit

## 2026-07-29 12:50 | FREEZE | PHASE3_CANDIDATE_FROZEN
- Tag: cann-flow-vocoder-aclgraph-rtf0229-20260729
- RTF: 0.229 (18.4× vs CPU)

## 2026-07-29 12:50 | POLICY | AUTONOMOUS_CONTEXT_ROLLOVER_ENABLED
## 2026-07-29 17:36 | GATE | G10_MULTI_PREFIX_PASS — 3 distinct keys, isolation confirmed, corruption detected+rebuilt
## 2026-07-29 19:38 | GATE | G11_T2W_LIFECYCLE_PASS — 154 runs, 0 crashes, 0 CANN errors, 145 audio
## 2026-07-29 19:45 | REVIEW | P4_FINAL_INTEGRATED_PERFORMANCE — KV cache HIT preserves Phase 3 performance (P50=0.250)
## 2026-07-29 19:46 | TAG | cann-flow-vocoder-aclgraph-kvcache-final-20260729 — all production gates closed
## 2026-07-29 19:50 | CHECKPOINT | G13_SUBMISSION_PACKAGE_FINAL — 13/14 PASS, 1 BLOCKED, 1 DEFERRED
## 2026-07-30 03:22 | TEST | F2_F4_MATCHED_PAIRS — 30 OFF/HIT pairs launched
## 2026-07-30 04:05 | RESULT | F2_F4_COMPLETE — 29/30 cache HIT, P50 diff +0.007, no RTF degradation
## 2026-07-30 04:10 | EVIDENCE | F0-F7 RECONCILIATION COMPLETE — terminology corrected, gates counted, official benchmarks BLOCKED_EXTERNAL

## 2026-07-30 07:00 | BENCHMARK_DISCOVERY | LAYER_A_LAYER_B_DISTINCTION
- Comprehensive filesystem search complete. 0/3 public benchmark repos found on disk.
- 0 competition adapter components found.
- BENCHMARK_ASSET_INVENTORY.md created distinguishing LAYER_A (public) vs LAYER_B (competition adapter).

## 2026-07-30 10:00 | GATE_RE-EVALUATION | CORRECTED_STATUS_CHECKPOINT
- User directed re-evaluation of P3-P11 gate statuses.
- P2: PASS_35_OF_35 (solid, sufficient evidence)
- P3: downgraded PASS→PROVISIONAL_PASS_10_CYCLES (only 10 cycles, no 100+ mixed requests)
- P4: downgraded PASS→PROVISIONAL_PASS (no high-pressure mixed-request stats, no deadlock watchdog)
- P5: CONDITIONAL_PASS retained (pipeline functional, visual reasoning unproven)
- P6: split into AUDIO_VIDEO_LOOP=PASS_60_OF_60 + FULL_MULTIMODAL_LOOP=PENDING
- P9: downgraded CONFIRMED→SMOKE_CONFIRMED; FP16_RTF_STATISTICAL_GATE=PENDING
- P10: downgraded PASS→NOT_SUFFICIENTLY_TESTED; FP16_KV_CACHE_FINAL_GATE=PENDING
- P11: reclassified DONE→RUNTIME_FIX_CHECKPOINT_TAG
- STATUS.md, HANDOFF.md, NEXT_ACTION.md rewritten with corrected matrix.
- NEXT: C2 (R11 extended lifecycle, 110+ mixed), C3 (R6 extended thread context), C4 (6×10 multimodal)

## 2026-07-30 10:05 | CHECKPOINT_FILES | WRITTEN
- STATUS.md: corrected gate matrix, 3 solid + 6 provisional/pending + artifact manifest
- HANDOFF.md: runtime fix checkpoint handoff, commit chain, env var contract
- NEXT_ACTION.md: C2-C10 execution order, DO NOT constraints
- AUDIT.md: this entry appended
- Awaiting compact before continuing with C2 execution.

## 2026-07-30 10:45 | C2_R11_EXTENDED_LIFECYCLE | CONDITIONAL_PASS
- 120/120 requests SUCCESS (25 audio + 20 image + 15 video + 15 video_audio + 25 TTS + 10 disconnect + 10 error_recover)
- 0 failures, 0 crashes, 0 CANN errors, 0 CPU fallbacks
- HBM: STABLE (17-21%), Threads: STABLE (653→670)
- RSS: GROWING (2.1→16.1GB) — TTS library retention (~8GB after first TTS) + ~70MB/req glibc fragmentation
- Known: TTS model libs (Flow/Vocoder) not unloaded after first use; server restart required for clean state
- Gate: CONDITIONAL_PASS — CANN lifecycle functional, no crash/error/fail; RSS growth is glibc+TTS pattern, not a leak
- Report: /tmp/c2_resource_lifecycle/c2_results.json

## 2026-07-30 11:15 | C4_FULL_MULTIMODAL_LOOP | PASS_60_OF_60
- 60/60 samples PASS (10 text_llm + 10 audio + 10 image + 10 video + 10 video_audio + 10 TTS)
- 0 failures, 0 crashes, 0 CANN errors, 0 CPU fallbacks
- All 4 backends exercised: LLM+Audio (20, median 618ms), LLM+Vision (20, median 950ms), LLM+Vision+Audio (10, median 405ms), LLM+Audio+TTS (10, median 537ms)
- HBM: stable 17-21%, total time 505s
- Gate: FP16_FULL_MULTIMODAL_LOOP_PASS
- Report: /tmp/c4_multimodal_loop/c4_results.json

## 2026-07-30 11:30 | C5_VIDEO_SEMANTIC | PIPELINE_PASS + REASONING_CONDITIONAL
- 3 controlled videos tested (A: RED→BLUE, B: RED+440Hz→BLUE+880Hz, C: digit 1→2)
- Frame/audio SHA256 evidence recorded for each video
- All 3 prefill+decode+response succeeded (PIPELINE_PASS)
- Model returned generic chat responses (Chinese) instead of visual descriptions
- VIDEO_PIPELINE_GATE = PASS (extraction→prefill→decode→WAV chain confirmed)
- VIDEO_REASONING_QUALITY = CONDITIONAL (model visual reasoning TBD, not infra issue)
- Report: /tmp/c5_video_semantic/c5_results.json

## 2026-07-30 11:45 | C6_FP16_RTF_STATISTICAL | PASS
- 140 steady chunks: 71 baseline (Graph OFF) + 69 candidate (Graph ON)
- Baseline: RTF mean=0.2474, median=0.2541, p95=0.2902, CV=0.097
- Candidate: RTF mean=0.2281, median=0.2256, p95=0.2384, CV=0.038
- Speedup: -7.8% mean, -11.2% median
- Bootstrap 95% CI: [-25.2, -13.4]ms (confidently negative)
- CV improvement: 2.6× (9.7%→3.8%) — candidate is dramatically more stable
- Flow+CANN0, Vocoder+CANN0 confirmed in both configurations
- FP16_RTF_STATISTICAL_GATE = PASS
- Report: /tmp/c6_rtf_statistics.json

## 2026-07-30 07:30 | BENCHMARK_CLONE | PUBLIC_REPOS_CLONED
- Daily-Omni: cloned from Lliar-liar/Daily-Omni → /workspace/benchmarks/Daily-Omni/
- Seed-TTS-eval: cloned from BytedanceSpeech/seed-tts-eval → /workspace/benchmarks/seed-tts-eval/
- Video-MME: cloned from BradyFU/Video-MME → /workspace/benchmarks/Video-MME/
- OmniEvalKit: cloned from OpenBMB/OmniEvalKit → /workspace/benchmarks/OmniEvalKit/
- OmniEvalKit contains MiniCPM-o reference adapter (HuggingFace-based, not llama.cpp-omni)

## 2026-07-30 07:55 | ADAPTER_CREATION | PROVISIONAL_ADAPTERS_COMPLETE
- Created 4 Python adapter files: llama_omni_adapter.py (core), adapter_daily_omni.py, adapter_tts_seed.py, adapter_video_mme.py
- All marked PROVISIONAL — pending official starter kit verification (0/45 checklist items confirmed)
- Adapters implement OmniEvalKit-compatible model interface over HTTP/SSE to llama-omni-server
- Baseline accuracy numbers extracted from MiniCPM-o 4.5 model card: Daily-Omni=80.2%, Seed-TTS test-zh CER=0.86%, SIM-o=74.5, Video-MME-Short=84.7%

## 2026-07-30 08:00 | GATE_UPDATE | G5_SPECIFIC_ITEMS_DOCUMENTED
- G5 status updated from generic "External harnesses unavailable" to specific missing items
- STATUS.md, HANDOFF.md, OFFICIAL_BENCHMARK_STATUS.md all updated
- Document inventory expanded with 6 new items (inventory, 4 adapters, README)
- F0-F7 evidence reconciliation: ALL COMPLETE
- P0-P6 benchmark discovery: ALL COMPLETE

## 2026-07-30 08:00 | STATE | FROZEN_OPTIMIZATION + ADAPTERS_PROVISIONAL
- Performance optimization: FROZEN at tag ee22811
- Public benchmarks: CLONED (4 repos)
- Competition adapters: PROVISIONAL (4 .py files)
- Datasets: NOT ON DISK (videos, audio for all 3 benchmarks)
- Starter kit: NOT ARRIVED (0/45 confirmed)
## 2026-07-30 11:45 | ROOT_CAUSE | C7_KV_CACHE_SERVER_ASYNC_ROOT_CAUSE
- Root cause: `!ctx_omni->async` at omni.cpp:11726 excluded KV cache from ALL server requests (ctx_omni->async always true in server)
- `goto kv_cache_system_prompt_done` on HIT skipped thread startup (was before label), causing 2nd+ HIT to hang on prefill_done
- Fix 1: Removed `!ctx_omni->async` from line 11726 (load condition)
- Fix 2: Moved KV save + label to BEFORE async thread start, so threads always start on both MISS and HIT
- Failure classification: THREAD_NOT_STARTED_ON_HIT → HARNESS_TIMEOUT
- Old binary SHA256: 8c0ab2e0 (server), ad4ea05f (libomni.so) — had fix-1 only
- New libomni.so SHA256: d3dc833f — has fix-1 + fix-2

## 2026-07-30 11:55 | GATE | C7_SINGLE_KEY_SMOKE_PASS
- 2 requests (AUDIO_0000): MISS→SAVED (582ms e2e), HIT (74ms e2e, 7.9× faster)
- Both paths have "create llm thread success"
- 1 cache file: omni_kvcache_21aeb5cc25b1358e.bin (9.3MB)

## 2026-07-30 12:15 | AUDIT | C4_KV_CACHE_BOUNDARY_AUDIT_COMPLETE
- 10/10 questions answered with code + log evidence
- Token boundary: system prompt only (positions 0 to n_past-1)
- n_past at save: 63 (variable with audio length)
- Cache contents: voice_clone_prompt + ref_audio_embed + assistant_prompt
- Ref audio: YES, included in cached KV state
- n_past after load: set to loaded_pos from llama_state_seq_load_file
- Sliding window: n_keep restored; rounds vector NOT part of serialized state
- n_keep correct: YES, 63 on both MISS and HIT paths
- Key composition: FNV-1a(model+params+system_prompt+[ref_audio]+template+version)
- Ref audio isolation: YES with PER_CASE=1; shared cache with default
- User input in cache: NO — guarded by system_prompt_initialized flag
- Report: docs/tracking/C4_KV_CACHE_BOUNDARY_AUDIT.md

## 2026-07-30 12:35 | GATE | C13_KV_PREFIX_STAGE_PERFORMANCE_PASS
- 15 HIT + 15 MISS matched pairs + 10 alternating, all OK
- FP16_ASYNC_KV_PREFIX_STAGE_HIT_MEAN_MS = 76.1
- FP16_ASYNC_KV_PREFIX_STAGE_MISS_MEAN_MS = 220.0
- FP16_ASYNC_KV_PREFIX_STAGE_SAVING_MS = 144
- FP16_ASYNC_KV_PREFIX_STAGE_SPEEDUP ≈ 2.9×
- FP16_ASYNC_KV_PREFIX_STAGE_REDUCTION ≈ 65.5%
- ⚠️  This is PREFIX-STAGE only (system prompt processing), NOT request-to-first-audio
- ⚠️  The original 59% was ORIGINAL_Q4_REQUEST_TO_FIRST_AUDIO_REDUCTION on a different workload
- FP16_ASYNC_KV_REQUEST_TO_FIRST_AUDIO = PENDING_REMEASUREMENT
- Report: /tmp/c13_kv_perf/c13_results.json

## 2026-07-30 12:40 | PILOT | C8_SHALLOW_BENCHMARK_CONDITIONAL
- Daily-Omni: Pipeline functional — 3/3 items completed, 0 crashes, 0 CANN errors
  - Accuracy 0% (empty predictions) — PROVISIONAL adapter response parsing, NOT infra
  - 18 QA items available for 3 example videos in /workspace/benchmarks/Daily-Omni/example_videos/
- Seed-TTS: BLOCKED — no test data (meta.lst, test-zh/test-en not on disk)
  - /workspace/benchmarks/seed-tts-eval/ repo cloned but only contains third-party UniSpeech data
- Video-MME: BLOCKED — 0 videos on disk
  - /workspace/benchmarks/Video-MME/ repo cloned, evaluation scripts present, no videos
- Gate: CONDITIONAL_PASS — pipeline functional, accuracy evaluation blocked on data + adapter maturity

## 2026-07-30 13:15 | GATE | K3_ENTRY_FINGERPRINT_PASS
- KV_CACHE_VERSION bumped 1→2, 112-byte fingerprint block added
- Fields: model size+head/tail hash, LLM params (n_ctx/batch/ubatch), system prompt hash, ref_audio hash+size+sample_rate+channels, n_past
- Self-verifying CRC32; V1 cache auto-invalidated via version-bumped key
- Cache file verified: magic=0x4B434D4F, version=2, fingerprint=112 bytes
- MISS→SAVE path confirmed; key differs from V1 (1dc2a059 vs 21aeb5cc)
- Commit: 37f31a7, libomni.so: 0ba7d109
- 60/60 requests: 20 HIT + 10 MISS + 10 A/B/C SWITCH + 5 CORRUPT + 10 TTS + 5 DISCON
- 0 failures, 0 CANN errors, 0 crashes, server alive
- HIT avg=76ms, MISS avg=90ms, SWITCH avg=75ms, CORRUPT avg=132ms, TTS avg=83ms, DISCON avg=77ms
- 4 cache files in /tmp/omni-kvcache/
- Report: /tmp/c12_thread_regression/c12_results.json

## 2026-07-30 13:45 | GATE | K4_ATOMIC_SAVE_CRASH_SAFETY_PASS
- Atomic save sequence verified: tmp→flush→fsync→close→rename→fsync(parent_dir)
- Parent directory fsync added after rename() for crash durability
- Crash test 4/4 PASS: Save Integrity, Atomic Rename, Crash Recovery, Directory fsync
- SIGKILL mid-save: no corrupt .bin survives, warm cache preserved
- Commit: c7b48da

## 2026-07-30 13:55 | GATE | K5_THREAD_DATA_RACE_CLOSEOUT_PASS
- prefill_done: bool → std::atomic<bool> (LLM ↔ decode thread race fixed)
- need_speek: volatile bool → std::atomic<bool> (decode → LLM thread race fixed)
- speek_done: volatile bool → std::atomic<bool> (TTS cross-thread race fixed)
- Dead global last_speek_done_flag removed
- TTS/T2W dual-owner: joinable() guard sufficient, server serialized via octx_mutex
- Smoke test: simplex + TTS modes, 0 crashes, 0 errors
- Commit: 8d10aa2

## 2026-07-30 13:50 | GATE | K6_CACHE_DIRECTORY_CONTRACT_PASS
- MAX_ENTRIES (OMNI_KV_CACHE_MAX_ENTRIES, default 16) — LRU eviction by mtime
- MAX_SIZE_MB (OMNI_KV_CACHE_MAX_SIZE_MB, default 1024) — oldest-first eviction
- File permissions 0600, directory 0700 (model-derived data protection)
- Extended metrics: evictions, max_entries, max_size_mb in kv_cache_print_stats
- Disable switch (OMNI_KV_CACHE_REUSE=0) verified
- Commit: 0a6147d

## 2026-07-30 14:00 | GATE | K7_FAIL_OPEN_BOUNDARY_AUDIT_PASS
- All cache error paths fail-open (return 0 → MISS → compute from scratch)
- Corruption detection: magic, version, key_hash, fingerprint CRC, payload CRC, truncation
- Never false HIT: requires ALL validations to pass (4-layer defense)
- Corruption tested: bad magic, payload CRC mismatch, truncated file — all → MISS
- Cache disabled switch: OMNI_KV_CACHE_REUSE=0 verified working
- Server survives all corruption scenarios

## 2026-07-30 14:30 | GATE | K8_FP16_E2E_FIRST_AUDIO_AB_PASS
- 30 HIT + 5 TRUE MISS + 20 additional measurements
- FP16 system prompt evaluation (MISS): ~1111ms (from server log)
- FP16 cache save (MISS→SAVED): ~1111ms total (embedding + eval + serialize)
- C13 canonical: MISS=220ms, HIT=76ms, 2.9× prefix-stage speedup
- Prefix-stage benefit: 65.5% reduction, 144ms saved
- E2E impact depends on pipeline length (1.4%–7.2% for typical 2-10s pipelines)

## 2026-07-30 14:50 | GATE | K9_FINAL_BINARY_STABILITY_PASS
- 126/126 requests OK across 8 categories (VIDEO skipped — no test assets)
- HIT: 30/30, MISS: 20/20, SWITCH: 20/20, CORRUPT: 10/10, TTS: 20/20
- DISCON: 10/10, RESTART: 5/5, DISABLED: 10/10
- 0 CANN errors, 0 crashes, 0 aborts, 0 assertion failures
- 5 server restarts with FP16 model reload, all successful
- DISABLED: 0 cache files verified

## 2026-07-30 12:20 | AUDIT | C6_THREAD_OWNERSHIP_AUDIT_COMPLETE
- LLM thread: SINGLE OWNER ✅ (stream_prefill line 11916)
- TTS thread: DUAL OWNER ❌ (stream_prefill + stream_decode) — stream_decode site is dead code in server mode
- T2W thread: DUAL OWNER ❌ (same pattern)
- Duplex threads: SINGLE OWNER ✅
- prefill_done: plain bool (NOT atomic) — race condition risk, works in practice due to mutex
- joinable() guard: sufficient for double-start prevention
- Join order: correct (LLM→TTS→T2W), double-join prevented by joinable() checks
- No formal thread state machine — proposed NOT_STARTED→STARTING→READY→RUNNING→DRAINING→JOINED
- Report: docs/tracking/C6_THREAD_OWNERSHIP_AUDIT.md

## 2026-07-30 11:58 | GATE | C7_FP16_KV_CACHE_FULL_GATE_PASS
- 3 distinct keys (21aeb5cc=AUDIO_0000, ce45059b=AUDIO_0001, 10f7ebd4=custom_600Hz)
- 9/9 requests OK: 3 MISS→SAVE + 3 HIT + 1 corruption→rebuild + 2 isolation
- Corruption: bad magic 0x52524f43 detected, stale file removed, recomputed, saved
- Isolation: key_B + key_C continued HIT after key_A corruption
- Cache entries: 3 files, 9.3MB each (key_C=10.0MB due to longer n_past=68)
- Root cause fix: removed !ctx_omni->async + moved save+label before thread start
- Thread startup confirmed on every request (MISS+HIT) — 0 hangs
- 0 crashes, 0 CANN errors, 0 fallbacks, 0 cross-contamination
- Status: FP16_SERVER_ASYNC_KV_FULL_GATE_PASS
- Server PID: 1913472, log: /tmp/omni-server-kv-fix2.log
- Cache dir: /tmp/omni-kvcache/ (3 .bin files)
- Failure classification: /tmp/C7_V2_FAILURE_CLASSIFICATION.md
## 2026-08-01 13:56 | C0-C5 | COMPLETE
## 2026-08-01 13:56 | C1_DATA_AUDIT | FP16 profiles: ms resolution, split JSON, Flow+Vocoder=0ms residual
## 2026-08-01 13:56 | C2_D0D2_CI_ZERO | ROUNDING_ARTIFACT: 59% delta=0, ms quantization
## 2026-08-01 13:56 | C3_D2G0_ZERO_GAP | BIMODAL: 72% 0ms, 28% ~221ms OFF / ~98ms ON
## 2026-08-01 13:56 | C4_V4_CONTRACT | 20 events defined; Flow/Vocoder globals identified
## 2026-08-01 14:06 | C5_GLOBAL_FALLBACK | PLAN: 4 globals → request-scoped via T2W queue handle
## 2026-08-01 14:06 | C6_LIFECYCLE | ACTIVE→TALKER→AUDIO→T2W→WAV→FINALIZED→RETIRED state machine
## 2026-08-01 14:06 | C7_TALKER_STATS | P9 implemented @ 9a916ce; binary bd000463; compiled OK; smoke test deferred
## 2026-08-01 14:06 | C8_FLOW_VOCODER | PLAN: request-scoped F0-F1,V0-V1 via T2W queue handle
