#!/usr/bin/env python3
"""30-minute single-session soak test — avoids session lifecycle issues."""
import asyncio, json, base64, time, wave, io, struct, os, sys
import websockets

AUDIO_FILE = "/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/cases/common/user_audio/000_user_audio0.wav"
SERVER_URL = "ws://127.0.0.1:22500/backend"
DURATION = 1800  # 30 minutes
CHUNK_S = 1.0
SR = 16000

def load_audio():
    with wave.open(AUDIO_FILE, 'rb') as w:
        frames = w.readframes(w.getnframes())
        sr, nch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
    if sw == 2:
        import struct
        samples = [s / 32768.0 for s in struct.unpack(f'<{len(frames)//2}h', frames)]
    else:
        import struct
        samples = list(struct.unpack(f'<{len(frames)//4}f', frames))
    if nch > 1:
        samples = [sum(samples[i:i+nch])/nch for i in range(0, len(samples), nch)]
    if sr != SR:
        ratio = SR / sr
        samples = [samples[min(int(i/ratio), len(samples)-1)] for i in range(int(len(samples)*ratio))]
    return samples

def make_chunk_b64(chunk):
    i16 = [max(-32768, min(32767, int(s * 32767))) for s in chunk]
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(struct.pack(f'<{len(i16)}h', *i16))
    return base64.b64encode(buf.getvalue()).decode()

def check_threads():
    try:
        with open('/tmp/gfh-die0/llama-omni.pid') as f:
            pid = int(f.read().strip())
    except:
        return -1
    try:
        with open(f'/proc/{pid}/status') as f:
            for line in f:
                if line.startswith('Threads:'):
                    return int(line.split()[1])
    except:
        return -1
    return -1

async def soak_test():
    audio = load_audio()
    chunk_size = int(SR * CHUNK_S)  # 16000 samples
    max_chunks = int(DURATION / CHUNK_S * 2)  # generous upper bound; time-based cutoff applies
    # Loop audio to cover max possible chunks
    loops_needed = (max_chunks * chunk_size + len(audio) - 1) // len(audio)
    audio_looped = (audio * (loops_needed + 1))[:max_chunks * chunk_size]

    errors = []
    chunk_results = []
    t0 = time.time()
    t_last = t0
    chunk_times = []

    print(f"Soak test: {DURATION}s target, {max_chunks} chunks, audio={len(audio_looped)} samples", flush=True)
    print(f"Threads at start: {check_threads()}", flush=True)

    try:
        async with websockets.connect(SERVER_URL, ping_interval=None) as ws:
            # Init session — correct format from benchmark
            await ws.send(json.dumps({"type": "session.init", "payload": {
                "mode": "full_duplex", "use_tts": True,
                "config": {"force_listen_count": 0},
            }}))
            drain_start = time.time()
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("type") == "session.created":
                    print(f"Session created in {(time.time()-drain_start)*1000:.0f}ms")
                    break
                if msg.get("type") in ("session.closed", "error"):
                    print(f"Session init failed: {msg}")
                    return
                if time.time() - drain_start > 30:
                    print("Session init timeout!")
                    return

            # Send audio chunks
            for i in range(max_chunks):
                chunk = audio_looped[i*chunk_size:(i+1)*chunk_size]
                b64 = make_chunk_b64(chunk)
                t_send = time.time()
                await ws.send(json.dumps({"type": "input.append", "input": {
                    "audio": b64, "streaming": True,
                    "generation": {"max_new_tokens": 200},
                }}))

                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
                    msg = json.loads(raw)
                    t_recv = time.time()
                    wall_ms = (t_recv - t_send) * 1000
                    et = msg.get("type", "")
                    kind = msg.get("kind", "")
                    has_audio = bool(msg.get("audio", "")) or kind == "speak"
                    has_text = bool(msg.get("text", ""))
                    chunk_results.append({
                        "i": i,
                        "wall_ms": wall_ms,
                        "type": et,
                        "kind": kind,
                        "has_text": has_text,
                        "has_audio": has_audio
                    })
                    chunk_times.append(wall_ms)
                    # Drain intermediate messages until we get a decisive event
                    while et in ("response.text.delta", "response.output.delta") and not has_audio and not has_text:
                        raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                        msg = json.loads(raw)
                        et = msg.get("type", "")
                        kind = msg.get("kind", "")
                        has_audio = bool(msg.get("audio", "")) or kind == "speak"
                        has_text = bool(msg.get("text", ""))
                except asyncio.TimeoutError:
                    errors.append(f"chunk {i}: timeout waiting for response")
                    chunk_results.append({"i": i, "wall_ms": -1, "error": "timeout"})

                # Progress every 30 chunks
                if (i + 1) % 30 == 0:
                    elapsed = time.time() - t0
                    recent = chunk_times[-30:]
                    avg = sum(recent) / len(recent) if recent else 0
                    t_now = time.time()
                    threads = check_threads()
                    print(f"  [{elapsed:5.0f}s] chunks {i-28:3d}-{i:3d} | wall_avg={avg:5.0f}ms | errors={len(errors)} | threads={threads}", flush=True)
                    t_last = t_now

                # Safety: stop if too slow
                if time.time() - t0 > DURATION + 120:
                    print(f"Stopping after {time.time()-t0:.0f}s")
                    break

            elapsed = time.time() - t0

    except Exception as e:
        errors.append(f"WebSocket error: {e}")
        print(f"WebSocket error: {e}")

    # Summary
    elapsed = time.time() - t0
    valid = [c for c in chunk_results if c["wall_ms"] > 0]
    wall_times = [c["wall_ms"] for c in valid]
    wall_times.sort()

    print(f"\n{'='*60}")
    print(f"SOAK TEST COMPLETE")
    print(f"Duration: {elapsed:.0f}s (target: {DURATION}s)")
    print(f"Chunks: {len(chunk_results)} total, {len(valid)} valid")
    print(f"Errors: {len(errors)}")
    if wall_times:
        n = len(wall_times)
        print(f"Wall p50: {wall_times[n//2]:.0f}ms")
        print(f"Wall mean: {sum(wall_times)/n:.0f}ms")
        print(f"Wall p95: {wall_times[int(n*0.95)]:.0f}ms")
    print(f"Threads at end: {check_threads()}")
    print(f"Server survived: {'YES' if errors == [] else 'PARTIAL' if len(valid) > 0 else 'NO'}")

    if errors:
        for e in errors[:5]:
            print(f"  Error: {e}")
        if len(errors) > 5:
            print(f"  ... and {len(errors)-5} more")

    return len(errors) == 0 and len(valid) > 0

if __name__ == "__main__":
    asyncio.run(soak_test())
