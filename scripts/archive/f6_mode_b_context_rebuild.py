#!/usr/bin/env python3 -u
"""MODE_B: Persistent server context rebuild — omni_init between EACH request.

Tests: New omni_context for each request (omni_init → omni_free → omni_init).
Confirms whether omni_init/omni_free lifecycle conflicts with T2W worker.
Proper PID tracking, clean kill, no pgrep/pkill.
"""
import json, os, signal, socket, subprocess, sys, time, urllib.request, urllib.error

socket.setdefaulttimeout(600)

BINARY  = "/workspace/llama.cpp-omni-f6/build-f6-phase3-relwithdebinfo/bin/llama-omni-server"
MODEL   = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf"
OUTDIR  = "/tmp/f6_mode_b"
LOGDIR  = f"{OUTDIR}/logs"
PORT    = 18083
N_REQUESTS = 10

os.makedirs(LOGDIR, exist_ok=True)

RUNNER_PID_FILE = f"{OUTDIR}/runner.pid"
SERVER_PID_FILE = f"{OUTDIR}/server.pid"


def write_pid(path, pid):
    with open(path, "w") as f:
        f.write(str(pid))


def read_pid(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return None


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


def kill_server_clean():
    """SIGTERM → wait 30s → SIGKILL. Only uses PID file."""
    pid = read_pid(SERVER_PID_FILE)
    if pid is None:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(30):
        try:
            os.kill(pid, 0)
            time.sleep(1)
        except ProcessLookupError:
            return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


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
    write_pid(SERVER_PID_FILE, proc.pid)
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
    write_pid(RUNNER_PID_FILE, os.getpid())
    kill_server_clean()
    time.sleep(2)

    base_url = f"http://127.0.0.1:{PORT}"

    results_log = open(f"{OUTDIR}/results.jsonl", "w")

    t_start = time.time()
    print(f"=== MODE_B: Context Rebuild ({N_REQUESTS} requests, omni_init BEFORE each) ===")
    print(f"Binary: {BINARY}")
    print(f"Port: {PORT}")
    print(f"Start time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Runner PID: {os.getpid()}")

    proc = start_server()
    print(f"Server PID: {proc.pid}")

    if not wait_health(base_url):
        print("FATAL: Server not healthy")
        kill_server_clean()
        sys.exit(1)
    print("[OK] Server healthy")

    results = []
    for i in range(N_REQUESTS):
        server_alive_before = (proc.poll() is None)

        # MODE_B: omni_init BEFORE each request (rebuilds context)
        t_init = time.time()
        init_res = http_post(f"{base_url}/v1/stream/omni_init",
                             {"media_type": 2, "use_tts": True, "output_dir": f"{OUTDIR}/omni_out"})
        init_time = time.time() - t_init
        if not init_res.get("success"):
            print(f"  [{i+1:2d}/{N_REQUESTS}] omni_init FAILED ({init_time:.1f}s): {init_res}")
            rec = {
                "request_index": i,
                "request_id": f"r{i:03d}",
                "elapsed_s": round(init_time, 1),
                "success": False,
                "error": f"omni_init failed: {init_res.get('_error', 'unknown')}",
                "server_alive_before": server_alive_before,
                "server_alive_after": (proc.poll() is None),
            }
            results.append(rec)
            results_log.write(json.dumps(rec) + "\n")
            results_log.flush()
            break

        # decode
        t0 = time.time()
        decode_res = http_post(f"{base_url}/v1/stream/decode",
                               {"debug_dir": f"{OUTDIR}/omni_out", "stream": False, "round_idx": i})
        elapsed = time.time() - t0
        server_alive_after = (proc.poll() is None)
        ok = decode_res.get("success", False)
        err = decode_res.get("_error", "") if not ok else ""
        status = "OK" if ok else f"FAIL: {err}"

        rec = {
            "request_index": i,
            "request_id": f"r{i:03d}",
            "start_time": time.strftime("%H:%M:%S", time.localtime(t0)),
            "init_s": round(init_time, 1),
            "decode_s": round(elapsed, 1),
            "total_s": round(init_time + elapsed, 1),
            "success": ok,
            "error": err,
            "server_alive_before": server_alive_before,
            "server_alive_after": server_alive_after,
        }
        results.append(rec)
        results_log.write(json.dumps(rec) + "\n")
        results_log.flush()

        print(f"  [{i+1:2d}/{N_REQUESTS}] init={init_time:.1f}s decode={elapsed:.1f}s total={init_time+elapsed:.1f}s {status}")

        if not server_alive_after:
            print(f"  FATAL: Server died after request {i}")
            break

    total_elapsed = time.time() - t_start
    alive_final = (proc.poll() is None)
    print(f"\nTotal elapsed: {total_elapsed:.0f}s")
    print(f"Server alive at end: {alive_final}")

    ok_count = sum(1 for r in results if r["success"])
    print(f"Requests completed: {ok_count}/{len(results)}")

    # Check server log
    with open(f"{LOGDIR}/server.log") as f:
        server_log = f.read()
    timeouts = server_log.count("TIMEOUT") + server_log.count("DRAIN_TIMEOUT")
    cann_errs = server_log.count("CANN error") + server_log.count("NPU error")
    crashes = server_log.count("SIGSEGV") + server_log.count("SIGABRT")

    print(f"\nServer Log Summary:")
    print(f"  Drain timeouts: {timeouts}")
    print(f"  CANN/NPU errors: {cann_errs}")
    print(f"  Crashes: {crashes}")
    print(f"  omni_init calls in log: {server_log.count('omni_init start')}")
    print(f"  omni_free calls in log: {server_log.count('omni_free')}")

    kill_server_clean()
    proc.wait(timeout=10)
    results_log.close()

    print(f"\nResult: {'PASS' if ok_count == N_REQUESTS and crashes == 0 else 'ISSUE_REPRODUCED'}")
    return 0 if ok_count >= 9 else 1


if __name__ == "__main__":
    sys.exit(main())
