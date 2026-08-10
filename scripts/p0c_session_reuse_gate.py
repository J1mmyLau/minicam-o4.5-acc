#!/usr/bin/env python3 -u
"""P0-C: Session reuse gate — unbuffered, diagnostic output to stderr."""
import json, os, signal, socket, subprocess, sys, time, urllib.request, urllib.error, glob, struct

MODEL = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf"
BINARY = "./build/bin/llama-omni-server"
AUDIO_PATH = "tools/omni/assets/test_case/omni_test_case/omni_test_case_0006"
N_SESSIONS = 50

PROMPTS = [
    "你好", "介绍一下人工智能", "什么是机器学习",
    "请讲一个故事", "推荐一首诗", "中国的首都是哪里",
    "介绍一下量子计算", "今天天气如何", "生命的意义是什么",
    "解释一下深度学习",
]

def log(msg):
    sys.stderr.write(f"[p0c] {msg}\n")
    sys.stderr.flush()

def find_port(start=18100):
    for p in range(start, start+50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    raise RuntimeError("No free port")

def http_req(url, data=None, timeout=120, method='POST'):
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

def main():
    import shutil
    shutil.rmtree("tools/omni/output", ignore_errors=True)

    port = find_port(18180)
    env = os.environ.copy()
    env.update({
        "OMNI_T2W_DEVICE": "cann-flow-only",
        "OMNI_T2W_PIPELINE_OVERLAP": "1",
        "OMNI_T2W_QUEUE_DIAG": "1",
    })

    cmd = [BINARY, "-m", MODEL, "--host", "127.0.0.1", "--port", str(port),
           "-ngl", "99", "-c", "4096", "-b", "512", "-ub", "512",
           "--split-mode", "layer", "-fa", "off", "-n", "128", "-t", "4"]

    log(f"Starting server on port {port}...")
    server_log = open("/tmp/p0c_server_stderr.log", "wb")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=server_log, env=env)

    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log(f"SERVER EXITED: rc={proc.returncode}")
            return 1
        r = http_req(f"http://127.0.0.1:{port}/health", timeout=5)
        if r.get("status") == "ok":
            break
        time.sleep(2)
    else:
        proc.kill()
        log("FAIL: server startup timeout")
        return 1

    log("Server ready. Running 50 sessions...")
    start_time = time.monotonic()
    results = []

    for i in range(N_SESSIONS):
        prompt = PROMPTS[i % len(PROMPTS)]
        sid = i + 1
        t_sess = time.monotonic()

        # omni_init
        r = http_req(f"http://127.0.0.1:{port}/v1/stream/omni_init",
                     {"msg_type": 1, "media_type": 1, "use_tts": True}, timeout=60)
        if not r.get("ok"):
            log(f"[{sid}/{N_SESSIONS}] INIT FAIL: {r}")
            results.append({"session": sid, "fail": "init", "detail": str(r)[:200]})
            continue

        # prefill
        r = http_req(f"http://127.0.0.1:{port}/v1/stream/prefill",
                     {"audio_path_prefix": AUDIO_PATH, "cnt": 1, "text": prompt}, timeout=120)
        if not r.get("ok"):
            log(f"[{sid}/{N_SESSIONS}] PREFILL FAIL: {r}")
            results.append({"session": sid, "fail": "prefill", "detail": str(r)[:200]})
            continue

        # decode — event-driven
        r = http_req(f"http://127.0.0.1:{port}/v1/stream/decode",
                     {"debug_dir": "./", "stream": False, "round_idx": 0,
                      "max_tokens": 32, "wall_timeout_ms": 120000}, timeout=180)
        if not r.get("ok"):
            log(f"[{sid}/{N_SESSIONS}] DECODE FAIL: {r}")
            results.append({"session": sid, "fail": "decode", "detail": str(r)[:200]})
            continue

        # Check for active-session rejection
        body = json.dumps(r)
        if "active session" in body.lower() or "busy" in body.lower():
            log(f"[{sid}/{N_SESSIONS}] REJECTED")
            results.append({"session": sid, "fail": "rejection"})
            continue

        elapsed = (time.monotonic() - t_sess) * 1000
        results.append({"session": sid, "success": True,
                        "stop": r.get("stop_reason", "?"),
                        "tokens": r.get("generated_token_count", -1),
                        "elapsed_ms": elapsed})
        log(f"[{sid}/{N_SESSIONS}] PASS | {elapsed:.0f}ms | tokens={r.get('generated_token_count','?')} | stop={r.get('stop_reason','?')}")

    total_elapsed = time.monotonic() - start_time

    # Stop server
    log("Stopping server...")
    proc.send_signal(signal.SIGTERM)
    try:
        _, err = proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        _, err = proc.communicate(timeout=5)
    stderr_lines = err.decode('utf-8', errors='replace') if err else ""

    # Analysis
    successes = [r for r in results if r.get("success")]
    failures = [r for r in results if not r.get("success")]
    rejections = [r for r in results if r.get("fail") == "rejection"]

    drain_timeouts = stderr_lines.count("DRAIN_TIMEOUT")
    dropped = stderr_lines.count("dropped")

    wavs = glob.glob("tools/omni/output/**/*.wav", recursive=True)
    bad_wavs = []
    for w in wavs:
        with open(w, 'rb') as f:
            data = f.read()
        if len(data) < 44:
            bad_wavs.append(w)
            continue
        doff = data.find(b'data')
        if doff < 0:
            bad_wavs.append(w)
            continue
        dsize = int.from_bytes(data[40:44], 'little')
        n_samp = min(dsize, len(data)-doff-4) // 2
        if n_samp <= 0:
            bad_wavs.append(w)
            continue
        pcm = struct.unpack('<' + 'h' * n_samp, data[doff+4:doff+4+n_samp*2])
        if any(s != s for s in pcm) or max(abs(s) for s in pcm) == 0:
            bad_wavs.append(w)

    print("")
    print("=" * 60)
    print("P0-C: 50-SESSION REUSE GATE")
    print("=" * 60)
    print(f"Total: {N_SESSIONS}")
    print(f"Success: {len(successes)}")
    print(f"Failed: {len(failures)}")
    print(f"Rejections: {len(rejections)}")
    print(f"DRAIN_TIMEOUTs: {drain_timeouts}")
    print(f"Dropped markers: {dropped}")
    print(f"WAVs: {len(wavs)} total, {len(bad_wavs)} bad")
    print(f"Time: {total_elapsed:.0f}s ({total_elapsed/N_SESSIONS:.1f}s/session)")
    print(f"")

    for f in failures[:5]:
        print(f"  FAIL[{f['session']}]: {f.get('fail')} — {f.get('detail','')[:120]}")

    print(f"")
    gates = [
        ("First-attempt success rate", len(successes), N_SESSIONS, len(successes) >= N_SESSIONS),
        ("Active-session rejections", len(rejections), 0, len(rejections) == 0),
        ("Drain timeouts", drain_timeouts, 0, drain_timeouts == 0),
        ("Dropped audio", dropped, 0, dropped == 0),
        ("Bad WAVs", len(bad_wavs), 0, len(bad_wavs) == 0),
    ]
    all_pass = True
    for name, actual, target, passed in gates:
        status = "PASS" if passed else "FAIL"
        if not passed: all_pass = False
        print(f"  {status}: {name} ({actual}/{target})")

    print(f"\nP0-C OVERALL: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(main())
