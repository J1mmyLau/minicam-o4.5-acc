#!/usr/bin/env python3 -u
"""Phase 3A: F16 50-session reuse gate."""
import json, os, signal, socket, subprocess, sys, time, urllib.request, urllib.error, struct, glob

MODEL = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
BINARY = "./build/bin/llama-omni-server"
AUDIO = "tools/omni/assets/test_case/omni_test_case/omni_test_case_0006"
N = 50

def log(msg):
    sys.stderr.write(f"[p3a] {msg}\n")
    sys.stderr.flush()

def find_port(start=18210):
    for p in range(start, start+30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    raise RuntimeError("no port")

def req(url, data=None, timeout=120):
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

port = find_port(18210)
env = os.environ.copy()
env.update({"OMNI_T2W_DEVICE": "cann-flow-only", "OMNI_T2W_PIPELINE_OVERLAP": "1", "OMNI_T2W_QUEUE_DIAG": "1"})

log(f"Starting F16 server on {port}...")
server_log = open("/tmp/p3a_server.log", "wb")
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

log("Server ready. Running 50 sessions...")
t0_total = time.monotonic()
results = []
rss_samples = []

for i in range(N):
    t0 = time.monotonic()
    sid = i + 1

    r = req(f"http://127.0.0.1:{port}/v1/stream/omni_init", {"msg_type":1,"media_type":1,"use_tts":True}, timeout=60)
    if not r.get("ok"): results.append({"s":sid,"fail":"init"}); log(f"[{sid}] INIT FAIL"); continue

    r = req(f"http://127.0.0.1:{port}/v1/stream/prefill", {"audio_path_prefix":AUDIO,"cnt":1,"text":"你好"}, timeout=120)
    if not r.get("ok"): results.append({"s":sid,"fail":"prefill"}); log(f"[{sid}] PREFILL FAIL"); continue

    r = req(f"http://127.0.0.1:{port}/v1/stream/decode", {"debug_dir":"./","stream":False,"round_idx":0,"max_tokens":32,"wall_timeout_ms":120000}, timeout=180)
    if not r.get("ok"): results.append({"s":sid,"fail":"decode"}); log(f"[{sid}] DECODE FAIL"); continue

    body = json.dumps(r)
    if "active session" in body.lower():
        results.append({"s":sid,"fail":"rejection"}); log(f"[{sid}] REJECTED"); continue

    elapsed = (time.monotonic() - t0)*1000
    results.append({"s":sid,"ok":True,"tokens":r.get("generated_token_count",-1),"stop":r.get("stop_reason","?"),"ms":elapsed})
    eta = (time.monotonic() - t0_total) / sid * (N - sid)
    log(f'[{sid}/{N}] PASS {elapsed:.0f}ms tokens={r.get("generated_token_count","?")} stop={r.get("stop_reason","?")} ETA={eta:.0f}s')

    if sid % 10 == 0:
        try:
            with open(f"/proc/{proc.pid}/statm") as f:
                rss_samples.append({"session":sid,"rss_pages":int(f.read().split()[1])})
        except: pass

total = time.monotonic() - t0_total
log("Stopping server...")
proc.send_signal(signal.SIGTERM)
try: _, err_out = proc.communicate(timeout=30)
except: proc.kill(); _, err_out = proc.communicate(timeout=5)
stderr_text = err_out.decode("utf-8","replace") if err_out else ""
server_log.close()

successes = [r for r in results if r.get("ok")]
failures = [r for r in results if not r.get("ok")]
rejections = [r for r in results if r.get("fail") == "rejection"]
drain_to = stderr_text.count("DRAIN_TIMEOUT")

wavs = glob.glob("tools/omni/output/**/*.wav", recursive=True)
bad = 0
for w in wavs:
    with open(w,"rb") as f: d = f.read()
    if len(d)<44 or d[:4]!=b"RIFF": bad+=1; continue
    doff = d.find(b"data")
    if doff<0: bad+=1; continue
    dsize = int.from_bytes(d[40:44],"little")
    n_samp = min(dsize, len(d)-doff-4)//2
    if n_samp <= 0: bad+=1; continue
    pcm = struct.unpack("<" + "h" * n_samp, d[doff+4:doff+4+n_samp*2])
    if any(s!=s for s in pcm) or max(abs(s) for s in pcm)==0: bad+=1

rss_growth = "N/A"
if len(rss_samples) >= 2:
    first_rss = rss_samples[0]["rss_pages"] * 4 // 1024
    last_rss = rss_samples[-1]["rss_pages"] * 4 // 1024
    rss_growth = f"{first_rss}MB -> {last_rss}MB ({last_rss-first_rss:+d}MB)"

print("")
print("="*60)
print("Phase 3A: F16 50-SESSION REUSE GATE")
print("="*60)
print(f"Success: {len(successes)}/{N}")
print(f"Failed: {len(failures)}")
print(f"Rejections: {len(rejections)}")
print(f"DRAIN_TIMEOUTs: {drain_to}")
print(f"WAVs: {len(wavs)} total, {bad} bad")
print(f"RSS: {rss_growth}")
print(f"Total time: {total:.0f}s ({total/N:.1f}s/session)")
print(f"")

gates = [
    ("50/50 first-attempt", len(successes), N, len(successes) >= N),
    ("0 rejections", len(rejections), 0, len(rejections) == 0),
    ("0 drain timeouts", drain_to, 0, drain_to == 0),
    ("0 bad WAVs", bad, 0, bad == 0),
]
all_pass = True
for name, actual, target, passed in gates:
    s = "PASS" if passed else "FAIL"
    if not passed: all_pass = False
    print(f"  {s}: {name} ({actual}/{target})")

print(f"")
print(f'P3A_F16_50_REUSE = {"PASS" if all_pass else "FAIL"}')
sys.exit(0 if all_pass else 1)
