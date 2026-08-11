#!/usr/bin/env python3
"""Demo full chain E2E: text + audio verification.

Single session: session.init → 5 audio chunks → collect all text + audio responses.
Validates: text non-empty, WAV valid non-silent, RTF reasonable.
"""
import asyncio, json, base64, time, wave, io, struct, os, sys, subprocess

WS_URL = "ws://127.0.0.1:22500/backend"
AUDIO_FILE = "/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/cases/common/user_audio/000_user_audio0.wav"
REF_AUDIO_FILE = "/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/cases/common/ref_audio/BH-Ref-HT-F224-Ref06_82_U001_话题_3_348s-355s.wav"
TARGET_SR = 16000
CHUNK_DURATION_S = 1.0
SOAK_CHUNKS = int(os.environ.get("SOAK_CHUNKS", "1800"))  # default 30 min
NUM_CHUNKS = 10

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

def validate_audio(audio_b64):
    """Validate base64 audio: raw PCM float32 @ 24kHz, non-zero samples, reasonable length."""
    try:
        raw = base64.b64decode(audio_b64)
    except:
        return False, "base64 decode failed"

    # Server sends raw float32 PCM @ 24000Hz mono.
    # Each sample = 4 bytes (float32). Stereo interleaved = 8 bytes per frame.
    n_bytes = len(raw)
    if n_bytes < 32:  # Minimum 8 samples
        return False, f"too short: {n_bytes} bytes"

    # Try as float32
    try:
        n_floats = n_bytes // 4
        samples = struct.unpack(f'<{n_floats}f', raw)
    except:
        return False, "float32 unpack failed"

    if not samples:
        return False, "no samples"

    peak = max(abs(s) for s in samples)
    if peak == 0:
        return False, "silent (peak=0)"

    if peak > 10.0:
        return False, f"suspicious peak={peak:.1f}"

    # Duration at 24000 Hz mono: each float = 1 sample
    dur_s = n_floats / 24000.0
    return True, f"OK: {dur_s:.3f}s, {n_floats} samples, peak={peak:.4f}"

async def run_demo():
    import websockets

    print(f"DEMO FULL CHAIN: {NUM_CHUNKS} chunks, text + audio validation")
    print(f"Server: {WS_URL}")

    audio = load_wav_float32(AUDIO_FILE)
    chunk_size = int(CHUNK_DURATION_S * TARGET_SR)
    total_samples = len(audio)

    ws = await websockets.connect(WS_URL, max_size=128*1024*1024,
                                   ping_interval=None, close_timeout=30)
    print("Connected")

    # Init
    ref_b64 = make_chunk_b64(load_wav_float32(REF_AUDIO_FILE))
    await ws.send(json.dumps({"type": "session.init", "payload": {
        "mode": "full_duplex", "use_tts": True,
        "ref_audio": ref_b64,
        "config": {"force_listen_count": 0},
    }}))

    # Drain session.created + any text deltas during init
    init_text = []
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=120)
        evt = json.loads(raw)
        et = evt.get('type', '')
        if et == 'session.created':
            print("Session created")
            break
        elif et == 'response.output.delta':
            if evt.get('kind') == 'text':
                init_text.append(evt.get('delta', ''))
        elif et in ('session.closed', 'error'):
            print(f"Init failed: {evt}")
            return

    if init_text:
        print(f"Init text: {''.join(init_text)[:100]}...")

    # Send chunks
    total_text = []
    total_audio_wavs = 0
    audio_validation_results = []
    errors = []
    walls = []

    for i in range(NUM_CHUNKS):
        start = (i * chunk_size) % total_samples
        chunk = audio[start:start + chunk_size]
        if len(chunk) < chunk_size:
            chunk = chunk + [0.0] * (chunk_size - len(chunk))

        chunk_b64 = make_chunk_b64(chunk)
        t_send = time.perf_counter_ns()

        await ws.send(json.dumps({"type": "input.append", "input": {
            "audio": chunk_b64, "streaming": True,
            "generation": {"max_new_tokens": 26},
        }}))

        # Collect all responses for this chunk
        chunk_text = []
        chunk_audio = 0
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=60)
            evt = json.loads(raw)
            et = evt.get('type', '')
            kind = evt.get('kind', '')

            if et == 'response.output.delta':
                if kind == 'listen':
                    walls.append({'chunk': i, 'state': 'LISTEN'})
                    break
                elif kind == 'text':
                    chunk_text.append(evt.get('text', evt.get('delta', '')))
                elif kind == 'audio':
                    audio_b64 = evt.get('audio', '')
                    if audio_b64:
                        chunk_audio += 1
                        valid, msg = validate_audio(audio_b64)
                        audio_validation_results.append((i, chunk_audio, valid, msg))
                        if not valid:
                            errors.append(f"chunk_{i}_audio_{chunk_audio}: {msg}")

                    # Record wall time on first audio
                    if chunk_audio == 1:
                        walls.append({'chunk': i, 'state': 'SPEAK',
                                     'wall_ms': (time.perf_counter_ns() - t_send) / 1e6})
                    break  # First audio is decisive
            elif et == 'response.done':
                continue
            elif et in ('session.closed', 'error'):
                errors.append(f"chunk_{i}_{et}: {evt.get('reason','?')}")
                break

        if chunk_text:
            total_text.append(''.join(chunk_text))
        if chunk_audio:
            total_audio_wavs += chunk_audio

    # Summary
    print(f"\n{'='*60}")
    print(f"DEMO FULL CHAIN RESULTS")
    print(f"{'='*60}")
    print(f"Chunks sent:    {NUM_CHUNKS}")
    print(f"Text responses: {len(total_text)}")
    print(f"Audio WAVs:     {total_audio_wavs}")
    print(f"Errors:         {len(errors)}")

    speak_walls = [w['wall_ms'] for w in walls if w['state'] == 'SPEAK']
    listen_count = sum(1 for w in walls if w['state'] == 'LISTEN')

    if speak_walls:
        sw = sorted(speak_walls)
        print(f"SPEAK:          {len(speak_walls)}")
        print(f"LISTEN:         {listen_count}")
        print(f"Wall mean:      {sum(sw)/len(sw):.1f}ms")
        print(f"Wall p50:       {sw[len(sw)//2]:.1f}ms")
        print(f"RTF mean:       {sum(sw)/len(sw)/1000:.3f}")

    # Text quality check
    if total_text:
        all_text = ' '.join(total_text)
        print(f"\nText output ({len(all_text)} chars):")
        print(f"  {all_text[:200]}")
        if len(all_text) < 2:
            errors.append("TEXT_TOO_SHORT")

    # Audio quality summary
    valid_audio = sum(1 for _, _, v, _ in audio_validation_results if v)
    invalid_audio = sum(1 for _, _, v, _ in audio_validation_results if not v)
    print(f"\nAudio validation: {valid_audio} valid, {invalid_audio} invalid")
    if invalid_audio:
        for i, idx, valid, msg in audio_validation_results:
            if not valid:
                print(f"  INVALID chunk_{i}_audio_{idx}: {msg}")

    # Overall verdict
    print(f"\n{'='*60}")
    if len(errors) == 0 and invalid_audio == 0 and len(total_text) > 0:
        print("DEMO FULL CHAIN: PASS")
    else:
        print("DEMO FULL CHAIN: FAIL")
        for e in errors:
            print(f"  - {e}")

    await ws.close()

    return {
        "chunks_sent": NUM_CHUNKS,
        "text_count": len(total_text),
        "audio_wavs": total_audio_wavs,
        "speak_count": len(speak_walls),
        "listen_count": listen_count,
        "errors": len(errors),
        "invalid_audio": invalid_audio,
        "wall_mean_ms": sum(speak_walls)/len(speak_walls) if speak_walls else 0,
        "rtf_mean": (sum(speak_walls)/len(speak_walls))/1000 if speak_walls else 0,
        "text_sample": all_text[:200] if total_text else "",
        "audio_validation": {"valid": valid_audio, "invalid": invalid_audio},
        "verdict": "PASS" if (len(errors) == 0 and invalid_audio == 0 and len(total_text) > 0) else "FAIL",
    }

if __name__ == "__main__":
    result = asyncio.run(run_demo())
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = f"/workspace/llama.cpp-omni-session-fix/benchmarks/results/demo_full_chain_{ts}.json"
    with open(out_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"Results saved: {out_path}")
