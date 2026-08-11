#!/usr/bin/env python3
"""C10 v3: One server, one omni_init, sequential decodes with sleep."""
import json, os, signal, socket, subprocess, sys, time, urllib.request, urllib.error
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
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"_error": str(e)}


def start_server(binary, model, mmproj, port, e2e_mode, out_dir):
    env = os.environ.copy()
    env["OMNI_E2E_PROFILE"] = e2e_mode
    if e2e_mode != "0":
        env["OMNI_E2E_PROFILE_DIR"] = f"{out_dir}/e2e_profiles"
        os.makedirs(f"{out_dir}/e2e_profiles", exist_ok=True)
    cmd = [binary, "--port", str(port), "--model", model, "--mmproj", mmproj,
           "--ctx-size", "2048", "--flash-attn", "off", "-ngl", "99", "--host", "0.0.0.0"]
    log_fh = open(f"{out_dir}/server.log", "w")
    proc = subprocess.Popen(cmd, env=env, stdout=log_fh, stderr=subprocess.STDOUT, preexec_fn=os.setsid)
    return proc


def stop_server(proc):
    if proc:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=15)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                pass


def wait_health(base_url, max_wait=300):
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            if http_get(f"{base_url}/health", timeout=5).get("status") == "ok":
                return True
        except Exception:
            pass
        time.sleep(5)
    return False


def run_single_config(binary, model, mmproj, port, e2e_mode, n_requests, out_dir, label):
    """One server instance, one omni_init, N sequential decodes."""
    print(f"\n{'='*60}")
    print(f"Config: OMNI_E2E_PROFILE={e2e_mode} ({label})")
    print(f"{'='*60}")

    os.makedirs(out_dir, exist_ok=True)
    proc = start_server(binary, model, mmproj, port, e2e_mode, out_dir)
    print(f"  Server PID: {proc.pid}")

    if not wait_health(f"http://127.0.0.1:{port}"):
        print("  FATAL: server not healthy")
        stop_server(proc)
        return []

    # omni_init ONCE at the beginning
    init_payload = {"media_type": 2, "use_tts": True, "output_dir": f"{out_dir}/omni_out"}
    init_res = http_post(f"http://127.0.0.1:{port}/v1/stream/omni_init", init_payload)
    if not init_res.get("success"):
        print(f"  FATAL: omni_init failed: {init_res}")
        stop_server(proc)
        return []
    print(f"  [OK] omni_init succeeded")

    results = []
    for i in range(n_requests):
        subdir = f"{out_dir}/omni_out/round_{i:03d}"
        os.makedirs(subdir, exist_ok=True)

        t0 = time.time()
        decode_res = http_post(f"http://127.0.0.1:{port}/v1/stream/decode",
                               {"debug_dir": subdir, "stream": False, "round_idx": i}, timeout=600)
        elapsed = time.time() - t0

        ok = decode_res.get("success", False)
        print(f"  [{label}] Req {i+1}/{n_requests}: {elapsed:.1f}s {'OK' if ok else 'FAIL'}")
        results.append({"index": i, "elapsed_s": round(elapsed, 3), "success": ok})

        if not ok:
            print(f"    Error: {decode_res.get('_error', 'unknown')}")

        if i < n_requests - 1:
            wait_time = max(10, int(elapsed * 0.3))  # 30% of request time as cooldown
            print(f"    Sleeping {wait_time}s for T2W drain...")
            time.sleep(wait_time)

    stop_server(proc)
    return results


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--binary", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--mmproj", required=True)
    p.add_argument("--port", type=int, default=18080)
    p.add_argument("--n-requests", type=int, default=5)
    p.add_argument("--output-dir", default="/tmp/f6_c10_v3")
    args = p.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"C10 v3: One-server-per-config, omni_init once, {args.n_requests} decodes each")
    print(f"  Output: {args.output_dir}")

    off_results = run_single_config(args.binary, args.model, args.mmproj, args.port,
                                    "0", args.n_requests, f"{args.output_dir}/off", "OFF")
    time.sleep(5)

    on_results = run_single_config(args.binary, args.model, args.mmproj, args.port,
                                   "summary", args.n_requests, f"{args.output_dir}/on", "ON ")

    off_ok = [r["elapsed_s"] for r in off_results if r["success"]]
    on_ok = [r["elapsed_s"] for r in on_results if r["success"]]

    print(f"\n{'='*60}")
    print(f"C10 Results")
    print(f"{'='*60}")
    print(f"  OFF: n={len(off_ok)}, mean={mean(off_ok):.3f}s, p50={median(off_ok):.3f}s")
    print(f"  ON:  n={len(on_ok)}, mean={mean(on_ok):.3f}s, p50={median(on_ok):.3f}s")

    pairs = min(len(off_ok), len(on_ok))
    if pairs:
        deltas = [on_ok[i] - off_ok[i] for i in range(pairs)]
        print(f"  Pairs: {pairs}")
        print(f"  Delta p50: {median(deltas):.3f}s")
        print(f"  Delta mean: {mean(deltas):.3f}s")
        print(f"  Overhead: {100.0 * mean(deltas) / mean(off_ok[:pairs]):.2f}%")

        abs_delta = abs(mean(deltas))
        passed = abs_delta < 1.0
        print(f"\n  C10 Gate: {'PASS' if passed else 'FAIL'} (|mean delta|={abs_delta:.3f}s {'<' if passed else '>='} 1.0s)")


if __name__ == "__main__":
    main()
