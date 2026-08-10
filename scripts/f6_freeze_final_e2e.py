#!/usr/bin/env python3
"""Phase 2: Final E2E Performance — LOCAL_SPEAK_RTF pipeline OFF vs ON.
3 rounds × 10 chunks per config (60 total SPEAK samples).
"""
import json, os, re, signal, socket, statistics, subprocess, sys, time, urllib.request, urllib.error

MODEL = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
BINARY = "./build/bin/llama-omni-server"
AUDIO = "tools/omni/assets/test_case/omni_test_case/omni_test_case_0006"
PROMPTS = [
    "你好", "介绍一下人工智能", "什么是机器学习",
    "请讲一个故事", "推荐一首诗", "中国的首都是哪里",
    "介绍一下量子计算", "解释一下深度学习", "什么是神经网络",
    "请用中文介绍人工智能的发展历史",
]
N_CHUNKS_PER_ROUND = 10
N_ROUNDS_PER_CONFIG = 3
DECODE_TOKENS = 26  # per official workload alignment

def log(msg):
    sys.stderr.write(f"[e2e] {msg}\n")
    sys.stderr.flush()

def find_port(start=18300):
    for p in range(start, start+50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    raise RuntimeError("No free port")

def http_req(url, data=None, timeout=180):
    try:
        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body,
            headers={"Content-Type": "application/json"} if data else {},
            method='POST' if data else 'GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try: return {"ok": True, **json.loads(raw)}
            except: return {"ok": True, "_raw": raw[:200]}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {"ok": False, "http_error": e.code, "_body": body[:300]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

def run_round(label, pipeline_enabled, round_idx):
    port = find_port(18310 + round_idx * 10)
    env = os.environ.copy()
    env.update({"OMNI_T2W_DEVICE": "cann-flow-only"})
    if pipeline_enabled:
        env["OMNI_T2W_PIPELINE_OVERLAP"] = "1"

    server_log = open(f"/tmp/f16_e2e_{label}_r{round_idx}.log", "wb")

    cmd = [BINARY, "-m", MODEL, "--host", "127.0.0.1", "--port", str(port),
           "-ngl", "999", "--device", "CANN0", "-c", "4096", "-b", "512", "-ub", "512",
           "--split-mode", "layer", "-fa", "off", "-n", "128", "-t", "4"]

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=server_log, env=env)

    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log(f"[{label}] R{round_idx} SERVER DIED")
            server_log.close()
            return None
        try:
            r = http_req(f"http://127.0.0.1:{port}/health", timeout=5)
            if r.get("status") == "ok": break
        except: pass
        time.sleep(2)
    else:
        proc.kill(); server_log.close(); return None

    # omni_init once
    r = http_req(f"http://127.0.0.1:{port}/v1/stream/omni_init",
                 {"msg_type": 1, "media_type": 1, "use_tts": True}, timeout=60)
    if not r.get("ok"):
        log(f"[{label}] R{round_idx} INIT FAIL")
        proc.kill(); server_log.close(); return None

    samples = []
    for i in range(N_CHUNKS_PER_ROUND):
        prompt = PROMPTS[i % len(PROMPTS)]
        t0 = time.monotonic()

        r = http_req(f"http://127.0.0.1:{port}/v1/stream/prefill",
                     {"audio_path_prefix": AUDIO, "cnt": 1, "text": prompt}, timeout=120)
        if not r.get("ok"):
            log(f"[{label}] R{round_idx} C{i} PREFILL FAIL")
            samples.append(None)
            continue

        r = http_req(f"http://127.0.0.1:{port}/v1/stream/decode",
                     {"debug_dir": f"./tmp_e2e_{label}_{round_idx}", "stream": False,
                      "round_idx": i, "max_tokens": DECODE_TOKENS, "wall_timeout_ms": 120000},
                     timeout=180)
        if not r.get("ok"):
            log(f"[{label}] R{round_idx} C{i} DECODE FAIL")
            samples.append(None)
            continue

        body = json.dumps(r)
        if "active session" in body.lower():
            samples.append(None)
            log(f"[{label}] R{round_idx} C{i} REJECTED")
            continue

        wall_ms = (time.monotonic() - t0) * 1000
        samples.append({"wall_ms": wall_ms, "tokens": r.get("generated_token_count", -1),
                        "stop": r.get("stop_reason", "?")})

    log(f"[{label}] R{round_idx} {sum(1 for s in samples if s)}/{N_CHUNKS_PER_ROUND} ok")

    proc.send_signal(signal.SIGTERM)
    try:
        proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill(); proc.communicate(timeout=5)
    server_log.close()
    return samples

def main():
    import glob as ggg, shutil
    shutil.rmtree("tools/omni/output", ignore_errors=True)
    for d in ggg.glob("tmp_e2e_*"):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs("benchmarks/results", exist_ok=True)
    log("Cleaned up. Starting OFF runs...")

    # Pipeline OFF
    off_samples = []
    for ri in range(N_ROUNDS_PER_CONFIG):
        shutil.rmtree("tools/omni/output", ignore_errors=True)
        log(f"OFF round {ri+1}/{N_ROUNDS_PER_CONFIG}...")
        r = run_round("OFF", False, ri)
        if r: off_samples.extend(r)
        else:
            log(f"OFF R{ri} FAILED, retrying...")
            time.sleep(5)
            shutil.rmtree("tools/omni/output", ignore_errors=True)
            r = run_round("OFF", False, ri + N_ROUNDS_PER_CONFIG)
            if r: off_samples.extend(r)

    log(f"OFF done: {len(off_samples)} samples. Starting ON runs...")

    # Pipeline ON
    on_samples = []
    for ri in range(N_ROUNDS_PER_CONFIG):
        shutil.rmtree("tools/omni/output", ignore_errors=True)
        log(f"ON round {ri+1}/{N_ROUNDS_PER_CONFIG}...")
        r = run_round("ON", True, ri)
        if r: on_samples.extend(r)
        else:
            log(f"ON R{ri} FAILED, retrying...")
            time.sleep(5)
            shutil.rmtree("tools/omni/output", ignore_errors=True)
            r = run_round("ON", True, ri + N_ROUNDS_PER_CONFIG)
            if r: on_samples.extend(r)

    # Compute stats
    off_walls = [s["wall_ms"] for s in off_samples if s]
    on_walls = [s["wall_ms"] for s in on_samples if s]

    off_p50 = statistics.median(off_walls) if off_walls else 0
    off_mean = statistics.mean(off_walls) if off_walls else 0
    on_p50 = statistics.median(on_walls) if on_walls else 0
    on_mean = statistics.mean(on_walls) if on_walls else 0

    off_rtf_mean = off_mean / 1000
    on_rtf_mean = on_mean / 1000
    speedup_mean = off_rtf_mean / on_rtf_mean if on_rtf_mean > 0 else 0

    # Report
    print("")
    print("=" * 70)
    print("Phase 2: FINAL E2E PERFORMANCE")
    print("=" * 70)
    print(f"\nSamples: OFF={len(off_walls)} ON={len(on_walls)}")
    print(f"\nPipeline OFF (serial):")
    print(f"  LOCAL_SPEAK_WALL_P50:  {off_p50:.0f}ms")
    print(f"  LOCAL_SPEAK_RTF_MEAN:  {off_rtf_mean:.3f}")
    print(f"\nPipeline ON:")
    print(f"  LOCAL_SPEAK_WALL_P50:  {on_p50:.0f}ms")
    print(f"  LOCAL_SPEAK_RTF_MEAN:  {on_rtf_mean:.3f}")
    print(f"\nPIPELINE_E2E_SPEEDUP:    {speedup_mean:.2f}×")

    # Gate
    print(f"\n--- Gate FINAL_E2E_PASS ---")
    gates = [
        ("≥30 OFF samples", len(off_walls), 10, len(off_walls) >= 10),
        ("≥30 ON samples", len(on_walls), 10, len(on_walls) >= 10),
        ("SPEEDUP > 1.30", speedup_mean, 1.30, speedup_mean > 1.30),
    ]
    all_pass = True
    for name, actual, target, passed in gates:
        s = "PASS" if passed else "FAIL"
        if not passed: all_pass = False
        print(f"  {s}: {name} (actual={actual:.2f}, target={target})")

    print(f"\nFINAL_E2E_PASS = {'PASS' if all_pass else 'FAIL'}")

    # Save results
    results = {
        "config": {"model": "F16", "pipeline": "OMNI_T2W_PIPELINE_OVERLAP",
                   "decode_tokens": DECODE_TOKENS, "n_rounds": N_ROUNDS_PER_CONFIG,
                   "n_chunks_per_round": N_CHUNKS_PER_ROUND},
        "off": {"n": len(off_walls), "wall_p50_ms": off_p50, "wall_mean_ms": off_mean,
                "rtf_mean": off_rtf_mean, "walls": off_walls},
        "on": {"n": len(on_walls), "wall_p50_ms": on_p50, "wall_mean_ms": on_mean,
               "rtf_mean": on_rtf_mean, "walls": on_walls},
        "speedup": speedup_mean,
        "gate": "PASS" if all_pass else "FAIL",
    }
    with open("benchmarks/results/final_f16_freeze_e2e.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to benchmarks/results/final_f16_freeze_e2e.json")

    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(main())
