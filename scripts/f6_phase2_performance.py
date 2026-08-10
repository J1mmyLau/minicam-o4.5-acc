#!/usr/bin/env python3 -u
"""Phase 2: LOCAL_BEST_EFFORT SPEAK→WAV RTF — frozen F16 candidate.

Uses WebSocket protocol (session.init → input.append → response.done).
Measures 3-state classification: LISTEN / SPEAK_GENERATION / SPEAK_TAIL.
Only SPEAK_GENERATION chunks count for RTF (arithmetic mean).

IMPORTANT: This is NOT the organizer's official harness.
Results labeled LOCAL_BEST_EFFORT_*, never OFFICIAL_*.
Official references: ALL_CHUNK_RTF=0.618, SPEAK→WAV_RTF=1.087 (comparison only).
"""
import asyncio, json, base64, time, wave, io, struct, os, sys, subprocess, socket, argparse, statistics

MODEL_PATH = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
SERVER_BIN = "/workspace/llama.cpp-omni-session-fix/build/bin/llama-omni-server"
DEFAULT_VIDEO = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5/assets/omni_duplex1.mp4"
REF_AUDIO = "/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/cases/common/ref_audio/BH-Ref-HT-F224-Ref06_82_U001_话题_3_348s-355s.wav"
TARGET_SR = 16000
CHUNK_DURATION_S = 1.0
OUTDIR = "/workspace/llama.cpp-omni-session-fix/benchmarks/results/formal"

log_file = None
def log(msg):
    line = f"[P2-RTF] {time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    if log_file:
        log_file.write(line + "\n")
        log_file.flush()

def find_port(start=22600):
    for p in range(start, start+30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    raise RuntimeError("no port")

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

def extract_audio(video_path):
    """Extract 16kHz mono WAV from MP4."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    subprocess.run(["ffmpeg", "-y", "-i", video_path, "-ac", "1", "-ar", str(TARGET_SR),
                    "-f", "wav", wav_path], capture_output=True, check=True)
    audio = load_wav_float32(wav_path)
    os.unlink(wav_path)
    return audio

def make_chunk_b64(chunk):
    i16 = [max(-32768, min(32767, int(s * 32767))) for s in chunk]
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(TARGET_SR)
        w.writeframes(struct.pack(f'<{len(i16)}h', *i16))
    return base64.b64encode(buf.getvalue()).decode()

def validate_audio_b64(audio_b64):
    """Validate base64 float32 PCM audio."""
    try:
        raw = base64.b64decode(audio_b64)
    except:
        return False, "decode_failed"
    n_floats = len(raw) // 4
    if n_floats < 8:
        return False, f"too_short:{n_floats}"
    try:
        samples = struct.unpack(f'<{n_floats}f', raw)
    except:
        return False, "unpack_failed"
    if not samples:
        return False, "empty"
    peak = max(abs(s) for s in samples)
    if peak == 0:
        return False, "silent"
    if any(s != s for s in samples):
        return False, "nan"
    dur_s = n_floats / 24000.0
    return True, f"{dur_s:.3f}s,peak={peak:.4f}"

def classify_chunk(events):
    """3-state: LISTEN / SPEAK_GENERATION / SPEAK_TAIL."""
    has_listen = any(e.get('kind') == 'listen' for e in events)
    has_audio = any(e.get('kind') == 'audio' for e in events)
    # SPEAK_GENERATION = audio AND NOT listen; SPEAK_TAIL = both; LISTEN = listen only
    if has_listen and not has_audio:
        return "LISTEN"
    elif has_audio and not has_listen:
        return "SPEAK_GENERATION"
    elif has_audio and has_listen:
        return "SPEAK_TAIL"
    else:
        return "OTHER"

async def run_formal_rtf(server_port, video_path, force_listen=0):
    import websockets

    ws_url = f"ws://127.0.0.1:{server_port}/backend"

    # Load audio
    log(f"Loading audio from {video_path}...")
    audio = extract_audio(video_path)
    chunk_size = int(CHUNK_DURATION_S * TARGET_SR)
    total_chunks = len(audio) // chunk_size
    log(f"Audio: {len(audio)/TARGET_SR:.1f}s, {total_chunks} chunks @ {CHUNK_DURATION_S}s")

    # Load ref audio
    ref_audio = load_wav_float32(REF_AUDIO) if os.path.exists(REF_AUDIO) else None
    if ref_audio:
        ref_b64 = make_chunk_b64(ref_audio[:int(10*TARGET_SR)])  # first 10s
    else:
        log("WARNING: ref_audio not found, using empty")
        ref_b64 = make_chunk_b64([0.0]*int(TARGET_SR))

    log(f"Connecting to {ws_url}...")
    ws = await websockets.connect(ws_url, max_size=128*1024*1024,
                                   ping_interval=None, close_timeout=30)
    log("Connected")

    # session.init
    init_payload = {
        "mode": "full_duplex",
        "use_tts": True,
        "ref_audio": ref_b64,
        "config": {"force_listen_count": force_listen},
    }
    await ws.send(json.dumps({"type": "session.init", "payload": init_payload}))

    # Wait for session.created
    init_start = time.perf_counter()
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=60)
        evt = json.loads(raw)
        if evt.get('type') == 'session.created':
            log(f"Session created in {(time.perf_counter()-init_start)*1000:.0f}ms")
            break
        elif evt.get('type') in ('session.closed', 'error'):
            log(f"Init failed: {evt}")
            return None

    # Send audio chunks
    chunk_results = []
    total_samples = len(audio)
    chunks_with_audio = 0
    chunks_with_text = 0

    for i in range(total_chunks):
        start = i * chunk_size
        chunk = audio[start:start + chunk_size]
        if len(chunk) < chunk_size:
            chunk = chunk + [0.0] * (chunk_size - len(chunk))

        chunk_b64 = make_chunk_b64(chunk)
        t_send = time.perf_counter_ns()

        await ws.send(json.dumps({"type": "input.append", "input": {
            "audio": chunk_b64,
            "streaming": True,
            "generation": {"max_new_tokens": 26},
        }}))

        # Collect events until response.done or LISTEN
        events = []
        t_first_audio = None
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=60)
            evt = json.loads(raw)
            et = evt.get('type', '')
            kind = evt.get('kind', '')

            if et == 'response.output.delta':
                events.append({'kind': kind, 'ts': time.perf_counter_ns()})
                if kind == 'listen':
                    break
                elif kind == 'audio':
                    if t_first_audio is None:
                        t_first_audio = time.perf_counter_ns()
                    audio_b64 = evt.get('audio', '')
                    valid, info = validate_audio_b64(audio_b64) if audio_b64 else (False, "empty")
                    if not valid:
                        log(f"  chunk {i}: INVALID audio: {info}")
                    chunks_with_audio += 1
            elif et == 'response.done':
                # Collect remaining text/audio from response.done
                events.append({'kind': 'done', 'ts': time.perf_counter_ns(),
                              'text': evt.get('text', ''),
                              'audio': evt.get('audio', '') is not None})
                if evt.get('text', '').strip():
                    chunks_with_text += 1
                break
            elif et in ('session.closed', 'error'):
                log(f"  chunk {i}: {et}: {evt.get('reason','?')}")
                break

        state = classify_chunk(events)
        wall_ms = (t_first_audio - t_send) / 1e6 if t_first_audio else None
        chunk_results.append({
            'chunk': i, 'state': state,
            'wall_ms': wall_ms,
            'first_audio_ms': wall_ms,
        })

        if i % 10 == 0 or i == total_chunks - 1:
            speak_gen = [c for c in chunk_results if c['state'] == 'SPEAK_GENERATION']
            listen = [c for c in chunk_results if c['state'] == 'LISTEN']
            walls = [c['wall_ms'] for c in speak_gen if c['wall_ms']]
            rtf_str = f"RTF p50={statistics.median(walls)/1000:.3f}" if walls else "RTF=N/A"
            log(f"  [{i+1}/{total_chunks}] SPEAK={len(speak_gen)} LISTEN={len(listen)} {rtf_str}")

    await ws.close()
    log("WebSocket closed")

    # Compute metrics
    speak_gen = [c for c in chunk_results if c['state'] == 'SPEAK_GENERATION']
    speak_tail = [c for c in chunk_results if c['state'] == 'SPEAK_TAIL']
    listen = [c for c in chunk_results if c['state'] == 'LISTEN']

    speak_walls = [c['wall_ms'] for c in speak_gen if c['wall_ms'] is not None]
    all_walls = [c['wall_ms'] for c in chunk_results if c['wall_ms'] is not None]

    return {
        'total_chunks': total_chunks,
        'speak_generation': len(speak_gen),
        'speak_tail': len(speak_tail),
        'listen': len(listen),
        'chunks_with_audio': chunks_with_audio,
        'chunks_with_text': chunks_with_text,
        'all_chunk_rtf': {
            'mean': statistics.mean(all_walls) / 1000 if all_walls else 0,
            'p50': statistics.median(all_walls) / 1000 if all_walls else 0,
            'p90': sorted(all_walls)[int(len(all_walls)*0.9)] / 1000 if all_walls else 0,
            'std': statistics.stdev(all_walls) / 1000 if len(all_walls) > 1 else 0,
            'n': len(all_walls),
        },
        'speak_to_wav_rtf': {
            'mean': statistics.mean(speak_walls) / 1000 if speak_walls else 0,
            'p50': statistics.median(speak_walls) / 1000 if speak_walls else 0,
            'p90': sorted(speak_walls)[int(len(speak_walls)*0.9)] / 1000 if speak_walls else 0,
            'std': statistics.stdev(speak_walls) / 1000 if len(speak_walls) > 1 else 0,
            'n': len(speak_walls),
        },
        'timer': {'start': 'first_audio', 'end': 'chunk_send'},
    }

async def main():
    global log_file
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", default=DEFAULT_VIDEO)
    parser.add_argument("--force-listen", type=int, default=0)
    parser.add_argument("--pipeline", type=int, default=1, choices=[0,1])
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    os.makedirs(OUTDIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = f"{OUTDIR}/phase2_formal_rtf_{ts}.log"
    log_file = open(log_path, "w")

    log("="*60)
    log("PHASE 2: LOCAL_BEST_EFFORT SPEAK→WAV RTF")
    log("="*60)
    log(f"Binary:    {SERVER_BIN}")
    log(f"Model:     {MODEL_PATH}")
    log(f"Video:     {args.video}")
    log(f"Pipeline:  {'ON' if args.pipeline else 'OFF'}")
    log(f"Log:       {log_path}")

    # Start server
    port = args.port if args.port else find_port(22600)
    env = os.environ.copy()
    env.update({
        "OMNI_T2W_DEVICE": "cann-flow-only",
        "OMNI_T2W_PIPELINE_OVERLAP": str(args.pipeline),
        "OMNI_T2W_DRAIN_TIMEOUT_MS": "5000",
        "OMNI_T2W_QUEUE_DIAG": "1",
    })

    server_log = open(f"/tmp/p2_server_{ts}.log", "wb")
    cmd = [SERVER_BIN, "-m", MODEL_PATH, "--host", "127.0.0.1", "--port", str(port),
           "-ngl", "999", "--device", "CANN0", "-c", "4096", "-b", "512", "-ub", "512",
           "--split-mode", "layer", "-fa", "off", "-n", "128", "-t", "4"]
    log(f"Server: {' '.join(cmd)}")

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=server_log, env=env)

    import urllib.request, urllib.error
    for i in range(180):
        if proc.poll() is not None:
            log(f"Server died rc={proc.returncode}")
            server_log.close()
            return 1
        try:
            r = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5)
            if json.loads(r.read()).get('status') == 'ok':
                break
        except:
            pass
        time.sleep(2)
    else:
        log("Server timeout")
        proc.kill(); server_log.close()
        return 1

    log(f"Server ready on port {port}")

    # Run RTF measurement
    result = await run_formal_rtf(port, args.video, args.force_listen)

    # Stop server
    log("Stopping server...")
    proc.send_signal(subprocess.signal.SIGTERM)
    try:
        proc.communicate(timeout=30)
    except:
        proc.kill(); proc.communicate(timeout=5)
    server_log.close()

    if not result:
        log("RTF measurement FAILED")
        return 1

    # Report
    all_rtf = result['all_chunk_rtf']
    speak_rtf = result['speak_to_wav_rtf']

    print("")
    print("="*60)
    print("PHASE 2: LOCAL_BEST_EFFORT PERFORMANCE RESULTS")
    print("="*60)
    print(f"Chunks: {result['total_chunks']} total")
    print(f"States: SPEAK_GEN={result['speak_generation']} SPEAK_TAIL={result['speak_tail']} LISTEN={result['listen']}")
    print(f"Timer:  {result['timer']['start']} → {result['timer']['end']}")
    print(f"")
    print(f"LOCAL_BEST_EFFORT_ALL_CHUNK_RTF:")
    print(f"  mean={all_rtf['mean']:.3f} p50={all_rtf['p50']:.3f} p90={all_rtf['p90']:.3f}")
    print(f"  std={all_rtf['std']:.3f} n={all_rtf['n']}")
    print(f"  official reference: 0.618 (comparison only, NOT_PROVEN)")
    print(f"")
    print(f"LOCAL_BEST_EFFORT_SPEAK_TO_WAV_RTF:")
    print(f"  mean={speak_rtf['mean']:.3f} p50={speak_rtf['p50']:.3f} p90={speak_rtf['p90']:.3f}")
    print(f"  std={speak_rtf['std']:.3f} n={speak_rtf['n']}")
    print(f"  official reference: 1.087 (comparison only, NOT_PROVEN)")
    print(f"")
    print(f"OFFICIAL_REFERENCE_COMPARABILITY = NOT_PROVEN")

    # Save
    output = {
        "phase": "2_performance",
        "label": "LOCAL_BEST_EFFORT",
        "binary_sha256": "768614abd68f93ff5b57a3eb99cb79ad14d2a839f0fcb7ebf0990c88f39d189e",
        "git_head": "051e993",
        "pipeline": args.pipeline,
        "config": {k: v for k, v in env.items() if k.startswith("OMNI_")},
        "video": args.video,
        "force_listen": args.force_listen,
        "result": result,
        "official_reference": {
            "all_chunk_rtf": 0.618,
            "speak_to_wav_rtf": 1.087,
            "comparability": "NOT_PROVEN",
        },
    }
    out_path = f"{OUTDIR}/phase2_local_best_effort_rtf_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results: {out_path}")

    log_file.close()
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
