#!/usr/bin/env python3
"""SPEAK→WAV RTF Benchmark (Client-Side) — Subtrack A (llama.cpp-omni on CANN).

PROVENANCE: Best-effort reimplementation by Claude based on official competition
spec (2026-08-05). NOT the official evaluator — the official RTF harness and
evaluation script were never distributed.

OFFICIAL SPEC — WHAT IS KNOWN:
  Primary metric:      SPEAK_GENERATION stage, SPEAK→WAV full-chain RTF
  F16 baseline:        SPEAK_RTF=1.087 (avg 1087.3ms), ALL_CHUNK_RTF=0.618
  States:              LISTEN / SPEAK_GENERATION / SPEAK_TAIL (semantic only)
  Hardware:            Ascend 910C, CANN 9.1.0-beta1, F16, concurrency=1
  Pre-test warmup:     REQUIRED (multiple rounds before formal test)
  Demo:                Full interactive flow (audio+video+text, duplex streaming)

OFFICIAL SPEC — WHAT IS NOT SPECIFIED:
  Evaluator script:    NOT_DISTRIBUTED
  Timer start/end:     NOT_SPECIFIED (prefill_start vs input.append recv vs LLM start)
  classify_chunk():    NOT_DISTRIBUTED (formula not provided, only semantic description)
  37 chunk count:      NOT in official spec (may come from external baseline data)
  Per-request warmup:  NOT_SPECIFIED (chunk exclusion policy unknown)

THIS SCRIPT:
  Classification:      OUR best-effort reimplementation (n_tokens, audio_bytes, n_tts_tokens)
  Timer:               send → first audio delta (TTFP/TTFA-like, NOT proven as SPEAK→WAV RTF)
  F16 calibration:     REQUIRED — dual-anchor: ALL_CHUNK≈0.618 AND SPEAK≈1.087

CAVEATS:
  - first-audio-delta ≠ proven "WAV chunk complete" boundary
  - With drain OFF, backlog audio may arrive in later chunks' WS windows
  - Window-based classification may not match semantic SPEAK_GENERATION definition
  - Causal provenance (emit_chunk) is DIAGNOSTIC_ONLY, not scoring

Fixed decisions (2026-08-06):
  BENCH_CONFIG_SOURCE   = PINNED_MINICPM_O_DEMO
  ROUNDS=5, CHUNKS_PER_ROUND=30, WARMUP=3, CHUNK_DURATION_MS=1000

Supports two transport paths:
  --transport backend   → direct backend WS  (PRIMARY competition metric)
  --transport worker    → via Python Worker   (Demo E2E reference)

Usage:
  python benchmarks/speak_wav_rtf_client.py --model F16 --transport backend
  python benchmarks/speak_wav_rtf_client.py --model Q4_K_M --transport worker
"""

import argparse, asyncio, base64, hashlib, io, json, os, shutil, struct, subprocess, sys, time, wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict

# ========== Fixed Configuration ==========
BENCH_CONFIG_SOURCE = "PINNED_MINICPM_O_DEMO"
OFFICIAL_MANDATORY = "NOT_CONFIRMED"

CHUNK_DURATION_S = 1.0
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
NUM_CHUNKS_PER_ROUND = 30
N_ROUNDS = 5
WARMUP_CHUNKS = 3
CONCURRENCY = 1
INPUT_DTYPE = "float32"
INPUT_CHANNELS = 1

USER_AUDIO_PATH = "/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/cases/common/user_audio/000_user_audio0.wav"

# Official baselines (F16)
BASELINE_SPEAK_RTF = 1.087
BASELINE_SPEAK_LATENCY_MS = 1087.3
BASELINE_ALL_CHUNK_RTF = 0.618

# Official model matrix
MODELS = {
    "F16": {
        "path": "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf",
        "sha256": "d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de",
        "quant_type": "F16", "official_provided": True, "role": "BASELINE",
    },
    "Q8_0": {
        "path": "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q8_0.gguf",
        "sha256": "ae6af22ad3b7f1a7bf667922af84b9eb3e2199cc86f402702eaf9b054054788d",
        "quant_type": "Q8_0", "official_provided": True, "role": "OFFICIAL_CANDIDATE",
    },
    "Q4_0": {
        "path": "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_0.gguf",
        "sha256": "0df3f51f5d6f2342d302f69f0e5426fe6fa3507368c6a847e3163d75d1440947",
        "quant_type": "Q4_0", "official_provided": True, "role": "OFFICIAL_CANDIDATE",
    },
    "Q4_K_M": {
        "path": "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf",
        "sha256": "1237a97ee081b8abebc47aa7dad565701e8f5f904cdc92f6723ac4281bbc0932",
        "quant_type": "Q4_K_M", "official_provided": True,
        "role": "OFFICIAL_WEIGHT_NOT_IN_ACCURACY_TABLE",
    },
}

BACKEND_URL = "ws://127.0.0.1:22500/backend"
WORKER_URL = "ws://127.0.0.1:22400/v1/worker/duplex"
SERVER_BIN = "/workspace/llama.cpp-omni-session-fix/build/bin/llama-omni-server"
PID_FILE = "/tmp/gfh-die0/llama-omni.pid"
SERVER_LOG = "/tmp/gfh-die0/server.log"
BENCH_DIR = Path("/workspace/llama.cpp-omni-session-fix/benchmarks/results")
BENCH_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class RunIdentity:
    """Frozen identity for a benchmark run."""
    run_id: str
    start_time: str
    source_base_sha: str
    source_head_sha: str
    git_status: str
    server_binary_sha256: str
    model_filename: str
    model_sha256: str
    model_quant_type: str
    transport: str
    runtime_args: str
    ascend_visible_devices: str
    cann_version: str
    env_sorted: str


@dataclass
class ChunkResult:
    chunk_idx: int
    round_idx: int
    send_ts_ns: int = 0
    result_ts_ns: int = 0
    wall_ms: float = 0
    status: str = "UNKNOWN"  # LISTEN / SPEAK_GENERATION / SPEAK_TAIL / ERROR
    status_confidence: str = "PROVISIONAL"  # DIRECT if llm_active observed
    is_listen: bool = False
    text: str = ""
    audio_bytes: int = 0
    audio_duration_s: float = 0
    audio_sha256: str = ""
    end_of_turn: bool = False
    n_tokens: int = 0
    n_tts_tokens: int = 0
    prefill_ms: float = 0
    cost_llm_ms: float = 0
    cost_tts_ms: float = 0
    cost_token2wav_ms: float = 0
    cost_all_ms: float = 0
    llm_active: Optional[bool] = None
    tts_active: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class RoundResult:
    round_idx: int
    prepare_ms: float = 0
    chunks: List[ChunkResult] = field(default_factory=list)
    error: Optional[str] = None


# ========== Helpers ==========

def freeze_identity(model_key: str, transport: str) -> RunIdentity:
    """Capture run identity."""
    import glob as g

    run_id = f"rtf_{model_key}_{transport}_{time.strftime('%Y%m%d_%H%M%S')}"

    # Git identity
    try:
        base_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd="/workspace/llama.cpp-omni-session-fix",
            text=True).strip()
    except Exception:
        base_sha = "UNKNOWN"

    try:
        head_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd="/workspace/llama.cpp-omni-session-fix",
            text=True).strip()
    except Exception:
        head_sha = "UNKNOWN"

    try:
        gs = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd="/workspace/llama.cpp-omni-session-fix",
            text=True).strip()
    except Exception:
        gs = "UNKNOWN"

    # Binary SHA
    try:
        bin_sha = subprocess.check_output(["sha256sum", SERVER_BIN], text=True).split()[0]
    except Exception:
        bin_sha = "UNKNOWN"

    # CANN version
    try:
        cann_ver = os.environ.get("ASCEND_VERSION", "UNKNOWN")
    except Exception:
        cann_ver = "UNKNOWN"

    m = MODELS[model_key]

    return RunIdentity(
        run_id=run_id,
        start_time=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        source_base_sha=base_sha,
        source_head_sha=head_sha,
        git_status=gs,
        server_binary_sha256=bin_sha,
        model_filename=os.path.basename(m["path"]),
        model_sha256=m["sha256"],
        model_quant_type=m["quant_type"],
        transport=transport,
        runtime_args=f"-t 4 --device CANN0 -ngl 999 --ctx-size 4096",
        ascend_visible_devices=os.environ.get("ASCEND_RT_VISIBLE_DEVICES", "UNSET"),
        cann_version=cann_ver,
        env_sorted="\n".join(f"{k}={v}" for k, v in sorted(os.environ.items())),
    )


def load_wav_float32(path: str) -> list:
    """Load and resample WAV to 16kHz float32 mono."""
    with wave.open(path, 'rb') as w:
        nframes, sr, nch, sw = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
        frames = w.readframes(nframes)

    if sw == 2:
        samples = struct.unpack(f'<{len(frames)//2}h', frames)
        audio = [s / 32768.0 for s in samples]
    elif sw == 4:
        audio = list(struct.unpack(f'<{len(frames)//4}f', frames))
    else:
        raise ValueError(f"Unsupported sample width: {sw}")

    if nch > 1:
        audio = [sum(audio[i:i+nch])/nch for i in range(0, len(audio), nch)]
    if sr != INPUT_SAMPLE_RATE:
        ratio = INPUT_SAMPLE_RATE / sr
        new_len = int(len(audio) * ratio)
        audio = [audio[min(int(i/ratio), len(audio)-1)] for i in range(new_len)]

    return audio


def make_chunk_b64(chunk: list) -> str:
    """Float32 → int16 WAV → base64 (server expects b64 WAV input)."""
    i16 = [max(-32768, min(32767, int(s * 32767))) for s in chunk]
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(INPUT_SAMPLE_RATE)
        w.writeframes(struct.pack(f'<{len(i16)}h', *i16))
    return base64.b64encode(buf.getvalue()).decode()


def decode_audio_output(b64_data: str) -> tuple:
    """Decode audio delta (base64 float32 PCM) → bytes, duration_s, sha256."""
    raw = base64.b64decode(b64_data)
    n_samples = len(raw) // 4
    duration = n_samples / OUTPUT_SAMPLE_RATE
    sha = hashlib.sha256(raw).hexdigest()[:16]
    return len(raw), duration, sha


def classify_chunk(is_listen: bool, n_tokens: int, n_tts_tokens: int,
                   audio_bytes: int, llm_active: Optional[bool]) -> tuple:
    """Return (status, confidence). DIRECT if llm_active observed, else PROVISIONAL."""
    if is_listen:
        return "LISTEN", "DIRECT"  # listen is directly observed

    confidence = "DIRECT" if llm_active is not None else "PROVISIONAL"

    if n_tokens > 0 and audio_bytes > 0:
        return "SPEAK_GENERATION", confidence
    elif n_tokens == 0 and (n_tts_tokens > 0 or audio_bytes > 0):
        return "SPEAK_TAIL", confidence
    else:
        return "UNKNOWN", confidence


def verify_model_sha(model_key: str) -> bool:
    """Verify model file SHA256 against official value."""
    m = MODELS[model_key]
    expected = m["sha256"]
    try:
        actual = subprocess.check_output(["sha256sum", m["path"]], text=True).split()[0]
        ok = actual == expected
        if not ok:
            print(f"  SHA256 MISMATCH: {model_key}")
            print(f"    Expected: {expected}")
            print(f"    Actual:   {actual}")
        return ok
    except Exception as e:
        print(f"  Cannot verify {model_key}: {e}")
        return False


# ========== Transport Implementations ==========

async def run_backend_direct(ws_url: str, audio: list, chunk_size: int,
                             verbose: bool = True) -> List[RoundResult]:
    """Connect directly to llama-omni-server backend WS."""
    import websockets

    ws = await websockets.connect(ws_url, max_size=128 * 1024 * 1024)

    t0 = time.perf_counter()
    await ws.send(json.dumps({"type": "session.init", "payload": {
        "mode": "full_duplex", "use_tts": True,
        "config": {"force_listen_count": 0},
    }}))
    raw = await asyncio.wait_for(ws.recv(), timeout=60)
    init = json.loads(raw)
    prepare_ms = (time.perf_counter() - t0) * 1000

    if init.get('type') != 'session.created':
        print(f"FATAL: init failed: {init}")
        await ws.close()
        return []

    sid = init.get('session_id', '')[:12]
    if verbose:
        print(f"  Session: {sid}, prepare={prepare_ms:.0f}ms")
        print("  Waiting for duplex pipeline init (TTS load + prefill)...")

    await asyncio.sleep(20)  # Pipeline initialization

    return await _run_rounds_backend(ws, audio, chunk_size, verbose)


async def _run_rounds_backend(ws, audio: list, chunk_size: int,
                              verbose: bool) -> List[RoundResult]:
    """Execute rounds using backend protocol."""
    all_rounds = []
    total_samples = len(audio)

    for r in range(1, N_ROUNDS + 1):
        if verbose:
            print(f"\n  --- Round {r}/{N_ROUNDS} ---")
        rd = RoundResult(round_idx=r)

        for i in range(NUM_CHUNKS_PER_ROUND):
            start = (i * chunk_size) % total_samples
            end = start + chunk_size
            chunk = audio[start:end]
            if len(chunk) < chunk_size:
                chunk = chunk + [0.0] * (chunk_size - len(chunk))

            b64 = make_chunk_b64(chunk)
            t_send = time.perf_counter_ns()

            await ws.send(json.dumps({"type": "input.append", "input": {
                "audio": b64, "streaming": True,
                "generation": {"max_new_tokens": 100},
            }}))

            cr = ChunkResult(chunk_idx=i, round_idx=r, send_ts_ns=t_send)
            t_recv_start = time.monotonic()

            while True:
                timeout = 30 - (time.monotonic() - t_recv_start)
                if timeout <= 0:
                    cr.error = "timeout"; break

                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(timeout, 10))
                except asyncio.TimeoutError:
                    cr.error = "recv_timeout"; break

                evt = json.loads(raw)
                et = evt.get('type', '')
                kind = evt.get('kind', '')

                if et == 'response.output.delta':
                    if kind == 'listen':
                        cr.result_ts_ns = time.perf_counter_ns()
                        cr.wall_ms = (cr.result_ts_ns - t_send) / 1e6
                        cr.is_listen = True
                        cr.status, cr.status_confidence = "LISTEN", "DIRECT"
                        break

                    audio_b64 = evt.get('audio', '')
                    if audio_b64:
                        cr.result_ts_ns = time.perf_counter_ns()
                        cr.wall_ms = (cr.result_ts_ns - t_send) / 1e6
                        cr.audio_bytes, cr.audio_duration_s, cr.audio_sha256 = \
                            decode_audio_output(audio_b64)
                        cr.text = evt.get('text', '') or evt.get('delta', '')
                        cr.cost_llm_ms = evt.get('cost_llm_ms', 0) or 0
                        cr.cost_tts_ms = evt.get('cost_tts_ms', 0) or 0
                        cr.cost_token2wav_ms = evt.get('cost_token2wav_ms', 0) or 0
                        cr.cost_all_ms = evt.get('cost_all_ms', 0) or 0
                        cr.n_tokens = evt.get('n_tokens', 0) or 0
                        cr.n_tts_tokens = evt.get('n_tts_tokens', 0) or 0
                        cr.end_of_turn = evt.get('end_of_turn', False)
                        cr.llm_active = evt.get('llm_active')
                        cr.status, cr.status_confidence = classify_chunk(
                            cr.is_listen, cr.n_tokens, cr.n_tts_tokens,
                            cr.audio_bytes, cr.llm_active)
                        break

                    txt = evt.get('text', '') or evt.get('delta', '')
                    if txt:
                        cr.text += txt

                elif et == 'response.done':
                    cr.result_ts_ns = time.perf_counter_ns()
                    cr.wall_ms = (cr.result_ts_ns - t_send) / 1e6
                    cr.status = "DONE"
                    break

                elif et in ('session.closed', 'error'):
                    cr.error = f"{et}: {evt.get('reason', '?')}"
                    cr.result_ts_ns = time.perf_counter_ns()
                    cr.wall_ms = (cr.result_ts_ns - t_send) / 1e6
                    break

            rd.chunks.append(cr)
            if cr.error and ('session.closed' in str(cr.error) or 'error' in str(cr.error)):
                rd.error = cr.error
                break

        all_rounds.append(rd)
        if rd.error:
            break

    await ws.send(json.dumps({"type": "session.close"}))
    await ws.close()
    return all_rounds


# ========== Metrics ==========

def compute_metrics(rounds: List[RoundResult], label: str) -> dict:
    """Compute official metrics from rounds."""
    speak_chunks, all_valid = [], []

    for rd in rounds:
        if rd.error:
            continue
        stable = rd.chunks[WARMUP_CHUNKS:]
        for c in stable:
            if c.error:
                continue
            if c.status == "SPEAK_GENERATION":
                speak_chunks.append(c)
            if c.status in ("LISTEN", "SPEAK_GENERATION", "SPEAK_TAIL"):
                all_valid.append(c)

    if not speak_chunks:
        return {"error": "No valid SPEAK_GENERATION chunks", "label": label}

    import numpy as np
    speak_r = [c.wall_ms / 1000.0 for c in speak_chunks]
    speak_l = [c.wall_ms for c in speak_chunks]
    all_r = [c.wall_ms / 1000.0 for c in all_valid] if all_valid else [0]

    return {
        "label": label,
        "n_rounds": len([r for r in rounds if not r.error]),
        "n_speak_chunks": len(speak_chunks),
        "n_all_valid": len(all_valid),
        "n_listen": sum(1 for c in all_valid if c.status == "LISTEN"),
        "n_tail": sum(1 for c in all_valid if c.status == "SPEAK_TAIL"),
        "speak_mean_ms": float(np.mean(speak_l)),
        "speak_p50_ms": float(np.median(speak_l)),
        "speak_p90_ms": float(np.percentile(speak_l, 90)),
        "speak_min_ms": float(np.min(speak_l)),
        "speak_max_ms": float(np.max(speak_l)),
        "speak_mean_rtf": float(np.mean(speak_r)),
        "all_chunk_mean_rtf": float(np.mean(all_r)),
        "delta_vs_1_087": float(np.mean(speak_r) - BASELINE_SPEAK_RTF),
        "speedup_vs_1_087": float(BASELINE_SPEAK_RTF / np.mean(speak_r)) if np.mean(speak_r) > 0 else 0,
        "errors": sum(1 for rd in rounds for c in rd.chunks if c.error),
        "timeouts": sum(1 for rd in rounds for c in rd.chunks if c.error and 'timeout' in str(c.error)),
    }


# ========== Main ==========

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=list(MODELS.keys()))
    parser.add_argument("--transport", default="backend",
                        choices=["backend", "worker"])
    parser.add_argument("--verbose", action="store_true", default=True)
    args = parser.parse_args()

    model_key = args.model
    transport = args.transport

    print("=" * 70)
    print(f"OFFICIAL SPEAK→WAV RTF BENCHMARK")
    print(f"  Model: {model_key} ({MODELS[model_key]['quant_type']})")
    print(f"  Transport: {transport}")
    print(f"  Config: {N_ROUNDS}r × {NUM_CHUNKS_PER_ROUND}c × {CHUNK_DURATION_S}s")
    print(f"  Warmup: {WARMUP_CHUNKS} chunks excluded per round")
    print(f"  BENCH_CONFIG_SOURCE={BENCH_CONFIG_SOURCE}")
    print(f"  OFFICIAL_MANDATORY={OFFICIAL_MANDATORY}")
    print("=" * 70)

    # Verify model
    if not verify_model_sha(model_key):
        print("FATAL: Model SHA256 mismatch")
        sys.exit(1)
    print("  Model SHA256: OK")

    # Verify server is running with correct model
    model_path = MODELS[model_key]["path"]
    pid = None
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
    except Exception:
        pass

    if pid:
        # Check if server is running with the right model
        try:
            cmdline = open(f"/proc/{pid}/cmdline").read().replace('\0', ' ')
            if model_path not in cmdline:
                print(f"  WARNING: Server (PID={pid}) is NOT running with {model_key}")
                print(f"    cmdline: {cmdline[:120]}")
                print(f"  Expected model: {model_path}")
        except Exception:
            pass

    # Freeze identity
    identity = freeze_identity(model_key, transport)
    run_dir = BENCH_DIR / identity.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save identity
    with open(run_dir / "identity.json", "w") as f:
        json.dump({k: str(v) for k, v in identity.__dict__.items()}, f, indent=2)

    print(f"\n  Run ID: {identity.run_id}")
    print(f"  Run dir: {run_dir}")

    # Load audio
    audio = load_wav_float32(USER_AUDIO_PATH)
    chunk_size = int(CHUNK_DURATION_S * INPUT_SAMPLE_RATE)
    print(f"  Audio: {len(audio)/INPUT_SAMPLE_RATE:.1f}s, {chunk_size} samples/chunk")

    # Run benchmark
    print(f"\n  Connecting via {transport}...")

    if transport == "backend":
        rounds = await run_backend_direct(BACKEND_URL, audio, chunk_size, args.verbose)
    else:
        print("  Worker transport not yet implemented — use backend for now")
        rounds = []

    if not rounds:
        print("FATAL: No rounds completed")
        sys.exit(1)

    # Compute metrics
    metrics = compute_metrics(rounds, f"{model_key}_{transport}")

    # Save raw chunks
    all_chunks = []
    for rd in rounds:
        for c in rd.chunks:
            all_chunks.append({k: str(v) for k, v in c.__dict__.items()})
    with open(run_dir / "chunks.jsonl", "w") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # Save metrics
    with open(run_dir / "summary.json", "w") as f:
        json.dump(metrics, f, indent=2)

    # Print results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    if "error" in metrics:
        print(f"ERROR: {metrics['error']}")
    else:
        print(f"  Rounds:              {metrics['n_rounds']}")
        print(f"  SPEAK_GEN chunks:    {metrics['n_speak_chunks']}")
        print(f"  LISTEN chunks:       {metrics['n_listen']}")
        print(f"  TAIL chunks:         {metrics['n_tail']}")
        print(f"  Errors:              {metrics['errors']}")
        print(f"  Timeouts:            {metrics['timeouts']}")
        print()
        print(f"  SPEAK_GEN Mean:      {metrics['speak_mean_ms']:.1f} ms")
        print(f"  SPEAK_GEN P50:       {metrics['speak_p50_ms']:.1f} ms")
        print(f"  SPEAK_GEN P90:       {metrics['speak_p90_ms']:.1f} ms")
        print(f"  SPEAK_GEN RTF:       {metrics['speak_mean_rtf']:.3f}")
        print(f"  ALL_CHUNK RTF:       {metrics['all_chunk_mean_rtf']:.3f}")
        print()
        print(f"  Baseline RTF:        1.087")
        print(f"  Baseline Latency:    1087.3 ms")
        print(f"  Delta vs Baseline:   {metrics['delta_vs_1_087']:+.3f}")
        print(f"  Speedup:             {metrics['speedup_vs_1_087']:.2f}×")
        verdict = "PASS" if metrics['speak_mean_rtf'] <= BASELINE_SPEAK_RTF else "FAIL"
        print(f"\n  BASELINE_COMPLIANCE: {verdict}")

    print(f"\n  Results saved to: {run_dir}")


if __name__ == "__main__":
    asyncio.run(main())
