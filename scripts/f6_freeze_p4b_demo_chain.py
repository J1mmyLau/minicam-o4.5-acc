#!/usr/bin/env python3 -u
"""Phase 4B: F16 Demo Full Chain — 10 turn-based interactions, text + audio validation."""
import json, os, signal, socket, subprocess, sys, time, urllib.request, urllib.error, struct, glob

MODEL = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
BINARY = "./build/bin/llama-omni-server"
AUDIO = "tools/omni/assets/test_case/omni_test_case/omni_test_case_0006"
PROMPTS = [
    "你好，请介绍一下你自己",
    "什么是人工智能？",
    "请讲一个简短的故事",
    "推荐一首中国古诗",
    "中国的首都是哪里？",
    "解释一下什么是机器学习",
    "今天天气怎么样？",
    "你会说几种语言？",
    "介绍一下深度学习",
    "谢谢你的帮助",
]
N = 10

def log(msg):
    sys.stderr.write(f"[4B] {msg}\n")
    sys.stderr.flush()

def find_port(start=18230):
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

def validate_text(text):
    """Check text is non-empty, valid UTF-8, contains meaningful content."""
    if not text or not text.strip():
        return False, "empty"
    if text.strip() in ("?", "？", ".", "。", "!", "！"):
        return False, f"punctuation_only: '{text}'"
    if all(c in "?？.。!！,， \t\n\r" for c in text):
        return False, f"no_content_chars: '{text[:50]}'"
    # Check for replacement characters (common encoding corruption)
    if '�' in text:
        return False, f"replacement_char at pos {text.index(chr(0xfffd))}"
    # Check most chars are printable
    printable = sum(1 for c in text if c.isprintable() or c in '\n\r\t')
    if printable / max(len(text), 1) < 0.5:
        return False, f"mostly_non_printable: {printable}/{len(text)}"
    return True, f"OK: {len(text)} chars"

# Cleanup
log("Cleaning...")
shutil = __import__('shutil')
shutil.rmtree("tools/omni/output", ignore_errors=True)

port = find_port(18230)
env = os.environ.copy()
env.update({"OMNI_T2W_DEVICE": "cann-flow-only", "OMNI_T2W_PIPELINE_OVERLAP": "1",
            "OMNI_T2W_QUEUE_DIAG": "1", "OMNI_T2W_DRAIN_TIMEOUT_MS": "5000"})

log(f"Starting F16 server on {port}...")
server_log = open("/tmp/p4b_server.log", "wb")
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

log("Server ready. Running 10 turn-based interactions...")

results = []
for i in range(N):
    t0 = time.monotonic()
    prompt = PROMPTS[i]
    log(f"[{i+1}/{N}] prompt='{prompt}'")

    # Init session
    r = req(f"http://127.0.0.1:{port}/v1/stream/omni_init",
            {"msg_type": 2, "media_type": 2, "use_tts": True}, timeout=60)
    if not r.get("ok"):
        results.append({"idx": i, "fail": "init", "detail": str(r)[:100]})
        log(f"  INIT FAIL"); continue

    # Prefill with text only (turn-based, no audio)
    r = req(f"http://127.0.0.1:{port}/v1/stream/prefill",
            {"audio_path_prefix": AUDIO, "cnt": 1, "text": prompt}, timeout=120)
    if not r.get("ok"):
        results.append({"idx": i, "fail": "prefill", "detail": str(r)[:100]})
        log(f"  PREFILL FAIL"); continue

    # Decode
    r = req(f"http://127.0.0.1:{port}/v1/stream/decode",
            {"debug_dir": f"./tmp_p4b_{i}", "stream": False,
             "round_idx": 0, "max_tokens": 64, "wall_timeout_ms": 180000},
            timeout=180)
    if not r.get("ok"):
        results.append({"idx": i, "fail": "decode", "detail": str(r)[:100]})
        log(f"  DECODE FAIL"); continue

    # Extract text from response
    text = r.get("text", r.get("content", ""))
    if not text:
        # Try nested fields
        for k in ("response", "output", "generated_text", "result"):
            if isinstance(r.get(k), str):
                text = r[k]
                break

    text_ok, text_msg = validate_text(text)
    tokens = r.get("generated_token_count", r.get("tokens", -1))
    stop = r.get("stop_reason", "?")
    wall_ms = (time.monotonic() - t0) * 1000

    result = {"idx": i, "ok": True, "text": text[:200], "text_ok": text_ok,
              "text_msg": text_msg, "tokens": tokens, "stop": stop, "wall_ms": wall_ms}
    results.append(result)

    status = "PASS" if text_ok else f"TEXT_FAIL({text_msg})"
    log(f"  {status} | {tokens}tok {stop} | {wall_ms:.0f}ms | '{text[:80]}'")

log("Done. Stopping server...")
proc.send_signal(signal.SIGTERM)
try: proc.communicate(timeout=30)
except: proc.kill(); proc.communicate(timeout=5)
server_log.close()

# Validate WAVs
wavs = glob.glob("tools/omni/output/**/*.wav", recursive=True)
bad_wavs = 0
for w in wavs:
    with open(w, "rb") as f: d = f.read()
    if len(d) < 44 or d[:4] != b"RIFF": bad_wavs += 1; continue
    doff = d.find(b"data")
    if doff < 0: bad_wavs += 1; continue
    dsize = int.from_bytes(d[40:44], "little")
    n_samp = min(dsize, len(d) - doff - 4) // 2
    if n_samp <= 0: bad_wavs += 1; continue
    pcm = struct.unpack("<" + "h" * n_samp, d[doff+4:doff+4+n_samp*2])
    if any(s != s for s in pcm) or max(abs(s) for s in pcm) == 0: bad_wavs += 1

# Summary
successes = [r for r in results if r.get("ok")]
text_pass = [r for r in successes if r.get("text_ok")]
text_fail = [r for r in successes if not r.get("text_ok")]
failures = [r for r in results if not r.get("ok")]

print("")
print("=" * 60)
print("Phase 4B: F16 DEMO FULL CHAIN GATE")
print("=" * 60)
print(f"Sessions: {len(successes)}/{N} ok, {len(failures)} failed")
print(f"Text valid: {len(text_pass)}/{len(successes)}")
print(f"Text failed: {len(text_fail)}")
print(f"WAVs: {len(wavs)} total, {bad_wavs} bad")
print(f"")

if text_fail:
    print("Text failures:")
    for r in text_fail:
        print(f"  [{r['idx']}] {r['text_msg']}: '{r['text'][:100]}'")

print(f"")
print("Text output samples:")
for r in successes[:5]:
    print(f"  [{r['idx']}] '{r['text'][:120]}'")

gates = [
    ("10/10 sessions", len(successes), N, len(successes) >= N),
    ("Text valid", len(text_pass), len(successes), len(text_pass) >= len(successes) * 0.8),
    ("0 bad WAVs", bad_wavs, 0, bad_wavs == 0),
]
all_pass = True
for name, actual, target, passed in gates:
    s = "PASS" if passed else "FAIL"
    if not passed: all_pass = False
    print(f"  {s}: {name} (actual={actual}, target={target})")

print(f"")
print(f'P4B_DEMO_FULL_CHAIN = {"PASS" if all_pass else "FAIL"}')
sys.exit(0 if all_pass else 1)
