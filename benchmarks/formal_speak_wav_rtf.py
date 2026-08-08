#!/usr/bin/env python3
"""Formal SPEAK→WAV RTF benchmark — Competition Track A.

Single video request, 1-second full-duplex chunks, WARMUP_CHUNKS=0.
Three-state classification: LISTEN / SPEAK_GENERATION / SPEAK_TAIL.
Only SPEAK_GENERATION chunks counted for RTF (arithmetic mean).

Official baseline: OFFICIAL_F16_SPEAK_RTF_MEAN=1.087 (37 valid SPEAK_GENERATION chunks).

Usage:
    python3 benchmarks/formal_speak_wav_rtf.py [--video VIDEO.mp4] [--force-listen 0]
"""
import asyncio, json, base64, time, wave, io, struct, os, sys, subprocess, argparse, hashlib

# ── Config defaults ──
MODEL_PATH = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q8_0.gguf"
SERVER_BIN = "/workspace/llama.cpp-omni-session-fix/build/bin/llama-omni-server"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 22500
WS_URL = f"ws://{SERVER_HOST}:{SERVER_PORT}/backend"
SERVER_LOG = "/tmp/gfh-die0/server-formal.log"
SERVER_PID_FILE = "/tmp/gfh-die0/llama-omni.pid"
OUTDIR = "/workspace/llama.cpp-omni-session-fix/benchmarks/results/formal"

# Default video (extracted audio used; server is audio-only)
DEFAULT_VIDEO = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5/assets/omni_duplex1.mp4"
REF_AUDIO_FILE = "/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/cases/common/ref_audio/BH-Ref-HT-F224-Ref06_82_U001_话题_3_348s-355s.wav"

TARGET_SR = 16000
CHUNK_DURATION_S = 1.0
DRAIN_TIMEOUT = 120  # seconds for draining chunk responses

os.makedirs(OUTDIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════
# Audio loading
# ═══════════════════════════════════════════════════════════

def extract_audio_16k_mono(video_path):
    """Extract 16kHz mono WAV from MP4 video, return (samples, sr)."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-ac", "1", "-ar", str(TARGET_SR), "-f", "wav", wav_path
    ], capture_output=True, check=True)
    audio = load_wav_float32(wav_path)
    os.unlink(wav_path)
    return audio


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


# ═══════════════════════════════════════════════════════════
# Server management
# ═══════════════════════════════════════════════════════════

def stop_server():
    """Stop server via PID file with TERM→KILL escalation."""
    if not os.path.exists(SERVER_PID_FILE):
        # Fallback: try pkill for legacy cleanup
        subprocess.run(["pkill", "-f", "llama-omni-server"], capture_output=True)
        time.sleep(3)
        return

    pid = int(open(SERVER_PID_FILE).read().strip())
    # Verify PID is a llama-omni-server
    try:
        exe = os.readlink(f"/proc/{pid}/exe")
        if "llama-omni-server" not in exe:
            print(f"  PID {pid} exe={exe} — not our server, skipping")
            os.unlink(SERVER_PID_FILE)
            return
    except (OSError, FileNotFoundError):
        os.unlink(SERVER_PID_FILE)
        return

    # TERM first
    os.kill(pid, 15)  # SIGTERM
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
            time.sleep(0.5)
        except OSError:
            break

    # KILL if still alive
    try:
        os.kill(pid, 0)
        os.kill(pid, 9)  # SIGKILL
        time.sleep(2)
    except OSError:
        pass

    if os.path.exists(SERVER_PID_FILE):
        os.unlink(SERVER_PID_FILE)
    time.sleep(3)


def start_server(env_overrides=None):
    """Start server and write PID file."""
    env = os.environ.copy()
    env["OMNI_T2W_DEVICE"] = "cann-flow-only"
    env["OMNI_T2W_DRAIN_TIMEOUT_MS"] = "120000"  # F6 causal: extended for complete WAV drain
    env["OMNI_T2W_PROFILE"] = "2"  # per-call T2W timing
    env["ASCEND_RT_VISIBLE_DEVICES"] = "0"
    if env_overrides:
        env.update(env_overrides)

    os.makedirs(os.path.dirname(SERVER_LOG), exist_ok=True)
    os.makedirs(os.path.dirname(SERVER_PID_FILE), exist_ok=True)

    with open(SERVER_LOG, "w") as lf:
        proc = subprocess.Popen([
            SERVER_BIN, "-m", MODEL_PATH,
            "--host", SERVER_HOST, "--port", str(SERVER_PORT),
            "-ngl", "999", "--device", "CANN0",
            "--ctx-size", "4096", "--batch-size", "512", "--ubatch-size", "512",
            "-t", "4",
        ], env=env, stdout=lf, stderr=subprocess.STDOUT)

    # Write PID file
    with open(SERVER_PID_FILE, "w") as f:
        f.write(str(proc.pid))
    print(f"  Server PID={proc.pid} written to {SERVER_PID_FILE}")

    # Verify /proc/PID/exe
    time.sleep(1)
    try:
        exe = os.readlink(f"/proc/{proc.pid}/exe")
        assert "llama-omni-server" in exe, f"Wrong exe: {exe}"
    except (OSError, AssertionError) as e:
        print(f"  WARNING: PID verification failed: {e}")

    # Symlink for convenience
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


def parse_server_timing():
    """Parse [bench] and [bench_wav] lines from server log.

    Returns:
        benches: list of dicts with frame, chunk_seq, state, prefill_start_ns, ...
        wavs:    list of dicts with wav_complete_ns, req (chunk_seq), wav_idx, ...
        t2w_lines: count of T2W timing lines
    """
    benches = []
    wavs = []
    t2w_count = 0
    try:
        import re
        with open(SERVER_LOG, 'rb') as f:
            content = f.read().decode('utf-8', errors='replace')
        for line in content.split('\n'):
            if '[timing]' in line:
                t2w_count += 1
            elif '[bench_wav]' in line and 'wav_idx' in line:
                m = re.search(
                    r'wav_complete_ns=(\d+).*?gen=(\d+).*?wav_count=(\d+).*?wav_idx=(\d+).*?audio_dur=([\d.]+)\s+req=(\d+)\s+req_min=(\d+)\s+req_max=(\d+)',
                    line)
                if m:
                    wavs.append({
                        'wav_complete_ns': int(m.group(1)),
                        'gen': int(m.group(2)),
                        'wav_count': int(m.group(3)),
                        'wav_idx': int(m.group(4)),
                        'audio_dur': float(m.group(5)),
                        'req': int(m.group(6)),       # legacy round_idx
                        'req_min': int(m.group(7)),   # F6 causal: earliest chunk_seq
                        'req_max': int(m.group(8)),   # F6 causal: latest chunk_seq
                    })
            elif '[bench]' in line and 'prefill_start' in line:
                m = re.search(
                    r'frame=(\d+)\s+chunk_seq=(\d+)\s+gen=(\d+)\s+state=(\S+)\s+'
                    r'prefill_start=(\d+)\s+prefill_end=(\d+)\s+'
                    r'llm_start=(\d+)\s+llm_end=(\d+)\s+'
                    r'text_len=(\d+).*?t2w_wav_count=(\d+)',
                    line)
                if m:
                    benches.append({
                        'frame': int(m.group(1)),
                        'chunk_seq': int(m.group(2)),
                        'gen': int(m.group(3)),
                        'state': m.group(4),
                        'prefill_start_ns': int(m.group(5)),
                        'prefill_end_ns': int(m.group(6)),
                        'llm_start_ns': int(m.group(7)),
                        'llm_end_ns': int(m.group(8)),
                        'text_len': int(m.group(9)),
                        't2w_wav_count': int(m.group(10)),
                    })
    except Exception as e:
        print(f"  [warn] Failed to parse server log: {e}", file=sys.stderr)
    return benches, wavs, t2w_count


def compute_server_rtf(benches, wavs):
    """Compute server-side per-chunk RTF using CAUSAL range-based attribution.

    Each [bench_wav] line carries req_min=C_min and req_max=C_max, where
    [C_min, C_max] is the range of chunk_seq values whose speech tokens are
    included in the T2W task that produced this WAV. The range is set at
    T2W task creation time from accumulated LLMOut chunk_seq values.

    For each SPEAK_GENERATION chunk with chunk_seq=C:
      - Find all WAVs where req_min <= C <= req_max (causally covers this chunk)
      - The LAST such WAV (highest wav_complete_ns) is the final_for_chunk
      - server_RTF = (final_wav_complete_ns - prefill_start_ns) / 1e9

    This is TRUE CAUSAL attribution: WAVs are assigned to chunks based on
    which chunk's speech tokens are in the task, not when the WAV completed
    or which chunk was being processed at creation time.
    """
    if not benches or not wavs:
        return []

    # Index benches by chunk_seq for O(1) lookup
    bench_by_cs = {b['chunk_seq']: b for b in benches}

    # Sort wavs by completion time
    wavs_sorted = sorted(wavs, key=lambda w: w['wav_complete_ns'])

    results = []
    for b in benches:
        if b['state'] != 'SPEAK_GENERATION':
            continue
        cs = b['chunk_seq']

        # Find all WAVs whose range covers this chunk_seq
        covering_wavs = [w for w in wavs_sorted
                         if w.get('req_min', w['req']) <= cs <= w.get('req_max', w['req'])]

        if covering_wavs:
            last_wav = covering_wavs[-1]  # final_for_chunk
            latency_ns = last_wav['wav_complete_ns'] - b['prefill_start_ns']
            rtf = latency_ns / 1e9

            results.append({
                'chunk_seq': cs,
                'frame': b['frame'],
                'prefill_start_ns': b['prefill_start_ns'],
                'last_wav_complete_ns': last_wav['wav_complete_ns'],
                'last_wav_idx': last_wav['wav_idx'],
                'latency_ns': latency_ns,
                'latency_ms': latency_ns / 1e6,
                'rtf': rtf,
                'num_wavs': len(covering_wavs),
                'text_len': b['text_len'],
            })

    # Verify causal completeness
    speak_chunks = [b for b in benches if b['state'] == 'SPEAK_GENERATION']
    mapped_chunks = set(r['chunk_seq'] for r in results)
    unmapped = [b['chunk_seq'] for b in speak_chunks if b['chunk_seq'] not in mapped_chunks]
    if unmapped:
        print(f"  [warn] CAUSAL MAPPING INCOMPLETE: {len(unmapped)} chunks with no WAVs: {unmapped}", file=sys.stderr)
    else:
        print(f"  [ok] CAUSAL MAPPING: {len(results)}/{len(speak_chunks)} SPEAK_GENERATION chunks mapped (causal range-based)")

    return results


# ═══════════════════════════════════════════════════════════
# Per-chunk state classification
# ═══════════════════════════════════════════════════════════

def classify_chunk_state(events):
    """
    Classify chunk state from ALL WS events collected until response.done.

    LISTEN:            kind=='listen' received
    SPEAK_GENERATION:  LLM actively produced text for this chunk
                       (text was generated → LLM is active → generation)
    SPEAK_TAIL:        audio produced but NO new text generated
                       (TTS residual after LLM finished turn)
    """
    has_listen = any(e.get('kind') == 'listen' for e in events)
    has_audio = any(e.get('kind') == 'audio' and e.get('audio', '') for e in events)
    has_text = any(e.get('kind') == 'text' and e.get('text', '').strip() for e in events)

    # LISTEN takes priority
    if has_listen:
        return 'LISTEN'

    # If text was generated → LLM is active → SPEAK_GENERATION
    # (regardless of whether audio arrived in this exact WS message batch)
    if has_text:
        return 'SPEAK_GENERATION'

    # Audio without text → TTS residual after LLM finished → SPEAK_TAIL
    if has_audio:
        return 'SPEAK_TAIL'

    # No audio, no text, no listen → assume tail/idle
    return 'SPEAK_TAIL'


# ═══════════════════════════════════════════════════════════
# Main benchmark
# ═══════════════════════════════════════════════════════════

async def run_formal_benchmark(video_path, force_listen_count=None):
    import websockets

    print(f"{'='*60}")
    print(f"FORMAL SPEAK→WAV RTF BENCHMARK — Competition Track A")
    print(f"{'='*60}")
    print(f"Video:    {video_path}")
    print(f"Model:    Q8_0 (cann-flow-only, -t 4)")
    print(f"Server:   {WS_URL}")

    # Load audio
    if video_path.endswith('.mp4'):
        print("Extracting audio from video...")
        audio = extract_audio_16k_mono(video_path)
    else:
        audio = load_wav_float32(video_path)

    chunk_size = int(CHUNK_DURATION_S * TARGET_SR)
    total_samples = len(audio)
    num_chunks = total_samples // chunk_size
    print(f"Audio:    {total_samples/TARGET_SR:.1f}s → {num_chunks} 1s chunks")

    # Start server
    stop_server()
    time.sleep(3)
    pid = start_server()
    if pid is None:
        print("FATAL: Server failed to start")
        return None
    print(f"Server:   PID={pid}")

    # Connect
    ws = await websockets.connect(WS_URL, max_size=128*1024*1024,
                                   ping_interval=None, close_timeout=30)
    print("WS:       connected")

    # ── Session init ──
    ref_b64 = make_chunk_b64(load_wav_float32(REF_AUDIO_FILE))
    init_config = {"use_tts": True, "mode": "full_duplex"}
    if force_listen_count is not None:
        init_config["force_listen_count"] = force_listen_count

    await ws.send(json.dumps({"type": "session.init", "payload": {
        "mode": "full_duplex", "use_tts": True,
        "ref_audio": ref_b64,
        "config": init_config,
    }}))

    # Drain session.created
    init_events = []
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=120)
        evt = json.loads(raw)
        et = evt.get('type', '')
        if et == 'session.created':
            print(f"Session:  created (force_listen_count={force_listen_count})")
            break
        elif et in ('session.closed', 'error'):
            print(f"Init FAILED: {evt}")
            return None
        else:
            init_events.append(evt)

    # ── Per-chunk loop ──
    all_chunks = []
    t_bench_start = time.perf_counter_ns()

    for chunk_id in range(num_chunks):
        # Get audio chunk
        start = chunk_id * chunk_size
        chunk = audio[start:start + chunk_size]
        if len(chunk) < chunk_size:
            chunk = chunk + [0.0] * (chunk_size - len(chunk))

        chunk_b64 = make_chunk_b64(chunk)
        t_send_ns = time.perf_counter_ns()
        video_ts = chunk_id * CHUNK_DURATION_S

        await ws.send(json.dumps({"type": "input.append", "input": {
            "audio": chunk_b64, "streaming": True,
            "generation": {"max_new_tokens": 26},
        }}))

        # Collect ALL events until response.done (or LISTEN, or timeout)
        # F6 formal: Do NOT break on first audio — collect everything so
        # classification sees both text and audio for this chunk.
        chunk_events = []
        t_first_audio_ns = None
        t_first_text_ns = None
        t_last_audio_ns = None
        t_done_ns = None
        audio_b64_collected = []
        text_collected = []
        done_received = False

        # Use a shorter drain timeout per chunk — formal video chunks
        # should complete quickly.  T2W drain is bounded by
        # OMNI_T2W_DRAIN_TIMEOUT_MS=5000.
        chunk_timeout = 30  # generous per-chunk timeout

        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=chunk_timeout)
            except asyncio.TimeoutError:
                print(f"  CHUNK {chunk_id}: TIMEOUT after {chunk_timeout}s — treating as done")
                break

            evt = json.loads(raw)
            et = evt.get('type', '')
            kind = evt.get('kind', '')

            chunk_events.append(evt)
            now_ns = time.perf_counter_ns()

            if et == 'response.output.delta':
                if kind == 'listen':
                    # LISTEN — done immediately (no more responses for this chunk)
                    break
                elif kind == 'text':
                    if t_first_text_ns is None:
                        t_first_text_ns = now_ns
                    t = evt.get('text', evt.get('delta', ''))
                    if t:
                        text_collected.append(t)
                elif kind == 'audio':
                    if t_first_audio_ns is None:
                        t_first_audio_ns = now_ns
                    t_last_audio_ns = now_ns
                    ab = evt.get('audio', '')
                    if ab:
                        audio_b64_collected.append(ab)
                    # F6 formal: do NOT break — continue collecting until
                    # response.done to capture all text+audio for this chunk
            elif et == 'response.done':
                t_done_ns = now_ns
                done_received = True
                break
            elif et in ('session.closed', 'error'):
                print(f"  CHUNK {chunk_id}: SESSION CLOSED/ERROR: {evt.get('reason', '?')}")
                break

        # ── Classify and record ──
        state = classify_chunk_state(chunk_events)

        # Timing: prefill_start ≈ t_send_ns (client approximation)
        #         wav_complete ≈ t_last_audio_ns (last audio delta)
        #         For text-only chunks, use t_done_ns as completion
        if t_last_audio_ns is not None:
            speak_to_wav_ns = t_last_audio_ns - t_send_ns
            speak_to_wav_ms = speak_to_wav_ns / 1e6
            rtf = speak_to_wav_ms / 1000.0  # chunk duration = 1s
        elif t_done_ns is not None:
            # Text-only chunk (no audio yet) — use done timestamp
            speak_to_wav_ns = t_done_ns - t_send_ns
            speak_to_wav_ms = speak_to_wav_ns / 1e6
            rtf = speak_to_wav_ms / 1000.0
        else:
            speak_to_wav_ns = None
            speak_to_wav_ms = None
            rtf = None

        # Audio validation
        total_audio_bytes = sum(len(base64.b64decode(ab)) for ab in audio_b64_collected)
        total_audio_samples = total_audio_bytes // 4  # float32
        audio_duration_ms = total_audio_samples / 24000.0 * 1000 if total_audio_bytes > 0 else 0

        record = {
            "chunk_id": chunk_id,
            "video_ts": video_ts,
            "state": state,
            "t_send_ns": t_send_ns,
            "t_first_text_ns": t_first_text_ns,
            "t_first_audio_ns": t_first_audio_ns,
            "t_last_audio_ns": t_last_audio_ns,
            "t_done_ns": t_done_ns,
            "speak_to_wav_ns": speak_to_wav_ns,
            "speak_to_wav_ms": speak_to_wav_ms,
            "rtf": rtf,
            "text": ''.join(text_collected),
            "text_len": sum(len(t) for t in text_collected),
            "audio_bytes": total_audio_bytes,
            "audio_duration_ms": audio_duration_ms,
            "num_audio_deltas": len(audio_b64_collected),
            "done_received": done_received,
        }

        all_chunks.append(record)

        # Progress
        state_display = state
        rtf_display = f"RTF={rtf:.3f}" if rtf is not None else "RTF=N/A"
        text_preview = (record['text'][:30] + '...') if record['text'] else ''
        print(f"  [{chunk_id}/{num_chunks}] {state_display:16s} {rtf_display:10s} "
              f"wall={speak_to_wav_ms:.0f}ms" if speak_to_wav_ms else f"  [{chunk_id}/{num_chunks}] {state_display:16s} {rtf_display:10s}",
              f" text={record['text_len']}ch" if record['text_len'] > 0 else "",
              f" {text_preview}" if text_preview else "")

    t_bench_end = time.perf_counter_ns()

    # ── Close WS ──
    try:
        await ws.close()
    except:
        pass

    # F6 causal: wait for T2W pipeline to drain remaining WAVs.
    # The server processes T2W tasks asynchronously; the WS close triggers
    # session cleanup which includes draining the T2W queue.
    # Use a long drain to ensure all WAVs complete for causal mapping.
    drain_timeout = 120
    print(f"\nWaiting for server T2W drain ({drain_timeout}s)...")
    elapsed = 0
    poll_interval = 5
    while elapsed < drain_timeout:
        time.sleep(poll_interval)
        elapsed += poll_interval
        # Check if new WAVs appeared in the log
        try:
            with open(SERVER_LOG, 'r') as f:
                wav_count = sum(1 for line in f if '[bench_wav]' in line)
        except:
            wav_count = 0
        print(f"  [{elapsed}s] WAVs in log: {wav_count}")
        if elapsed >= 30 and wav_count > 0:
            # After 30s, check if WAV count has stabilized (no new WAVs in last 10s)
            time.sleep(10)
            elapsed += 10
            try:
                with open(SERVER_LOG, 'r') as f:
                    new_wav_count = sum(1 for line in f if '[bench_wav]' in line)
            except:
                new_wav_count = 0
            if new_wav_count == wav_count:
                print(f"  WAV count stabilized at {wav_count}, drain complete")
                break

    # Stop server to flush all remaining output to log
    stop_server()

    # ── Parse server timing ──
    benches, wavs, t2w_count = parse_server_timing()
    server_rtfs = compute_server_rtf(benches, wavs)

    # ── Compute formal statistics ──
    speak_gen = [c for c in all_chunks if c['state'] == 'SPEAK_GENERATION']
    speak_tail = [c for c in all_chunks if c['state'] == 'SPEAK_TAIL']
    listen_chunks = [c for c in all_chunks if c['state'] == 'LISTEN']
    unknown_chunks = [c for c in all_chunks if c['state'] == 'UNKNOWN']

    n_speak_gen = len(speak_gen)
    speak_rtfs = [c['rtf'] for c in speak_gen if c['rtf'] is not None]
    speak_walls = [c['speak_to_wav_ms'] for c in speak_gen if c['speak_to_wav_ms'] is not None]

    formal_rtf_mean = sum(speak_rtfs) / len(speak_rtfs) if speak_rtfs else None
    formal_wall_mean = sum(speak_walls) / len(speak_walls) if speak_walls else None

    # ── Report ──
    print(f"\n{'='*60}")
    print(f"FORMAL BENCHMARK RESULTS")
    print(f"{'='*60}")
    print(f"Total chunks:              {num_chunks}")
    print(f"  LISTEN:                  {len(listen_chunks)}")
    print(f"  SPEAK_GENERATION:        {n_speak_gen}")
    print(f"  SPEAK_TAIL:              {len(speak_tail)}")
    print(f"  UNKNOWN:                 {len(unknown_chunks)}")
    print(f"Total wall clock:          {(t_bench_end - t_bench_start)/1e9:.1f}s")
    print()

    if speak_rtfs:
        sw = sorted(speak_walls)
        sr = sorted(speak_rtfs)
        print(f"SPEAK_GENERATION statistics (n={n_speak_gen}):")
        print(f"  wall mean:               {formal_wall_mean:.1f}ms")
        print(f"  wall p50:                {sw[len(sw)//2]:.1f}ms")
        print(f"  wall p90:                {sw[int(len(sw)*0.9)]:.1f}ms")
        print(f"  wall p95:                {sw[int(len(sw)*0.95)]:.1f}ms")
        print(f"  wall min:                {min(sw):.1f}ms")
        print(f"  wall max:                {max(sw):.1f}ms")
        print()
        print(f"  RTF mean:                {formal_rtf_mean:.4f}")
        print(f"  RTF p50:                 {sr[len(sr)//2]:.4f}")
        print(f"  RTF p90:                 {sr[int(len(sr)*0.9)]:.4f}")
        print(f"  RTF p95:                 {sr[int(len(sr)*0.95)]:.4f}")
        print(f"  RTF min:                 {min(sr):.4f}")
        print(f"  RTF max:                 {max(sr):.4f}")
        print()
        if formal_rtf_mean:
            speedup = 1.087 / formal_rtf_mean
            print(f"  SPEEDUP vs 1.087:        {speedup:.2f}×")
        print()

    # Per-chunk detail
    print(f"{'='*60}")
    print(f"Per-chunk detail:")
    print(f"{'chunk':>5s} {'state':16s} {'wall_ms':>8s} {'RTF':>8s} {'audio_ms':>8s} {'text_ch':>7s}")
    for c in all_chunks:
        wall_str = f"{c['speak_to_wav_ms']:.0f}" if c['speak_to_wav_ms'] is not None else "N/A"
        rtf_str = f"{c['rtf']:.4f}" if c['rtf'] is not None else "N/A"
        print(f"{c['chunk_id']:5d} {c['state']:16s} {wall_str:>8s} {rtf_str:>8s} "
              f"{c['audio_duration_ms']:>8.0f} {c['text_len']:>7d}")

    # Server timing lines count
    print(f"\nServer T2W calls (log): {t2w_count}")
    print(f"Server [bench_wav] lines: {len(wavs)}")
    print(f"Server [bench] frames:    {len(benches)}")

    # ── Server-side RTF ──
    srv_rtf_mean = None
    srv_wall_mean = None
    if server_rtfs:
        srv_rtf_vals = [r['rtf'] for r in server_rtfs]
        srv_wall_vals = [r['latency_ms'] for r in server_rtfs]
        srv_rtf_mean = sum(srv_rtf_vals) / len(srv_rtf_vals) if srv_rtf_vals else None
        srv_wall_mean = sum(srv_wall_vals) / len(srv_wall_vals) if srv_wall_vals else None
        sw_srv = sorted(srv_wall_vals)
        sr_srv = sorted(srv_rtf_vals)
        n_srv = len(server_rtfs)

        print(f"\n{'='*60}")
        print(f"SERVER-SIDE SPEAK→WAV RTF (prefill_start → wav_complete)")
        print(f"{'='*60}")
        print(f"Server-side SPEAK_GENERATION chunks: {n_srv}")
        print(f"  wall mean:               {srv_wall_mean:.1f}ms")
        print(f"  wall p50:                {sw_srv[len(sw_srv)//2]:.1f}ms")
        print(f"  wall p90:                {sw_srv[int(len(sw_srv)*0.9)]:.1f}ms")
        print(f"  wall p95:                {sw_srv[int(len(sw_srv)*0.95)]:.1f}ms")
        print(f"  wall min:                {min(sw_srv):.1f}ms")
        print(f"  wall max:                {max(sw_srv):.1f}ms")
        print()
        print(f"  RTF mean:                {srv_rtf_mean:.4f}")
        print(f"  RTF p50:                 {sr_srv[len(sr_srv)//2]:.4f}")
        print(f"  RTF p90:                 {sr_srv[int(len(sr_srv)*0.9)]:.4f}")
        print(f"  RTF p95:                 {sr_srv[int(len(sr_srv)*0.95)]:.4f}")
        print(f"  RTF min:                 {min(sr_srv):.4f}")
        print(f"  RTF max:                 {max(sr_srv):.4f}")
        if srv_rtf_mean:
            print(f"\n  SPEEDUP vs 1.087:        {1.087/srv_rtf_mean:.2f}×")

        # Per-chunk server-side detail (causal attribution)
        print(f"\n  Per-chunk server-side RTF (causal req→chunk_seq):")
        print(f"  {'chunk':>5s} {'frame':>5s} {'latency_ms':>10s} {'RTF':>8s} {'wavs':>5s} {'last_wav':>8s} {'text_ch':>7s}")
        for r in server_rtfs:
            print(f"  {r['chunk_seq']:5d} {r['frame']:5d} {r['latency_ms']:10.1f} {r['rtf']:8.4f} {r['num_wavs']:5d} {r['last_wav_idx']:8d} {r['text_len']:7d}")

    # ── Formal verdict ──
    print(f"\n{'='*60}")
    print(f"FORMAL VERDICT")
    print(f"{'='*60}")
    print(f"METHODOLOGY:          SINGLE_VIDEO, WARMUP_CHUNKS=0")
    print(f"CLASSIFICATION:       LISTEN / SPEAK_GENERATION / SPEAK_TAIL")
    print(f"METRIC:               ARITHMETIC_MEAN(SPEAK_GENERATION RTF)")
    print(f"OFFICIAL_REFERENCE:   1.087 (F16, 37 chunks)")
    print(f"Q8_FORMAL_CHUNKS:     {n_speak_gen}")

    if n_speak_gen == 37:
        print(f"WORKLOAD_ALIGNMENT:   PASS (exactly 37)")
    else:
        print(f"WORKLOAD_ALIGNMENT:   PARTIAL ({n_speak_gen} ≠ 37 official)")

    if formal_rtf_mean:
        print(f"Q8_FORMAL_RTF_MEAN:   {formal_rtf_mean:.4f}")
        print(f"Q8_FORMAL_WALL_MEAN:  {formal_wall_mean:.1f}ms")
        print(f"SPEEDUP_VS_1.087:     {1.087/formal_rtf_mean:.2f}×")

    # ── Save results ──
    result = {
        "benchmark_type": "FORMAL_SPEAK_WAV_RTF",
        "methodology": {
            "warmup_chunks": 0,
            "chunk_duration_s": CHUNK_DURATION_S,
            "aggregation": "ARITHMETIC_MEAN",
            "classification": ["LISTEN", "SPEAK_GENERATION", "SPEAK_TAIL"],
            "metric_chunks": "SPEAK_GENERATION",
        },
        "config": {
            "model": "Q8_0",
            "device": "cann-flow-only",
            "threads": 4,
            "drain_timeout_ms": 5000,
            "video_path": video_path,
            "force_listen_count": force_listen_count,
        },
        "official_baseline": {
            "rtf_mean": 1.087,
            "wall_mean_ms": 1087.3,
            "valid_chunks": 37,
        },
        "results": {
            "total_chunks": num_chunks,
            "listen_chunks": len(listen_chunks),
            "speak_generation_chunks": n_speak_gen,
            "speak_tail_chunks": len(speak_tail),
            "unknown_chunks": len(unknown_chunks),
            "workload_alignment": "PASS" if n_speak_gen == 37 else f"PARTIAL ({n_speak_gen} != 37)",
            "speak_generation_wall_mean_ms": formal_wall_mean,
            "speak_generation_wall_p50_ms": sw[len(sw)//2] if speak_walls else None,
            "speak_generation_wall_p90_ms": sw[int(len(sw)*0.9)] if speak_walls else None,
            "speak_generation_wall_p95_ms": sw[int(len(sw)*0.95)] if speak_walls else None,
            "speak_generation_wall_min_ms": min(sw) if speak_walls else None,
            "speak_generation_wall_max_ms": max(sw) if speak_walls else None,
            "rtf_mean": formal_rtf_mean,
            "rtf_p50": sr[len(sr)//2] if speak_rtfs else None,
            "rtf_p90": sr[int(len(sr)*0.9)] if speak_rtfs else None,
            "rtf_p95": sr[int(len(sr)*0.95)] if speak_rtfs else None,
            "rtf_min": min(sr) if speak_rtfs else None,
            "rtf_max": max(sr) if speak_rtfs else None,
            "speedup_vs_1_087": 1.087/formal_rtf_mean if formal_rtf_mean else None,
        },
        "per_chunk": all_chunks,
        "server_t2w_calls": t2w_count,
        "server_bench_wav_lines": len(wavs),
        "server_bench_frames": len(benches),
        "server_side_rtf": {
            "method": "CAUSAL (req→chunk_seq matching)",
            "description": "Each WAV assigned to the chunk that produced it via simplex_round_idx→req, not temporal window",
            "n": len(server_rtfs),
            "rtf_mean": srv_rtf_mean if server_rtfs else None,
            "wall_mean_ms": srv_wall_mean if server_rtfs else None,
            "per_chunk": server_rtfs,
        } if server_rtfs else None,
    }

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(OUTDIR, f"formal_speak_wav_rtf_Q8_0_{ts}.json")
    with open(out_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nResults saved: {out_path}")

    return result


# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Formal SPEAK→WAV RTF Benchmark")
    parser.add_argument("--video", type=str, default=DEFAULT_VIDEO,
                        help="MP4 video or WAV audio file")
    parser.add_argument("--force-listen", type=int, default=None,
                        help="force_listen_count (None=use server default)")
    args = parser.parse_args()

    result = asyncio.run(run_formal_benchmark(args.video, args.force_listen))
