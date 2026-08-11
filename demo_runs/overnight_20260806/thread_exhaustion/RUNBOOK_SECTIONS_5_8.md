# Runbook: Sections 5→8 Execution Plan
Date: 2026-08-06
Server binary: SHA256 2bfb2e5028c4f0cf5b8a9e17b22c2cd071505db9e0baa9afc456c00bae84ceb4
Source: FROZEN at bdd4550

## Section 5: 25-Session Verification (IN PROGRESS)

### Status
- Server: PID 1018787, `-t 4`, Q4_K_M model
- Completed: 4/25 sessions
  - S01-S03: Δ=+3 each (new httplib workers, new OpenMP teams)
  - S04: Δ=+0 (worker reuse — OpenMP team already exists for this worker)
- Threads: 653 (644 baseline + 9 from sessions)
- Pattern confirmed: 3 threads per NEW worker, 0 for reuse

### Gates (to evaluate after completion)
1. THREAD_COUNT_GROWTH_AFTER_WARMUP <= 5%
   - With -t 4: ~3 threads per NEW worker. 25 sessions might hit 10-20 new workers.
   - Expected growth: 30-60 threads from 650 baseline = 4.6-9.2%
   - MAY FAIL at -t 4. If so, Option B: re-run with -t 1 (0 growth, slower).
2. NET_THREAD_GROWTH_PER_SESSION ≈ 0
   - With -t 4: avg ~1.5-2.4/session (declining with worker reuse)
   - With -t 1: exactly 0/session
3. CGROUP_PIDS_HEADROOM > 50%
   - 639 workers × 3 threads = 1917 max additional threads
   - With baseline ~1000 threads: max ~3000 total < 5000 (50% of 10000)
   - SHOULD PASS
4. DRAIN_TIMEOUT_COUNT=0
   - Currently: 1 baseline DRAIN_TIMEOUT (pre-existing)
   - NEEDS: 0 NEW timeouts during verification

### Post-verification
- 60min stability test (Section 5b)
- Then proceed to Section 6

## Section 6: WS Adapter Integration Test

### Prerequisites
- Server must be IDLE (no active sessions)
- Server must be running with turn_based TTS support

### Test Plan
1. Kill verification server after Section 5 completes
2. Start fresh server: `-t 4` with Q4_K_M (fast iteration)
3. Run ws_adapter.py independently (NOT via benchmark_client.py first)
4. Validate field mapping:
   - session.init → session.created
   - input.append → response.output.delta (kind=text)
   - response.output.delta (kind=audio, field="audio")
   - response.done
5. Save raw WS events for audit
6. Then integrate with benchmark_client.py

### Test Script
/tmp/test_ws_adapter.py (to be created)

## Section 7: Official RTF Measurement

### Prerequisites
- F16 model at /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf
- Server with -t 4 flag
- benchmark_client.py from /workspace/llama.cpp-omni-official-eval/competition/
- WS adapter from /workspace/llama.cpp-omni-session-fix/submission/adapters/ws_adapter.py

### Server Launch (F16)
```bash
ASCEND_RT_VISIBLE_DEVICES=0 \
./build/bin/llama-omni-server \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf \
  --host 0.0.0.0 --port 8080 \
  -ngl 99 --ctx-size 2048 --batch-size 512 --ubatch-size 512 \
  -t 4
```

### RTF Measurement
```bash
cd /workspace/llama.cpp-omni-official-eval/competition
PYTHONPATH=/workspace/llama.cpp-omni-session-fix/submission/adapters \
python3 benchmark_client.py --adapter ws --url ws://localhost:8080/backend -c 1 -n 5
```

### Expected RTF Calculation
- RTF = (LLM decode time + TTS vocoder time) / audio duration
- With -t 4: LLM decode slower than -t 320 but no thread explosion
- F16 model: larger weights, slower inference than Q4_K_M
- Target: compare against official baseline 1.087 (F16)

## Section 8: Final Status Output

### Template
See /tmp/final_status_20260806.md (to be created)

### Status Items
1. THREAD_LEAK_ROOT_CAUSE: libgomp OpenMP pool per httplib worker (cpuparams.n_threads=320 → 319 new threads)
2. THREAD_FIX_COMMIT: N/A (source frozen) — runtime flag -t 4
3. THREAD_FIX_EFFECTIVENESS: 99.1% reduction (319→3 threads per NEW worker)
4. LONG_RUNNING_STABILITY: PENDING 60min test
5. OFFICIAL_RTF: PENDING F16 measurement
6. FIX_BRANCH_RELEASE_CANDIDATE: TBD
7. OFFICIAL_COMPETITION_READY: TBD
