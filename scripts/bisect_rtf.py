#!/usr/bin/env python3
"""Minimal SPEAK RTF benchmark for git bisect — consistent WS client-side timing.

Uses the same protocol format at ALL commits. Measures send→response.done wall time.
Only classifies SPEAK_GENERATION chunks (audio emitted) for RTF.

Usage:
    source cann_env.sh
    OMNI_PER_CHUNK_DRAIN=0 OMNI_T2W_DEVICE=cann-flow-only \
        ./build/bin/llama-omni-server -m F16.gguf -t 4 --port 22500 &
    sleep 30  # wait for model load
    python3 bisect_rtf.py [--rounds 1]
"""
import asyncio, json, base64, struct, time, sys, os, wave, io, subprocess
import numpy as np

WS_URL = "ws://127.0.0.1:22500/backend"
VIDEO = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5/assets/omni_duplex1.mp4"
CHUNK_DURATION_S = 1.0
TARGET_SR = 16000

def extract_audio(path):
    """Extract 16kHz mono float32 audio from video or WAV."""
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

async def run_one_round():
    import websockets

    audio = extract_audio(VIDEO)
    chunk_size = int(CHUNK_DURATION_S * TARGET_SR)
    total_chunks = len(audio) // chunk_size
    print(f"Audio: {len(audio)/TARGET_SR:.1f}s, {total_chunks} chunks")

    ws = await websockets.connect(WS_URL, max_size=128*1024*1024, ping_interval=None)
    t0 = time.perf_counter()
    await ws.send(json.dumps({"type": "session.init", "payload": {
        "mode": "full_duplex", "use_tts": True,
        "config": {"force_listen_count": 0},
    }}))
    raw = await asyncio.wait_for(ws.recv(), timeout=60)
    init = json.loads(raw)
    prepare_ms = (time.perf_counter() - t0) * 1000
    sid = init.get('session_id', '')[:12]
    print(f"Session: {sid}, prepare={prepare_ms:.0f}ms")

    # Wait for pipeline init
    print("Waiting for pipeline init (TTS load + prefill)...")
    await asyncio.sleep(20)

    chunks = []
    for i in range(total_chunks):
        start = i * chunk_size
        chunk = audio[start:start+chunk_size]
        if len(chunk) < chunk_size:
            break

        b64 = make_chunk_b64(chunk)
        t_send = time.perf_counter_ns()
        await ws.send(json.dumps({"type": "input.append", "input": {
            "audio": b64, "streaming": True,
            "generation": {"max_new_tokens": 100},
        }}))

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
            state = "LISTEN"
        elif has_audio:
            state = "SPEAK_GENERATION"
        elif error:
            state = f"ERROR({error})"
        else:
            state = "SPEAK_TAIL"

        chunks.append({"idx": i, "state": state, "wall_ms": wall_ms})
        print(f"  chunk {i:02d}: {state:20s} wall={wall_ms:.0f}ms")

    await ws.send(json.dumps({"type": "session.close"}))
    await ws.close()

    # Compute metrics
    speak_chunks = [c for c in chunks if c['state'] == 'SPEAK_GENERATION']
    if speak_chunks:
        speak_walls = [c['wall_ms'] for c in speak_chunks]
        speak_rtf = np.mean(speak_walls) / 1000.0
        print(f"\n{'='*60}")
        print(f"RESULTS:")
        print(f"  Total chunks:     {len(chunks)}")
        print(f"  SPEAK_GENERATION: {len(speak_chunks)}")
        print(f"  LISTEN:           {sum(1 for c in chunks if c['state']=='LISTEN')}")
        print(f"  SPEAK_TAIL:       {sum(1 for c in chunks if c['state']=='SPEAK_TAIL')}")
        print(f"  SPEAK wall mean:  {np.mean(speak_walls):.1f}ms")
        print(f"  SPEAK wall p50:   {np.median(speak_walls):.1f}ms")
        print(f"  SPEAK RTF mean:   {speak_rtf:.4f}")
    else:
        print("NO SPEAK_GENERATION chunks found!")

    return chunks

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=1)
    args = parser.parse_args()

    all_speak_walls = []
    for r in range(args.rounds):
        if args.rounds > 1:
            print(f"\n--- Round {r+1}/{args.rounds} ---")
        chunks = await run_one_round()
        all_speak_walls.extend([c['wall_ms'] for c in chunks if c['state'] == 'SPEAK_GENERATION'])

    if all_speak_walls:
        rtf = np.mean(all_speak_walls) / 1000.0
        print(f"\nFINAL: {len(all_speak_walls)} SPEAK chunks, MEAN_RTF={rtf:.4f}")

if __name__ == "__main__":
    asyncio.run(main())
