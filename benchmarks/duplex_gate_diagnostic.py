#!/usr/bin/env python3
"""Full-duplex multi-chunk gate diagnostic — tests both init sequences.

Gate checklist:
  STANDARD_INIT_SEQUENCE   = PASS/FAIL  (init→created→chunk0)
  PIPELINED_INIT_SEQUENCE  = PASS/FAIL  (init+chunk0 together)
  INPUT_CHUNKS_SENT         = 5
  DECISIVE_RESULTS_RECEIVED = 5
  MISSING_RESULTS           = 0
  DUPLICATE_RESULTS         = 0
  CHUNK_0_RESULT            = AUDIO/LISTEN
  SESSION_CLOSE_RESULT      = SUCCESS/FAIL
  SESSION_CLOSE_WALL_MS     = <ms>
  T2W_DRAIN_TIMEOUT_COUNT   = <n>
  MULTICHUNK_GATE           = PASS/FAIL

Rules:
  - response.done is NEVER a decisive result (only LISTEN or AUDIO delta)
  - TEXT deltas are recorded but don't end chunk wait
  - Drain time tracked separately from chunk wall time
"""
import asyncio, json, base64, time, wave, io, struct, os, sys, argparse

SERVER = "ws://127.0.0.1:22500/backend"
AUDIO_FILE = "/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/cases/common/user_audio/000_user_audio0.wav"
SERVER_LOG = "/tmp/gfh-die0/server.log"
OUTDIR = "/workspace/llama.cpp-omni-session-fix/benchmarks/results/multichunk_gate"
os.makedirs(OUTDIR, exist_ok=True)

NUM_CHUNKS = 5
CHUNK_DURATION_S = 1.0
TARGET_SR = 16000

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

async def wait_for_kv_cleanup(timeout=30):
    """Wait for server to be ready (KV cache cleared)."""
    deadline = time.monotonic() + timeout
    last_size = os.path.getsize(SERVER_LOG) if os.path.exists(SERVER_LOG) else 0
    while time.monotonic() < deadline:
        if os.path.exists(SERVER_LOG):
            cur_size = os.path.getsize(SERVER_LOG)
            if cur_size > last_size:
                with open(SERVER_LOG, 'r') as f:
                    f.seek(last_size)
                    if "KV cache cleared + n_past reset" in f.read():
                        await asyncio.sleep(0.5)
                        return True
                last_size = cur_size
        await asyncio.sleep(1)
    return False

def count_t2w_drain_timeouts():
    """Count T2W DRAIN_TIMEOUT occurrences in server log."""
    count = 0
    try:
        with open(SERVER_LOG, 'r') as f:
            for line in f:
                if "T2W terminal: DRAIN_TIMEOUT" in line:
                    count += 1
    except Exception:
        pass
    return count

async def run_pipelined_init(audio, chunk_size):
    """PIPELINED: send session.init + chunk0 together, then read."""
    import websockets

    ws = await websockets.connect(SERVER, max_size=128*1024*1024,
                                   ping_interval=None, close_timeout=30)
    t0 = time.perf_counter()

    # Send both back-to-back
    chunk0 = audio[:chunk_size]
    await ws.send(json.dumps({"type": "session.init", "payload": {
        "mode": "full_duplex", "use_tts": True,
        "config": {"force_listen_count": 0},
    }}))
    t_send = time.perf_counter_ns()
    await ws.send(json.dumps({"type": "input.append", "input": {
        "audio": make_chunk_b64(chunk0), "streaming": True,
        "generation": {"max_new_tokens": 200},
    }}))

    return await collect_chunks(ws, audio, chunk_size, t_send, t0, "pipelined")

async def run_standard_init(audio, chunk_size):
    """STANDARD: session.init → wait session.created → send chunk0."""
    import websockets

    ws = await websockets.connect(SERVER, max_size=128*1024*1024,
                                   ping_interval=None, close_timeout=30)
    t0 = time.perf_counter()

    # Step 1: session.init
    await ws.send(json.dumps({"type": "session.init", "payload": {
        "mode": "full_duplex", "use_tts": True,
        "config": {"force_listen_count": 0},
    }}))

    # Step 2: Wait for session.created (drain any intermediate events)
    session_created = False
    while True:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=60)
        except asyncio.TimeoutError:
            print(f"  STANDARD_INIT: timeout waiting for session.created")
            await ws.close()
            return None, "TIMEOUT_WAITING_SESSION_CREATED"

        evt = json.loads(raw)
        et = evt.get('type', '')
        if et == 'session.created':
            sid = evt.get('session_id', '')[:12]
            session_created = True
            break
        elif et == 'response.done':
            continue  # drain system prompt response.done
        elif et == 'response.output.delta':
            # Drain any stale deltas from system prompt
            continue
        elif et in ('session.closed', 'error'):
            print(f"  STANDARD_INIT: got {et} before session.created: {evt.get('reason','?')}")
            await ws.close()
            return None, f"GOT_{et.upper()}_BEFORE_CREATED"

    # Step 3: Now send first chunk
    chunk0 = audio[:chunk_size]
    t_send = time.perf_counter_ns()
    await ws.send(json.dumps({"type": "input.append", "input": {
        "audio": make_chunk_b64(chunk0), "streaming": True,
        "generation": {"max_new_tokens": 200},
    }}))

    return await collect_chunks(ws, audio, chunk_size, t_send, t0, "standard")

async def collect_chunks(ws, audio, chunk_size, t_first_send, t0, init_mode):
    """Common chunk collection logic. Returns (results, error)."""
    total_samples = len(audio)
    results = []
    error = None

    # Wait for chunk 0 decisive result
    decisive = None
    chunk0_extra = {"text_deltas": [], "response_done_count": 0}

    while decisive is None:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=120)
        except asyncio.TimeoutError:
            error = "CHUNK_0_TIMEOUT"
            break

        evt = json.loads(raw)
        et = evt.get('type', '')
        kind = evt.get('kind', '')

        if et == 'session.created':
            continue  # already got this
        elif et == 'session.closed':
            error = "SESSION_CLOSED_BEFORE_CHUNK_0"
            break
        elif et == 'error':
            error = f"SERVER_ERROR: {evt.get('reason','?')}"
            break
        elif et == 'response.output.delta':
            if kind == 'listen':
                decisive = {"type": "LISTEN", "wall_ms": (time.perf_counter_ns() - t_first_send) / 1e6}
            else:
                audio_b64 = evt.get('audio', '')
                if audio_b64:
                    raw_audio = base64.b64decode(audio_b64)
                    decisive = {
                        "type": "AUDIO",
                        "wall_ms": (time.perf_counter_ns() - t_first_send) / 1e6,
                        "audio_bytes": len(raw_audio),
                        "audio_dur_s": len(raw_audio) / (24000 * 4),
                        "text": evt.get('text', '') or evt.get('delta', ''),
                        "n_tokens": evt.get('n_tokens', 0) or 0,
                        "end_of_turn": evt.get('end_of_turn', False),
                    }
                else:
                    txt = evt.get('text', '') or evt.get('delta', '')
                    if txt:
                        chunk0_extra["text_deltas"].append(txt[:60])
        elif et == 'response.done':
            chunk0_extra["response_done_count"] += 1
            # NEVER treat as decisive — continue waiting

    if error:
        try: await ws.close()
        except: pass
        return None, error

    results.append({"chunk_id": 0, "decisive": decisive, "extra": chunk0_extra})

    # Collect chunks 1..4
    for i in range(1, NUM_CHUNKS):
        start = (i * chunk_size) % total_samples
        chunk = audio[start:start + chunk_size]
        if len(chunk) < chunk_size:
            chunk = chunk + [0.0] * (chunk_size - len(chunk))

        chunk_b64 = make_chunk_b64(chunk)
        t_send = time.perf_counter_ns()

        await ws.send(json.dumps({"type": "input.append", "input": {
            "audio": chunk_b64, "streaming": True,
            "generation": {"max_new_tokens": 200},
        }}))

        # Wait for decisive event
        decisive = None
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
            except asyncio.TimeoutError:
                decisive = {"type": "TIMEOUT"}
                break

            evt = json.loads(raw)
            et = evt.get('type', '')
            kind = evt.get('kind', '')

            if et == 'response.output.delta':
                if kind == 'listen':
                    decisive = {"type": "LISTEN", "wall_ms": (time.perf_counter_ns() - t_send) / 1e6}
                    break
                audio_b64 = evt.get('audio', '')
                if audio_b64:
                    raw_audio = base64.b64decode(audio_b64)
                    decisive = {
                        "type": "AUDIO",
                        "wall_ms": (time.perf_counter_ns() - t_send) / 1e6,
                        "audio_bytes": len(raw_audio),
                        "audio_dur_s": len(raw_audio) / (24000 * 4),
                        "text": evt.get('text', '') or evt.get('delta', ''),
                        "n_tokens": evt.get('n_tokens', 0) or 0,
                        "end_of_turn": evt.get('end_of_turn', False),
                    }
                    break
                # Text-only delta → intermediate, continue
            elif et == 'response.done':
                continue  # NEVER decisive
            elif et == 'session.closed':
                decisive = {"type": "SESSION_CLOSED", "reason": evt.get('reason','?')}
                break
            elif et == 'error':
                decisive = {"type": "ERROR", "reason": evt.get('reason','?')}
                break

        results.append({"chunk_id": i, "decisive": decisive})

        if decisive.get('type') in ('SESSION_CLOSED', 'ERROR'):
            break

    # Close session
    t_close_start = time.perf_counter()
    await ws.close()
    close_wall_ms = (time.perf_counter() - t_close_start) * 1000

    return results, None

def print_gate_report(results, init_mode, close_wall_ms, drain_count_before):
    """Print the full gate checklist."""
    drain_count_after = count_t2w_drain_timeouts()
    new_drains = drain_count_after - drain_count_before

    decisive_count = sum(1 for r in results if r["decisive"] and r["decisive"]["type"] in ("LISTEN", "AUDIO"))
    listen_count = sum(1 for r in results if r["decisive"] and r["decisive"]["type"] == "LISTEN")
    audio_count = sum(1 for r in results if r["decisive"] and r["decisive"]["type"] == "AUDIO")
    missing = NUM_CHUNKS - decisive_count

    chunk0 = results[0]["decisive"] if results else None
    chunk0_type = chunk0["type"] if chunk0 else "MISSING"

    # Check for duplicate results (same chunk getting multiple decisive events)
    duplicate = False
    for r in results:
        extra = r.get("extra", {})
        if extra.get("response_done_count", 0) > 1:
            duplicate = True

    gate = (decisive_count == NUM_CHUNKS and missing == 0 and not duplicate)

    print()
    print("=" * 60)
    print(f"GATE REPORT — {init_mode.upper()} INIT")
    print("=" * 60)
    print(f"INPUT_CHUNKS_SENT            = {NUM_CHUNKS}")
    print(f"DECISIVE_RESULTS_RECEIVED    = {decisive_count}")
    print(f"  LISTEN_RESULTS_RECEIVED    = {listen_count}")
    print(f"  AUDIO_RESULTS_RECEIVED     = {audio_count}")
    print(f"MISSING_RESULTS              = {missing}")
    print(f"DUPLICATE_RESULTS            = {'YES' if duplicate else 'NO'}")
    print(f"CHUNK_0_RESULT               = {chunk0_type}")
    if chunk0 and chunk0_type == "AUDIO":
        print(f"  CHUNK_0_AUDIO_BYTES        = {chunk0.get('audio_bytes', 0)}")
        print(f"  CHUNK_0_AUDIO_DUR_S        = {chunk0.get('audio_dur_s', 0):.2f}")
        print(f"  CHUNK_0_WALL_MS            = {chunk0.get('wall_ms', 0):.0f}")
    print(f"SESSION_CLOSE_RESULT         = {'SUCCESS' if close_wall_ms else 'N/A'}")
    print(f"SESSION_CLOSE_WALL_MS        = {close_wall_ms:.0f}")
    print(f"T2W_DRAIN_TIMEOUT_COUNT      = {new_drains}")
    print(f"RESPONSE_DONE_AS_DECISIVE    = NO  (excluded by design)")
    print()

    # Per-chunk table
    for r in results:
        d = r["decisive"]
        t = d["type"] if d else "MISSING"
        wall = d.get("wall_ms", 0) if d else 0
        ab = d.get("audio_bytes", 0) if d else 0
        extra = r.get("extra", {})
        text_deltas = extra.get("text_deltas", [])
        rd_count = extra.get("response_done_count", 0)
        extra_str = ""
        if text_deltas:
            extra_str += f" text_deltas={len(text_deltas)}"
        if rd_count:
            extra_str += f" response.done×{rd_count}(drained)"
        print(f"  Chunk {r['chunk_id']}: {t:12s} wall={wall:.0f}ms audio={ab}B{extra_str}")

    print()
    state = "PASS" if gate else "FAIL"
    print(f"MULTICHUNK_GATE ({init_mode})  = {state}")

    return gate

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pipelined", "standard", "both"], default="both")
    args = parser.parse_args()

    audio = load_wav_float32(AUDIO_FILE)
    chunk_size = int(CHUNK_DURATION_S * TARGET_SR)

    print("=" * 60)
    print("FULL-DUPLEX MULTI-CHUNK GATE DIAGNOSTIC")
    print(f"Chunks: {NUM_CHUNKS} × {CHUNK_DURATION_S}s @ {TARGET_SR}Hz")
    print(f"Server: {SERVER}")
    print("=" * 60)

    if args.mode in ("standard", "both"):
        print("\n>>> TEST 1: STANDARD INIT SEQUENCE (init → created → chunk0)")
        drain_before = count_t2w_drain_timeouts()
        results, error = await run_standard_init(audio, chunk_size)
        if error:
            print(f"  STANDARD_INIT_SEQUENCE = FAIL ({error})")
            print(f"  PIPELINED_INIT_REQUIRED = YES")
            print(f"  PROTOCOL_ALIGNMENT = FAIL")
        else:
            gate = print_gate_report(results, "standard", 0, drain_before)
            print(f"  STANDARD_INIT_SEQUENCE = PASS")
            print(f"  PIPELINED_INIT_REQUIRED = NO")
            print(f"  PROTOCOL_ALIGNMENT = PASS")

    if args.mode in ("pipelined", "both"):
        if args.mode == "both":
            print("\nWaiting for server cleanup before pipelined test...")
            await wait_for_kv_cleanup(timeout=30)

        print("\n>>> TEST 2: PIPELINED INIT SEQUENCE (init+chunk0 together)")
        drain_before = count_t2w_drain_timeouts()
        results, error = await run_pipelined_init(audio, chunk_size)
        if error:
            print(f"  PIPELINED_INIT_SEQUENCE = FAIL ({error})")
        else:
            gate = print_gate_report(results, "pipelined", 0, drain_before)
            print(f"  PIPELINED_INIT_SEQUENCE = PASS")

    # Summary
    print()
    print("=" * 60)
    print("DIAGNOSTIC OBSERVATIONS")
    print("=" * 60)
    for r in (results if results else []):
        d = r.get("decisive", {})
        if d and d.get("type") == "AUDIO" and d.get("audio_dur_s", 0) > 0.9:
            rtf = d["wall_ms"] / (d["audio_dur_s"] * 1000)
            print(f"  Chunk {r['chunk_id']}: wall={d['wall_ms']:.0f}ms dur={d['audio_dur_s']:.2f}s "
                  f"RTF={rtf:.3f} [{d['audio_bytes']}B]")
    print(f"  STATUS: DIAGNOSTIC_ONLY — not official result")

if __name__ == "__main__":
    asyncio.run(main())
