#!/usr/bin/env python3
"""Alternating F16/Q8 A/B test — proves/disproves vocoder CPU quantization causal mechanism.

Runs F16→Q8→F16→Q8→F16→Q8 (6 runs, 30 measurement chunks each).
Records per-run: encoder, flow_match, token2mel, vocoder, T2W total, wall, RTF mean/p50.

Usage:
  python3 benchmarks/alternating_ab.py
"""
import subprocess, json, time, os, sys, re

# Config
MODELS = {
    "F16": "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf",
    "Q8_0": "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q8_0.gguf",
}
SERVER_BIN = "/workspace/llama.cpp-omni-session-fix/build/bin/llama-omni-server"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 22500
SERVER_LOG = "/tmp/gfh-die0/server-ab.log"
BENCHMARK = "/workspace/llama.cpp-omni-session-fix/benchmarks/speak_wav_rtf_v2.py"
OUTDIR = "/workspace/llama.cpp-omni-session-fix/benchmarks/results"
SEQUENCE = ["F16", "Q8_0", "F16", "Q8_0", "F16", "Q8_0"]  # 6 alternating runs

os.makedirs(OUTDIR, exist_ok=True)

def stop_server():
    """Kill any running llama-omni-server."""
    r = subprocess.run(["pkill", "-f", "llama-omni-server"], capture_output=True)
    time.sleep(2)
    # Verify stopped
    for _ in range(10):
        r2 = subprocess.run(["pgrep", "-f", "llama-omni-server"], capture_output=True)
        if r2.returncode != 0:
            return True
        time.sleep(2)
    return False

def start_server(model_name):
    """Start server with given model. Returns True if health check passes."""
    model_path = MODELS[model_name]
    env = os.environ.copy()
    env["OMNI_T2W_DEVICE"] = "cann-flow-only"
    env["OMNI_T2W_DRAIN_TIMEOUT_MS"] = "5000"
    env["OMNI_T2W_PROFILE"] = "2"  # Enable per-call [timing] lines
    env["ASCEND_RT_VISIBLE_DEVICES"] = "0"

    cmd = [
        SERVER_BIN,
        "-m", model_path,
        "--host", SERVER_HOST,
        "--port", str(SERVER_PORT),
        "-ngl", "999",
        "--device", "CANN0",
        "--ctx-size", "4096",
        "--batch-size", "512",
        "--ubatch-size", "512",
        "-t", "4",
    ]

    log_f = open(SERVER_LOG, "w")
    proc = subprocess.Popen(cmd, env=env, stdout=log_f, stderr=subprocess.STDOUT)

    # Write PID
    with open("/tmp/gfh-die0/llama-omni.pid", "w") as f:
        f.write(str(proc.pid))

    # Symlink
    if os.path.exists("/tmp/gfh-die0/server.log"):
        os.unlink("/tmp/gfh-die0/server.log")
    os.symlink(SERVER_LOG, "/tmp/gfh-die0/server.log")

    # Wait for health check
    import urllib.request
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            r = urllib.request.urlopen(f"http://{SERVER_HOST}:{SERVER_PORT}/health", timeout=5)
            if r.status == 200:
                time.sleep(3)  # Extra settle time for model loading
                return proc
        except Exception:
            pass
        time.sleep(2)
    return None

def run_benchmark(model_name):
    """Run 1-round benchmark and return results."""
    cmd = [
        sys.executable, BENCHMARK,
        "--model", model_name,
        "--rounds", "1",
        "--chunks", "33",  # 33 chunks, warmup=3 => 30 measurement
        "--transport", "backend",
    ]
    env = os.environ.copy()
    env["SERVER_LOG"] = SERVER_LOG
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)

    # Find the results JSON file
    ts_match = None
    for line in r.stdout.split("\n"):
        if "Results saved:" in line:
            path = line.split("Results saved:")[-1].strip()
            if os.path.exists(path):
                with open(path) as f:
                    return json.load(f)
    return None

def parse_t2w_timing(log_path, start_offset):
    """Parse [timing] lines from log after start_offset."""
    if not os.path.exists(log_path):
        return []

    with open(log_path, 'rb') as f:
        f.seek(start_offset)
        content = f.read().decode('utf-8', errors='replace')

    timing_re = re.compile(
        r'\[timing\] call=\d+.*?encoder=([\d.]+)ms flow_match=([\d.]+)ms '
        r'token2mel=([\d.]+)ms vocoder=([\d.]+)ms total=([\d.]+)ms'
    )

    results = []
    for m in timing_re.finditer(content):
        results.append({
            "encoder_ms": float(m.group(1)),
            "flow_match_ms": float(m.group(2)),
            "token2mel_ms": float(m.group(3)),
            "vocoder_ms": float(m.group(4)),
            "total_ms": float(m.group(5)),
        })
    return results

def compute_stats(vals):
    """Compute mean, p50 from list of values."""
    if not vals:
        return {"mean": 0, "p50": 0, "n": 0}
    s = sorted(vals)
    return {"mean": sum(s)/len(s), "p50": s[len(s)//2], "n": len(s)}

def main():
    results = []

    for run_idx, model in enumerate(SEQUENCE):
        print(f"\n{'='*60}")
        print(f"Run {run_idx+1}/6: {model}")
        print(f"{'='*60}")

        # Stop server
        print("Stopping server...")
        if not stop_server():
            print("WARNING: server may still be running")

        # Get log offset
        log_offset = os.path.getsize(SERVER_LOG) if os.path.exists(SERVER_LOG) else 0
        if not os.path.exists(SERVER_LOG):
            open(SERVER_LOG, 'w').close()
            log_offset = 0

        # Start server
        print(f"Starting server with {model}...")
        proc = start_server(model)
        if proc is None:
            print(f"FATAL: server failed to start for {model}")
            results.append({"model": model, "error": "server_start_failed"})
            continue

        # Note log offset after server started (skip init lines)
        time.sleep(2)
        post_init_offset = os.path.getsize(SERVER_LOG)

        # Run benchmark
        print(f"Running benchmark...")
        try:
            bench_result = run_benchmark(model)
        except Exception as e:
            print(f"Benchmark error: {e}")
            bench_result = None

        # Parse T2W timing
        t2w_components = parse_t2w_timing(SERVER_LOG, post_init_offset)

        # Compute stats
        encoder_vals = [c["encoder_ms"] for c in t2w_components]
        fm_vals = [c["flow_match_ms"] for c in t2w_components]
        token2mel_vals = [c["token2mel_ms"] for c in t2w_components]
        vocoder_vals = [c["vocoder_ms"] for c in t2w_components]
        total_vals = [c["total_ms"] for c in t2w_components]

        # Extract wall clock from benchmark
        wall_vals = []
        wall_mean = None
        wall_p50 = None
        rtf_mean = None
        if bench_result:
            for r in bench_result.get("rounds", []):
                for c in r.get("chunks", []):
                    if c.get("state") == "SPEAK_GENERATION" and c.get("chunk_id", 0) >= 3:
                        wall_vals.append(c["wall_ms"])

        run_stats = {
            "run": run_idx + 1,
            "model": model,
            "encoder": compute_stats(encoder_vals),
            "flow_match": compute_stats(fm_vals),
            "token2mel": compute_stats(token2mel_vals),
            "vocoder": compute_stats(vocoder_vals),
            "t2w_total": compute_stats(total_vals),
            "wall": compute_stats(wall_vals),
            "speak_count": len(wall_vals),
        }

        # Print summary
        s = run_stats
        print(f"  T2W samples: {s['t2w_total']['n']}, SPEAK samples: {s['speak_count']}")
        print(f"  encoder   mean={s['encoder']['mean']:.1f}ms  p50={s['encoder']['p50']:.1f}ms")
        print(f"  flow_match mean={s['flow_match']['mean']:.1f}ms  p50={s['flow_match']['p50']:.1f}ms")
        print(f"  token2mel mean={s['token2mel']['mean']:.1f}ms  p50={s['token2mel']['p50']:.1f}ms")
        print(f"  vocoder   mean={s['vocoder']['mean']:.1f}ms  p50={s['vocoder']['p50']:.1f}ms")
        print(f"  T2W total mean={s['t2w_total']['mean']:.1f}ms  p50={s['t2w_total']['p50']:.1f}ms")
        print(f"  WALL      mean={s['wall']['mean']:.1f}ms  p50={s['wall']['p50']:.1f}ms")
        if s['wall']['mean'] > 0:
            rtf = s['wall']['mean'] / 1000.0
            print(f"  RTF mean  ={rtf:.3f}")

        results.append(run_stats)

        # Stop server after each run
        stop_server()

    # Final summary
    print(f"\n{'='*60}")
    print("SUMMARY: Alternating F16/Q8 A/B")
    print(f"{'='*60}")
    print(f"{'Run':<6} {'Model':<6} {'Encoder':>8} {'FM':>8} {'T2M':>8} {'Vocoder':>8} {'T2W':>8} {'Wall':>8} {'RTF':>7} {'n_T2W':>6} {'n_SPK':>6}")
    print("-" * 90)

    for s in results:
        if "error" in s:
            print(f"{s['run']:<6} {s['model']:<6} ERROR: {s['error']}")
            continue
        rtf = s['wall']['mean'] / 1000.0 if s['wall']['mean'] > 0 else 0
        print(f"{s['run']:<6} {s['model']:<6} "
              f"{s['encoder']['mean']:>7.1f}ms {s['flow_match']['mean']:>7.1f}ms "
              f"{s['token2mel']['mean']:>7.1f}ms {s['vocoder']['mean']:>7.1f}ms "
              f"{s['t2w_total']['mean']:>7.1f}ms {s['wall']['mean']:>7.1f}ms "
              f"{rtf:>6.3f} {s['t2w_total']['n']:>5} {s['speak_count']:>5}")

    # Per-model aggregates
    print(f"\n--- Per-Model Aggregates ---")
    for model in ["F16", "Q8_0"]:
        model_runs = [s for s in results if s.get("model") == model and "error" not in s]
        if not model_runs:
            continue
        voc_means = [s["vocoder"]["mean"] for s in model_runs]
        wall_means = [s["wall"]["mean"] for s in model_runs]
        t2w_means = [s["t2w_total"]["mean"] for s in model_runs]
        print(f"\n{model} ({len(model_runs)} runs):")
        print(f"  vocoder mean range: {min(voc_means):.1f} - {max(voc_means):.1f}ms (avg {sum(voc_means)/len(voc_means):.1f}ms)")
        print(f"  wall mean range:    {min(wall_means):.1f} - {max(wall_means):.1f}ms (avg {sum(wall_means)/len(wall_means):.1f}ms)")
        print(f"  T2W mean range:     {min(t2w_means):.1f} - {max(t2w_means):.1f}ms (avg {sum(t2w_means)/len(t2w_means):.1f}ms)")

    # Save results
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = f"{OUTDIR}/alternating_ab_{ts}.json"
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {out_path}")

if __name__ == "__main__":
    main()
