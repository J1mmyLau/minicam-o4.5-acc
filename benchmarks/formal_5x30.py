#!/usr/bin/env python3
"""Formal 5×30 Q8_0 benchmark with server restart between rounds.

Workaround for server crash-on-cleanup bug.
Each round: start server → run benchmark → stop server → save results → repeat.
"""
import subprocess, json, time, os, sys, re

MODEL_NAME = "Q8_0"
MODEL_PATH = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q8_0.gguf"
SERVER_BIN = "/workspace/llama.cpp-omni-session-fix/build/bin/llama-omni-server"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 22500
SERVER_LOG = "/tmp/gfh-die0/server-formal5x30.log"
BENCHMARK = "/workspace/llama.cpp-omni-session-fix/benchmarks/speak_wav_rtf_v2.py"
OUTDIR = "/workspace/llama.cpp-omni-session-fix/benchmarks/results"
ROUNDS = 5
CHUNKS = 33  # 33 chunks, warmup=3 → 30 measurement

os.makedirs(OUTDIR, exist_ok=True)

def stop_server():
    subprocess.run(["pkill", "-9", "-f", "llama-omni-server"], capture_output=True)
    for _ in range(15):
        r = subprocess.run(["pgrep", "-f", "llama-omni-server"], capture_output=True)
        if r.returncode != 0:
            return True
        time.sleep(2)
    return False

def start_server():
    env = os.environ.copy()
    env["OMNI_T2W_DEVICE"] = "cann-flow-only"
    env["OMNI_T2W_DRAIN_TIMEOUT_MS"] = "5000"
    env["OMNI_T2W_PROFILE"] = "2"
    env["ASCEND_RT_VISIBLE_DEVICES"] = "0"

    cmd = [
        SERVER_BIN, "-m", MODEL_PATH,
        "--host", SERVER_HOST, "--port", str(SERVER_PORT),
        "-ngl", "999", "--device", "CANN0",
        "--ctx-size", "4096", "--batch-size", "512", "--ubatch-size", "512",
        "-t", "4",
    ]

    with open(SERVER_LOG, "w") as lf:
        proc = subprocess.Popen(cmd, env=env, stdout=lf, stderr=subprocess.STDOUT)

    with open("/tmp/gfh-die0/llama-omni.pid", "w") as f:
        f.write(str(proc.pid))

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
                return proc
        except Exception:
            pass
        time.sleep(2)
    return None

def run_round():
    """Run single-round benchmark."""
    cmd = [sys.executable, BENCHMARK, "--model", MODEL_NAME,
           "--rounds", "1", "--chunks", str(CHUNKS), "--transport", "backend"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    for line in r.stdout.split("\n"):
        if "Results saved:" in line:
            path = line.split("Results saved:")[-1].strip()
            if os.path.exists(path):
                with open(path) as f:
                    return json.load(f)
    return None

def parse_t2w_timing(log_path):
    """Parse [timing] lines from entire log."""
    if not os.path.exists(log_path):
        return []
    with open(log_path, 'rb') as f:
        content = f.read().decode('utf-8', errors='replace')

    timing_re = re.compile(
        r'\[timing\] call=\d+.*?encoder=([\d.]+)ms flow_match=([\d.]+)ms '
        r'token2mel=([\d.]+)ms vocoder=([\d.]+)ms total=([\d.]+)ms'
    )
    return [{"encoder_ms": float(m.group(1)), "flow_match_ms": float(m.group(2)),
             "token2mel_ms": float(m.group(3)), "vocoder_ms": float(m.group(4)),
             "total_ms": float(m.group(5))} for m in timing_re.finditer(content)]

def compute_stats(vals):
    if not vals: return {"mean": 0, "p50": 0, "n": 0}
    s = sorted(vals)
    return {"mean": sum(s)/len(s), "p50": s[len(s)//2], "n": len(s)}

def main():
    all_results = []

    for rnd in range(1, ROUNDS + 1):
        print(f"\n{'='*60}")
        print(f"Round {rnd}/{ROUNDS}: Starting server...")
        print(f"{'='*60}")

        # Ensure clean state
        stop_server()
        time.sleep(3)

        proc = start_server()
        if proc is None:
            print(f"FATAL: server failed to start for round {rnd}")
            continue

        print(f"Server ready, running benchmark...")
        try:
            bench = run_round()
        except Exception as e:
            print(f"Benchmark error: {e}")
            bench = None

        # Parse T2W timing
        t2w = parse_t2w_timing(SERVER_LOG)

        # Extract SPEAK chunks
        walls = []
        if bench:
            for r in bench.get("rounds", []):
                for c in r.get("chunks", []):
                    if c.get("state") == "SPEAK_GENERATION" and c.get("chunk_id", 0) >= 3:
                        walls.append(c["wall_ms"])

        voc_vals = [t["vocoder_ms"] for t in t2w]
        fm_vals = [t["flow_match_ms"] for t in t2w]
        total_vals = [t["total_ms"] for t in t2w]

        stats = {
            "round": rnd,
            "speak_count": len(walls),
            "t2w_count": len(t2w),
            "wall": compute_stats(walls),
            "vocoder": compute_stats(voc_vals),
            "flow_match": compute_stats(fm_vals),
            "t2w_total": compute_stats(total_vals),
        }

        if stats["wall"]["mean"] > 0:
            rtf = stats["wall"]["mean"] / 1000.0
            print(f"  SPEAK={stats['speak_count']}, T2W={stats['t2w_count']}")
            print(f"  Wall mean={stats['wall']['mean']:.1f}ms p50={stats['wall']['p50']:.1f}ms RTF={rtf:.3f}")
            print(f"  Vocoder mean={stats['vocoder']['mean']:.1f}ms p50={stats['vocoder']['p50']:.1f}ms")
        else:
            print(f"  NO SPEAK data collected!")

        all_results.append(stats)
        stop_server()

    # Summary
    all_walls = []
    all_vocs = []
    all_fms = []
    all_t2ws = []
    for s in all_results:
        if s.get("speak_count", 0) > 0:
            all_walls.extend([s["wall"]["mean"]] * s["speak_count"])
            all_vocs.extend([s["vocoder"]["mean"]] * s["t2w_count"])
            all_fms.extend([s["flow_match"]["mean"]] * s["t2w_count"])
            all_t2ws.extend([s["t2w_total"]["mean"]] * s["t2w_count"])

    print(f"\n{'='*60}")
    print(f"FINAL SUMMARY: Q8_0 5×30 Formal Run")
    print(f"{'='*60}")
    for s in all_results:
        rtf = s["wall"]["mean"] / 1000.0 if s["wall"]["mean"] > 0 else 0
        print(f"  R{s['round']}: {s['speak_count']} SPEAK, wall={s['wall']['mean']:.1f}ms, "
              f"voc={s['vocoder']['mean']:.1f}ms, fm={s['flow_match']['mean']:.1f}ms, "
              f"RTF={rtf:.3f}")

    ws = compute_stats([s["wall"]["mean"] for s in all_results if s.get("speak_count", 0) > 0])
    vs = compute_stats([s["vocoder"]["mean"] for s in all_results if s.get("speak_count", 0) > 0])
    fm_agg = compute_stats([s["flow_match"]["mean"] for s in all_results if s.get("speak_count", 0) > 0])
    tw_agg = compute_stats([s["t2w_total"]["mean"] for s in all_results if s.get("speak_count", 0) > 0])

    print(f"\nPer-Round Aggregate:")
    print(f"  Wall mean:    {ws['mean']:.1f}ms (p50={ws['p50']:.1f})")
    print(f"  Vocoder mean: {vs['mean']:.1f}ms (p50={vs['p50']:.1f})")
    print(f"  FM mean:      {fm_agg['mean']:.1f}ms (p50={fm_agg['p50']:.1f})")
    print(f"  T2W mean:     {tw_agg['mean']:.1f}ms (p50={tw_agg['p50']:.1f})")
    rtfm = ws['mean'] / 1000.0 if ws['mean'] > 0 else 0
    print(f"  RTF mean:     {rtfm:.3f}")
    print(f"  Speedup:      {1.087/rtfm:.2f}× vs official 1.087")

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = f"{OUTDIR}/formal_5x30_Q8_0_{ts}.json"
    with open(out_path, 'w') as f:
        json.dump({"rounds": all_results,
                   "aggregate": {"wall": ws, "vocoder": vs, "flow_match": fm_agg,
                                 "t2w_total": tw_agg, "rtf_mean": rtfm,
                                 "speedup_vs_1_087": 1.087/rtfm if rtfm > 0 else 0}},
                  f, indent=2, default=str)
    print(f"\nResults saved: {out_path}")

if __name__ == "__main__":
    main()
