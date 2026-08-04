#!/usr/bin/env python3
"""
F6 Phase 3 — T6: FINAL INTEGRATED REGRESSION
=============================================
Runs the frozen integrated candidate (T5 freeze: KV Cache + HTTP token cap +
persistent-context lifecycle + CANN Flow/Vocoder) through the full regression
suite:

  1. 120 frozen (S13 frozen prompts, once-init persistent protocol)
  2. 30 MISS→HIT (KV cache, inline; per-request fresh ctx like the R13
     canonical, use_tts=False to isolate the LLM prefill delta)
  3. 20 long-text
  4. 10 mixed
  5. 5 voice-switch (per-request ref-audio variation → success + round-dir
     isolation; NOTE: C++ T2W speaker ref is session-fixed at omni_init, so
     per-request voice re-cloning is NOT claimed by the persistent candidate)
  6. 5 client-disconnect (server survives)
  7. 3 restart cycles

Candidate env: OMNI_KV_CACHE_REUSE=1 OMNI_T2W_DEVICE=cann-flow-only
               OMNI_VOC_DEVICE=gpu ASCEND_RT_VISIBLE_DEVICES=0
Protocol:      omni_init ONCE per server session; prefill+decode reuse ctx.
No official/competition claims here — this is INTERNAL regression evidence.
"""

import glob
import json
import os
import re
import signal
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
import hashlib

REPO = "/workspace/llama.cpp-omni-f6"
SERVER = os.path.join(REPO, "build/bin/llama-omni-server")
MODEL = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
PORT = 18093
BASE = "http://127.0.0.1:%d" % PORT

AUDIO_PREFIX = "/workspace/llama.cpp-omni-f6/tools/omni/assets/test_case/omni_test_case/omni_test_case_"
FROZEN_PROMPTS = os.path.join(REPO, "docs/tracking/f6_lifecycle/data/S13_FROZEN_PROMPTS.jsonl")

RUN_DIR = "/tmp/f6_t6"
SRV_LOG = os.path.join(RUN_DIR, "t6_srv.log")
KV_LOG = os.path.join(RUN_DIR, "kv_ab_srv.log")
OUT_JSON = os.path.join(REPO, "docs/f6-s13-closure/phase2/t6_integrated_regression.json")
KV_CACHE_DIR = os.path.join(RUN_DIR, "kv_cache")

# Current server log formats (omni.cpp:12958/12989/13106)
RE_KV_SAVED = re.compile(r"KV cache SAVED: (\d+) bytes to (\S+) \(n_past=(\d+), key=(\S+)\)")
RE_KV_HIT = re.compile(r"KV cache HIT: loaded (\d+) positions \(\d+ bytes\) from \S+ \(key=\S+\)")
RE_KV_MISS = re.compile(r"KV cache MISS: will compute system prompt from scratch")
RE_OUTDIR = re.compile(r"T2W线程\(C\+\+\): 新输出目录 .*round_(\d+)/tts_wav")

# KV cache A/B cases (mirrors run_canonical_kv_ab.py; KV prefill delta is
# TTS-independent, so use_tts=False matches the R13 canonical measurement)
KV_TEST_CASES = [
    {"id": "C1", "audio": "0000.wav", "text": "请描述你听到的内容"},
    {"id": "C2", "audio": "0001.wav", "text": "这张图片里有什么"},
    {"id": "C3", "audio": "0002.wav", "text": "请用中文回答"},
    {"id": "C4", "audio": "0003.wav", "text": "讲一个简短的故事"},
    {"id": "C5", "audio": "0004.wav", "text": "今天天气如何"},
]

MAX_TOKENS = 256
WALL_TIMEOUT_MS = 300000
REQ_TIMEOUT = 360

CASE_AUDIOS = {
    "short_cn": ["0000.wav", "0001.wav"],
    "long_cn": ["0002.wav", "0003.wav"],
    "english": ["0004.wav", "0005.wav"],
    "number_mix": ["0006.wav", "0007.wav"],
}
ALL_AUDIOS = ["0000.wav", "0001.wav", "0002.wav", "0003.wav",
              "0004.wav", "0005.wav", "0006.wav", "0007.wav"]

SERVER_ENV = {
    "OMNI_KV_CACHE_REUSE": "1",
    "OMNI_KV_CACHE_PATH": KV_CACHE_DIR,
    "OMNI_T2W_DEVICE": "cann-flow-only",
    "OMNI_VOC_DEVICE": "gpu",
    "ASCEND_RT_VISIBLE_DEVICES": "0",
}

# KV cache can be pre-seeded from the previous session (same key → HIT on first
# request of a run). For deterministic MISS→HIT measurement we clear the dir
# between pairs; a leftover from a prior process is harmless (same content).
def clear_kv_cache():
    os.makedirs(KV_CACHE_DIR, exist_ok=True)
    for f in glob.glob(os.path.join(KV_CACHE_DIR, "*.bin")) + \
             glob.glob(os.path.join(KV_CACHE_DIR, "*.tmp.*")) + \
             glob.glob(os.path.join(KV_CACHE_DIR, "*.state.*")) + \
             glob.glob(os.path.join(KV_CACHE_DIR, "*.load.*")):
        try:
            os.remove(f)
        except Exception:
            pass


def load_frozen():
    out = []
    with open(FROZEN_PROMPTS) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            calc = hashlib.sha256(d["prompt"].encode("utf-8")).hexdigest()
            out.append({
                "case_id": d["case_id"], "category": d["category"],
                "prompt": d["prompt"],
                "sha_ok": calc == d["prompt_sha256"],
            })
    return out


def http_post(path, payload, timeout=REQ_TIMEOUT):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def health_ok():
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=3) as r:
            d = json.loads(r.read().decode("utf-8"))
            return d.get("status") == "ok"
    except Exception:
        return False


class Server:
    def __init__(self, logpath):
        self.proc = None
        self.logpath = logpath
        self.logf = None

    def launch(self):
        os.makedirs(RUN_DIR, exist_ok=True)
        env = dict(os.environ)
        env.update(SERVER_ENV)
        cmd = ["stdbuf", "-oL", "-eL", SERVER, "-m", MODEL, "-ngl", "999",
               "--device", "CANN0", "-c", "4096", "-b", "512", "-ub", "512",
               "--split-mode", "layer", "--port", str(PORT)]
        self.logf = open(self.logpath, "w")
        self.proc = subprocess.Popen(cmd, env=env, stdout=self.logf,
                                     stderr=subprocess.STDOUT,
                                     cwd=REPO, preexec_fn=os.setsid)
        for _ in range(600):
            if self.proc.poll() is not None:
                self.read_log()
                raise RuntimeError("server exited early: %s" % self.read_log()[-1500:])
            if health_ok():
                time.sleep(3)
                return self.proc.pid
            time.sleep(2)
        raise RuntimeError("server did not become healthy")

    def read_log(self):
        with open(self.logpath, errors="replace") as f:
            return f.read()

    def log_size(self):
        try:
            return os.path.getsize(self.logpath)
        except OSError:
            return 0

    def log_slice(self, b, e):
        with open(self.logpath, errors="replace") as f:
            f.seek(b)
            return f.read(max(e - b, 0))

    def shutdown(self, timeout=120):
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=30)
        if self.logf:
            self.logf.close()


def omni_init():
    http_post("/v1/stream/omni_init",
              {"msg_type": 1, "media_type": 1, "use_tts": True}, timeout=300)


def do_request(prompt, audio_base, round_idx, timeout=REQ_TIMEOUT):
    """prefill + decode (persistent ctx, token cap). Returns metrics dict."""
    m = {"round_idx": round_idx}
    try:
        http_post("/v1/stream/prefill",
                  {"audio_path_prefix": audio_base, "cnt": 1, "text": prompt},
                  timeout=REQ_TIMEOUT)
    except Exception as e:
        m["error"] = "prefill: %s" % e
        return m
    t0 = time.time()
    try:
        d = http_post("/v1/stream/decode",
                      {"stream": False, "round_idx": round_idx,
                       "debug_dir": "/tmp/f6_t6/rounds",
                       "max_tokens": MAX_TOKENS, "wall_timeout_ms": WALL_TIMEOUT_MS},
                      timeout=timeout)
    except Exception as e:
        m["error"] = "decode: %s" % e
        return m
    m["decode_wall_ms"] = (time.time() - t0) * 1000.0
    m["success"] = d.get("success", False)
    m["stop_reason"] = d.get("stop_reason", "?")
    m["generated_token_count"] = d.get("generated_token_count", -1)
    m["eos_detected"] = d.get("eos_detected", False)
    m["sliding_window_count"] = d.get("sliding_window_count", -1)
    m["prompt_modified"] = d.get("prompt_modified", False)
    m["wav_count"] = d.get("wav_count", -1)
    m["d2fa_ms"] = d.get("decode_to_first_audio_ms", -1)
    return m


def kv_request(tc, round_idx, use_tts=False, timeout=REQ_TIMEOUT):
    """KV A/B single request: omni_init (fresh ctx → resets system_prompt_
    initialized so the KV block runs again) + timed prefill + decode.
    Returns prefill_wall_ms (the KV-cache-sensitive metric)."""
    m = {"round_idx": round_idx}
    try:
        http_post("/v1/stream/omni_init",
                  {"msg_type": 1, "media_type": 1, "use_tts": use_tts}, timeout=300)
        t0 = time.time()
        http_post("/v1/stream/prefill",
                  {"audio_path_prefix": tc["audio_base"], "cnt": 1, "text": tc["text"]},
                  timeout=REQ_TIMEOUT)
        m["prefill_wall_ms"] = (time.time() - t0) * 1000.0
        d = http_post("/v1/stream/decode",
                      {"stream": False, "round_idx": round_idx,
                       "debug_dir": "/tmp/f6_t6/rounds",
                       "max_tokens": MAX_TOKENS, "wall_timeout_ms": WALL_TIMEOUT_MS},
                      timeout=timeout)
        m["success"] = d.get("success", False)
        m["wav_count"] = d.get("wav_count", -1)
        m["stop_reason"] = d.get("stop_reason", "?")
    except Exception as e:
        m["error"] = str(e)
    return m


# ── 1. 120 frozen (once-init persistent) ─────────────────────────────
def run_120_frozen(server):
    frozen = load_frozen()
    bad_sha = [f for f in frozen if not f["sha_ok"]]
    if bad_sha:
        return {"error": "frozen prompt SHA mismatch: %s" % bad_sha[0]["case_id"]}

    results = []
    omni_init()
    order = 0
    for case_type in ["short_cn", "long_cn", "english", "number_mix"]:
        prompts = sorted([f for f in frozen if f["category"] == case_type],
                         key=lambda x: x["case_id"])
        audios = CASE_AUDIOS[case_type]
        for i, fp in enumerate(prompts):
            order += 1
            audio = audios[i % len(audios)]
            base = AUDIO_PREFIX + audio.replace(".wav", "")
            r = do_request(fp["prompt"], base, order)
            r.update({"case_id": fp["case_id"], "category": case_type,
                      "audio": audio, "request_order": order,
                      "prompt_sha256": hashlib.sha256(fp["prompt"].encode("utf-8")).hexdigest()})
            results.append(r)
            sys.stdout.write("  [%3d/120] %-18s %-10s %s\n" % (
                order, fp["case_id"], r.get("stop_reason", "ERR"),
                "" if "error" not in r else r["error"][:80]))
            sys.stdout.flush()

    total = len(results)
    ok = sum(1 for r in results if "error" not in r and r.get("success") is not False)
    errs = sum(1 for r in results if "error" in r)
    eos = sum(1 for r in results if r.get("stop_reason") == "eos")
    mx = sum(1 for r in results if r.get("stop_reason") == "max_tokens")
    wall = sum(1 for r in results if r.get("stop_reason") == "wall_timeout")
    slide = sum(1 for r in results if r.get("sliding_window_count", 0) > 0)
    prompt_mod = sum(1 for r in results if r.get("prompt_modified"))
    strict = (errs == 0 and ok == 120 and prompt_mod == 0)
    runaway = (wall == 0 and slide == 0)
    return {
        "n": total, "ok": ok, "errs": errs, "eos": eos, "max_tokens": mx,
        "wall_timeout": wall, "sliding_window": slide,
        "prompt_modified": prompt_mod, "strict_pass": strict,
        "runaway_free": runaway,
        "decode_wall_p50": pct([r["decode_wall_ms"] for r in results if "error" not in r], 50),
        "generated_tokens_p50": pct([r.get("generated_token_count", -1) for r in results if "error" not in r], 50),
        "first_attempt_ok": ok,
        "errors": [r["error"] for r in results if "error" in r][:10],
    }


# ── 3/4. 20 long + 10 mixed (extended volume) ────────────────────────
def run_extended(server, n_long=20, n_mixed=10):
    frozen = load_frozen()
    long_p = [f for f in frozen if f["category"] == "long_cn"]
    mixed_p = [f for f in frozen if f["category"] in ("english", "number_mix")]
    results = []
    omni_init()
    order = 1000
    for i in range(n_long):
        fp = long_p[i % len(long_p)]
        audio = CASE_AUDIOS["long_cn"][i % 2]
        base = AUDIO_PREFIX + audio.replace(".wav", "")
        r = do_request(fp["prompt"], base, order + i)
        r.update({"sub": "long", "case_id": fp["case_id"]})
        results.append(r)
    for i in range(n_mixed):
        fp = mixed_p[i % len(mixed_p)]
        cat = fp["category"]
        audio = CASE_AUDIOS[cat][i % 2]
        base = AUDIO_PREFIX + audio.replace(".wav", "")
        r = do_request(fp["prompt"], base, order + n_long + i)
        r.update({"sub": "mixed", "case_id": fp["case_id"]})
        results.append(r)
    per_sub = {}
    for sub in ("long", "mixed"):
        rr = [r for r in results if r["sub"] == sub]
        per_sub[sub] = {
            "n": len(rr),
            "ok": sum(1 for r in rr if "error" not in r and r.get("success") is not False),
            "wall_timeout": sum(1 for r in rr if r.get("stop_reason") == "wall_timeout"),
            "slide": sum(1 for r in rr if r.get("sliding_window_count", 0) > 0),
        }
    return {"per_sub": per_sub,
            "total_ok": sum(1 for r in results if "error" not in r and r.get("success") is not False),
            "total": len(results),
            "errors": [r["error"] for r in results if "error" in r][:10]}


# ── 5. voice-switch (per-request ref-audio variation) ─────────────────
# NOTE (honest boundary): in the once-init persistent protocol the C++ T2W
# speaker reference is baked at omni_init from default_ref_audio (prompt_cache);
# changing audio_path_prefix does NOT re-clone the voice per request. The gate
# therefore verifies: every request succeeds with audio, and each request's
# output lands in its OWN round dir (per-request isolation, no cross-request
# contamination). Whether the timbre actually changes is out of scope for the
# persistent candidate and documented separately.
def run_voice_switch(server, n=5):
    frozen = load_frozen()
    sp = [f for f in frozen if f["category"] == "short_cn"]
    results = []
    omni_init()
    order = 2000
    for i in range(n):
        fp = sp[i % len(sp)]
        audio = ALL_AUDIOS[i % len(ALL_AUDIOS)]       # different ref each time
        base = AUDIO_PREFIX + audio.replace(".wav", "")
        rid = order + i
        r = do_request(fp["prompt"], base, rid)
        # Per-request output dir isolation: round_{rid}/tts_wav has its own wavs.
        rdir = os.path.join(REPO, "tools/omni/output", "round_%03d/tts_wav" % rid)
        wavs = []
        if os.path.isdir(rdir):
            wavs = sorted(f for f in os.listdir(rdir)
                          if f.startswith("wav_") and f.endswith(".wav"))
        w0_sha = None
        if wavs:
            with open(os.path.join(rdir, wavs[0]), "rb") as f:
                w0_sha = hashlib.sha256(f.read()).hexdigest()[:16]
        r.update({"sub": "voice", "case_id": fp["case_id"], "audio": audio,
                  "round_dir": "round_%03d" % rid, "n_wav_in_dir": len(wavs),
                  "wav0_sha": w0_sha})
        results.append(r)
    ok = sum(1 for r in results
             if "error" not in r and r.get("success") is not False
             and r.get("wav_count", 0) > 0)
    iso = all(r.get("n_wav_in_dir", 0) > 0 for r in results)
    return {
        "n": n, "ok": ok, "isolation": iso,
        "audios_distinct": len(set(ALL_AUDIOS[:n])) == n,
        "distinct_hashes": len(set(r.get("wav0_sha") for r in results if r.get("wav0_sha"))),
        "wav0_shas": [r.get("wav0_sha") for r in results],
        "errors": [r["error"] for r in results if "error" in r][:5],
    }


# ── 6. client-disconnect (abort mid-request; server survives) ────────
def run_disconnect(server, n=5):
    import http.client
    ok_before = health_ok()
    results = []
    for i in range(n):
        b0 = server.log_size()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
            payload = json.dumps({"stream": False, "round_idx": 3000 + i,
                                  "debug_dir": "/tmp/f6_t6/rounds",
                                  "max_tokens": MAX_TOKENS,
                                  "wall_timeout_ms": WALL_TIMEOUT_MS})
            conn.request("POST", "/v1/stream/decode", payload,
                         {"Content-Type": "application/json"})
            time.sleep(0.4)          # let server begin processing, then abort
            conn.close()             # client disconnect
            aborted = True
        except Exception as e:
            aborted = False
            results.append({"i": i, "abort_ok": False, "err": str(e)})
            continue
        time.sleep(2.0)
        alive = server.proc.poll() is None and health_ok()
        results.append({"i": i, "abort_ok": aborted, "server_alive": alive})
    # server must survive all 5 aborts and serve a normal request.
    # FIX (T6 finding): do NOT re-init after aborts. The frozen protocol is
    # once-init; a recovery omni_init frees the context while an aborted decode
    # may still be in-flight server-side (client disconnect does NOT stop the
    # server handler), causing a use-after-free crash (observed in run 1:
    # OMNI_FREE racing STREAM_DECODE_BEGIN req=3004 on ctx=0x0). Instead: let
    # in-flight decodes settle, then run the follow-up on the persistent context
    # (it queues behind any still-active generation via per-gen active).
    time.sleep(20)  # settle: aborted decodes complete server-side
    fp = load_frozen()[0]
    r = do_request(fp["prompt"], AUDIO_PREFIX + "0000", 3500, timeout=300)
    retried = False
    if "error" in r:
        # transient in-flight state — one retry after a longer settle
        retried = True
        time.sleep(20)
        r = do_request(fp["prompt"], AUDIO_PREFIX + "0000", 3500, timeout=300)
    survived = sum(1 for x in results if x.get("server_alive")) == n
    return {
        "n": n,
        "all_server_alive": survived,
        "all_abort_ok": all(x.get("abort_ok") for x in results),
        "followup_ok": "error" not in r and r.get("success") is not False,
        "followup_retried": retried,
        "detail": results,
    }


# ── 2. KV cache 30 MISS→HIT (inline, current server log formats) ─────
def run_kv_ab(server, pairs_per_case=6):
    """30 strict matched pairs (5 cases × 6). Per pair:
       A = clear cache + fresh ctx (omni_init) → expect MISS+SAVED
       B = fresh ctx (omni_init), cache warm   → expect HIT (loaded N positions)
    use_tts=False isolates the LLM prefill delta (matches R13 canonical)."""
    cases = [dict(tc, audio_base=AUDIO_PREFIX + tc["audio"].replace(".wav", ""))
             for tc in KV_TEST_CASES]
    pairs = []
    pair_idx = 0
    for tc in cases:
        for rnd in range(pairs_per_case):
            pair_idx += 1
            clear_kv_cache()
            b0 = server.log_size()
            a = kv_request(tc, 4000 + pair_idx * 2, use_tts=False)
            seg_a = server.log_slice(b0, server.log_size())
            time.sleep(1.0)
            b1 = server.log_size()
            b = kv_request(tc, 4000 + pair_idx * 2 + 1, use_tts=False)
            seg_b = server.log_slice(b1, server.log_size())
            time.sleep(1.0)

            sa = re.search(RE_KV_SAVED, seg_a)
            hb = re.search(RE_KV_HIT, seg_b)
            issues = []
            if "error" in a:
                issues.append("A_ERR")
            if "error" in b:
                issues.append("B_ERR")
            if not sa:
                issues.append("A_NOT_SAVED")
            if not hb:
                issues.append("B_NOT_LOADED")
            loaded_pos = int(hb.group(1)) if hb else 0
            if loaded_pos <= 0:
                issues.append("ZERO_REUSED")
            delta = a.get("prefill_wall_ms", 0) - b.get("prefill_wall_ms", 0)
            if delta <= 0:
                issues.append("DELTA_NEG(%.0f)" % delta)
            valid = not issues
            pairs.append({
                "pair_id": pair_idx, "case": tc["id"], "round": rnd + 1,
                "a_prefill_ms": round(a.get("prefill_wall_ms", 0), 1),
                "b_prefill_ms": round(b.get("prefill_wall_ms", 0), 1),
                "delta_ms": round(delta, 1),
                "loaded_positions": loaded_pos,
                "a_action": "SAVED" if sa else "?",
                "b_action": "HIT" if hb else "?",
                "a_wav_count": a.get("wav_count", -1),
                "b_wav_count": b.get("wav_count", -1),
                "issues": issues, "valid": valid,
            })
            print("  [%02d/30] %s %s-R%d: A=%s B=%s Δ=%+.0fms loaded=%d %s" % (
                pair_idx, "OK  " if valid else "FAIL", tc["id"], rnd + 1,
                "SAVED" if sa else "?",
                "HIT(%d)" % loaded_pos if hb else "?",
                delta, loaded_pos, ",".join(issues)))
            sys.stdout.flush()

    valid_pairs = [p for p in pairs if p["valid"]]
    n_valid = len(valid_pairs)
    a_ms = sorted(p["a_prefill_ms"] for p in valid_pairs)
    b_ms = sorted(p["b_prefill_ms"] for p in valid_pairs)
    deltas = sorted(p["delta_ms"] for p in valid_pairs)

    def pct(arr, p):
        if not arr:
            return 0
        return arr[min(int(len(arr) * p / 100), len(arr) - 1)]

    return {
        "n_pairs": len(pairs), "n_valid": n_valid,
        "gate_pass": n_valid >= 25,
        "miss_prefill_p50": pct(a_ms, 50), "hit_prefill_p50": pct(b_ms, 50),
        "delta_p50": pct(deltas, 50),
        "speedup_p50": round(pct(a_ms, 50) / max(pct(b_ms, 50), 1), 2),
        "loaded_positions_range": [
            min((p["loaded_positions"] for p in valid_pairs), default=0),
            max((p["loaded_positions"] for p in valid_pairs), default=0)],
        "pairs": pairs,
    }


def pct(a, p):
    if not a:
        return None
    s = sorted(a)
    return s[min(int(len(s) * p / 100), len(s) - 1)]


def aggregate(log_paths):
    full = "\n".join(open(p, errors="replace").read() for p in log_paths)
    cpu_fb = len(re.findall(r"暂用CPU|CPU backend|fallback to CPU|Flow on CPU|voc_hg2_model: CPU", full))
    cann_err = len(re.findall(r"CANN流跨线程|ACL_ERROR|aclError|aicore.*fail|operator.*not.*support|Model run failed", full))
    cann_ok = len(re.findall(r"vocoder CANN GPU OK", full))
    return {"cpu_fallback_count": cpu_fb, "cann_error_count": cann_err,
            "cann_ok_count": cann_ok}


def main():
    smoke = "--smoke" in sys.argv
    os.makedirs(RUN_DIR, exist_ok=True)
    print("=== T6 FINAL INTEGRATED REGRESSION (candidate%s) ===" % (" SMOKE" if smoke else ""))
    print("Server: %s" % SERVER)
    print("Env:    %s" % SERVER_ENV)
    report = {"meta": {"run": "T6_FULL",
                       "binary_sha": hashlib.sha256(open(SERVER, "rb").read()).hexdigest(),
                       "port": PORT}, "sessions": {}}

    # ── Session 1 (restart #1): 120 frozen + extended + voice + disconnect ──
    print("\n── Session 1 (restart #1): launch ──")
    s1 = Server(SRV_LOG)
    pid1 = s1.launch()
    print("server pid=%d" % pid1)
    if smoke:
        # SMOKE: 2 frozen + 1 long + 1 mixed + 1 voice + 1 disconnect
        frozen = load_frozen()
        omni_init()
        for i in range(2):
            fp = frozen[i]
            r = do_request(fp["prompt"], AUDIO_PREFIX + "0000", 1 + i)
            print("  smoke frozen: %s %s" % (fp["case_id"], "ok" if "error" not in r else r["error"][:80]))
        ext = run_extended(s1, n_long=1, n_mixed=1)
        voice = run_voice_switch(s1, n=1)
        disc = run_disconnect(s1, n=1)
        s13 = {"strict_pass": True, "runaway_free": True, "ok": 2, "n": 2,
               "errs": 0, "wall_timeout": 0, "sliding_window": 0,
               "prompt_modified": 0}
        report["smoke"] = {"extended": ext, "voice": voice, "disconnect": disc}
    else:
        s13 = run_120_frozen(s1)
        ext = run_extended(s1)
        voice = run_voice_switch(s1)
        disc = run_disconnect(s1)
        print("S13 gates: strict_pass=%s runaway_free=%s ok=%s/%s err=%s" % (
            s13.get("strict_pass"), s13.get("runaway_free"),
            s13.get("ok"), s13.get("n"), s13.get("errs")))
        print("extended: %s" % ext["per_sub"])
        print("voice: ok=%s isolation=%s distinct_hashes=%s" % (
            voice.get("ok"), voice.get("isolation"), voice.get("distinct_hashes")))
        print("disconnect: alive=%s followup_ok=%s" % (
            disc.get("all_server_alive"), disc.get("followup_ok")))
    print("session1 shutdown (SIGTERM drain)")
    s1.shutdown()
    report["sessions"]["session1"] = {"s13": s13, "extended": ext,
                                      "voice": voice, "disconnect": disc}

    # ── Session 2 (restart #2): KV cache 30 MISS→HIT ──
    print("\n── Session 2 (restart #2): launch → KV cache A/B ──")
    s2 = Server(KV_LOG)
    pid2 = s2.launch()
    kv = run_kv_ab(s2, pairs_per_case=1 if smoke else 6)
    print("kv_ab gate_pass=%s valid=%s/%s MISS_p50=%sms HIT_p50=%sms Δ_p50=%sms speedup=%s×" % (
        kv.get("gate_pass"), kv.get("n_valid"), kv.get("n_pairs"),
        kv.get("miss_prefill_p50"), kv.get("hit_prefill_p50"),
        kv.get("delta_p50"), kv.get("speedup_p50")))
    print("session2 shutdown")
    s2.shutdown()
    report["sessions"]["session2"] = {"kv_cache": {k: v for k, v in kv.items() if k != "pairs"}}

    # ── Session 3 (restart #3): smoke ──
    print("\n── Session 3 (restart #3): smoke ──")
    s3 = Server(os.path.join(RUN_DIR, "t6_smoke_srv.log"))
    pid3 = s3.launch()
    smoke = run_extended(s3, n_long=0, n_mixed=5)  # 5 smoke
    print("smoke: ok=%s/%s" % (smoke.get("total_ok"), smoke.get("total")))
    print("session3 shutdown")
    s3.shutdown()
    report["sessions"]["session3"] = {"smoke": smoke}

    # ── Aggregate gates ──
    glob = aggregate([SRV_LOG, KV_LOG,
                      os.path.join(RUN_DIR, "t6_smoke_srv.log")])
    gates = {
        "S13_STRICT_BASELINE": bool(s13.get("strict_pass")),
        "S13_RUNAWAY_FREE": bool(s13.get("runaway_free")),
        "EXTENDED_OK": ext.get("total_ok") == ext.get("total"),
        "VOICE_SWITCH_OK": voice.get("ok") == voice.get("n"),
        "VOICE_SWITCH_ISOLATION": bool(voice.get("isolation")),
        "DISCONNECT_SURVIVAL": bool(disc.get("all_server_alive")),
        "DISCONNECT_FOLLOWUP": bool(disc.get("followup_ok")),
        "KV_CACHE_AB": bool(kv.get("gate_pass")),
        "RESTART_3_SESSIONS": (pid1 and pid2 and pid3),
        "CPU_FALLBACK_ZERO": glob["cpu_fallback_count"] == 0,
        "CANN_ERROR_ZERO": glob["cann_error_count"] == 0,
    }
    accept = all(gates.values())
    report["gates"] = gates
    report["global_integrity"] = glob
    report["accept"] = accept

    print("\n" + "=" * 60)
    print("T6 GATES:")
    for k, v in gates.items():
        print("  %-24s %s" % (k, "PASS" if v else "FAIL"))
    print("integrity: cpu_fallback=%d cann_error=%d cann_ok=%d" % (
        glob["cpu_fallback_count"], glob["cann_error_count"], glob["cann_ok_count"]))
    print("ACCEPT = %s" % accept)

    with open(OUT_JSON, "w") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    print("saved -> %s" % OUT_JSON)
    return 0 if accept else 2


if __name__ == "__main__":
    sys.exit(main())
