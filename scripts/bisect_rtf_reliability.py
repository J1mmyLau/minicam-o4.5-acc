#!/usr/bin/env python3
"""WS session reliability test harness — N sequential sessions against one server.

Usage:
    OMNI_WS_DIAG=1 OMNI_PER_CHUNK_DRAIN=0 OMNI_T2W_DEVICE=cann-flow-only \
        ./build/bin/llama-omni-server -m F16.gguf -t 4 --port 22500 &
    sleep 30
    python3 bisect_rtf_reliability.py [--sessions 50] [--max-failures 10]
"""

import asyncio, json, base64, struct, time, sys, os, wave, io, subprocess
import numpy as np

WS_URL = None  # set by --port
VIDEO = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5/assets/omni_duplex1.mp4"
CHUNK_DURATION_S = 1.0
TARGET_SR = 16000
INTER_SESSION_SLEEP_S = 25

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

async def run_one_session(session_n, all_chunks, chunk_size):
    """Run one full-duplex session. Returns dict with result."""
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
    }

    for connect_retry in range(3):
        try:
            ws = await websockets.connect(WS_URL, max_size=128*1024*1024, ping_interval=None)
            break
        except Exception as e:
            if connect_retry < 2:
                print(f"  [retry] connect attempt {connect_retry+1} failed: {str(e)[:80]}")
                await asyncio.sleep(5)
            else:
                result["fail_stage"] = "connect"
                result["error"] = str(e)[:120]
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
            await ws.close()
            return result

        init = json.loads(raw)
        result["prepare_ms"] = (time.perf_counter() - t0) * 1000
        sid = init.get('session_id', '')[:12]

        # Wait for pipeline init (TTS load + prefill)
        await asyncio.sleep(20)

        # Send chunks with shorter timeout for reliability testing
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
        await ws.close()

        if result["n_speak"] > 0:
            result["rtf_mean"] = np.mean(speak_walls) / 1000.0
            result["wall_mean_ms"] = np.mean(speak_walls)
            result["success"] = True
        else:
            result["fail_stage"] = "no_speak_chunks"
            result["error"] = "0 SPEAK_GENERATION chunks"
        return result

    except Exception as e:
        result["fail_stage"] = result.get("fail_stage") or "exception"
        result["error"] = str(e)[:200]
        print(f"  [exception] {result['error']}")
        try:
            await ws.close()
        except Exception:
            pass
        return result

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=50, help="Max sessions to run")
    parser.add_argument("--max-failures", type=int, default=10, help="Stop after N failures")
    parser.add_argument("--port", type=int, default=22500, help="Server port")
    args = parser.parse_args()

    global WS_URL
    WS_URL = f"ws://127.0.0.1:{args.port}/backend"

    audio = extract_audio(VIDEO)
    chunk_size = int(CHUNK_DURATION_S * TARGET_SR)
    total_chunks = len(audio) // chunk_size

    print(f"Reliability test: up to {args.sessions} sessions, {total_chunks} chunks each")
    print(f"Stop condition: {args.max_failures} failures or {args.sessions} sessions total")
    print(f"Inter-session sleep: {INTER_SESSION_SLEEP_S}s")
    print(f"{'='*60}")

    results = []
    t_start = time.monotonic()

    for n in range(1, args.sessions + 1):
        t_session_start = time.monotonic()
        print(f"\n--- Session {n}/{args.sessions} ---")
        r = await run_one_session(n, audio, chunk_size)
        elapsed = time.monotonic() - t_session_start
        results.append(r)

        status = "PASS" if r["success"] else f"FAIL({r['fail_stage']})"
        print(f"  {status} | speak={r['n_speak']} listen={r['n_listen']} tail={r['n_tail']} | "
              f"rtf={r['rtf_mean']:.4f} wall={r['wall_mean_ms']:.0f}ms | "
              f"session_time={elapsed:.0f}s")

        n_fail = sum(1 for r in results if not r["success"])
        n_pass = sum(1 for r in results if r["success"])

        # Stop if we hit max failures
        if n_fail >= args.max_failures:
            print(f"\nSTOPPED: reached {n_fail} failures")
            break

        # Inter-session sleep
        if n < args.sessions:
            await asyncio.sleep(INTER_SESSION_SLEEP_S)

    total_time = time.monotonic() - t_start

    # Summary
    n_pass = sum(1 for r in results if r["success"])
    n_fail = sum(1 for r in results if not r["success"])
    n_total = len(results)

    print(f"\n{'='*60}")
    print(f"RELIABILITY TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Total sessions:  {n_total}")
    print(f"Pass:            {n_pass} ({100*n_pass/n_total:.1f}%)" if n_total > 0 else "Pass: 0")
    print(f"Fail:            {n_fail} ({100*n_fail/n_total:.1f}%)" if n_total > 0 else "Fail: 0")
    print(f"Total wall time: {total_time:.0f}s ({total_time/60:.1f}min)")

    # Breakdown by fail stage
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

if __name__ == "__main__":
    asyncio.run(main())
