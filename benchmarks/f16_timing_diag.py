#!/usr/bin/env python3
"""F16 Fine-Grained Timing Attribution Diagnostic — Step 1 of 5.

Captures per-chunk timing from client + server log.
Outputs: PREFILL_MEAN_MS, LLM_MEAN_MS, T2W_MEAN_MS, QUEUE_WAIT_MEAN_MS,
         TRANSPORT_MEAN_MS, UNATTRIBUTED_MEAN_MS.
Verifies: sum of known stages ≈ wall_ms within 5%.

IMPORTANT: TTS timing is NOT instrumented in this server build.
The "unattributed remainder" includes TTS + thread scheduling + WS transport.
"""
import asyncio, json, base64, time, wave, io, struct, os, sys

SERVER = "ws://127.0.0.1:22500/backend"
AUDIO_FILE = "/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/cases/common/user_audio/000_user_audio0.wav"
SERVER_LOG = "/tmp/gfh-die0/server.log"
OUTDIR = "/workspace/llama.cpp-omni-session-fix/benchmarks/results"
os.makedirs(OUTDIR, exist_ok=True)

NUM_CHUNKS = 10
CHUNK_DURATION_S = 1.0
TARGET_SR = 16000  # We send 16kHz int16. Server resamples internally.

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

def get_log_tail_since(start_byte):
    """Read server log from start_byte to end."""
    with open(SERVER_LOG, 'rb') as f:
        f.seek(start_byte)
        return f.read().decode('utf-8', errors='replace')

def parse_server_timing(log_text):
    """Extract per-chunk timing from server log text.

    Returns list of dicts, one per chunk, aligned by occurrence order.

    Each chunk produces:
      [prof] encoder index=N VPM=Xms APM=Yms wall=Zms
      [prof] llm prefill (fused) n_past=A->B tokens=T ms=M
      [prof] llm decode n_past=B->C tokens=T ms=M listen=0/1
      T2W线程: wav_N.wav | dur_s audio | inf_ms inference | RTF=r | t=Tms | queue_wait=Qms
    """
    import re

    encoders = []
    for m in re.finditer(
        r'\[prof\] encoder index=(\d+) VPM=([\d.]+)ms APM=([\d.]+)ms wall=([\d.]+)ms',
        log_text
    ):
        encoders.append({
            'index': int(m.group(1)),
            'vpm_ms': float(m.group(2)),
            'apm_ms': float(m.group(3)),
            'enc_wall_ms': float(m.group(4)),
        })

    prefills = []
    for m in re.finditer(
        r'\[prof\] llm prefill \(fused\) n_past=\d+->\d+ tokens=(\d+) ms=([\d.]+)',
        log_text
    ):
        prefills.append({
            'tokens': int(m.group(1)),
            'ms': float(m.group(2)),
        })

    decodes = []
    for m in re.finditer(
        r'\[prof\] llm decode n_past=\d+->\d+ tokens=(\d+) ms=([\d.]+) listen=(\d+)',
        log_text
    ):
        decodes.append({
            'tokens': int(m.group(1)),
            'ms': float(m.group(2)),
            'listen': int(m.group(3)),
        })

    t2ws = []
    for m in re.finditer(
        r'T2W线程: wav_(\d+)\.wav \| ([\d.]+)s audio \| ([\d.]+)ms inference \| RTF=([\d.]+) \| t=(\d+)ms \| queue_wait=([\d.]+)ms',
        log_text
    ):
        t2ws.append({
            'wav_idx': int(m.group(1)),
            'audio_dur_s': float(m.group(2)),
            'inference_ms': float(m.group(3)),
            'rtf': float(m.group(4)),
            't_ms': int(m.group(5)),
            'queue_wait_ms': float(m.group(6)),
        })

    # Also check for TTS disk messages
    tts_lines = []
    for m in re.finditer(r'TTS:.*', log_text):
        tts_lines.append(m.group(0))

    # Check for drain timeouts
    drain_timeouts = []
    for m in re.finditer(r'T2W drain: TIMEOUT after (\d+)ms', log_text):
        drain_timeouts.append(int(m.group(1)))

    # First Audio Response
    first_audio = None
    m = re.search(r'首响时间.*?(\d+)ms\s*\(decode_to_first_audio\)', log_text)
    if m:
        first_audio = int(m.group(1))

    return {
        'encoders': encoders,
        'prefills': prefills,
        'decodes': decodes,
        't2ws': t2ws,
        'tts_lines': tts_lines,
        'drain_timeouts': drain_timeouts,
        'first_audio_ms': first_audio,
    }

async def run_diagnostic():
    import websockets

    audio = load_wav_float32(AUDIO_FILE)
    chunk_size = int(CHUNK_DURATION_S * TARGET_SR)

    # Mark log position
    log_start_byte = os.path.getsize(SERVER_LOG)

    print(f"=== F16 FINE-GRAINED TIMING DIAGNOSTIC ===")
    print(f"Chunks: {NUM_CHUNKS} × {CHUNK_DURATION_S}s @ {TARGET_SR}Hz")
    print(f"Server: {SERVER}")
    print(f"Log start byte: {log_start_byte}")
    print()

    ws = await websockets.connect(SERVER, max_size=128*1024*1024,
                                   ping_interval=None, close_timeout=30)

    # STANDARD init
    await ws.send(json.dumps({"type": "session.init", "payload": {
        "mode": "full_duplex", "use_tts": True,
        "config": {"force_listen_count": 0},
    }}))

    # Wait for session.created (drain intermediate)
    t_wait_start = time.perf_counter()
    created = False
    drained_events = 0
    while not created:
        evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
        et = evt.get('type', '')
        if et == 'session.created':
            created = True
            sid = evt.get('session_id', '')[:12]
        elif et in ('session.closed', 'error'):
            print(f"FATAL: got {et} before session.created")
            return
        else:
            drained_events += 1

    t_init_done = time.perf_counter()
    init_wall_ms = (t_init_done - t_wait_start) * 1000
    print(f"Session created: {sid} (drained {drained_events} events, init+created wall={init_wall_ms:.0f}ms)")

    # Per-chunk data
    chunk_data = []

    # Send all chunks
    for i in range(NUM_CHUNKS):
        start = (i * chunk_size) % len(audio)
        c = audio[start:start + chunk_size]
        if len(c) < chunk_size:
            c = c + [0.0] * (chunk_size - len(c))

        chunk_b64 = make_chunk_b64(c)
        t_send_ns = time.perf_counter_ns()

        await ws.send(json.dumps({"type": "input.append", "input": {
            "audio": chunk_b64, "streaming": True,
            "generation": {"max_new_tokens": 200},
        }}))

        # Wait for decisive event
        decisive = None
        text_deltas = []
        metrics_seen = {}

        while decisive is None:
            raw = await asyncio.wait_for(ws.recv(), timeout=60)
            evt = json.loads(raw)
            et = evt.get('type', '')
            kind = evt.get('kind', '')

            if et == 'response.output.delta':
                if kind == 'listen':
                    t_recv_ns = time.perf_counter_ns()
                    decisive = {
                        "type": "LISTEN",
                        "wall_ns": t_recv_ns - t_send_ns,
                    }
                else:
                    audio_b64 = evt.get('audio', '')
                    if audio_b64:
                        t_recv_ns = time.perf_counter_ns()
                        raw_audio = base64.b64decode(audio_b64)
                        decisive = {
                            "type": "AUDIO",
                            "wall_ns": t_recv_ns - t_send_ns,
                            "audio_bytes": len(raw_audio),
                            "audio_dur_s": len(raw_audio) / (24000 * 4),
                            "n_tokens": evt.get('n_tokens', 0) or 0,
                            "end_of_turn": evt.get('end_of_turn', False),
                        }
                        # Capture metrics if present
                        for key in ('prefill_ms', 'generate_ms', 'cost_llm_ms',
                                     'cost_all_ms', 'wall_clock_ms'):
                            if key in evt:
                                metrics_seen[key] = evt[key]
                    else:
                        text_deltas.append(evt.get('text', '') or evt.get('delta', ''))
            elif et == 'response.done':
                continue  # NEVER decisive
            elif et == 'session.closed':
                decisive = {"type": "SESSION_CLOSED", "reason": evt.get('reason', '?')}
                break
            elif et == 'error':
                decisive = {"type": "ERROR", "reason": evt.get('reason', '?')}
                break

        chunk_data.append({
            'chunk_id': i,
            'send_ns': t_send_ns,
            'decisive': decisive,
            'metrics_seen': metrics_seen,
            'text_delta_count': len(text_deltas),
        })

        if decisive and decisive['type'] in ('SESSION_CLOSED', 'ERROR'):
            print(f"  Chunk {i}: {decisive['type']} — stopping")
            break

    # Close
    t_close_start = time.perf_counter()
    await ws.close()
    close_wall_ms = (time.perf_counter() - t_close_start) * 1000

    # Wait briefly for log flush
    await asyncio.sleep(1)

    # Read server log tail
    log_end_byte = os.path.getsize(SERVER_LOG)
    log_text = get_log_tail_since(log_start_byte)
    server_timing = parse_server_timing(log_text)

    # --- REPORT ---
    print()
    print("=" * 70)
    print("CLIENT-SIDE PER-CHUNK TIMING")
    print("=" * 70)
    print(f"{'Chk':>3s} {'Type':>8s} {'Wall_ms':>8s} {'Audio_B':>7s} {'Dur_s':>6s} {'n_tok':>5s} {'EOT':>3s}")
    print("-" * 70)

    speak_walls = []
    listen_walls = []
    for cd in chunk_data:
        d = cd['decisive']
        t = d['type'] if d else 'MISSING'
        w_ms = d.get('wall_ns', 0) / 1e6 if d else 0
        ab = d.get('audio_bytes', 0) if d else 0
        ad = d.get('audio_dur_s', 0) if d else 0
        nt = d.get('n_tokens', 0) if d else 0
        eot = 'Y' if (d and d.get('end_of_turn')) else ''

        if t == 'AUDIO':
            speak_walls.append(w_ms)
        elif t == 'LISTEN':
            listen_walls.append(w_ms)

        print(f"{cd['chunk_id']:3d} {t:>8s} {w_ms:8.0f} {ab:7d} {ad:6.2f} {nt:5d} {eot:>3s}")

    print()
    print("=" * 70)
    print("SERVER-SIDE TIMING (from log)")
    print("=" * 70)

    st = server_timing
    print(f"Encoder events:  {len(st['encoders'])}")
    print(f"Prefill events:  {len(st['prefills'])}")
    print(f"Decode events:   {len(st['decodes'])}")
    print(f"T2W events:      {len(st['t2ws'])}")
    print(f"Drain timeouts:  {len(st['drain_timeouts'])}")
    print(f"First audio:     {st['first_audio_ms']}ms")

    # Alignment: the first prefill is for system prompt (n_past=82), skip it
    # Then each chunk produces: encoder + prefill + decode + T2W items
    # encoder is for APM (audio processor), runs per chunk
    # For 10 chunks, we expect up to 10 prefill+decode pairs (after system prompt)

    print()
    print(f"{'Idx':>3s} {'Enc_ms':>7s} {'Prefill_ms':>10s} {'Decode_ms':>9s} "
          f"{'T2W_inf_ms':>10s} {'T2W_qwait':>9s} {'Decode_tok':>10s} {'Listen':>6s}")
    print("-" * 85)

    # Align: skip first prefill+decode if it's the system prompt (n_past starts at 82)
    p_offset = 0
    if st['prefills'] and st['prefills'][0]['tokens'] == 7:
        # First prefill with 7 tokens could be chunk 0 (system prompt prefill also has 7 tokens)
        # For full_duplex, the system prompt prefill happens during init
        # The first real chunk prefill also has 7 tokens (whisper encoder output)
        # We need to match by count — if we have more prefills than chunks, skip the first
        if len(st['prefills']) > NUM_CHUNKS:
            p_offset = 1  # Skip system prompt prefill
            print(f"  (skipping system prompt prefill at index 0)")

    for i in range(min(NUM_CHUNKS, len(st['prefills']) - p_offset)):
        p = st['prefills'][i + p_offset] if (i + p_offset) < len(st['prefills']) else {'tokens': 0, 'ms': 0}
        d = st['decodes'][i + p_offset] if (i + p_offset) < len(st['decodes']) else {'tokens': 0, 'ms': 0, 'listen': -1}
        e = st['encoders'][i] if i < len(st['encoders']) else {'enc_wall_ms': 0}
        t2 = st['t2ws'][i] if i < len(st['t2ws']) else {'inference_ms': 0, 'queue_wait_ms': 0}

        print(f"{i:3d} {e.get('enc_wall_ms', 0):7.1f} {p['ms']:10.1f} {d['ms']:9.1f} "
              f"{t2['inference_ms']:10.1f} {t2['queue_wait_ms']:9.1f} {d['tokens']:10d} {d['listen']:6d}")

    # --- AGGREGATE BREAKDOWN ---
    print()
    print("=" * 70)
    print("AGGREGATE TIMING ATTRIBUTION (per chunk, means)")
    print("=" * 70)

    # Use only SPEAK chunks for the breakdown (LISTEN chunks have no T2W)
    n_speak = len([cd for cd in chunk_data if cd['decisive']['type'] == 'AUDIO'])

    # Aligned server timing
    n_align = min(NUM_CHUNKS, len(st['prefills']) - p_offset, len(st['decodes']) - p_offset)

    import statistics
    prefill_vals = [st['prefills'][i + p_offset]['ms'] for i in range(n_align)]
    decode_vals = [st['decodes'][i + p_offset]['ms'] for i in range(n_align)]
    enc_vals = [st['encoders'][i].get('enc_wall_ms', 0) for i in range(min(n_align, len(st['encoders'])))]
    t2w_inf_vals = [st['t2ws'][i]['inference_ms'] for i in range(min(n_align, len(st['t2ws']))) if st['t2ws'][i]['inference_ms'] > 0]
    t2w_qwait_vals = [st['t2ws'][i]['queue_wait_ms'] for i in range(min(n_align, len(st['t2ws'])))]

    # Client wall times for SPEAK chunks
    speak_wall_vals = speak_walls if speak_walls else [cd['decisive'].get('wall_ns', 0)/1e6 for cd in chunk_data if cd['decisive'] and cd['decisive']['type'] == 'AUDIO']

    # Means
    pref_m = statistics.mean(prefill_vals) if prefill_vals else 0
    dec_m = statistics.mean(decode_vals) if decode_vals else 0
    enc_m = statistics.mean(enc_vals) if enc_vals else 0
    t2w_inf_m = statistics.mean(t2w_inf_vals) if t2w_inf_vals else 0
    t2w_qwait_m = statistics.mean(t2w_qwait_vals) if t2w_qwait_vals else 0
    wall_m = statistics.mean(speak_wall_vals) if speak_wall_vals else 0

    # Attribution
    known = enc_m + pref_m + dec_m + t2w_inf_m
    unattributed = wall_m - known

    print(f"  ENCODER_MEAN_MS     = {enc_m:8.1f}   (VPM+APM audio encoding)")
    print(f"  PREFILL_MEAN_MS     = {pref_m:8.1f}   (whisper encoder, fused with LLM prefill)")
    print(f"  DECODE_MEAN_MS      = {dec_m:8.1f}   (LLM decode, speech+text tokens)")
    print(f"  T2W_INF_MEAN_MS     = {t2w_inf_m:8.1f}   (flow_matching + vocoder, CPU)")
    print(f"  ---")
    print(f"  KNOWN_TOTAL_MS      = {known:8.1f}")
    print(f"  WALL_MEAN_MS        = {wall_m:8.1f}   (client-measured end-to-end)")
    print(f"  ---")
    print(f"  UNATTRIBUTED_MS     = {unattributed:8.1f}   (TTS + thread sched + WS transport + overlap)")
    print(f"  ---")

    # Verify: the T2W inference runs in background. Decode + T2W may overlap.
    # For non-overlapping: wall ≈ prefill + decode + T2W_inf (serially)
    # For overlapping: wall ≈ max(decode, T2W_inf) + prefill + overhead
    # Check which model fits

    serial_sum = enc_m + pref_m + dec_m + t2w_inf_m
    overlap_sum = enc_m + pref_m + max(dec_m, t2w_inf_m)

    err_serial = abs(wall_m - serial_sum) / wall_m * 100 if wall_m > 0 else 0
    err_overlap = abs(wall_m - overlap_sum) / wall_m * 100 if wall_m > 0 else 0

    print(f"  Serial model (enc+pref+dec+t2w): sum={serial_sum:.0f}ms, err={err_serial:.1f}%")
    print(f"  Overlap model (enc+pref+max(dec,t2w)): sum={overlap_sum:.0f}ms, err={err_overlap:.1f}%")
    print()

    if err_serial <= 5:
        print(f"  ✓ Serial model fits within 5% — T2W and decode are NOT pipelined")
    elif err_overlap <= 5:
        print(f"  ✓ Overlap model fits within 5% — T2W and decode ARE pipelined")
    else:
        print(f"  ⚠ Neither model fits within 5%.")
        print(f"    Serial error: {err_serial:.1f}%  Overlap error: {err_overlap:.1f}%")
        print(f"    Additional unaccounted time: {unattributed:.0f}ms")

    # TTS error check
    if st['tts_lines']:
        print(f"\n  ⚠ TTS errors in log: {len(st['tts_lines'])} lines")
        for line in st['tts_lines'][:5]:
            print(f"    {line[:120]}")

    # RTF computation
    if speak_wall_vals:
        speak_rtfs = [w / 1000 for w in speak_wall_vals]  # 1s audio → RTF = wall_s / 1.0
        print(f"\n  SPEAK_GENERATION_RTF:")
        print(f"    p50 = {statistics.median(speak_rtfs):.3f}")
        print(f"    p95 = {sorted(speak_rtfs)[int(len(speak_rtfs)*0.95)]:.3f}" if len(speak_rtfs) >= 20 else f"    (n={len(speak_rtfs)}, too few for p95)")
        print(f"    min = {min(speak_rtfs):.3f}")
        print(f"    max = {max(speak_rtfs):.3f}")

    # Summary
    print()
    print("=" * 70)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 70)
    print(f"  SPEAK chunks: {n_speak}/{len(chunk_data)}")
    print(f"  LISTEN chunks: {len(listen_walls)}/{len(chunk_data)}")
    print(f"  T2W CPU inference p50: {statistics.median(t2w_inf_vals) if t2w_inf_vals else 0:.0f}ms")
    print(f"  T2W queue_wait p50: {statistics.median(t2w_qwait_vals) if t2w_qwait_vals else 0:.0f}ms")
    print(f"  LLM decode p50: {statistics.median(decode_vals) if decode_vals else 0:.0f}ms")
    print(f"  Bottleneck: {'T2W (CPU)' if t2w_inf_m > dec_m else 'LLM decode'}")
    print(f"  RTF vs official: {statistics.median(speak_rtfs) if speak_wall_vals else 0:.3f} vs 1.087 "
          f"({statistics.median(speak_rtfs)/1.087 if speak_wall_vals else 0:.1f}× baseline)")
    print()
    print(f"  STATUS: DIAGNOSTIC — not official result")

    return chunk_data, server_timing

if __name__ == "__main__":
    asyncio.run(run_diagnostic())
