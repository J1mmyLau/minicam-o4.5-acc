#!/usr/bin/env python3
"""
C10 Runtime Instrumentation Overhead A/B Test (v2)
===================================================
Measures E2E profiling instrumentation overhead.
Pattern: call omni_init before EVERY decode (matches w8 smoke test).
ABBA design: OFF → ON → ON → OFF.

Usage:
  python3 scripts/f6_c10_overhead_ab.py \
    --binary .../llama-omni-server --model .../model.gguf --mmproj .../mmproj.gguf \
    --port 18080 --n-requests 10
"""

import argparse, json, os, signal, socket, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path
from statistics import median, mean, stdev

socket.setdefaulttimeout(600)
PROMPTS = [f"Tell me about topic number {i}." for i in range(50)]


def http_post(url, data, timeout=600):
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {"_error": f"HTTP {e.code}", "_body": body}
    except Exception as e:
        return {"_error": str(e)}


def http_get(url, timeout=10):
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"_error": str(e)}


def wait_health(base_url, max_wait=300):
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            if http_get(f"{base_url}/health", timeout=5).get("status") == "ok":
                return True
        except Exception:
            pass
        print(f"    Waiting for server... ({int(deadline - time.time())}s)")
        time.sleep(5)
    return False


def start_server(binary, model, mmproj, port, e2e_profile, profile_dir, log_file):
    env = os.environ.copy()
    env["OMNI_E2E_PROFILE"] = e2e_profile
    if profile_dir:
        env["OMNI_E2E_PROFILE_DIR"] = profile_dir
    cmd = [binary, "--port", str(port), "--model", model, "--mmproj", mmproj,
           "--ctx-size", "2048", "--flash-attn", "off", "-ngl", "99", "--host", "0.0.0.0"]
    log_fh = open(log_file, "w")
    proc = subprocess.Popen(cmd, env=env, stdout=log_fh, stderr=subprocess.STDOUT,
                            preexec_fn=os.setsid)
    with open(f"/tmp/c10_server_{port}.pid", "w") as f:
        f.write(str(proc.pid))
    return proc


def stop_server(proc, port):
    if proc is None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait(timeout=5)
    except ProcessLookupError:
        pass
    for f in [f"/tmp/c10_server_{port}.pid"]:
        if os.path.exists(f):
            os.remove(f)


def run_pass(base_url, n_requests, output_dir, label):
    """Run one test pass. Returns list of timing dicts."""
    results = []
    for i in range(n_requests):
        subdir = f"{output_dir}/req_{i:03d}"
        os.makedirs(subdir, exist_ok=True)

        # omni_init before EVERY decode (matching w8 smoke test pattern)
        init_payload = {"media_type": 2, "use_tts": True, "output_dir": subdir}
        init_res = http_post(f"{base_url}/v1/stream/omni_init", init_payload)
        if not init_res.get("success"):
            print(f"  [{label}] Req {i+1}: omni_init FAILED: {init_res}")
            results.append({"request_index": i, "elapsed_s": -1, "success": False, "error": "omni_init_failed"})
            continue

        t0 = time.time()
        decode_res = http_post(f"{base_url}/v1/stream/decode",
                               {"debug_dir": subdir, "stream": False, "round_idx": 0}, timeout=600)
        elapsed = time.time() - t0

        ok = decode_res.get("success", False)
        status = "OK" if ok else f"FAIL: {decode_res.get('_error', 'unknown')}"
        print(f"  [{label}] Req {i+1}/{n_requests}: {elapsed:.1f}s [{status}]")
        results.append({"request_index": i, "elapsed_s": round(elapsed, 3), "success": ok})

        if i < n_requests - 1:
            time.sleep(2)
    return results


def compute_stats(results, label):
    elapsed = [r["elapsed_s"] for r in results if r["success"]]
    if not elapsed:
        return {"label": label, "n": 0, "failures": len(results)}
    s = sorted(elapsed); n = len(s)
    return {"label": label, "n": n, "failures": len(results) - n,
            "p50_s": round(s[n//2], 3), "p95_s": round(s[int(n*0.95)], 3) if n >= 20 else s[-1],
            "min_s": round(s[0], 3), "max_s": round(s[-1], 3),
            "mean_s": round(mean(elapsed), 3), "stdev_s": round(stdev(elapsed), 3) if n >= 2 else 0,
            "total_s": round(sum(elapsed), 1)}


def compare(off, on):
    off_map = {r["request_index"]: r["elapsed_s"] for r in off if r["success"]}
    on_map = {r["request_index"]: r["elapsed_s"] for r in on if r["success"]}
    deltas = [on_map[i] - off_map[i] for i in sorted(set(off_map) & set(on_map))]
    n = len(deltas)
    if n == 0:
        return {"n_pairs": 0}
    return {"n_pairs": n,
            "delta_p50_s": round(sorted(deltas)[n//2], 3),
            "delta_mean_s": round(mean(deltas), 3),
            "delta_stdev_s": round(stdev(deltas), 3) if n >= 2 else 0,
            "off_mean_s": round(mean([off_map[i] for i in sorted(set(off_map) & set(on_map))]), 3),
            "on_mean_s": round(mean([on_map[i] for i in sorted(set(off_map) & set(on_map))]), 3),
            "overhead_pct": round(100.0 * mean(deltas) / mean([off_map[i] for i in sorted(set(off_map) & set(on_map))]), 2),
            "deltas": deltas}


def main():
    p = argparse.ArgumentParser(description="C10 Runtime Overhead A/B Test v2")
    p.add_argument("--binary", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--mmproj", required=True)
    p.add_argument("--port", type=int, default=18080)
    p.add_argument("--n-requests", type=int, default=10)
    p.add_argument("--output-dir", default="/tmp/f6_c10")
    args = p.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    base_url = f"http://127.0.0.1:{args.port}"

    print("=" * 65)
    print("C10: Instrumentation Overhead A/B (v2, ABBA)")
    print("=" * 65)
    print(f"  N requests per pass: {args.n_requests}")
    print(f"  Output: {args.output_dir}")

    all_phases = {}

    for phase_idx, (phase_name, e2e_profile) in enumerate([
        ("OFF (pass 1)", "0"),
        ("ON  (pass 1)", "summary"),
        ("ON  (pass 2)", "summary"),
        ("OFF (pass 2)", "0"),
    ]):
        print(f"\n{'─'*65}")
        print(f"Phase {phase_idx+1}/4: OMNI_E2E_PROFILE={e2e_profile} ({phase_name})")
        print(f"{'─'*65}")

        label = phase_name.replace(" ", "_").replace("(", "").replace(")", "").lower()
        log_file = f"{args.output_dir}/server_{label}.log"
        profile_dir = f"{args.output_dir}/e2e_{label}" if e2e_profile != "0" else ""

        proc = start_server(args.binary, args.model, args.mmproj, args.port,
                            e2e_profile, profile_dir, log_file)
        print(f"  Server PID: {proc.pid}")
        if profile_dir:
            os.makedirs(profile_dir, exist_ok=True)

        if not wait_health(base_url):
            print("  FATAL: Server not healthy")
            stop_server(proc, args.port)
            sys.exit(1)
        print("  [OK] Server healthy")

        results = run_pass(base_url, args.n_requests, f"{args.output_dir}/{label}_output", label)
        stats = compute_stats(results, phase_name)
        all_phases[label] = {"config": phase_name, "e2e_profile": e2e_profile,
                             "results": results, "stats": stats}
        print(f"  Stats: n={stats['n']}, mean={stats.get('mean_s','?')}s, "
              f"p50={stats.get('p50_s','?')}s, failures={stats['failures']}")

        stop_server(proc, args.port)
        time.sleep(5)

    # ── Analysis ──
    print(f"\n{'='*65}")
    print("C10 Gate Decision")
    print(f"{'='*65}")

    off1 = all_phases["off_pass_1"]["results"]
    on1 = all_phases["on_pass_1"]["results"]
    off2 = all_phases["off_pass_2"]["results"]
    on2 = all_phases["on_pass_2"]["results"]

    cmp1 = compare(off1, on1)
    cmp2 = compare(off2, on2)

    # Combined
    all_off = [r for r in off1 + off2 if r["success"]]
    all_on = [r for r in on1 + on2 if r["success"]]

    for name, cmp in [("OFF1 vs ON1", cmp1), ("OFF2 vs ON2", cmp2)]:
        if cmp["n_pairs"] == 0:
            continue
        print(f"\n  {name}:")
        print(f"    n_pairs:     {cmp['n_pairs']}")
        print(f"    off mean:    {cmp['off_mean_s']}s")
        print(f"    on mean:     {cmp['on_mean_s']}s")
        print(f"    delta p50:   {cmp['delta_p50_s']}s")
        print(f"    delta mean:  {cmp['delta_mean_s']}s")
        print(f"    overhead:    {cmp['overhead_pct']}%")

    # Gate: |delta mean| < 1.0s or |overhead| < 5%
    primary = cmp1 if cmp1["n_pairs"] >= cmp2.get("n_pairs", 0) else cmp2
    abs_delta = abs(primary.get("delta_mean_s", 999) or 999)
    abs_pct = abs(primary.get("overhead_pct", 999) or 999)
    passed = abs_delta < 1.0 or abs_pct < 5.0

    print(f"\n  C10 Gate: {'PASS' if passed else 'FAIL'}")
    print(f"    |mean delta| = {abs_delta:.3f}s  (need < 1.0s)")
    print(f"    |overhead %| = {abs_pct:.2f}%  (need < 5.0%)")

    for r in all_phases.values():
        r.pop("results", None)  # strip results for compact report

    report = {"test": "C10 v2 ABBA", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "binary": args.binary, "n_requests": args.n_requests,
              "phases": all_phases, "comparison_pass1": cmp1, "comparison_pass2": cmp2,
              "gate": {"passed": passed, "abs_mean_delta_s": abs_delta, "abs_overhead_pct": abs_pct}}

    rpath = f"{args.output_dir}/C10_REPORT.json"
    with open(rpath, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report: {rpath}")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
