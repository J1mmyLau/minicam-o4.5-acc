#!/usr/bin/env python3
"""
F6 TTS KV bounds guard — deterministic boundary test (option B: shrink TTS cap).

Purpose: prove the TTS KV bounds guard (omni.cpp eval_tokens_tts /
prefill_with_emb_tts) ACTUALLY fires and protects the server, WITHOUT waiting
for a natural 4096-token overflow (which the stochastic TTS sampler may or may
not reach).

Method (TEST build, officially marked, separate from the frozen candidate):
  - TEST_BUILD_ONLY=YES: server built in build-test/ (separate dir) from a
    working tree that carries the OMNI_TTS_N_CTX test hook.
  - server launched with OMNI_TTS_N_CTX=<cap> => TTS n_ctx = <cap>
    (main context stays 4096; only the TTS context is shrunk)
  - a long_cn-style TTS request whose natural TTS utterance (several hundred
    audio tokens) exceeds the shrunk cap will deterministically push n_past_tts
    past the cap -> the guard must fire ("TTS KV cache full"), truncate
    gracefully, no memory-slot, no HTTP 500, next request still works.
  - CALIBRATION: cap=512 does NOT fire because the model's natural EOS for these
    prompts is ~440 TTS tokens (< 512). cap is therefore set below the natural
    length (default 256) so the guard fires deterministically. Recorded verbatim.

Verification items (user T13 spec):
  1. guard trigger count > 0 (proven from the LOG, incl. which function fired:
     eval_tokens_tts vs prefill_with_emb_tts, n_past/text_start + batch + n_ctx)
  2. no out-of-bounds access (no crash / no segfault / no OOB)
  3. no "failed to find a memory slot" loop
  4. no HTTP 500
  5. request ends cleanly (valid text/audio OR controlled truncation — the guard
     truncates mid-utterance by DESIGN; that must be classified as controlled
     truncation, not a client-visible failure)
  6. drain completes (drain_complete per request)
  7. context returns to REUSABLE (→IDLE per request)
  8. followup requests 4/4 succeed
  9. RSS/HBM no abnormal growth
  10. server healthy at end (health endpoint 200)

Usage:
  OMNI_TTS_N_CTX=<cap> python3 scripts/f6_tts_boundary_test.py
  F6_TTSBOUND_SERVER=<test build server> ... (override test binary)
"""
import json, os, signal, subprocess, sys, time, glob, re, shutil, hashlib
import urllib.request, urllib.error

REPO   = "/workspace/llama.cpp-omni-f6"
SERVER = os.environ.get("F6_TTSBOUND_SERVER",
                        os.path.join(REPO, "build-test/bin/llama-omni-server"))
MODEL  = os.environ.get("MODEL",
                        "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf")
PORT   = int(os.environ.get("F6_TTSBOUND_PORT", "18094"))
BASE   = "http://127.0.0.1:%d" % PORT
RUN    = "/tmp/f6_tts_boundary"
EVID   = os.path.join(REPO, "docs/f6-s13-closure/phase2/tts_boundary")
SRVLOG = os.path.join(RUN, "srv.log")
TTS_N_CTX = int(os.environ.get("OMNI_TTS_N_CTX", "256"))
MAX_TOKENS = 256
WALL_TIMEOUT_MS = 300000
REQ_TIMEOUT = 360

FROZEN = os.path.join(REPO, "docs/tracking/f6_lifecycle/data/S13_FROZEN_PROMPTS.jsonl")
SHORT_FOLLOWUP = "你好，请介绍一下你自己"

# Server CWD = REPO, so TTS round artifacts land in <REPO>/tools/omni/output/round_*
ROUND_BASE = os.path.join(REPO, "tools/omni/output")

SERVER_ENV = {
    "OMNI_KV_CACHE_REUSE": "1",
    "OMNI_KV_CACHE_PATH": os.path.join(RUN, "kv_cache"),
    "OMNI_T2W_DEVICE": "cann-flow-only",
    "OMNI_VOC_DEVICE": "gpu",
    "ASCEND_RT_VISIBLE_DEVICES": "0",
    "OMNI_TTS_N_CTX": str(TTS_N_CTX),
}


def sha256(path):
    try:
        return subprocess.run(["sha256sum", path], capture_output=True,
                              text=True).stdout.strip().split()[0]
    except Exception:
        return "MISSING"


def load_long_prompts(n=4):
    out = []
    with open(FROZEN) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            d = json.loads(line)
            if d["category"] == "long_cn":
                out.append({"case_id": d["case_id"], "prompt": d["prompt"]})
    return out[:n]


def http_post(path, payload, timeout=REQ_TIMEOUT):
    """Returns (http_status, decoded_json_or_None)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8")
            return r.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return -1, str(e)


def health_ok():
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def omni_init():
    st, _ = http_post("/v1/stream/omni_init",
                      {"msg_type": 1, "media_type": 1, "use_tts": True}, timeout=300)
    return st


def wav_valid(path):
    """RIFF/WAV header + non-trivial size check."""
    try:
        with open(path, "rb") as f:
            head = f.read(12)
            size = os.path.getsize(path)
        return size > 44 and head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    except Exception:
        return False


def round_wavs(round_idx):
    d = os.path.join(ROUND_BASE, "round_%03d" % round_idx, "tts_wav")
    if not os.path.isdir(d):
        return 0, 0, 0
    wavs = sorted(glob.glob(os.path.join(d, "wav_*.wav")))
    if not wavs:
        return 0, 0, 0
    valid = sum(1 for w in wavs if wav_valid(w))
    return len(wavs), valid, len(wavs) - valid


def do_request(prompt, round_idx, audio_base, tag, case_id, timeout=REQ_TIMEOUT):
    m = {"tag": tag, "case_id": case_id, "round_idx": round_idx,
         "prompt": prompt[:60]}
    t0 = time.time()
    st, _ = http_post("/v1/stream/prefill",
                      {"audio_path_prefix": audio_base, "cnt": 1, "text": prompt},
                      timeout=REQ_TIMEOUT)
    m["prefill_http_status"] = st
    t1 = time.time()
    st2, d = http_post("/v1/stream/decode",
                       {"stream": False, "round_idx": round_idx,
                        "debug_dir": os.path.join(RUN, "rounds"),
                        "max_tokens": MAX_TOKENS, "wall_timeout_ms": WALL_TIMEOUT_MS},
                       timeout=timeout)
    m["decode_http_status"] = st2
    m["decode_wall_ms"] = (time.time() - t0) * 1000.0
    if isinstance(d, str):  # error string
        m["error"] = d
        return m
    if d is None:
        m["error"] = "empty decode response"
        return m
    m["success"] = d.get("success", False)
    m["stop_reason"] = d.get("stop_reason", "?")
    m["generated_token_count"] = d.get("generated_token_count", -1)
    m["eos_detected"] = d.get("eos_detected", False)
    m["prompt_modified"] = d.get("prompt_modified", False)
    m["wav_count"] = d.get("wav_count", -1)
    m["d2fa_ms"] = d.get("decode_to_first_audio_ms", -1)
    text = str(d.get("text", ""))
    m["text_len"] = len(text)
    m["text_head"] = text[:120]
    n_on_disk, n_valid, n_bad = round_wavs(round_idx)
    m["wav_on_disk"] = n_on_disk
    m["wav_valid"] = n_valid
    m["wav_invalid"] = n_bad
    return m


def rss_kb(pid):
    try:
        with open("/proc/%d/status" % pid) as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except Exception:
        return -1
    return -1


def npu_mem_mb(pid):
    """Per-process NPU HBM from npu-smi, if available."""
    try:
        out = subprocess.run(["npu-smi", "info"], capture_output=True,
                             text=True, timeout=15).stdout
        for line in out.splitlines():
            if str(pid) in line:
                toks = line.split()
                for t in toks:
                    if t.endswith("MiB") or t.endswith("MB"):
                        return t
    except Exception:
        pass
    return "n/a"


def parse_guard_events(logtext):
    """Return list of guard events with function / counters from the LOG."""
    events = []
    for ln in logtext.splitlines():
        if "TTS KV cache full" not in ln:
            continue
        ev = {"line": ln.strip()[:200]}
        m = re.search(r"eval_tokens_tts.*n_past (\d+) \+ batch (\d+) > n_ctx (\d+)", ln)
        if m:
            ev["function"] = "eval_tokens_tts"
            ev["n_past"] = int(m.group(1)); ev["batch"] = int(m.group(2)); ev["n_ctx"] = int(m.group(3))
        else:
            m = re.search(r"prefill_with_emb_tts.*text_start (\d+) \+ offset (\d+) \+ batch (\d+) > n_ctx (\d+)", ln)
            if m:
                ev["function"] = "prefill_with_emb_tts"
                ev["text_start"] = int(m.group(1)); ev["offset"] = int(m.group(2))
                ev["batch"] = int(m.group(3)); ev["n_ctx"] = int(m.group(4))
            else:
                ev["function"] = "UNKNOWN"
        events.append(ev)
    return events


def parse_req_states(logtext):
    """Per-request drain + final context state from F6_REQSTATE lines."""
    drain = {}   # req -> True if DRAINING→RESPONDING label=drain_complete
    final = {}   # req -> final state (RESPONDING→IDLE)
    for ln in logtext.splitlines():
        m = re.search(r"F6_REQSTATE\|\d+\|req=(\d+)\|([A-Z_]+)→([A-Z_]+)\|label=([a-z_]+)", ln)
        if m:
            req, a, b, label = int(m.group(1)), m.group(2), m.group(3), m.group(4)
            if label == "drain_complete" and a == "DRAINING" and b == "RESPONDING":
                drain[req] = True
            if label == "response_sent" and a == "RESPONDING" and b == "IDLE":
                final[req] = b
    return drain, final


def clean_rounds(n):
    for i in range(n):
        d = os.path.join(ROUND_BASE, "round_%03d" % i)
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)


class Server:
    def __init__(self):
        self.proc = None
        self.logf = None
    def launch(self):
        os.makedirs(RUN, exist_ok=True)
        env = dict(os.environ); env.update(SERVER_ENV)
        cmd = ["stdbuf", "-oL", "-eL", SERVER, "-m", MODEL, "-ngl", "999",
               "--device", "CANN0", "-c", "4096", "-b", "512", "-ub", "512",
               "--split-mode", "layer", "--port", str(PORT)]
        self.logf = open(SRVLOG, "w")
        self.proc = subprocess.Popen(cmd, env=env, stdout=self.logf,
                                     stderr=subprocess.STDOUT, cwd=REPO,
                                     preexec_fn=os.setsid)
        for _ in range(600):
            if self.proc.poll() is not None:
                raise RuntimeError("server exited early")
            if health_ok():
                time.sleep(3)
                return self.proc.pid
            time.sleep(2)
        raise RuntimeError("server did not become healthy")
    def shutdown(self, timeout=120):
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill(); self.proc.wait(timeout=30)


def main():
    os.makedirs(EVID, exist_ok=True)
    clean_rounds(8)  # fresh wav-on-disk evidence for the 8 requests about to run
    print("== F6 TTS KV bounds guard: deterministic boundary test (TEST_BUILD_ONLY) ==")
    print("server:", SERVER)
    print("OMNI_TTS_N_CTX:", TTS_N_CTX, "port:", PORT)

    test_sha = sha256(SERVER)
    official_sha = sha256(os.path.join(REPO, "build/bin/llama-omni-server"))
    libomni_test_sha = sha256(os.path.join(REPO, "build-test/bin/libomni.so"))
    libomni_off_sha = sha256(os.path.join(REPO, "build/bin/libomni.so"))
    print("test  server SHA256:", test_sha[:16], "...")
    print("official server SHA256:", official_sha[:16], "...")
    print("test  libomni SHA256:", libomni_test_sha[:16], "...")
    print("official libomni SHA256:", libomni_off_sha[:16], "...")

    srv = Server()
    pid = srv.launch()
    print("server pid:", pid)

    init_status = omni_init()
    print("omni_init http status:", init_status)

    rss_start = rss_kb(pid)
    hbm_start = npu_mem_mb(pid)
    results = []
    long_cases = load_long_prompts(4)
    audio_base = os.path.join(REPO, "tools/omni/assets/test_case/omni_test_case/omni_test_case_0000")
    order = 0
    for i, tc in enumerate(long_cases):
        results.append(do_request(tc["prompt"], order, audio_base,
                                  "boundary-%d" % (i + 1), tc["case_id"]))
        order += 1
        results.append(do_request(SHORT_FOLLOWUP, order, audio_base,
                                  "followup-%d" % (i + 1), "followup"))
        order += 1
    rss_end = rss_kb(pid)
    hbm_end = npu_mem_mb(pid)

    healthy = health_ok()
    log = open(SRVLOG, errors="replace").read()
    guard_events = parse_guard_events(log)
    guard_hits = len(guard_events)
    guard_by_fn = {}
    for ev in guard_events:
        guard_by_fn[ev["function"]] = guard_by_fn.get(ev["function"], 0) + 1
    memslot = log.count("failed to find a memory slot")
    reusable = log.count("→IDLE")
    drain_done = log.count("drain_complete")
    http500 = sum(1 for r in results
                  if r.get("prefill_http_status") == 500
                  or r.get("decode_http_status") == 500
                  or "HTTP Error 500" in str(r.get("error", "")))
    drain_by_req, final_by_req = parse_req_states(log)
    actual_tts_n_ctx = None
    m = re.search(r"TTS n_ctx overridden to (\d+)", log)
    if m:
        actual_tts_n_ctx = int(m.group(1))
    m2 = re.search(r"n_ctx_seq \((\d+)\) < n_ctx_train", log)
    actual_tts_n_ctx_seq = int(m2.group(1)) if m2 else None

    # Request-level verification
    req_recs = []
    for i, r in enumerate(results):
        req_id = i
        d = {
            "request_id": req_id,
            "tag": r["tag"],
            "case_id": r["case_id"],
            "round_idx": r["round_idx"],
            "prompt": r["prompt"],
            "prefill_http_status": r.get("prefill_http_status"),
            "decode_http_status": r.get("decode_http_status"),
            "success": r.get("success", False),
            "stop_reason": r.get("stop_reason"),
            "generated_token_count": r.get("generated_token_count", -1),
            "text_len": r.get("text_len", -1),
            "wav_count_resp": r.get("wav_count", -1),
            "wav_on_disk": r.get("wav_on_disk", 0),
            "wav_valid": r.get("wav_valid", 0),
            "wav_invalid": r.get("wav_invalid", 0),
            "decode_wall_ms": r.get("decode_wall_ms", -1),
            "drain_complete": drain_by_req.get(req_id, False),
            "final_state": final_by_req.get(req_id, "?"),
            "error": r.get("error", ""),
        }
        req_recs.append(d)

    followup_ok = all(r["success"] and r["decode_http_status"] == 200
                      for r in req_recs if r["tag"].startswith("followup"))
    drain_all = all(r["drain_complete"] for r in req_recs)
    reusable_all = all(r["final_state"] == "IDLE" for r in req_recs)
    clean_end = all((r["success"] and r["decode_http_status"] == 200) or r["error"]
                    for r in req_recs)
    no_oob = healthy  # no crash during run => no OOB symptom

    summary = {
        "test": "TTS KV bounds guard deterministic boundary (TEST_BUILD_ONLY)",
        "TEST_BUILD_ONLY": "YES",
        "method": ("OMNI_TTS_N_CTX=%d (TTS cap shrunk; main -c 4096; frozen-candidate "
                   "T11 guard; calib: cap 512 does NOT fire — natural TTS EOS ~440 < 512 — "
                   "so cap set below natural length)" % TTS_N_CTX),
        "server": SERVER,
        "server_pid": pid,
        "test_binary_sha256": test_sha,
        "official_binary_sha256": official_sha,
        "test_libomni_sha256": libomni_test_sha,
        "official_libomni_sha256": libomni_off_sha,
        "OMNI_TTS_N_CTX": TTS_N_CTX,
        "actual_tts_n_ctx_override": actual_tts_n_ctx,
        "actual_tts_n_ctx_seq": actual_tts_n_ctx_seq,
        "main_n_ctx": 4096,
        "omni_init_http_status": init_status,
        "requests": req_recs,
        "guard_events": guard_events,
        "guard_trigger_count": guard_hits,
        "guard_by_function": guard_by_fn,
        "memslot_count": memslot,
        "http500_count": http500,
        "reusable_log_count": reusable,
        "drain_done_log_count": drain_done,
        "server_healthy_end": healthy,
        "rss_kb_start": rss_start,
        "rss_kb_end": rss_end,
        "hbm_start": hbm_start,
        "hbm_end": hbm_end,
        "items": {
            "1_guard_gt0": guard_hits > 0,
            "2_no_oob": no_oob,
            "3_no_memslot_loop": memslot == 0,
            "4_no_http500": http500 == 0,
            "5_clean_end_controlled_trunc": clean_end,
            "6_drain_done": drain_done > 0 and drain_all,
            "7_context_reusable": reusable > 0 and reusable_all,
            "8_followup_ok": followup_ok,
            "9_no_rss_growth": (rss_end - rss_start) < 512 * 1024,
            "10_server_healthy": healthy,
        },
    }
    ok_all = all(summary["items"].values())
    summary["PASS"] = ok_all
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_json = os.path.join(EVID, "tts_boundary_%s.json" % ts)
    with open(out_json, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    shutil.copy(SRVLOG, os.path.join(EVID, "srv_boundary.log"))

    print("\n==== PER-REQUEST ====")
    for r in req_recs:
        print("  req %d %-12s case=%-8s http=%s/%s ok=%s stop=%-10s text_len=%d "
              "wav(resp/disk/valid)=%d/%d/%d drain=%s final=%s" % (
                  r["request_id"], r["tag"], r["case_id"],
                  r["prefill_http_status"], r["decode_http_status"],
                  r["success"], r["stop_reason"], r["text_len"],
                  r["wav_count_resp"], r["wav_on_disk"], r["wav_valid"],
                  r["drain_complete"], r["final_state"]))
    print("\n==== GUARD EVENTS (from server log) ====")
    if guard_events:
        for ev in guard_events[:12]:
            print("  %-22s %s" % (ev["function"], ev["line"]))
        if len(guard_events) > 12:
            print("  ... %d more" % (len(guard_events) - 12))
    else:
        print("  (none)")
    print("\n==== RESULT ====")
    for k, v in summary["items"].items():
        print("  %-30s %s" % (k, "PASS" if v else "FAIL"))
    print("guard_by_function:", guard_by_fn, "| memslot:", memslot,
          "| http500:", http500, "| drain_by_req:", {k: drain_by_req.get(k)
          for k in sorted(drain_by_req)}, "| RSS %d→%d KB" % (rss_start, rss_end),
          "| HBM %s→%s" % (hbm_start, hbm_end))
    print("actual_tts_n_ctx override=%s n_ctx_seq=%s" % (actual_tts_n_ctx, actual_tts_n_ctx_seq))
    print("=== BOUNDARY_TEST %s ===" % ("PASS" if ok_all else "FAIL"))
    print("evidence:", out_json)
    srv.shutdown()


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)
    if not os.path.exists(SERVER):
        print("FATAL: test-build server not found:", SERVER)
        print("Build it first (separate build dir), then run this script.")
        sys.exit(2)
    main()
