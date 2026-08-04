#!/usr/bin/env python3 -u
"""MODE_A: Context reuse — with client-side events + stderr capture.

Captures both client events (CLIENT_REQUEST_SEND, CLIENT_RESPONSE_COMPLETE, etc.)
and server handler lifecycle events (F6_EVENT via stderr).

4 variants:
  V1: 2 strict serial requests (no overlap)
  V2: 10 strict serial requests (no overlap)
  V3: Request A still draining → submit Request B (overlap test)
  V4: 2 requests, wait for full response before next

Proper PID tracking. No pgrep/pkill.
"""
import json, os, signal, socket, subprocess, sys, time, urllib.request, urllib.error, threading

socket.setdefaulttimeout(600)

BINARY  = "/workspace/llama.cpp-omni-f6/build-f6-phase3-relwithdebinfo/bin/llama-omni-server"
MODEL   = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf"
PORT    = 18084

os.makedirs("/tmp/f6_mode_a", exist_ok=True)

RUNNER_PID_FILE = "/tmp/f6_mode_a/runner.pid"
SERVER_PID_FILE = "/tmp/f6_mode_a/server.pid"


def write_pid(path, pid):
    with open(path, "w") as f:
        f.write(str(pid))


def read_pid(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return None


def monotonic_ms():
    return int(time.monotonic() * 1000)


def f6_client_event(event_name, req_id, extra=""):
    """Emit client-side event in same format as server F6_EVENT."""
    ms = monotonic_ms()
    thread_hash = hash(threading.get_ident()) & 0xFFFF
    line = f"F6_CLIENT|{ms}|{event_name}|req={req_id}|tid=0x{thread_hash:04x}"
    if extra:
        line += f"|{extra}"
    print(line, flush=True)


def http_post_with_events(url, data, req_id, timeout=600):
    """HTTP POST with client-side event instrumentation."""
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})

    f6_client_event("CLIENT_REQUEST_SEND", req_id)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            f6_client_event("CLIENT_RESPONSE_HEADERS", req_id,
                            f"status={r.status}")
            body = r.read()
            f6_client_event("CLIENT_FIRST_BYTE", req_id,
                            f"bytes={len(body)}")
            result = json.loads(body.decode("utf-8"))
            f6_client_event("CLIENT_RESPONSE_COMPLETE", req_id,
                            f"success={result.get('success', False)}")
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        f6_client_event("CLIENT_RESPONSE_COMPLETE", req_id,
                        f"HTTP_{e.code}")
        return {"_error": f"HTTP {e.code}", "_body": body}
    except Exception as e:
        f6_client_event("CLIENT_RESPONSE_COMPLETE", req_id,
                        f"ERROR_{type(e).__name__}")
        return {"_error": str(e)}


def kill_server_clean():
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


def start_server(variant_name, stderr_fh):
    outdir = f"/tmp/f6_mode_a/{variant_name}"
    for d in [f"{outdir}/logs", f"{outdir}/e2e", f"{outdir}/kv_cache", f"{outdir}/omni_out"]:
        os.makedirs(d, exist_ok=True)

    env = os.environ.copy()
    env["OMNI_E2E_PROFILE"] = "1"
    env["OMNI_E2E_PROFILE_DIR"] = f"{outdir}/e2e"
    env["OMNI_KV_CACHE_PATH"] = f"{outdir}/kv_cache"
    env["OMNI_T2W_DRAIN_TIMEOUT_MS"] = "120000"  # 120s — default, enough for CPU T2W

    log_fh = open(f"{outdir}/logs/server.log", "w")
    proc = subprocess.Popen(
        [BINARY, "--port", str(PORT), "--model", MODEL,
         "--ctx-size", "2048", "--flash-attn", "off", "-ngl", "99", "--host", "0.0.0.0"],
        env=env, stdout=log_fh, stderr=stderr_fh,
        preexec_fn=os.setsid,
    )
    write_pid(SERVER_PID_FILE, proc.pid)
    return proc, outdir


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


def run_variant(variant_name, requests_spec, description=""):
    """Run a test variant.

    requests_spec is a list of dicts:
      {"action": "init"|"decode", "idx": int, "delay_before_s": float}

    For V3 (overlap), we fire decode for req B while req A is in drain,
    achieved by sending req B immediately after req A without waiting.
    """
    base_url = f"http://127.0.0.1:{PORT}"
    kill_server_clean()
    time.sleep(2)

    # Open stderr capture file for server F6 events
    stderr_path = f"/tmp/f6_mode_a/{variant_name}/f6_events.log"
    os.makedirs(f"/tmp/f6_mode_a/{variant_name}", exist_ok=True)
    stderr_fh = open(stderr_path, "w")

    print(f"\n{'='*60}")
    print(f"=== MODE_A VARIANT: {variant_name} ===")
    print(f"=== {description} ===")
    print(f"{'='*60}")
    print(f"Server stderr → {stderr_path}")
    f6_client_event("RUNNER_START", -1, f"variant={variant_name}")

    proc, outdir = start_server(variant_name, stderr_fh)
    print(f"Server PID: {proc.pid}")

    if not wait_health(base_url):
        print("FATAL: Server not healthy")
        kill_server_clean()
        stderr_fh.close()
        return {"variant": variant_name, "result": "SERVER_NOT_HEALTHY"}

    results = []
    init_done = False

    for step, spec in enumerate(requests_spec):
        action = spec["action"]
        idx = spec["idx"]
        delay = spec.get("delay_before_s", 0)

        if delay > 0:
            time.sleep(delay)

        server_alive_before = (proc.poll() is None)
        t0 = time.time()

        if action == "init":
            f6_client_event("CLIENT_NEXT_REQUEST_SEND", idx, "type=omni_init")
            res = http_post_with_events(f"{base_url}/v1/stream/omni_init",
                                        {"media_type": 2, "use_tts": True,
                                         "output_dir": f"{outdir}/omni_out"},
                                        idx)
            init_done = res.get("success", False)
        elif action == "decode":
            if not init_done:
                print(f"  SKIP decode {idx}: init not done")
                continue
            f6_client_event("CLIENT_NEXT_REQUEST_SEND", idx, "type=stream_decode")
            res = http_post_with_events(f"{base_url}/v1/stream/decode",
                                        {"debug_dir": f"{outdir}/omni_out",
                                         "stream": False, "round_idx": idx},
                                        idx)
        else:
            continue

        elapsed = time.time() - t0
        server_alive_after = (proc.poll() is None)
        ok = res.get("success", False)
        err = res.get("_error", "") if not ok else ""

        rec = {
            "request_index": idx, "action": action,
            "elapsed_s": round(elapsed, 1), "success": ok,
            "error": err,
            "server_alive_before": server_alive_before,
            "server_alive_after": server_alive_after,
        }
        results.append(rec)
        status = "OK" if ok else f"FAIL: {err}"
        print(f"  [{action}] req={idx} {elapsed:.1f}s {status} alive=[{server_alive_before}→{server_alive_after}]")

        if not server_alive_after:
            print(f"  FATAL: Server died after {action} idx={idx}")
            break

    alive_final = (proc.poll() is None)
    ok_count = sum(1 for r in results if r["success"])
    print(f"\n  Completed: {ok_count}/{len(results)}, Server alive: {alive_final}")

    kill_server_clean()
    proc.wait(timeout=10)
    stderr_fh.close()
    f6_client_event("RUNNER_END", -1, f"variant={variant_name}|ok={ok_count}")

    return {
        "variant": variant_name,
        "ok_count": ok_count,
        "total": len(results),
        "alive_final": alive_final,
        "stderr_path": stderr_path,
        "results": results,
    }


def main():
    write_pid(RUNNER_PID_FILE, os.getpid())

    all_results = {}

    # === V1: 10 rounds of 2 strict serial requests (A5 requirement: 10 rounds) ===
    spec_v1 = [{"action": "init", "idx": 0}]
    for i in range(1, 21):  # 20 decode requests = 10 pairs
        spec_v1.append({"action": "decode", "idx": i, "delay_before_s": 5})
    all_results["V1"] = run_variant("V1_2_requests", spec_v1,
                                    "10 rounds — 20 strict serial decode requests, 5s gap")

    # === V2-V4 SKIPPED for A5 V1-only validation ===
    # Will be re-enabled in A3 after V1 root cause confirmed.
    all_results["V2"] = {"variant": "V2", "ok_count": 0, "total": 0, "alive_final": True, "stderr_path": "",
                         "results": [], "note": "SKIPPED — focus on V1 10 rounds"}
    all_results["V3"] = {"variant": "V3", "ok_count": 0, "total": 0, "alive_final": True, "stderr_path": "",
                         "results": [], "note": "SKIPPED — focus on V1 10 rounds"}
    all_results["V4"] = {"variant": "V4", "ok_count": 0, "total": 0, "alive_final": True, "stderr_path": "",
                         "results": [], "note": "SKIPPED — focus on V1 10 rounds"}

    # Summary
    print(f"\n{'='*60}")
    print("=== SUMMARY ===")
    for name, r in all_results.items():
        print(f"  {name}: ok={r['ok_count']}/{r['total']} alive_final={r['alive_final']}")
    print(f"  Runner PID: {os.getpid()}")
    print(f"  All stderr logs under /tmp/f6_mode_a/*/f6_events.log")

    return 0


if __name__ == "__main__":
    sys.exit(main())
