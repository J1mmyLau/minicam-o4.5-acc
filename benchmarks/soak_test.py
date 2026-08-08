#!/usr/bin/env python3
"""Soak test: single-session multi-chunk endurance run.

No disconnects — sends N chunks in one WS session, monitors thread count and RTF drift.
"""
import asyncio, json, base64, time, wave, io, struct, os, sys, subprocess, hashlib

# Config
MODEL_PATH = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q8_0.gguf"
MODEL_NAME = "Q8_0"
SERVER_BIN = "/workspace/llama.cpp-omni-session-fix/build/bin/llama-omni-server"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 22500
WS_URL = f"ws://{SERVER_HOST}:{SERVER_PORT}/backend"
SERVER_LOG = "/tmp/gfh-die0/server-soak.log"
AUDIO_FILE = "/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/cases/common/user_audio/000_user_audio0.wav"
REF_AUDIO_FILE = "/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/cases/common/ref_audio/BH-Ref-HT-F224-Ref06_82_U001_话题_3_348s-355s.wav"
OUTDIR = "/workspace/llama.cpp-omni-session-fix/benchmarks/results"
TARGET_SR = 16000
CHUNK_DURATION_S = 1.0
SOAK_CHUNKS = int(os.environ.get("SOAK_CHUNKS", "1800"))  # default 30 min
THREAD_CHECK_INTERVAL = 100  # check threads every N chunks

os.makedirs(OUTDIR, exist_ok=True)

def load_wav_float32(path):
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
    if sr != TARGET_SR:
        ratio = TARGET_SR / sr
        audio = [audio[min(int(i/ratio), len(audio)-1)] for i in range(int(len(audio)*ratio))]
    return audio

def make_chunk_b64(chunk):
    i16 = [max(-32768, min(32767, int(s * 32767))) for s in chunk]
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(TARGET_SR)
        w.writeframes(struct.pack(f'<{len(i16)}h', *i16))
    return base64.b64encode(buf.getvalue()).decode()

def get_thread_count():
    try:
        r = subprocess.run(["ps", "-eLf"], capture_output=True, text=True, timeout=5)
        return r.stdout.count('\n')
    except:
        return -1

def get_server_pid():
    try:
        r = subprocess.run(["pgrep", "-f", "llama-omni-server"], capture_output=True, text=True)
        return int(r.stdout.strip().split('\n')[0]) if r.stdout.strip() else 0
    except:
        return 0

def stop_server():
    subprocess.run(["pkill", "-9", "-f", "llama-omni-server"], capture_output=True)
    time.sleep(3)

def start_server():
    env = os.environ.copy()
    env["OMNI_T2W_DEVICE"] = "cann-flow-only"
    env["OMNI_T2W_DRAIN_TIMEOUT_MS"] = "5000"
    env["ASCEND_RT_VISIBLE_DEVICES"] = "0"

    with open(SERVER_LOG, "w") as lf:
        proc = subprocess.Popen([
            SERVER_BIN, "-m", MODEL_PATH,
            "--host", SERVER_HOST, "--port", str(SERVER_PORT),
            "-ngl", "999", "--device", "CANN0",
            "--ctx-size", "4096", "--batch-size", "512", "--ubatch-size", "512",
            "-t", "4",
        ], env=env, stdout=lf, stderr=subprocess.STDOUT)

    if os.path.exists("/tmp/gfh-die0/server.log"):
        os.unlink("/tmp/gfh-die0/server.log")
    os.symlink(SERVER_LOG, "/tmp/gfh-die0/server.log")

    import urllib.request
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            r = urllib.request.urlopen(f"http://{SERVER_HOST}:{SERVER_PORT}/health", timeout=5)
            if r.status == 200:
                time.sleep(3)
                return proc.pid
        except:
            pass
        time.sleep(2)
    return None

async def run_soak():
    import websockets

    print(f"SOAK TEST: {SOAK_CHUNKS} chunks, single session")
    print(f"Thread check every {THREAD_CHECK_INTERVAL} chunks")

    # Start server
    stop_server()
    time.sleep(3)
    pid = start_server()
    if pid is None:
        print("FATAL: Server failed to start")
        return None
    print(f"Server PID={pid}")

    # Load audio
    audio = load_wav_float32(AUDIO_FILE)
    chunk_size = int(CHUNK_DURATION_S * TARGET_SR)
    total_audio_samples = len(audio)

    # Connect
    ws = await websockets.connect(WS_URL, max_size=128*1024*1024,
                                   ping_interval=None, close_timeout=30)

    # Init session
    ref_audio_b64 = make_chunk_b64(load_wav_float32(REF_AUDIO_FILE))
    await ws.send(json.dumps({"type": "session.init", "payload": {
        "mode": "full_duplex", "use_tts": True,
        "ref_audio": ref_audio_b64,
        "config": {"force_listen_count": 0},
    }}))

    # Drain session.created
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=120)
        evt = json.loads(raw)
        if evt.get('type') == 'session.created':
            break
        elif evt.get('type') in ('session.closed', 'error'):
            print(f"Init failed: {evt}")
            return None

    # Initial thread count
    threads_start = get_thread_count()
    t_start = time.monotonic()
    results = []
    errors = []
    listen_count = 0
    thread_history = [(0, threads_start)]

    # Send chunks
    for i in range(SOAK_CHUNKS):
        # Get audio chunk
        start = (i * chunk_size) % total_audio_samples
        chunk = audio[start:start + chunk_size]
        if len(chunk) < chunk_size:
            chunk = chunk + [0.0] * (chunk_size - len(chunk))

        chunk_b64 = make_chunk_b64(chunk)
        t_send = time.perf_counter_ns()

        await ws.send(json.dumps({"type": "input.append", "input": {
            "audio": chunk_b64, "streaming": True,
            "generation": {"max_new_tokens": 26},
        }}))

        # Wait for decisive event
        decisive = None
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
            except asyncio.TimeoutError:
                decisive = ('timeout', 0)
                break

            evt = json.loads(raw)
            et = evt.get('type', '')
            kind = evt.get('kind', '')

            if et == 'response.output.delta':
                if kind == 'listen':
                    decisive = ('LISTEN', time.perf_counter_ns())
                    break
                audio_b64 = evt.get('audio', '')
                if audio_b64:
                    decisive = ('AUDIO', time.perf_counter_ns(), len(base64.b64decode(audio_b64)))
                    break
            elif et == 'response.done':
                continue
            elif et in ('session.closed', 'error'):
                errors.append(f"chunk_{i}_{et}: {evt.get('reason','?')}")
                decisive = ('error', time.perf_counter_ns())
                break

        wall_ms = (decisive[1] - t_send) / 1e6
        results.append({"chunk_id": i, "state": decisive[0], "wall_ms": wall_ms,
                       "audio_bytes": decisive[2] if len(decisive) > 2 else 0})

        if decisive[0] == 'LISTEN':
            listen_count += 1

        # Periodic thread check
        if i > 0 and i % THREAD_CHECK_INTERVAL == 0:
            tc = get_thread_count()
            elapsed = time.monotonic() - t_start
            recent = [r["wall_ms"] for r in results[-50:] if r["state"] == "AUDIO"]
            avg_ms = sum(recent)/len(recent) if recent else 0
            thread_history.append((i, tc))
            print(f"  [{i}/{SOAK_CHUNKS}] elapsed={elapsed:.0f}s  threads={tc}  "
                  f"wall_avg_last50={avg_ms:.0f}ms  listen={listen_count}  errors={len(errors)}")
            if errors:
                print(f"  ERRORS: {errors[-3:]}")
                break  # Stop on errors

    # Final stats
    t_end = time.monotonic()
    threads_end = get_thread_count()
    total_wall = t_end - t_start

    speak_walls = [r["wall_ms"] for r in results if r["state"] == "AUDIO"]
    speak_sorted = sorted(speak_walls) if speak_walls else []
    n_speak = len(speak_walls)

    # Close WS cleanly
    try:
        await ws.close()
    except:
        pass

    # Report
    print(f"\n{'='*60}")
    print(f"SOAK TEST COMPLETE")
    print(f"{'='*60}")
    print(f"Chunks:         {SOAK_CHUNKS}")
    print(f"SPEAK:          {n_speak} ({100*n_speak/SOAK_CHUNKS:.1f}%)")
    print(f"LISTEN:         {listen_count} ({100*listen_count/SOAK_CHUNKS:.1f}%)")
    print(f"Errors:         {len(errors)}")
    print(f"Total wall:     {total_wall:.0f}s")
    print(f"Threads start:  {threads_start}")
    print(f"Threads end:    {threads_end}")
    print(f"Thread delta:   {threads_end - threads_start:+d}")

    if speak_sorted:
        mean_w = sum(speak_walls)/n_speak
        p50_w = speak_sorted[n_speak//2]
        p95_w = speak_sorted[int(n_speak*0.95)]
        # Split into thirds for drift analysis
        third = n_speak // 3
        first_mean = sum(speak_walls[:third])/third if third > 0 else 0
        last_mean = sum(speak_walls[-third:])/third if third > 0 else 0
        drift_pct = (last_mean - first_mean) / first_mean * 100 if first_mean > 0 else 0

        print(f"Wall mean:      {mean_w:.1f}ms")
        print(f"Wall p50:       {p50_w:.1f}ms")
        print(f"Wall p95:       {p95_w:.1f}ms")
        print(f"RTF mean:       {mean_w/1000:.3f}")
        print(f"RTF drift:      {drift_pct:+.1f}% (first third={first_mean:.0f}ms → last third={last_mean:.0f}ms)")

    # Thread history
    print(f"\nThread history:")
    for chunk_idx, tc in thread_history:
        print(f"  chunk {chunk_idx}: {tc}")

    return {
        "config": {"chunks": SOAK_CHUNKS, "chunk_dur_s": CHUNK_DURATION_S},
        "model": MODEL_NAME,
        "total_wall_s": total_wall,
        "speak_count": n_speak,
        "listen_count": listen_count,
        "errors": len(errors),
        "threads_start": threads_start,
        "threads_end": threads_end,
        "thread_delta": threads_end - threads_start,
        "thread_history": thread_history,
        "wall_mean_ms": sum(speak_walls)/n_speak if n_speak > 0 else 0,
        "wall_p50_ms": speak_sorted[n_speak//2] if n_speak > 0 else 0,
        "wall_p95_ms": speak_sorted[int(n_speak*0.95)] if n_speak > 0 else 0,
        "rtf_mean": (sum(speak_walls)/n_speak)/1000 if n_speak > 0 else 0,
        "rtf_drift_pct": drift_pct if n_speak > 0 else 0,
    }

if __name__ == "__main__":
    result = asyncio.run(run_soak())

    if result:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = f"{OUTDIR}/soak_{SOAK_CHUNKS}chunks_Q8_0_{ts}.json"
        with open(out_path, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nResults saved: {out_path}")
