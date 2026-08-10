#!/usr/bin/env python3
"""Quick test: send one round of chunks to capture CANN profiling data."""
import asyncio, json, base64, struct, time, sys, os
import websockets

WS_URL = "ws://127.0.0.1:22500/backend"
VIDEO = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5/assets/omni_duplex1.mp4"
REF_AUDIO = "/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/cases/common/ref_audio/BH-Ref-HT-F224-Ref06_82_U001_话题_3_348s-355s.wav"

def extract_audio_16k_mono(path):
    import subprocess
    cmd = ["ffmpeg", "-i", path, "-vn", "-acodec", "pcm_s16le",
           "-ar", "16000", "-ac", "1", "-f", "s16le", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode()}")
    return list(struct.iter_unpack('<h', proc.stdout)), 16000

async def main():
    samples, sr = extract_audio_16k_mono(VIDEO)
    chunk_size = int(sr * 1.0)  # 1s chunks
    n_chunks = len(samples) // chunk_size

    with open(REF_AUDIO, 'rb') as f:
        ref_b64 = base64.b64encode(f.read()).decode()

    print(f"Connecting to {WS_URL}...")
    async with websockets.connect(WS_URL, max_size=200*1024*1024, ping_interval=None) as ws:
        # Session init
        init = {
            "type": "session.init",
            "session_id": "",
            "duplex_mode": "full_duplex",
            "media_type": 2,
            "ref_audio_b64": ref_b64,
            "force_listen_count": 3,
            "output_dir": "/tmp/quick_test"
        }
        await ws.send(json.dumps(init))
        resp = json.loads(await ws.recv())
        session_id = resp.get("session_id", "")
        print(f"Session: {session_id[:8]}...")

        # Send all chunks
        for i in range(min(n_chunks, 10)):  # Just 10 chunks
            chunk = samples[i*chunk_size:(i+1)*chunk_size]
            pcm = struct.pack(f'<{len(chunk)}h', *[s[0] for s in chunk])
            b64 = base64.b64encode(pcm).decode()

            msg = {
                "type": "input.append",
                "session_id": session_id,
                "audio_b64": b64,
                "chunk_id": i
            }

            t0 = time.time()
            await ws.send(json.dumps(msg))

            # Wait for response
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                event = json.loads(raw)
                kind = event.get("kind", event.get("delta", {}).get("kind", "?"))
                wall_ms = (time.time() - t0) * 1000
                print(f"  chunk {i:02d}: {kind:12s} wall={wall_ms:.1f}ms")
            except asyncio.TimeoutError:
                print(f"  chunk {i:02d}: TIMEOUT")
                break

    print("Done. Check server log for profiling data.")

asyncio.run(main())
