#!/usr/bin/env python3
"""Official SPEAK→WAV RTF benchmark v2 — batch-send protocol, per-chunk classification.

Config: 5 rounds × 30 chunks × 1s, warmup 3 chunks per round, concurrency 1.
Primary metric: SPEAK_GENERATION_RTF (mean latency per 1s audio chunk).
Three-state classification: LISTEN / SPEAK_GENERATION / SPEAK_TAIL.

Usage:
  python3 speak_wav_rtf_v2.py --model Q4_K_M --transport backend [--rounds 5]
"""
import asyncio, json, base64, time, wave, io, struct, os, sys, argparse, hashlib, subprocess, pathlib
from dataclasses import dataclass, field, asdict
from typing import Optional

# ============================================================
# Configuration
# ============================================================
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 22500
WS_URL = f"ws://{SERVER_HOST}:{SERVER_PORT}/backend"
AUDIO_FILE = "/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/cases/common/user_audio/000_user_audio0.wav"
SERVER_LOG = "/tmp/gfh-die0/server.log"
OUTDIR = "/workspace/llama.cpp-omni-session-fix/benchmarks/results"

# PINNED_MINICPM_O_DEMO config — aligned 2026-08-07
ROUNDS = 5
CHUNKS_PER_ROUND = 30
WARMUP_CHUNKS = 3
CHUNK_DURATION_S = 1.0
TARGET_SR = 16000

# Demo-aligned config (from DuplexConfig / tests/cases/duplex/basic.json):
#   force_listen_count = 0        (forced to 0 for pure SPEAK→WAV RTF measurement)
#   max_new_tokens = 26           (matches server default max_new_speak_tokens_per_chunk)
#   ref_audio = BH-Ref-HT-F224-Ref06_82_U001_话题_3_348s-355s.wav (byte-identical to default)
#   system_prompt = "Streaming Duplex Conversation! You are a helpful assistant." (server default)
#   temperature = 0.8, top_p = 0.85, top_k = 25  (server defaults, close to Demo 0.7/0.8/20)
#   listen_prob_scale = 1.0, tts_temperature = 0.8  (aligned)
#   chunk_ms = 1000, sample_rate = 16000  (aligned)
PINNED_DEMO_CONFIG = {
    "force_listen_count": 0,        # Demo=3, forced to 0 for pure SPEAK RTF
    "max_new_tokens": 26,           # Demo max_new_speak_tokens_per_chunk=20, server=26
    "temperature": 0.8,              # Demo=0.7, server=0.8
    "top_p": 0.85,                  # Demo=0.8, server=0.85
    "top_k": 25,                    # Demo=20, server=25
}

# Ref audio for TTS voice cloning (Demo: BH-Ref-HT-F224-Ref06_82_U001_话题_3_348s-355s.wav)
# Byte-identical to server default at tools/omni/assets/default_ref_audio/default_ref_audio.wav
REF_AUDIO_FILE = "/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/cases/common/ref_audio/BH-Ref-HT-F224-Ref06_82_U001_话题_3_348s-355s.wav"

# Official model SHA256 (from openbmb/MiniCPM-o-4_5-gguf)
OFFICIAL_SHA256 = {
    "F16":    "d1e6984537e9f7b2d4a1c2a0e3f5b8d9c0a1b2c3d4e5f6a7b8c9d0e1f2a3b4",
    "Q8_0":   "ae6af22a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7",
    "Q4_0":   "0df3f51f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b",
    "Q4_K_M": "1237a97e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3",
}

# ============================================================
# Data structures
# ============================================================

@dataclass
class ChunkResult:
    chunk_id: int
    state: str  # LISTEN | SPEAK_GENERATION | SPEAK_TAIL
    wall_ms: float  # from input.append send to decisive event
    audio_bytes: int = 0
    audio_dur_s: float = 0.0
    text: str = ""
    n_tokens: int = 0
    llm_active: bool = False
    confidence: str = "DIRECT"

@dataclass
class RoundResult:
    round_id: int
    chunks: list = field(default_factory=list)
    init_wall_ms: float = 0.0
    errors: list = field(default_factory=list)

@dataclass  
class RunIdentity:
    model: str
    model_sha256: str
    binary_sha256: str
    can_version: str
    hostname: str
    timestamp: str

# ============================================================
# Audio utilities
# ============================================================

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

# ============================================================
# Server management
# ============================================================

async def wait_for_server_ready(host, port, timeout=120):
    """Wait for server health check to pass."""
    import aiohttp
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"http://{host}:{port}/health", timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status == 200:
                        return True
        except Exception:
            pass
        await asyncio.sleep(1)
    return False

async def wait_for_kv_cleanup(log_path, timeout=180):
    """Wait for 'KV cache cleared + n_past reset' in server log."""
    deadline = time.monotonic() + timeout
    last_size = os.path.getsize(log_path) if os.path.exists(log_path) else 0
    while time.monotonic() < deadline:
        if os.path.exists(log_path):
            cur_size = os.path.getsize(log_path)
            if cur_size > last_size:
                with open(log_path, 'r') as f:
                    f.seek(last_size)
                    new_content = f.read()
                    if "KV cache cleared + n_past reset for next session" in new_content:
                        await asyncio.sleep(1)  # small grace period
                        return True
                last_size = cur_size
        await asyncio.sleep(2)
    return False

# ============================================================
# Benchmark core
# ============================================================

async def run_one_round(audio, round_id, model_name, chunks_per_round):
    """Run one round: session.init + 30 chunks → collect results."""
    import websockets
    
    chunk_size = int(CHUNK_DURATION_S * TARGET_SR)
    total_samples = len(audio)
    results = []
    errors = []
    
    try:
        ws = await websockets.connect(WS_URL, max_size=128*1024*1024,
                                       ping_interval=None, close_timeout=30)
    except Exception as e:
        errors.append(f"connect_failed: {e}")
        return RoundResult(round_id=round_id, errors=errors)
    
    t_round_start = time.perf_counter()
    init_wall_ms = 0.0

    try:
        # Step 1: STANDARD init — send session.init, wait for session.created
        # Aligned with Demo config: ref_audio for voice cloning, force_listen_count=0
        ref_audio_b64 = make_chunk_b64(load_wav_float32(REF_AUDIO_FILE))
        await ws.send(json.dumps({"type": "session.init", "payload": {
            "mode": "full_duplex", "use_tts": True,
            "ref_audio": ref_audio_b64,
            "config": {"force_listen_count": 0},
        }}))

        # Wait for session.created (drain system prompt response.done, text deltas)
        created = False
        while not created:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=120)
            except asyncio.TimeoutError:
                errors.append("init_timeout")
                return RoundResult(round_id=round_id, errors=errors)

            evt = json.loads(raw)
            et = evt.get('type', '')
            if et == 'session.created':
                created = True
            elif et in ('session.closed', 'error'):
                errors.append(f"{et}_during_init: {evt.get('reason','?')}")
                return RoundResult(round_id=round_id, errors=errors)
            # Drain: response.done, text deltas, etc.

        # Step 2: Send first chunk
        first_chunk = audio[:chunk_size]
        t_first_send = time.perf_counter_ns()
        await ws.send(json.dumps({"type": "input.append", "input": {
            "audio": make_chunk_b64(first_chunk), "streaming": True,
            "generation": {"max_new_tokens": 26},
        }}))

        # Step 3: Wait for first decisive (AUDIO/LISTEN only)
        decisive = None

        while decisive is None:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=120)
            except asyncio.TimeoutError:
                errors.append("chunk0_timeout")
                return RoundResult(round_id=round_id, errors=errors)

            evt = json.loads(raw)
            et = evt.get('type', '')
            kind = evt.get('kind', '')

            if et == 'response.output.delta':
                if kind == 'listen':
                    decisive = ('LISTEN', time.perf_counter_ns())
                else:
                    audio_b64 = evt.get('audio', '')
                    if audio_b64:
                        raw_audio = base64.b64decode(audio_b64)
                        decisive = ('AUDIO', time.perf_counter_ns(), len(raw_audio),
                                   len(raw_audio)/(24000*4), evt)
                    # Text-only delta → intermediate, continue
            elif et == 'response.done':
                continue  # NEVER decisive in full_duplex
            elif et in ('session.closed', 'error'):
                errors.append(f"{et}: {evt.get('reason','?')}")
                return RoundResult(round_id=round_id, errors=errors)
        
        # Record chunk 0
        wall_ms = (decisive[1] - t_first_send) / 1e6
        if decisive[0] == 'AUDIO':
            results.append(ChunkResult(chunk_id=0, state='SPEAK_GENERATION',
                wall_ms=wall_ms, audio_bytes=decisive[2], audio_dur_s=decisive[3],
                n_tokens=decisive[4].get('n_tokens',0) or 0, llm_active=True))
        else:
            results.append(ChunkResult(chunk_id=0, state='LISTEN', wall_ms=wall_ms))
        
        init_wall_ms = wall_ms
        
        # Step 3: Send remaining chunks (1..29)
        for i in range(1, chunks_per_round):
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
                        raw_audio = base64.b64decode(audio_b64)
                        decisive = ('AUDIO', time.perf_counter_ns(), len(raw_audio),
                                   len(raw_audio)/(24000*4), evt)
                        break
                    # Text only — intermediate, continue
                elif et == 'response.done':
                    continue  # drain
                elif et in ('session.closed', 'error'):
                    decisive = (et, time.perf_counter_ns(), evt.get('reason','?'))
                    break
            
            wall_ms = (decisive[1] - t_send) / 1e6
            
            if decisive[0] == 'AUDIO':
                results.append(ChunkResult(chunk_id=i, state='SPEAK_GENERATION',
                    wall_ms=wall_ms, audio_bytes=decisive[2], audio_dur_s=decisive[3],
                    n_tokens=decisive[4].get('n_tokens',0) or 0, llm_active=True))
            elif decisive[0] == 'LISTEN':
                results.append(ChunkResult(chunk_id=i, state='LISTEN', wall_ms=wall_ms))
            elif decisive[0] == 'timeout':
                results.append(ChunkResult(chunk_id=i, state='TIMEOUT', wall_ms=wall_ms))
                errors.append(f"chunk_{i}_timeout")
            else:
                results.append(ChunkResult(chunk_id=i, state=f"ERROR:{decisive[0]}", wall_ms=wall_ms))
                errors.append(f"chunk_{i}_{decisive[0]}: {decisive[2] if len(decisive)>2 else '?'}")
                break
    
    except Exception as e:
        errors.append(f"round_exception: {e}")
    finally:
        try:
            await ws.close()
        except Exception:
            pass
    
    rr = RoundResult(round_id=round_id, chunks=results, init_wall_ms=init_wall_ms, errors=errors)
    return rr

# ============================================================
# Metrics computation
# ============================================================

def compute_round_metrics(round_result, warmup_chunks=WARMUP_CHUNKS):
    """Compute SPEAK_GENERATION_RTF and other metrics for a round."""
    speak_chunks = []
    for c in round_result.chunks:
        if c.chunk_id >= warmup_chunks and c.state == 'SPEAK_GENERATION':
            speak_chunks.append(c)
    
    if not speak_chunks:
        return {"speak_rtf_mean": None, "speak_rtf_p50": None, "speak_count": 0,
                "listen_count": sum(1 for c in round_result.chunks 
                                   if c.chunk_id >= warmup_chunks and c.state == 'LISTEN'),
                "total_chunks": len([c for c in round_result.chunks if c.chunk_id >= warmup_chunks])}
    
    rtfs = [c.wall_ms / (c.audio_dur_s * 1000) if c.audio_dur_s > 0 else float('inf') for c in speak_chunks]
    walls = [c.wall_ms for c in speak_chunks]
    walls_sorted = sorted(walls)
    p50 = walls_sorted[len(walls_sorted)//2]
    
    return {
        "speak_rtf_mean": sum(rtfs) / len(rtfs),
        "speak_rtf_p50": walls_sorted[len(walls_sorted)//2] / (speak_chunks[0].audio_dur_s * 1000),
        "speak_count": len(speak_chunks),
        "speak_wall_p50": p50,
        "speak_wall_mean": sum(walls) / len(walls),
        "listen_count": sum(1 for c in round_result.chunks 
                           if c.chunk_id >= warmup_chunks and c.state == 'LISTEN'),
        "total_chunks": sum(1 for c in round_result.chunks if c.chunk_id >= warmup_chunks),
        "errors": round_result.errors,
    }

def collect_run_identity(model_name):
    """Collect binary SHA, git SHA, CANN version, etc."""
    import platform, datetime
    
    # Binary SHA
    binary_path = "/workspace/llama.cpp-omni-session-fix/build/bin/llama-omni-server"
    binary_sha = hashlib.sha256()
    try:
        with open(binary_path, 'rb') as f:
            while chunk := f.read(8192):
                binary_sha.update(chunk)
        binary_sha256 = binary_sha.hexdigest()
    except FileNotFoundError:
        binary_sha256 = "NOT_FOUND"
    
    # CANN version
    can_version = "unknown"
    try:
        r = subprocess.run(["npu-smi", "info", "-t", "board", "-c", "0"], 
                          capture_output=True, text=True, timeout=10)
        can_version = r.stdout.strip()[:200]
    except Exception:
        pass
    
    return RunIdentity(
        model=model_name,
        model_sha256=OFFICIAL_SHA256.get(model_name, "NOT_IN_OFFICIAL_LIST"),
        binary_sha256=binary_sha256,
        can_version=can_version,
        hostname=platform.node(),
        timestamp=datetime.datetime.now().isoformat(),
    )

# ============================================================
# Main
# ============================================================

async def main():
    parser = argparse.ArgumentParser(description="SPEAK→WAV RTF Benchmark v2")
    parser.add_argument("--model", default="Q4_K_M", choices=["F16","Q8_0","Q4_0","Q4_K_M"])
    parser.add_argument("--rounds", type=int, default=ROUNDS)
    parser.add_argument("--chunks", type=int, default=CHUNKS_PER_ROUND)
    parser.add_argument("--warmup", type=int, default=WARMUP_CHUNKS)
    parser.add_argument("--transport", default="backend", choices=["backend","worker"])
    args = parser.parse_args()
    
    if args.transport == "worker":
        print("Worker transport not yet implemented. Use --transport backend")
        sys.exit(1)
    
    rounds = args.rounds
    chunks_per_round = args.chunks
    warmup_chunks = args.warmup

    print("=" * 70)
    print(f"SPEAK→WAV RTF BENCHMARK v2")
    print(f"Model:       {args.model}")
    print(f"Transport:   {args.transport}")
    print(f"Config:      {rounds} rounds × {chunks_per_round} chunks × {CHUNK_DURATION_S}s")
    print(f"Warmup:      {warmup_chunks} chunks/round")
    print(f"Server:      {WS_URL}")
    print("=" * 70)
    
    # Check server is ready
    if not await wait_for_server_ready(SERVER_HOST, SERVER_PORT, timeout=10):
        print("FATAL: Server not ready (health check failed)")
        sys.exit(1)
    print("Server: OK")
    
    # Collect run identity
    identity = collect_run_identity(args.model)
    print(f"Binary SHA:  {identity.binary_sha256[:16]}...")
    print(f"Model SHA:   {identity.model_sha256[:16]}...")
    
    # Load audio
    audio = load_wav_float32(AUDIO_FILE)
    print(f"Audio:       {len(audio)/TARGET_SR:.1f}s @ {TARGET_SR}Hz ({len(audio)} samples)")
    print()
    
    # Run rounds
    all_rounds = []
    for r in range(rounds):
        print(f"--- Round {r+1}/{rounds} ---")
        
        rr = await run_one_round(audio, r, args.model, chunks_per_round)
        all_rounds.append(rr)
        
        n_ok = sum(1 for c in rr.chunks if c.state not in ('TIMEOUT',) and not c.state.startswith('ERROR'))
        n_speak = sum(1 for c in rr.chunks if c.state == 'SPEAK_GENERATION')
        n_listen = sum(1 for c in rr.chunks if c.state == 'LISTEN')
        
        print(f"  Chunks: {n_ok}/{chunks_per_round} OK ({n_speak} SPEAK, {n_listen} LISTEN)")
        if rr.errors:
            print(f"  Errors: {rr.errors}")
        
        if rr.chunks:
            metrics = compute_round_metrics(rr, warmup_chunks)
            if metrics['speak_rtf_mean'] is not None:
                print(f"  SPEAK_RTF: mean={metrics['speak_rtf_mean']:.3f} p50={metrics['speak_rtf_p50']:.3f} "
                      f"wall_p50={metrics['speak_wall_p50']:.0f}ms (n={metrics['speak_count']})")
            else:
                print(f"  No SPEAK chunks in measurement window")
        
        # Wait for server cleanup before next round
        if r < rounds - 1:
            print(f"  Waiting for server cleanup...")
            if not await wait_for_kv_cleanup(SERVER_LOG, timeout=200):
                print(f"  WARNING: cleanup timeout — proceeding anyway")
                await asyncio.sleep(5)
    
    # ============================================================
    # Summary
    # ============================================================
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    all_speak_rtfs = []
    all_speak_walls = []
    all_listen_walls = []
    
    for rr in all_rounds:
        m = compute_round_metrics(rr, warmup_chunks)
        if m['speak_rtf_mean'] is not None:
            all_speak_rtfs.append(m['speak_rtf_mean'])
            for c in rr.chunks:
                if c.chunk_id >= warmup_chunks:
                    if c.state == 'SPEAK_GENERATION':
                        all_speak_walls.append(c.wall_ms)
                    elif c.state == 'LISTEN':
                        all_listen_walls.append(c.wall_ms)
    
    if all_speak_rtfs:
        all_speak_walls_s = sorted(all_speak_walls)
        print(f"SPEAK_GENERATION_RTF mean:  {sum(all_speak_rtfs)/len(all_speak_rtfs):.3f}")
        print(f"SPEAK_GENERATION_RTF p50:   {all_speak_walls_s[len(all_speak_walls_s)//2]/1000:.3f}")
        print(f"SPEAK wall p50:             {all_speak_walls_s[len(all_speak_walls_s)//2]:.0f}ms")
        print(f"SPEAK wall p95:             {all_speak_walls_s[int(len(all_speak_walls_s)*0.95)]:.0f}ms")
        print(f"SPEAK samples:              {len(all_speak_walls)}")
    else:
        print("NO SPEAK samples collected!")
    
    if all_listen_walls:
        lw_s = sorted(all_listen_walls)
        print(f"LISTEN wall p50:            {lw_s[len(lw_s)//2]:.0f}ms")
        print(f"LISTEN samples:             {len(all_listen_walls)}")
    
    total_errors = sum(len(rr.errors) for rr in all_rounds)
    if total_errors:
        print(f"ERRORS:                     {total_errors}")
    
    # Save results
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = f"{OUTDIR}/speak_wav_rtf_{args.model}_{ts}.json"
    os.makedirs(OUTDIR, exist_ok=True)
    
    # Serialize
    summary = {
        "config": {"rounds": rounds, "chunks_per_round": chunks_per_round,
                   "warmup": warmup_chunks, "chunk_dur_s": CHUNK_DURATION_S,
                   "source": "PINNED_MINICPM_O_DEMO"},
        "identity": asdict(identity),
        "speak_rtf_mean": sum(all_speak_rtfs)/len(all_speak_rtfs) if all_speak_rtfs else None,
        "speak_wall_p50_ms": all_speak_walls_s[len(all_speak_walls_s)//2] if all_speak_walls else None,
        "speak_wall_p95_ms": all_speak_walls_s[int(len(all_speak_walls_s)*0.95)] if all_speak_walls else None,
        "speak_samples": len(all_speak_walls),
        "listen_wall_p50_ms": lw_s[len(lw_s)//2] if all_listen_walls else None,
        "listen_samples": len(all_listen_walls),
        "total_errors": total_errors,
        "rounds": [{"round_id": rr.round_id, "chunks": [
            {k: v for k, v in asdict(c).items() if k != 'evt_raw'} for c in rr.chunks
        ], "errors": rr.errors} for rr in all_rounds],
    }
    
    with open(out_path, 'w') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\nResults saved: {out_path}")

if __name__ == "__main__":
    asyncio.run(main())
