#!/usr/bin/env python3
"""S13 Phase 3 Baseline — 10-request pilot."""
import json, os, signal, socket, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path

socket.setdefaulttimeout(900)  # 15 min per request


def http_post(url, data, timeout=900):
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


def start_server(binary, model, mmproj, port, profile_dir, log_file):
    env = os.environ.copy()
    env["OMNI_E2E_PROFILE"] = "1"
    env["OMNI_E2E_PROFILE_DIR"] = profile_dir
    os.makedirs(profile_dir, exist_ok=True)
    cmd = [binary, "--port", str(port), "--model", model, "--mmproj", mmproj,
           "--ctx-size", "2048", "--flash-attn", "off", "-ngl", "99", "--host", "0.0.0.0"]
    log_fh = open(log_file, "w")
    return subprocess.Popen(cmd, env=env, stdout=log_fh, stderr=subprocess.STDOUT, preexec_fn=os.setsid)


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
            if json.loads(urllib.request.urlopen(
                urllib.request.Request(f"{base_url}/health"), timeout=5
            ).read().decode("utf-8")).get("status") == "ok":
                return True
        except Exception:
            pass
        time.sleep(5)
    return False


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--binary", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--mmproj", required=True)
    p.add_argument("--port", type=int, default=18080)
    p.add_argument("--n-requests", type=int, default=10)
    p.add_argument("--output-dir", default="/tmp/f6_s13_pilot")
    args = p.parse_args()

    out_dir = args.output_dir
    profile_dir = f"{out_dir}/e2e_profiles"
    os.makedirs(out_dir, exist_ok=True)
    base_url = f"http://127.0.0.1:{args.port}"

    print(f"S13 Pilot: {args.n_requests} requests, OMNI_E2E_PROFILE=1 (FULL)")
    print(f"  Output: {out_dir}")
    print(f"  Profiles: {profile_dir}")

    # Start server
    proc = start_server(args.binary, args.model, args.mmproj, args.port,
                        profile_dir, f"{out_dir}/server.log")
    print(f"  Server PID: {proc.pid}")

    if not wait_health(base_url):
        print("FATAL: Server not healthy")
        stop_server(proc)
        sys.exit(1)
    print("  [OK] Server healthy")

    # omni_init ONCE at the beginning (HTTP drain ensures sequential safety)
    init_res = http_post(f"{base_url}/v1/stream/omni_init",
                         {"media_type": 2, "use_tts": True, "output_dir": f"{out_dir}/omni_out"})
    if not init_res.get("success"):
        print(f"FATAL: omni_init failed: {init_res}")
        stop_server(proc)
        sys.exit(1)
    print("  [OK] omni_init")

    results = []
    for i in range(args.n_requests):
        # Re-init omni before each decode (required for request lifecycle)
        if i > 0:
            init_res = http_post(f"{base_url}/v1/stream/omni_init",
                                 {"media_type": 2, "use_tts": True, "output_dir": f"{out_dir}/omni_out"})
            if not init_res.get("success"):
                print(f"  WARNING: omni_init failed before req {i}: {init_res}")
        t0 = time.time()
        decode_res = http_post(f"{base_url}/v1/stream/decode",
                               {"debug_dir": f"{out_dir}/omni_out", "stream": False, "round_idx": i})
        elapsed = time.time() - t0
        ok = decode_res.get("success", False)
        err = decode_res.get("_error", "") if not ok else ""
        print(f"  [{i+1:3d}/{args.n_requests}] {elapsed:.1f}s {'OK' if ok else 'FAIL: '+err}")
        results.append({"index": i, "elapsed_s": round(elapsed, 3), "success": ok, "error": err})

        if not ok:
            print(f"    WARNING: Request {i} failed — continuing")

    stop_server(proc)
    time.sleep(3)

    # ── Verify profiles ──
    print(f"\n── Profile Verification ──")
    sync_profiles = sorted(Path(profile_dir).glob("e2e_*.json"))
    audio_profiles = sorted(Path(profile_dir).glob("e2e_*_audio.json"))
    sync_no_audio = [f for f in sync_profiles if "_audio" not in f.name]

    print(f"  Sync profiles:  {len(sync_no_audio)}")
    print(f"  Audio profiles: {len(audio_profiles)}")

    stale_count = 0
    cross_count = 0
    missing_flow = 0
    gen_mismatch = 0
    request_indices = []

    for sf in sync_no_audio:
        try:
            data = json.loads(sf.read_text())
            request_indices.append(data.get("request_index", -1))
            stale_count += data.get("stale_write_count", 0)
            cross_count += data.get("cross_request_write_count", 0)
            stages = data.get("stages_ms", {})
            if "flow_start" not in stages or stages["flow_start"] <= 0:
                missing_flow += 1
        except Exception:
            pass

    for af in audio_profiles:
        try:
            data = json.loads(af.read_text())
            idx = data.get("request_index", -1)
            gen = data.get("generation_id", 0)
            sync_match = [s for s in sync_no_audio
                          if s.name == f"e2e_{idx:04d}.json"]
            if sync_match:
                sync_data = json.loads(sync_match[0].read_text())
                if sync_data.get("generation_id", 0) != gen:
                    gen_mismatch += 1
        except Exception:
            pass

    # Check monotonic indices
    sorted_idx = sorted(set(request_indices))
    gaps = [sorted_idx[i] - sorted_idx[i-1] for i in range(1, len(sorted_idx)) if sorted_idx[i-1] >= 0]
    non_monotonic = sum(1 for g in gaps if g != 1)

    # Server log checks
    with open(f"{out_dir}/server.log") as f:
        server_log = f.read()
    timeout_count = server_log.count("TIMEOUT") + server_log.count("DRAIN_TIMEOUT")
    cann_errors = server_log.count("CANN error") + server_log.count("NPU error")
    crashes = server_log.count("SIGSEGV") + server_log.count("SIGABRT") + server_log.count("assertion failed")

    ok_requests = sum(1 for r in results if r["success"])
    elapsed_times = [r["elapsed_s"] for r in results if r["success"]]
    p50 = sorted(elapsed_times)[len(elapsed_times)//2] if elapsed_times else -1

    # ── Gate Check ──
    print(f"\n── S13 Pilot Gate Check ──")
    checks = [
        ("Requests completed", ok_requests, args.n_requests, "=="),
        ("Stale writes (total)", stale_count, 0, "=="),
        ("Cross-request writes", cross_count, 0, "=="),
        ("Missing flow_start", missing_flow, 0, "=="),
        ("Gen mismatches", gen_mismatch, 0, "=="),
        ("Non-monotonic indices", non_monotonic, 0, "=="),
        ("Drain timeouts", timeout_count, 0, "=="),
        ("CANN/NPU errors", cann_errors, 0, "=="),
        ("Server crashes", crashes, 0, "=="),
    ]

    all_pass = True
    for name, actual, expected, op in checks:
        if op == "==":
            passed = actual == expected
        elif op == ">=":
            passed = actual >= expected
        else:
            passed = False
        flag = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{flag}] {name}: {actual} (expected {op} {expected})")

    if elapsed_times:
        print(f"\n  Request timing: p50={p50:.1f}s, min={min(elapsed_times):.1f}s, max={max(elapsed_times):.1f}s")
        print(f"  Total test time: {sum(elapsed_times):.1f}s ({sum(elapsed_times)/60:.1f} min)")

    print(f"\n  S13 Pilot: {'PASS' if all_pass else 'FAIL'}")

    # Report
    report = {
        "test": "S13 10-request pilot",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "binary": args.binary,
        "n_requests": args.n_requests,
        "results": results,
        "verification": {c[0]: {"actual": c[1], "expected": c[2], "passed": c[1] == c[2]} for c in checks},
        "passed": all_pass,
    }
    rpath = f"{out_dir}/S13_PILOT_REPORT.json"
    with open(rpath, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Report: {rpath}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
