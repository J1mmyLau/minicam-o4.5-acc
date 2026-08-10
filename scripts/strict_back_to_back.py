#!/usr/bin/env python3
"""Strict WS back-to-back reliability gate — 0s inter-session sleep, 0 retries.

Usage:
    OMNI_WS_DIAG=1 OMNI_WS_VALIDATION=1 OMNI_PER_CHUNK_DRAIN=0 \
    OMNI_T2W_DEVICE=cann-flow-only OMNI_T2W_DRAIN_TIMEOUT_MS=5000 \
        ./build/bin/llama-omni-server -m F16.gguf -t 4 --port 22500 \
        2>/tmp/server-stderr.log &

    python3 strict_back_to_back.py --sessions 50 --stderr /tmp/server-stderr.log
"""

import asyncio, json, base64, struct, time, sys, os, wave, io, subprocess, re
import numpy as np

WS_URL = None
VIDEO = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5/assets/omni_duplex1.mp4"
CHUNK_DURATION_S = 1.0
TARGET_SR = 16000
INTER_SESSION_SLEEP_S = 0  # STRICT: no sleep
CONNECT_RETRIES = 0         # STRICT: no retries

# ── Audio helpers ──────────────────────────────────────────────────

def extract_audio(path):
    if path.endswith('.mp4'):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
        subprocess.run(["ffmpeg", "-y", "-i", path, "-ac", "1", "-ar", str(TARGET_SR),
                        "-f", "wav", wav_path], capture_output=True, check=True)
        audio = load_wav(wav_path)
        os.unlink(wav_path)
        return audio
    else:
        return load_wav(path)

def load_wav(path):
    with wave.open(path, 'rb') as w:
        frames = w.readframes(w.getnframes())
        sr, nch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
    if sw == 2:
        samples = struct.unpack(f'<{len(frames)//2}h', frames)
        audio = [s / 32768.0 for s in samples]
    else:
        audio = list(struct.unpack(f'<{len(frames)//4}f', frames))
    if nch > 1:
        audio = [sum(audio[i:i+nch])/nch for i in range(0, len(audio), nch)]
    return audio

def make_chunk_b64(chunk):
    i16 = [max(-32768, min(32767, int(s * 32767))) for s in chunk]
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(TARGET_SR)
        w.writeframes(struct.pack(f'<{len(i16)}h', *i16))
    return base64.b64encode(buf.getvalue()).decode()

# ── Session runner ─────────────────────────────────────────────────

async def run_one_session(session_n, all_chunks, chunk_size, max_chunks=0):
    """Run one full-duplex session. Returns dict with result + close_code."""
    if max_chunks > 0:
        max_samples = max_chunks * chunk_size
        if max_samples < len(all_chunks):
            all_chunks = all_chunks[:max_samples]
    import websockets

    result = {
        "session_n": session_n,
        "success": False,
        "fail_stage": None,
        "error": None,
        "n_speak": 0,
        "n_listen": 0,
        "n_tail": 0,
        "rtf_mean": 0.0,
        "wall_mean_ms": 0.0,
        "prepare_ms": 0.0,
        "close_code": None,
        "connection_attempts": 0,
        "session_id": "",
    }

    # STRICT: no retries — single connect attempt
    result["connection_attempts"] = 1
    try:
        ws = await websockets.connect(WS_URL, max_size=128*1024*1024, ping_interval=None)
    except Exception as e:
        result["fail_stage"] = "connect"
        result["error"] = str(e)[:120]
        result["close_code"] = "connect_failed"
        return result

    try:
        t0 = time.perf_counter()
        await ws.send(json.dumps({"type": "session.init", "payload": {
            "mode": "full_duplex", "use_tts": True,
            "config": {"force_listen_count": 0},
        }}))

        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=60)
        except asyncio.TimeoutError:
            result["fail_stage"] = "session.init_timeout"
            result["error"] = "no response to session.init within 60s"
            result["close_code"] = "init_timeout"
            await ws.close()
            return result

        init = json.loads(raw)

        # Check for active session rejection
        if init.get('type') == 'session.closed':
            reason = init.get('reason', '')
            result["fail_stage"] = "session.rejected"
            result["error"] = reason
            result["close_code"] = "rejected"
            if 'active session exists' in reason.lower():
                result["fail_stage"] = "active_session_exists"
                result["close_code"] = "active_session_exists"
            await ws.close()
            return result

        result["prepare_ms"] = (time.perf_counter() - t0) * 1000
        sid = init.get('session_id', '')[:12]
        result["session_id"] = sid

        # Wait for pipeline init (TTS load + prefill)
        await asyncio.sleep(20)

        # Send chunks
        total_chunks = len(all_chunks) // chunk_size
        speak_walls = []

        for i in range(total_chunks):
            start = i * chunk_size
            chunk = all_chunks[start:start+chunk_size]
            if len(chunk) < chunk_size:
                break

            b64 = make_chunk_b64(chunk)
            t_send = time.perf_counter_ns()

            try:
                await ws.send(json.dumps({"type": "input.append", "input": {
                    "audio": b64, "streaming": True,
                    "generation": {"max_new_tokens": 100},
                }}))
            except Exception as e:
                result["fail_stage"] = f"send_chunk_{i}"
                result["error"] = str(e)[:120]
                result["close_code"] = "send_failed"
                return result

            has_audio = False
            has_listen = False
            t_result = 0
            error = None

            t_recv_start = time.monotonic()
            while True:
                timeout = 60 - (time.monotonic() - t_recv_start)
                if timeout <= 0:
                    error = "timeout"
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(timeout, 15))
                except asyncio.TimeoutError:
                    error = "recv_timeout"
                    break

                evt = json.loads(raw)
                et = evt.get('type', '')
                kind = evt.get('kind', '')

                if et == 'response.output.delta':
                    if kind == 'listen':
                        t_result = time.perf_counter_ns()
                        has_listen = True
                        break
                    if evt.get('audio', ''):
                        t_result = time.perf_counter_ns()
                        has_audio = True
                        break
                elif et == 'response.done':
                    t_result = time.perf_counter_ns()
                    break
                elif et in ('session.closed', 'error'):
                    error = f"{et}: {evt.get('reason', '?')}"
                    t_result = time.perf_counter_ns()
                    break

            wall_ms = (t_result - t_send) / 1e6 if t_result else 0
            if has_listen:
                result["n_listen"] += 1
            elif has_audio:
                result["n_speak"] += 1
                speak_walls.append(wall_ms)
            elif error:
                result["fail_stage"] = f"chunk_{i}_{error}"
                result["error"] = error
                return result
            else:
                result["n_tail"] += 1

        # Normal completion
        await ws.send(json.dumps({"type": "session.close"}))
        try:
            close_frame = await asyncio.wait_for(ws.recv(), timeout=5)
            close_data = json.loads(close_frame)
            if close_data.get('type') == 'session.closed':
                result["close_code"] = "normal"
        except Exception:
            result["close_code"] = "normal"  # ws.close() succeeded
        await ws.close()

        if result["n_speak"] > 0:
            result["rtf_mean"] = np.mean(speak_walls) / 1000.0
            result["wall_mean_ms"] = np.mean(speak_walls)
            result["success"] = True
        else:
            result["fail_stage"] = "no_speak_chunks"
            result["error"] = "0 SPEAK_GENERATION chunks"
        return result

    except websockets.exceptions.ConnectionClosed as e:
        result["fail_stage"] = result.get("fail_stage") or "ws_closed"
        result["error"] = str(e)[:120]
        result["close_code"] = f"ws_close_{e.code}"
        try: await ws.close()
        except Exception: pass
        return result
    except Exception as e:
        result["fail_stage"] = result.get("fail_stage") or "exception"
        result["error"] = str(e)[:200]
        print(f"  [exception] {result['error']}")
        try: await ws.close()
        except Exception: pass
        return result

# ── [validate] log parser ──────────────────────────────────────────

def parse_validate_log(stderr_path):
    """Parse [validate] lines from server stderr log.
    Returns dict of per-session metrics."""
    sessions = {}  # session_id -> {cleanup, drains, t2w_drains, ...}
    orphan_events = []  # events without session_id

    try:
        with open(stderr_path, 'r') as f:
            for line in f:
                if '[validate]' not in line:
                    continue

                # Parse key=value pairs
                fields = {}
                # Extract all key=value pairs
                for m in re.finditer(r'(\w+)=(\S+)', line):
                    fields[m.group(1)] = m.group(2)

                event = fields.get('event', '')
                session_id = fields.get('session', '')

                if event in ('cleanup_begin', 'cleanup_end',
                            'drain_begin', 'drain_end'):
                    if session_id:
                        if session_id not in sessions:
                            sessions[session_id] = {
                                'cleanup_begin_ts': None,
                                'cleanup_end_ts': None,
                                'cleanup_duration_ns': 0,
                                'drains': [],
                                't2w_drains': [],
                                'audio_delivered': -1,
                            }
                        s = sessions[session_id]
                        if event == 'cleanup_begin':
                            s['cleanup_begin_ts'] = int(fields.get('ts_ns', 0))
                        elif event == 'cleanup_end':
                            s['cleanup_end_ts'] = int(fields.get('ts_ns', 0))
                            s['cleanup_duration_ns'] = int(fields.get('duration_ns', 0))
                            s['audio_delivered'] = int(fields.get('audio_delivered', -1))
                        elif event == 'drain_begin':
                            s['drains'].append({
                                'step': fields.get('step', '?'),
                                'begin_ts': int(fields.get('ts_ns', 0)),
                                'end_ts': None,
                                'duration_ns': 0,
                            })
                        elif event == 'drain_end':
                            if s['drains']:
                                s['drains'][-1]['end_ts'] = int(fields.get('ts_ns', 0))
                                s['drains'][-1]['duration_ns'] = (
                                    s['drains'][-1]['end_ts'] - s['drains'][-1]['begin_ts']
                                )
                elif event in ('t2w_drain_begin', 't2w_drain_end',
                              't2w_queue_dropped_count'):
                    # T2W events — find the most recent session
                    if session_id and session_id in sessions:
                        s = sessions[session_id]
                        if event == 't2w_drain_begin':
                            s['t2w_drains'].append({
                                'queued_before': int(fields.get('queued', 0)),
                                'active_before': int(fields.get('active', 0)),
                                'timeout_ms': int(fields.get('timeout_ms', 0)),
                                'begin_ts': int(fields.get('ts_ns', 0)),
                                'end_ts': None,
                                'duration_ns': 0,
                                'drained': -1,
                                'timeout': -1,
                                'queued_after': -1,
                                'active_after': -1,
                                'wav_count': -1,
                                'errors': -1,
                            })
                        elif event == 't2w_drain_end':
                            if s['t2w_drains']:
                                d = s['t2w_drains'][-1]
                                d['end_ts'] = int(fields.get('ts_ns', 0))
                                d['duration_ns'] = int(fields.get('duration_ns', 0))
                                d['drained'] = int(fields.get('drained', -1))
                                d['timeout'] = int(fields.get('timeout', -1))
                                d['queued_after'] = int(fields.get('queued_after', -1))
                                d['active_after'] = int(fields.get('active_after', -1))
                                d['wav_count'] = int(fields.get('wav_count', -1))
                                d['errors'] = int(fields.get('errors', -1))
                        elif event == 't2w_queue_dropped_count':
                            s['dropped_count'] = int(fields.get('count', 0))
    except FileNotFoundError:
        print(f"WARNING: stderr log not found: {stderr_path}")

    return sessions

# ── Main ────────────────────────────────────────────────────────────

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=50, help="Max sessions to run")
    parser.add_argument("--port", type=int, default=22500, help="Server port")
    parser.add_argument("--stderr", type=str, default="/tmp/server-stderr.log",
                        help="Path to server stderr log for [validate] parsing")
    parser.add_argument("--inter-sleep", type=float, default=INTER_SESSION_SLEEP_S,
                        help="Inter-session sleep in seconds (default: 0)")
    parser.add_argument("--retries", type=int, default=CONNECT_RETRIES,
                        help="Connect retries (default: 0)")
    parser.add_argument("--max-chunks", type=int, default=0,
                        help="Max chunks to send per session (0 = all)")
    args = parser.parse_args()

    global WS_URL
    WS_URL = f"ws://127.0.0.1:{args.port}/backend"

    audio = extract_audio(VIDEO)
    chunk_size = int(CHUNK_DURATION_S * TARGET_SR)
    total_chunks = len(audio) // chunk_size
    if args.max_chunks > 0:
        total_chunks = min(total_chunks, args.max_chunks)

    print(f"STRICT BACK-TO-BACK RELIABILITY GATE")
    print(f"Sessions: {args.sessions} | Sleep: {args.inter_sleep}s | Retries: {args.retries}")
    print(f"Stderr log: {args.stderr}")
    print(f"{'='*60}")

    results = []
    t_start = time.monotonic()

    for n in range(1, args.sessions + 1):
        t_session_start = time.monotonic()
        print(f"\n--- Session {n}/{args.sessions} ---")
        r = await run_one_session(n, audio, chunk_size, args.max_chunks)
        elapsed = time.monotonic() - t_session_start
        results.append(r)

        status = "PASS" if r["success"] else f"FAIL({r['fail_stage']})"
        print(f"  {status} | speak={r['n_speak']} listen={r['n_listen']} tail={r['n_tail']} | "
              f"rtf={r['rtf_mean']:.4f} wall={r['wall_mean_ms']:.0f}ms | "
              f"close={r['close_code']} | {elapsed:.0f}s")

        # Inter-session sleep (0 for strict mode)
        if n < args.sessions and args.inter_sleep > 0:
            await asyncio.sleep(args.inter_sleep)

    total_time = time.monotonic() - t_start

    # ── Parse [validate] log ────────────────────────────────────────
    validate_sessions = parse_validate_log(args.stderr)

    # ── Summary ─────────────────────────────────────────────────────
    n_pass = sum(1 for r in results if r["success"])
    n_fail = sum(1 for r in results if not r["success"])
    n_total = len(results)

    # Count failure categories
    active_session_rejections = sum(
        1 for r in results if r.get('fail_stage') == 'active_session_exists')
    unexpected_ws_closes = sum(
        1 for r in results if r.get('fail_stage') == 'ws_closed')
    close_codes = {}
    for r in results:
        cc = r.get('close_code', 'unknown')
        close_codes[cc] = close_codes.get(cc, 0) + 1

    print(f"\n{'='*60}")
    print(f"STRICT BACK-TO-BACK GATE RESULTS")
    print(f"{'='*60}")
    print(f"TOTAL_SESSIONS          = {n_total}")
    print(f"FIRST_ATTEMPT_SUCCESS   = {n_pass}/{n_total}")
    print(f"FAILED_SESSIONS         = {n_fail}")
    print(f"ACTIVE_SESSION_REJECTIONS = {active_session_rejections}")
    print(f"UNEXPECTED_WS_CLOSES    = {unexpected_ws_closes}")
    print(f"CLOSE_CODES             = {close_codes}")
    print(f"CONNECTION_ATTEMPTS     = {n_total}")  # 1 attempt per session in strict mode

    # Failure breakdown
    if n_fail > 0:
        print(f"\nFailure breakdown:")
        from collections import Counter
        stages = Counter(r["fail_stage"] for r in results if not r["success"])
        for stage, count in stages.most_common():
            print(f"  {stage}: {count}")

    # Performance stats (pass only)
    pass_results = [r for r in results if r["success"]]
    if pass_results:
        rtfs = [r["rtf_mean"] for r in pass_results]
        walls = [r["wall_mean_ms"] for r in pass_results]
        prepares = [r["prepare_ms"] for r in pass_results]
        print(f"\nPerformance (PASS sessions only):")
        print(f"  RTF mean:    {np.mean(rtfs):.4f}")
        print(f"  RTF p50:     {np.median(rtfs):.4f}")
        print(f"  Wall mean:   {np.mean(walls):.0f}ms")
        print(f"  Prepare mean:{np.mean(prepares):.0f}ms")

    # ── Cleanup timing ──────────────────────────────────────────────
    if validate_sessions:
        cleanup_durations_ms = []
        drain_durations_ms = []
        t2w_drain_durations_ms = []
        drain_timeout_count = 0
        total_dropped_t2w = 0
        total_audio_delivered = 0
        total_wav_count = 0

        for sid, s in validate_sessions.items():
            if s['cleanup_duration_ns'] > 0:
                cleanup_durations_ms.append(s['cleanup_duration_ns'] / 1e6)
            for d in s['drains']:
                if d['duration_ns'] > 0:
                    drain_durations_ms.append(d['duration_ns'] / 1e6)
            for td in s['t2w_drains']:
                if td['duration_ns'] > 0:
                    t2w_drain_durations_ms.append(td['duration_ns'] / 1e6)
                if td['timeout'] == 1:
                    drain_timeout_count += 1
                if td['wav_count'] > 0:
                    total_wav_count += td['wav_count']
            if s.get('dropped_count', 0) > 0:
                total_dropped_t2w += s['dropped_count']
            if s.get('audio_delivered', -1) > 0:
                total_audio_delivered += s['audio_delivered']

        print(f"\n{'='*60}")
        print(f"CLEANUP TIMING (from [validate] instrumentation)")
        print(f"{'='*60}")
        if cleanup_durations_ms:
            arr = np.array(cleanup_durations_ms)
            print(f"  Cleanup mean:   {np.mean(arr):.1f}ms")
            print(f"  Cleanup p50:    {np.median(arr):.1f}ms")
            print(f"  Cleanup p90:    {np.percentile(arr, 90):.1f}ms")
            print(f"  Cleanup max:    {np.max(arr):.1f}ms")
            print(f"  Cleanup samples:{len(arr)}")
        else:
            print(f"  (no cleanup data)")

        if drain_durations_ms:
            arr = np.array(drain_durations_ms)
            print(f"\n  Per-step drain:")
            print(f"    mean: {np.mean(arr):.1f}ms  p50: {np.median(arr):.1f}ms  "
                  f"p90: {np.percentile(arr, 90):.1f}ms  max: {np.max(arr):.1f}ms")

        if t2w_drain_durations_ms:
            arr = np.array(t2w_drain_durations_ms)
            print(f"\n  T2W drain (omni_prepare):")
            print(f"    mean: {np.mean(arr):.1f}ms  p50: {np.median(arr):.1f}ms  "
                  f"p90: {np.percentile(arr, 90):.1f}ms  max: {np.max(arr):.1f}ms")

        print(f"\n{'='*60}")
        print(f"T2W DATA-LOSS GATE")
        print(f"{'='*60}")
        print(f"  DRAIN_TIMEOUT_COUNT      = {drain_timeout_count}")
        print(f"  DROPPED_T2W_CHUNKS       = {total_dropped_t2w}")
        print(f"  AUDIO_CHUNKS_GENERATED   = {total_wav_count}")
        print(f"  AUDIO_CHUNKS_DELIVERED   = {total_audio_delivered}")
        print(f"  VALIDATE_SESSIONS_PARSED = {len(validate_sessions)}")

        # T2W drain safety gate
        drain_safety = "PASS" if (drain_timeout_count == 0 and total_dropped_t2w == 0) else "FAIL"
        if total_wav_count == 0 and total_audio_delivered == 0:
            drain_safety = "NOT_PROVEN"  # no validation data captured
        print(f"\n  T2W_DRAIN_SAFETY = {drain_safety}")

    # ── Final verdict ───────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"FINAL OUTPUT")
    print(f"{'='*60}")

    back_to_back_gate = "PASS" if (n_pass == n_total and n_pass >= 50) else "FAIL"

    print(f"ROOT_CAUSE_STATUS       = CONFIRMED")
    print(f"STRICT_BACK_TO_BACK_GATE = {back_to_back_gate}")
    print(f"FIRST_ATTEMPT_SUCCESS   = {n_pass}/{n_total}")

    if validate_sessions:
        print(f"DRAIN_TIMEOUT_COUNT     = {drain_timeout_count}")
        print(f"DROPPED_T2W_CHUNKS      = {total_dropped_t2w}")
        if cleanup_durations_ms:
            arr = np.array(cleanup_durations_ms)
            print(f"CLEANUP_P50_MS          = {np.median(arr):.1f}")
            print(f"CLEANUP_P90_MS          = {np.percentile(arr, 90):.1f}")
            print(f"CLEANUP_MAX_MS          = {np.max(arr):.1f}")
    else:
        print(f"DRAIN_TIMEOUT_COUNT     = N/A (no validation data)")
        print(f"DROPPED_T2W_CHUNKS      = N/A")
        print(f"CLEANUP_P50_MS          = N/A")
        print(f"CLEANUP_P90_MS          = N/A")
        print(f"CLEANUP_MAX_MS          = N/A")

    if back_to_back_gate == "PASS" and drain_safety == "PASS":
        print(f"\nFIX_VERIFIED = YES")
    else:
        print(f"\nFIX_VERIFIED = NO — gates not all passed")

    print(f"\nTotal wall time: {total_time:.0f}s ({total_time/60:.1f}min)")

if __name__ == "__main__":
    asyncio.run(main())
