#!/usr/bin/env python3
"""Quick timing A/B: serial vs pipeline with OMNI_T2W_PROFILE=2.
Parses [timing] / [timing_flow] / [timing_voc] from stderr to compute per-window stats.
"""
import argparse, json, os, signal, socket, subprocess, sys, time, urllib.request

AUDIO_PATH = "tools/omni/assets/test_case/omni_test_case/omni_test_case_0006"
PROMPT = "你好，请用中文简要介绍人工智能"

def http_post(url, data, timeout=180):
    import urllib.request, urllib.error, json as j
    req = urllib.request.Request(url, data=j.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return j.loads(r.read().decode("utf-8"))

def http_get(url, timeout=10):
    import urllib.request, json as j
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return j.loads(r.read().decode("utf-8"))

def find_port(start=18100):
    for p in range(start, start+10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0: return p
    raise RuntimeError("no port")

def run_one(binary, model, port, env, label):
    cmd = [binary, "-m", model, "--host", "127.0.0.1", "--port", str(port),
           "-ngl", "99", "-c", "4096", "-b", "512", "-ub", "512",
           "--split-mode", "layer", "-fa", "off", "-n", "128", "-t", "4"]
    me = os.environ.copy()
    me.update(env)

    print(f"\n{'='*60}\n{label}\n{'='*60}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=me)

    deadline = time.monotonic() + 300
    ready = False
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate()
            print(f"FAIL: server exited early")
            return {"error": "server_exit", "stderr": err.decode('utf-8', errors='replace')[-5000:]}
        try:
            r = http_get(f"http://127.0.0.1:{port}/health")
            if r.get("status") == "ok":
                ready = True
                break
        except Exception:
            pass
        time.sleep(1)
    if not ready:
        proc.kill(); return {"error": "health_timeout"}

    # Run request
    t0 = time.monotonic()
    http_post(f"http://127.0.0.1:{port}/v1/stream/omni_init",
              {"msg_type": 1, "media_type": 1, "use_tts": True})
    http_post(f"http://127.0.0.1:{port}/v1/stream/prefill",
              {"audio_path_prefix": AUDIO_PATH, "cnt": 1, "text": PROMPT})
    result = http_post(f"http://127.0.0.1:{port}/v1/stream/decode",
                       {"debug_dir": "./", "stream": False, "round_idx": 0,
                        "max_tokens": 64, "wall_timeout_ms": 180000})
    wall_ms = (time.monotonic() - t0) * 1000

    # Stop server
    proc.send_signal(signal.SIGTERM)
    try:
        out, err = proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill(); out, err = proc.communicate(timeout=5)
    stderr_text = err.decode('utf-8', errors='replace')

    # Parse timing
    timings = []
    for line in stderr_text.split('\n'):
        if '[timing]' in line and 'call=' in line:
            timings.append(line)
        elif '[timing_flow]' in line:
            timings.append(line)
        elif '[timing_voc]' in line:
            timings.append(line)

    # Extract values
    window_data = []
    for t in timings:
        parts = {}
        for part in t.split():
            if '=' in part:
                k, v = part.split('=', 1)
                try:
                    parts[k] = float(v.rstrip('ms'))
                except ValueError:
                    parts[k] = v
        window_data.append(parts)

    flow_times = [w.get('total', 0) for w in window_data if 'flow_match' in str(w)]
    voc_times = [w.get('vocoder', 0) for w in window_data if 'vocoder' in str(w)]
    all_times = [w.get('total', 0) for w in window_data if w.get('total', 0) > 0]

    return {
        "label": label, "success": result.get("success", False),
        "tokens": result.get("generated_token_count", -1),
        "wall_ms": wall_ms,
        "timing_count": len(timings),
        "flow_avg_ms": sum(flow_times)/len(flow_times) if flow_times else 0,
        "voc_avg_ms": sum(voc_times)/len(voc_times) if voc_times else 0,
        "total_avg_ms": sum(all_times)/len(all_times) if all_times else 0,
        "flow_n": len(flow_times), "voc_n": len(voc_times), "total_n": len(all_times),
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--binary", default="./build/bin/llama-omni-server")
    p.add_argument("--model", required=True)
    args = p.parse_args()

    # Clean old output
    import shutil
    if os.path.exists("tools/omni/output"):
        shutil.rmtree("tools/omni/output", ignore_errors=True)

    env_base = {"OMNI_T2W_DEVICE": "cann-flow-only", "OMNI_T2W_PROFILE": "2"}

    # Serial
    port_s = find_port(18100)
    env_s = dict(env_base)
    r_s = run_one(args.binary, args.model, port_s, env_s, "SERIAL (pipeline=OFF)")

    # Clean
    if os.path.exists("tools/omni/output"):
        shutil.rmtree("tools/omni/output", ignore_errors=True)

    # Pipeline
    port_p = find_port(port_s + 1)
    env_p = dict(env_base)
    env_p["OMNI_T2W_PIPELINE_OVERLAP"] = "1"
    r_p = run_one(args.binary, args.model, port_p, env_p, "PIPELINE (pipeline=ON)")

    # Summary
    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    for r in [r_s, r_p]:
        print(f"\n{r['label']}:")
        print(f"  success={r.get('success')} tokens={r.get('tokens')} wall={r.get('wall_ms',0):.0f}ms")
        print(f"  timing events: {r['timing_count']}")
        if r['total_n'] > 0:
            print(f"  combined avg: {r['total_avg_ms']:.1f}ms (n={r['total_n']})")
        if r['flow_n'] > 0:
            print(f"  flow avg:     {r['flow_avg_ms']:.1f}ms (n={r['flow_n']})")
        if r['voc_n'] > 0:
            print(f"  voc avg:      {r['voc_avg_ms']:.1f}ms (n={r['voc_n']})")

if __name__ == "__main__":
    sys.exit(main())
