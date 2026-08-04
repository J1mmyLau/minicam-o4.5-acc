#!/usr/bin/env python3 -u
"""Reproduce persistent server sequential-request issue.

Test: 10 same-TTS requests on ONE server instance WITHOUT omni_init between.
Records: success/fail, response time, drain status.

Binary: build-f6-phase3-relwithdebinfo (libomni.so 9f25d2f7 @ c1d9418)
"""
import json, os, signal, socket, subprocess, sys, time, urllib.request, urllib.error

socket.setdefaulttimeout(600)

BINARY = "/workspace/llama.cpp-omni-f6/build-f6-phase3-relwithdebinfo/bin/llama-omni-server"
MODEL  = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf"
OUTDIR = "/tmp/f6_sequential_repro"
LOGDIR = f"{OUTDIR}/logs"
PORT   = 18081

os.makedirs(LOGDIR, exist_ok=True)


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


def kill_existing():
    subprocess.run(["pkill", "-f", f"llama-omni-server.*{PORT}"], capture_output=True)
    time.sleep(2)


def start_server():
    env = os.environ.copy()
    env["OMNI_E2E_PROFILE"] = "1"
    env["OMNI_E2E_PROFILE_DIR"] = f"{OUTDIR}/e2e"
    env["OMNI_KV_CACHE_PATH"] = f"{OUTDIR}/kv_cache"
    env["OMNI_T2W_DRAIN_TIMEOUT_MS"] = "30000"
    os.makedirs(env["OMNI_E2E_PROFILE_DIR"], exist_ok=True)
    os.makedirs(env["OMNI_KV_CACHE_PATH"], exist_ok=True)

    log_fh = open(f"{LOGDIR}/server.log", "w")
    proc = subprocess.Popen(
        [BINARY, "--port", str(PORT), "--model", MODEL,
         "--ctx-size", "2048", "--flash-attn", "off", "-ngl", "99", "--host", "0.0.0.0"],
        env=env, stdout=log_fh, stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )
    return proc


def wait_health(base_url, max_wait=120):
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            r = json.loads(urllib.request.urlopen(
                urllib.request.Request(f"{base_url}/health"), timeout=5
            ).read().decode("utf-8"))
            if r.get("status") == "ok":
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def main():
    kill_existing()
    base_url = f"http://127.0.0.1:{PORT}"

    print("=== Sequential Request Reproduction ===")
    print(f"Binary: {BINARY}")
    print(f"Port: {PORT}")

    proc = start_server()
    print(f"Server PID: {proc.pid}")

    if not wait_health(base_url):
        print("FATAL: Server not healthy")
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        sys.exit(1)
    print("[OK] Server healthy")

    # omni_init ONCE
    t0 = time.time()
    init_res = http_post(f"{base_url}/v1/stream/omni_init",
                         {"media_type": 2, "use_tts": True, "output_dir": f"{OUTDIR}/omni_out"})
    init_time = time.time() - t0
    if not init_res.get("success"):
        print(f"FATAL: omni_init failed: {init_res}")
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        sys.exit(1)
    print(f"[OK] omni_init ({init_time:.1f}s)")

    results = []
    for i in range(10):
        t0 = time.time()
        decode_res = http_post(f"{base_url}/v1/stream/decode",
                               {"debug_dir": f"{OUTDIR}/omni_out", "stream": False, "round_idx": i})
        elapsed = time.time() - t0
        ok = decode_res.get("success", False)
        err = decode_res.get("_error", "") if not ok else ""
        status = "OK" if ok else f"FAIL: {err}"
        print(f"  [{i+1:2d}/10] {elapsed:.1f}s {status}")

        results.append({"req": i, "elapsed_s": round(elapsed, 1), "success": ok, "error": err})

        if not ok:
            print(f"  WARNING: Request {i} failed at {elapsed:.1f}s")
            # Continue to see if server recovers

    # Check server still alive
    alive = (proc.poll() is None)
    print(f"\nServer alive after 10 requests: {alive}")

    # Check server log
    with open(f"{LOGDIR}/server.log") as f:
        log = f.read()
    timeouts = log.count("TIMEOUT") + log.count("DRAIN_TIMEOUT")
    cann_errs = log.count("CANN error") + log.count("NPU error")
    crashes = log.count("SIGSEGV") + log.count("SIGABRT")
    drains = log.count("T2W drain: complete")

    print(f"\nServer Log Summary:")
    print(f"  Drain timeouts: {timeouts}")
    print(f"  CANN/NPU errors: {cann_errs}")
    print(f"  Crashes: {crashes}")
    print(f"  Successful drains: {drains}")

    ok_count = sum(1 for r in results if r["success"])
    print(f"\nRequests completed: {ok_count}/10")
    if ok_count == 10:
        elapsed_times = [r["elapsed_s"] for r in results]
        print(f"  Time range: {min(elapsed_times):.0f}s - {max(elapsed_times):.0f}s")
        print(f"  Mean: {sum(elapsed_times)/len(elapsed_times):.0f}s")

    print(f"\nReproduction result: {'PASS' if ok_count >= 9 else 'ISSUE_REPRODUCED'}")

    # Cleanup
    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    proc.wait(timeout=10)
    return 0 if ok_count >= 9 else 1


if __name__ == "__main__":
    sys.exit(main())
