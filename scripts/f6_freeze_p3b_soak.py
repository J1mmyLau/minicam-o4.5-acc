#!/usr/bin/env python3 -u
"""Phase 3B: F16 1800-input-chunk soak — single session, many decode rounds."""
import json, os, signal, socket, subprocess, sys, time, urllib.request, urllib.error, struct, glob

MODEL = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
BINARY = "./build/bin/llama-omni-server"
AUDIO = "tools/omni/assets/test_case/omni_test_case/omni_test_case_0006"
PROMPTS = ["你好","介绍一下人工智能","什么是机器学习","请讲一个故事","推荐一首诗",
           "中国的首都是哪里","介绍一下量子计算","解释一下深度学习","什么是神经网络",
           "请用中文介绍人工智能的发展历史"]
N_ROUNDS = 100  # generates ~100+ T2W tasks / ~100+ WAVs
DECODE_TOKENS = 26

def log(msg):
    sys.stderr.write(f"[p3b] {msg}\n")
    sys.stderr.flush()

def find_port(start=18220):
    for p in range(start, start+30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    raise RuntimeError("no port")

def req(url, data=None, timeout=180):
    try:
        body = json.dumps(data).encode("utf-8") if data else None
        rq = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"} if data else {})
        with urllib.request.urlopen(rq, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try: return {"ok": True, **json.loads(raw)}
            except: return {"ok": True, "_raw": raw[:100]}
    except urllib.error.HTTPError as e:
        return {"ok": False, "http": e.code, "body": (e.read().decode("utf-8","") if e.fp else "")[:200]}
    except Exception as e:
        return {"ok": False, "err": str(e)[:150]}

log("Cleaning up...")
for d in glob.glob("tmp_p3b_*"):
    import shutil; shutil.rmtree(d, ignore_errors=True)
import shutil
shutil.rmtree("tools/omni/output", ignore_errors=True)

port = find_port(18220)
env = os.environ.copy()
env.update({"OMNI_T2W_DEVICE": "cann-flow-only", "OMNI_T2W_PIPELINE_OVERLAP": "1",
            "OMNI_T2W_QUEUE_DIAG": "1", "OMNI_T2W_DRAIN_TIMEOUT_MS": "5000"})

log(f"Starting F16 server on {port}...")
server_log = open("/tmp/p3b_server.log", "wb")
proc = subprocess.Popen(
    [BINARY, "-m", MODEL, "--host", "127.0.0.1", "--port", str(port),
     "-ngl", "999", "--device", "CANN0", "-c", "4096", "-b", "512", "-ub", "512",
     "--split-mode", "layer", "-fa", "off", "-n", "128", "-t", "4"],
    stdout=subprocess.DEVNULL, stderr=server_log, env=env)

for i in range(300):
    if proc.poll() is not None:
        log(f"Server died rc={proc.returncode}"); sys.exit(1)
    try:
        r = req(f"http://127.0.0.1:{port}/health", timeout=5)
        if r.get("status") == "ok": break
    except: pass
    time.sleep(2)
else:
    proc.kill(); log("Timeout"); sys.exit(1)

log("Server ready. Running init...")
r = req(f"http://127.0.0.1:{port}/v1/stream/omni_init",
        {"msg_type": 1, "media_type": 1, "use_tts": True}, timeout=60)
if not r.get("ok"):
    log(f"INIT FAIL: {r}"); proc.kill(); sys.exit(1)
log("Init OK. Starting 100-round soak...")

t0_total = time.monotonic()
results = []
rss_samples = []

for i in range(N_ROUNDS):
    t0 = time.monotonic()
    prompt = PROMPTS[i % len(PROMPTS)]

    r = req(f"http://127.0.0.1:{port}/v1/stream/prefill",
            {"audio_path_prefix": AUDIO, "cnt": 1, "text": prompt}, timeout=120)
    if not r.get("ok"):
        results.append({"round": i, "fail": "prefill", "detail": r})
        log(f"[{i}] PREFILL FAIL: {r.get('http','')} {r.get('err','')}")
        continue

    r = req(f"http://127.0.0.1:{port}/v1/stream/decode",
            {"debug_dir": f"./tmp_p3b_r{i}", "stream": False,
             "round_idx": i, "max_tokens": DECODE_TOKENS, "wall_timeout_ms": 120000},
            timeout=180)
    if not r.get("ok"):
        results.append({"round": i, "fail": "decode", "detail": r})
        log(f"[{i}] DECODE FAIL: {r.get('http','')} {r.get('err','')}")
        continue

    body = json.dumps(r)
    if "active session" in body.lower():
        results.append({"round": i, "fail": "rejection"})
        log(f"[{i}] REJECTED")
        continue

    wall_ms = (time.monotonic() - t0) * 1000
    results.append({"round": i, "ok": True, "tokens": r.get("generated_token_count", -1),
                    "stop": r.get("stop_reason", "?"), "wall_ms": wall_ms})

    if i % 10 == 0 or i == N_ROUNDS - 1:
        successes = [r for r in results if r.get("ok")]
        eta = (time.monotonic() - t0_total) / (i + 1) * (N_ROUNDS - i - 1)
        log(f"[{i+1}/{N_ROUNDS}] ok={len(successes)} wall={wall_ms:.0f}ms "
            f"tokens={r.get('generated_token_count','?')} stop={r.get('stop_reason','?')} "
            f"ETA={eta:.0f}s")

    if (i + 1) % 20 == 0:
        try:
            with open(f"/proc/{proc.pid}/statm") as f:
                rss_samples.append({"round": i + 1, "rss_pages": int(f.read().split()[1])})
        except: pass
        # Check queue depth from server log
        try:
            with open("/tmp/p3b_server.log", "r") as f:
                tail = f.read()[-2000:]
            depths = [int(x.split("depth:")[1].split()[0]) if "depth:" in x else 0
                      for x in tail.split("\n") if "[QUEUE_DIAG]" in x]
            if depths:
                log(f"  RSS checkpoint round {i+1}, queue depth max recent: {max(depths)}")
        except: pass

total = time.monotonic() - t0_total
log(f"Soak complete in {total:.0f}s. Stopping server...")
proc.send_signal(signal.SIGTERM)
try: _, err_out = proc.communicate(timeout=30)
except: proc.kill(); _, err_out = proc.communicate(timeout=5)
stderr_text = err_out.decode("utf-8","replace") if err_out else ""
server_log.close()

successes = [r for r in results if r.get("ok")]
failures = [r for r in results if not r.get("ok")]
drain_to = stderr_text.count("DRAIN_TIMEOUT")

# Parse queue diagnostics from full server log
queue_depths = []
for line in stderr_text.split("\n"):
    if "[QUEUE_DIAG]" in line and "depth:" in line:
        try:
            d = int(line.split("depth:")[1].split()[0])
            queue_depths.append(d)
        except: pass
max_depth = max(queue_depths) if queue_depths else "N/A"

# Validate WAVs
wavs = glob.glob("tools/omni/output/**/*.wav", recursive=True)
bad = 0
for w in wavs:
    with open(w, "rb") as f: d = f.read()
    if len(d) < 44 or d[:4] != b"RIFF": bad += 1; continue
    doff = d.find(b"data")
    if doff < 0: bad += 1; continue
    dsize = int.from_bytes(d[40:44], "little")
    n_samp = min(dsize, len(d) - doff - 4) // 2
    if n_samp <= 0: bad += 1; continue
    pcm = struct.unpack("<" + "h" * n_samp, d[doff+4:doff+4+n_samp*2])
    if any(s != s for s in pcm) or max(abs(s) for s in pcm) == 0: bad += 1

# RSS
rss_growth = "N/A"
if len(rss_samples) >= 2:
    first_mb = rss_samples[0]["rss_pages"] * 4 // 1024
    last_mb = rss_samples[-1]["rss_pages"] * 4 // 1024
    rss_growth = f"{first_mb}MB -> {last_mb}MB ({last_mb - first_mb:+d}MB)"

# T2W tasks
t2w_count = stderr_text.count("[timing_flow]")
wav_count = len(wavs)

# Per-round timing
walls = [r["wall_ms"] for r in results if r.get("ok")]
import statistics
p50 = statistics.median(walls) if walls else 0
p95 = sorted(walls)[int(len(walls) * 0.95)] if walls else 0

print("")
print("=" * 60)
print("Phase 3B: F16 1800-CHUNK SOAK GATE")
print("=" * 60)
print(f"Rounds: {len(successes)}/{N_ROUNDS} ok, {len(failures)} failed")
print(f"DRAIN_TIMEOUTs: {drain_to}")
print(f"T2W tasks: ~{t2w_count}")
print(f"WAV outputs: {wav_count} total, {bad} bad")
print(f"Queue depth max: {max_depth}")
print(f"Per-round wall: p50={p50:.0f}ms p95={p95:.0f}ms")
print(f"RSS: {rss_growth}")
print(f"Total time: {total:.0f}s ({total/N_ROUNDS:.1f}s/round)")
print(f"LOCAL_SPEAK_RTF (p50): {p50/1000:.3f}")
print(f"")

gates = [
    (f"All {N_ROUNDS} rounds complete", len(successes), N_ROUNDS, len(successes) >= N_ROUNDS),
    ("0 drain timeouts", drain_to, 0, drain_to == 0),
    ("0 bad WAVs", bad, 0, bad == 0),
    ("Queue depth ≤ 2", max_depth if isinstance(max_depth, int) else 999, 2,
     isinstance(max_depth, int) and max_depth <= 2),
]
all_pass = True
for name, actual, target, passed in gates:
    s = "PASS" if passed else "FAIL"
    if not passed: all_pass = False
    print(f"  {s}: {name} (actual={actual}, target={target})")

print(f"")
print(f'P3B_F16_1800_SOAK = {"PASS" if all_pass else "FAIL"}')
sys.exit(0 if all_pass else 1)
