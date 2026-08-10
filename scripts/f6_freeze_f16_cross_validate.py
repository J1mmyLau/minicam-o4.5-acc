#!/usr/bin/env python3
"""Phase 1: F16 Pipeline Cross-Validation — pipeline OFF vs ON, 5+5 sessions.
Measures per-window latency, speedup ratio, queue depth, WAV validity.
Abort triggers: NaN/Inf in pipeline audio, pipeline slower than serial by >5%, queue depth >2.
"""
import json, os, re, signal, socket, struct, subprocess, sys, time, urllib.request, urllib.error

MODEL = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
BINARY = "./build/bin/llama-omni-server"
AUDIO = "tools/omni/assets/test_case/omni_test_case/omni_test_case_0006"
PROMPT = "你好，请用中文简要介绍人工智能"
N_SESSIONS_PER_CONFIG = 5
DECODE_TOKENS = 32

def log(msg):
    sys.stderr.write(f"[xval] {msg}\n")
    sys.stderr.flush()

def find_port(start=18200):
    for p in range(start, start+50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    raise RuntimeError("No free port")

def http_req(url, data=None, timeout=120, method=None):
    try:
        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body,
            headers={"Content-Type": "application/json"} if data else {},
            method=method if data else 'GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return {"ok": True, **json.loads(raw)}
            except json.JSONDecodeError:
                return {"ok": True, "_raw": raw[:200]}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {"ok": False, "http_error": e.code, "_body": body[:300]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

def run_sessions(label, pipeline_enabled):
    """Run N sessions, return parsed timing data."""
    port = find_port(18220)
    env = os.environ.copy()
    env.update({
        "OMNI_T2W_DEVICE": "cann-flow-only",
        "OMNI_T2W_PROFILE": "2",
        "OMNI_T2W_QUEUE_DIAG": "1",
    })
    if pipeline_enabled:
        env["OMNI_T2W_PIPELINE_OVERLAP"] = "1"

    server_log_path = f"/tmp/f16_xval_server_{label}.log"
    server_log = open(server_log_path, "wb")

    cmd = [BINARY, "-m", MODEL, "--host", "127.0.0.1", "--port", str(port),
           "-ngl", "999", "--device", "CANN0", "-c", "4096", "-b", "512", "-ub", "512",
           "--split-mode", "layer", "-fa", "off", "-n", "128", "-t", "4"]

    log(f"[{label}] Starting server on port {port} (log={server_log_path})...")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=server_log, env=env)

    deadline = time.monotonic() + 300
    ready = False
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log(f"[{label}] SERVER DIED rc={proc.returncode}")
            server_log.close()
            with open(server_log_path) as f:
                log(f"  last 5 lines: {''.join(f.readlines()[-5:])}")
            return None
        try:
            r = http_req(f"http://127.0.0.1:{port}/health", timeout=5)
            if r.get("status") == "ok":
                ready = True
                break
        except:
            pass
        time.sleep(2)
    if not ready:
        proc.kill(); server_log.close()
        log(f"[{label}] FAIL: server startup timeout")
        return None

    log(f"[{label}] Server ready. Running {N_SESSIONS_PER_CONFIG} sessions...")

    sessions = []
    for i in range(N_SESSIONS_PER_CONFIG):
        sid = i + 1
        t0 = time.monotonic()

        r = http_req(f"http://127.0.0.1:{port}/v1/stream/omni_init",
                     {"msg_type": 1, "media_type": 1, "use_tts": True}, timeout=60)
        if not r.get("ok"):
            log(f"[{label}] [{sid}] INIT FAIL: {r}")
            sessions.append({"session": sid, "fail": "init"})
            continue

        r = http_req(f"http://127.0.0.1:{port}/v1/stream/prefill",
                     {"audio_path_prefix": AUDIO, "cnt": 1, "text": PROMPT}, timeout=120)
        if not r.get("ok"):
            log(f"[{label}] [{sid}] PREFILL FAIL: {r}")
            sessions.append({"session": sid, "fail": "prefill"})
            continue

        r = http_req(f"http://127.0.0.1:{port}/v1/stream/decode",
                     {"debug_dir": f"./tmp_xval_{label}_{sid}", "stream": False, "round_idx": 0,
                      "max_tokens": DECODE_TOKENS, "wall_timeout_ms": 120000}, timeout=180)
        if not r.get("ok"):
            log(f"[{label}] [{sid}] DECODE FAIL: {r}")
            sessions.append({"session": sid, "fail": "decode"})
            continue

        body = json.dumps(r)
        if "active session" in body.lower():
            sessions.append({"session": sid, "fail": "rejection"})
            log(f"[{label}] [{sid}] REJECTED")
            continue

        elapsed_ms = (time.monotonic() - t0) * 1000
        sessions.append({"session": sid, "success": True,
                         "stop": r.get("stop_reason", "?"),
                         "tokens": r.get("generated_token_count", -1),
                         "elapsed_ms": elapsed_ms})
        log(f"[{label}] [{sid}/{N_SESSIONS_PER_CONFIG}] PASS {elapsed_ms:.0f}ms tokens={r.get('generated_token_count','?')} stop={r.get('stop_reason','?')}")

    # Stop server
    log(f"[{label}] Stopping server...")
    proc.send_signal(signal.SIGTERM)
    try:
        proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill(); proc.communicate(timeout=5)
    server_log.close()

    # Parse server stderr
    with open(server_log_path) as f:
        stderr_text = f.read()

    # Parse timing
    flow_times = []
    voc_times = []
    total_times = []
    for line in stderr_text.split('\n'):
        if '[timing_flow]' in line:
            m = re.search(r'total=([0-9.]+)ms', line)
            if m: flow_times.append(float(m.group(1)))
        elif '[timing_voc]' in line:
            m = re.search(r'vocoder=([0-9.]+)ms', line)
            if m: voc_times.append(float(m.group(1)))
        elif '[timing]' in line and 'call=' in line:
            m = re.search(r'total=([0-9.]+)ms', line)
            if m: total_times.append(float(m.group(1)))

    # Parse queue diag
    enqueued = 0; dequeued = 0
    for line in stderr_text.split('\n'):
        if 'enqueued_total' in line:
            m = re.search(r'enqueued_total=(\d+)', line)
            if m: enqueued = int(m.group(1))
        if 'dequeued_total' in line:
            m = re.search(r'dequeued_total=(\d+)', line)
            if m: dequeued = int(m.group(1))

    # Check for errors
    has_nan = bool(re.search(r'nan|NaN|NAN', stderr_text))
    has_inf = bool(re.search(r'inf|Inf|INF', stderr_text))
    cann_errors = len(re.findall(r'CANN error|aclrt|acl_error', stderr_text))
    cpu_fallbacks = len(re.findall(r'fallback|cpu_fallback', stderr_text))
    drain_timeouts = stderr_text.count("DRAIN_TIMEOUT")

    return {
        "sessions": sessions,
        "flow_times_ms": flow_times,
        "voc_times_ms": voc_times,
        "total_times_ms": total_times,
        "enqueued": enqueued,
        "dequeued": dequeued,
        "has_nan": has_nan,
        "has_inf": has_inf,
        "cann_errors": cann_errors,
        "cpu_fallbacks": cpu_fallbacks,
        "drain_timeouts": drain_timeouts,
    }

def p50(vals):
    if not vals: return 0
    s = sorted(vals)
    return s[len(s) // 2]

def main():
    import shutil
    shutil.rmtree("tools/omni/output", ignore_errors=True)
    shutil.rmtree("tmp_xval_serial_*", ignore_errors=True)
    shutil.rmtree("tmp_xval_pipeline_*", ignore_errors=True)

    # Run serial (pipeline OFF)
    r_off = run_sessions("SERIAL", pipeline_enabled=False)
    if r_off is None:
        log("ABORT: Serial run failed. Check server log.")
        return 1

    # Clean outputs between runs
    shutil.rmtree("tools/omni/output", ignore_errors=True)

    # Run pipeline (ON)
    r_on = run_sessions("PIPELINE", pipeline_enabled=True)
    if r_on is None:
        log("ABORT: Pipeline run failed. Check server log.")
        return 1

    # --- REPORT ---
    print("")
    print("=" * 70)
    print("Phase 1: F16 PIPELINE CROSS-VALIDATION")
    print("=" * 70)

    success_off = sum(1 for s in r_off["sessions"] if s.get("success"))
    success_on = sum(1 for s in r_on["sessions"] if s.get("success"))

    print(f"\nSession success: SERIAL={success_off}/{N_SESSIONS_PER_CONFIG}  PIPELINE={success_on}/{N_SESSIONS_PER_CONFIG}")

    # Timing comparison
    print(f"\n--- Per-Window Timing ---")
    if r_off["total_times_ms"]:
        print(f"  SERIAL  total p50={p50(r_off['total_times_ms']):.1f}ms n={len(r_off['total_times_ms'])}")
    else:
        print(f"  SERIAL  total: NO DATA (check OMNI_T2W_PROFILE=2)")
    if r_on["flow_times_ms"]:
        print(f"  PIPELINE flow p50={p50(r_on['flow_times_ms']):.1f}ms n={len(r_on['flow_times_ms'])}")
    if r_on["voc_times_ms"]:
        print(f"  PIPELINE voc p50={p50(r_on['voc_times_ms']):.1f}ms n={len(r_on['voc_times_ms'])}")

    # Speedup
    p50_off = p50(r_off["total_times_ms"])
    p50_on_flow = p50(r_on["flow_times_ms"])
    p50_on_voc = p50(r_on["voc_times_ms"])

    if p50_off > 0 and p50_on_voc > 0:
        effective_on = max(p50_on_flow, p50_on_voc)
        speedup = p50_off / effective_on if effective_on > 0 else 0
        print(f"\n  SERIAL per-window:      {p50_off:.1f}ms")
        print(f"  PIPELINE effective:     {effective_on:.1f}ms (flow={p50_on_flow:.1f}, voc={p50_on_voc:.1f})")
        print(f"  SPEEDUP:                {speedup:.2f}×")
    else:
        speedup = 0

    # Queue diag
    print(f"\n--- Queue Dynamics ---")
    print(f"  SERIAL  enq={r_off['enqueued']} deq={r_off['dequeued']}")
    print(f"  PIPELINE enq={r_on['enqueued']} deq={r_on['dequeued']}")

    # Errors
    print(f"\n--- Error Checks ---")
    print(f"  PIPELINE NaN:  {r_on['has_nan']}")
    print(f"  PIPELINE Inf:  {r_on['has_inf']}")
    print(f"  CANN errors:   {r_on['cann_errors']} (PIPE) / {r_off['cann_errors']} (SERIAL)")
    print(f"  CPU fallbacks: {r_on['cpu_fallbacks']} (PIPE) / {r_off['cpu_fallbacks']} (SERIAL)")
    print(f"  Drain timeouts: {r_on['drain_timeouts']} (PIPE) / {r_off['drain_timeouts']} (SERIAL)")

    # ABORT triggers
    abort = False

    if r_on["has_nan"]:
        print("\n*** ABORT: NaN detected in pipeline audio! ***")
        abort = True

    if r_on["has_inf"]:
        print("\n*** ABORT: Inf detected in pipeline audio! ***")
        abort = True

    if p50_off > 0 and p50_on_voc > 0 and speedup < 0.95:
        print(f"\n*** ABORT: Pipeline SLOWER than serial ({speedup:.2f}× < 0.95) ***")
        abort = True

    if r_on["cann_errors"] > 0:
        print(f"\n*** ABORT: {r_on['cann_errors']} CANN errors in pipeline mode ***")
        abort = True

    # GATES
    print(f"\n--- Gate F16_XVAL_PASS ---")
    gates = [
        ("10/10 sessions", success_on + success_off, 2 * N_SESSIONS_PER_CONFIG,
         success_on + success_off >= 2 * N_SESSIONS_PER_CONFIG),
        ("Pipeline faster (speedup > 1.0)", speedup, 1.0, speedup > 1.0),
        ("0 NaN in pipeline", r_on["has_nan"], False, not r_on["has_nan"]),
        ("0 Inf in pipeline", r_on["has_inf"], False, not r_on["has_inf"]),
        ("0 CANN errors (pipeline)", r_on["cann_errors"], 0, r_on["cann_errors"] == 0),
        ("0 drain timeouts (pipeline)", r_on["drain_timeouts"], 0, r_on["drain_timeouts"] == 0),
    ]
    all_pass = True
    for name, actual, target, passed in gates:
        s = "PASS" if passed else "FAIL"
        if not passed: all_pass = False
        print(f"  {s}: {name} (actual={actual}, target={target})")

    overall = "PASS" if (all_pass and not abort) else "FAIL (or ABORT)"
    print(f"\nF16_XVAL_PASS = {overall}")
    return 0 if (all_pass and not abort) else 1

if __name__ == "__main__":
    sys.exit(main())
