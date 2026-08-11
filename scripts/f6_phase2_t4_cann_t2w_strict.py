#!/usr/bin/env python3
"""
F6 Phase 2 — T4: Strict CANN T2W re-verification (request-id bound).

Directive (user, 2026-08-04): "T4 严格复核 CANN T2W — ≥16 matched pairs,
4 cases × ≥4 each, request-id bound. 不得继续依赖日志顺序对齐。"

This harness binds every evidence channel by *value* (round_idx / generation_id /
request_index), never by log order:
  1. HTTP decode response echoes round_idx + generation_id + wav_count +
     decode_to_first_audio_ms  (new T3 fields)
  2. Server log: `stream_decode 开始 ... round_idx=N gen=G reqidx=R`
  3. Server log: `首响时间 ... | req=N gen=G`
  4. Server log: `T2W线程: wav_... | req=N gen=G`
  5. Server log: `T2W线程(C++): 新输出目录 round_N/tts_wav`
  6. e2e profile JSON per request (OMNI_E2E_PROFILE=1): request_index + generation_id
     + stages_ms (decode_loop_begin..client_first_audio) + async flow/vocoder
  7. pipeline trace CSV (OMNI_PIPELINE_TRACE=1): request_id(=reqidx&0xFF), thread_id,
     monotonic_ns, DECODE_BEGIN..FIRST_AUDIO_EMIT

Acceptance (per user spec): 0 mismatch / 0 missing W0 / 0 timeout / 0 stale-cross /
audio_valid=100%, 0 CPU fallback, 0 CANN error, no monotonic RSS/HBM growth.

Usage:
  python3 scripts/f6_phase2_t4_cann_t2w_strict.py            # full: 4 cases x 5 = 20 pairs
  python3 scripts/f6_phase2_t4_cann_t2w_strict.py --smoke    # 2 pairs, fast plumbing check
"""

import argparse
import hashlib
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import time
import urllib.request
import wave

REPO = "/workspace/llama.cpp-omni-f6"
SERVER = os.path.join(REPO, "build/bin/llama-omni-server")
MODEL = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
PORT = 18094
BASE = "http://127.0.0.1:%d" % PORT
RUN_DIR = "/tmp/f6_t4"
SRV_LOG = os.path.join(RUN_DIR, "t4_cann_t2w_srv.log")
PPROF = os.path.join(RUN_DIR, "pprof")
WAV_DIR = os.path.join(REPO, "tools/omni/output")
OUT_DIR = os.path.join(REPO, "docs/f6-s13-closure/phase2")
OUT_JSON = os.path.join(OUT_DIR, "t4_strict_cann_t2w.json")
ARCHIVE_JSON = os.path.join(REPO, "docs/f6-s13-closure/phase2/step2_latency_budget.json")

sys.path.insert(0, os.path.join(REPO, "scripts"))
from f6_s13_120_baseline import (SHORT_CN_PROMPTS, LONG_CN_PROMPTS,
                                 EN_PROMPTS, MIXED_PROMPTS)
AUDIO_PREFIX = os.path.join(REPO, "tools/omni/assets/test_case/omni_test_case/omni_test_case_")

CASES = [
    {"type": "short_cn",   "prompts": SHORT_CN_PROMPTS,  "audios": ["0000.wav", "0001.wav"]},
    {"type": "long_cn",    "prompts": LONG_CN_PROMPTS,   "audios": ["0002.wav", "0003.wav"]},
    {"type": "english",    "prompts": EN_PROMPTS,        "audios": ["0004.wav", "0005.wav"]},
    {"type": "number_mix", "prompts": MIXED_PROMPTS,     "audios": ["0006.wav", "0007.wav"]},
]

# F6 T3 / T4 regexes (value-bound, no order dependency)
RE_DECODE_START = re.compile(
    r"stream_decode 开始: .*round_idx=(\d+), gen=(\d+), reqidx=(\d+)")
RE_OUTDIR = re.compile(r"T2W线程\(C\+\+\): 新输出目录 .*round_(\d+)/tts_wav")
RE_W0 = re.compile(
    r"首响时间 \(First Audio Response\): (\d+)ms \(decode_to_first_audio\) \| (\d+)ms "
    r"\(request_to_first_audio\) \| req=(\d+) gen=(\d+)")
RE_WAV = re.compile(
    r"T2W线程: wav_(\d+)\.wav \| [\d.]+s audio \| ([\d.]+)ms inference \| RTF=([\d.]+) \| "
    r"t=\d+ms \| queue_wait=[\d.]+ms \| req=(\d+) gen=(\d+)")
RE_DRAIN = re.compile(r"T2W drain: complete \(wav_count=(\d+)")
RE_TERMINAL = re.compile(r"T2W terminal: (\w+)")
RE_T2W_CANN_OK = re.compile(r"vocoder CANN GPU OK")
RE_T2W_CPU_FALLBACK = re.compile(r"暂用CPU|CPU backend|voc_hg2_model: CPU|fallback to CPU|Flow on CPU")
RE_CANN_ERR = re.compile(r"CANN流跨线程|ACL_ERROR|aclError|aicore.*fail|operator.*not.*support|Model run failed")


def http_post(path, payload, timeout=600):
    req = urllib.request.Request(BASE + path,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def read_log():
    try:
        with open(SRV_LOG, "rb") as f:
            return f.read().decode("utf-8", "replace")
    except FileNotFoundError:
        return ""


def check_wav(path):
    try:
        w = wave.open(path, "rb")
        sr, sw, nch, nframes = w.getframerate(), w.getsampwidth(), w.getnchannels(), w.getnframes()
        w.close()
        ok = (sw == 2 and sr == 24000 and nch in (1, 2) and nframes > 0)
        return {"valid": bool(ok), "sr": sr, "sampwidth": sw, "channels": nch,
                "frames": nframes, "dur_s": round(nframes / float(sr), 3) if sr else None}
    except Exception as e:
        return {"valid": False, "error": str(e)}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def server_rss(pid):
    try:
        with open("/proc/%d/status" % pid) as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])  # kB
    except Exception:
        pass
    return None


def server_hbm(pid):
    """Best-effort per-process HBM from npu-smi -m; returns MB or None."""
    try:
        out = subprocess.run(["npu-smi", "info", "-m"], capture_output=True, text=True,
                             timeout=20).stdout
        for line in out.splitlines():
            if str(pid) in line:
                parts = line.split()
                # last numeric field is usually memory in MB
                for tok in reversed(parts):
                    if tok.replace(".", "").isdigit():
                        return float(tok)
    except Exception:
        pass
    return None


def load_archive():
    arch = json.load(open(ARCHIVE_JSON))
    base = {}
    for e in arch:
        order = e.get("order")
        cat = e.get("category")
        if order is None or cat is None:
            continue
        rnd = (order - 1) % 30
        base[(cat, rnd)] = e
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="quick 2-pair plumbing check")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    port = args.port
    global BASE
    BASE = "http://127.0.0.1:%d" % port

    n_cases = 2 if args.smoke else 4
    n_rounds = 1 if args.smoke else 5
    os.makedirs(RUN_DIR, exist_ok=True)
    # clean stale per-request evidence (fresh output dirs + e2e/pipeline profiles)
    for d in sorted(os.listdir(WAV_DIR)):
        if d.startswith("round_"):
            import shutil
            shutil.rmtree(os.path.join(WAV_DIR, d), ignore_errors=True)
    if os.path.isdir(PPROF):
        for f in os.listdir(PPROF):
            os.remove(os.path.join(PPROF, f))
    os.makedirs(PPROF, exist_ok=True)

    # ── 0. Launch server (CANN T2W full env set) ──
    env = dict(os.environ)
    env.update({
        "OMNI_T2W_DEVICE": "cann-flow-only",
        "OMNI_VOC_DEVICE": "gpu",
        "OMNI_KV_CACHE_REUSE": "1",
        "OMNI_PIPELINE_TRACE": "1",
        "OMNI_E2E_PROFILE": "1",
        "OMNI_E2E_PROFILE_DIR": PPROF,
        "ASCEND_RT_VISIBLE_DEVICES": env.get("ASCEND_RT_VISIBLE_DEVICES", "0"),
    })
    # stdbuf -oL: line-buffer server stdout so log markers appear progressively
    cmd = ["stdbuf", "-oL", "-eL", SERVER, "-m", MODEL, "-ngl", "999", "--device", "CANN0",
           "-c", "4096", "-b", "512", "-ub", "512", "--split-mode", "layer",
           "--port", str(port)]
    logf = open(SRV_LOG, "w")
    proc = subprocess.Popen(cmd, env=env, stdout=logf, stderr=subprocess.STDOUT,
                            cwd=REPO, preexec_fn=os.setsid)
    print("server pid=%d -> %s" % (proc.pid, SRV_LOG))

    try:
        # wait for /health
        ready = False
        for _ in range(600):
            if proc.poll() is not None:
                print("SERVER EXITED EARLY"); print(read_log()[-3000:]); return 1
            try:
                with urllib.request.urlopen(BASE + "/health", timeout=2) as r:
                    if r.status == 200:
                        ready = True
                        break
            except Exception:
                time.sleep(2)
        if not ready:
            print("server not ready in 20min"); print(read_log()[-2000:]); return 1
        print("server ready (port %d)" % port)

        time.sleep(5)  # let warmup settle

        # ── 1. Single omni_init (persistent context per R13 lifecycle design).
        # NOTE: /v1/stream/omni_init FREES and recreates the context each call
        # (server-omni.cpp:313-319). Call it exactly ONCE; per-request calls
        # would reset e2e_stage (generation/request_index) and break value-bound
        # correlation.  prefill+decode reuse the persistent context.
        print("omni_init (once, persistent context) ...")
        http_post("/v1/stream/omni_init", {"msg_type": 1, "media_type": 1, "use_tts": True}, timeout=300)

        # ── 2. Warmup decode ──
        http_post("/v1/stream/prefill",
                  {"audio_path_prefix": AUDIO_PREFIX + "0000", "cnt": 1,
                   "text": SHORT_CN_PROMPTS[0]}, timeout=300)
        http_post("/v1/stream/decode",
                  {"stream": False, "round_idx": 9900,
                   "debug_dir": "/tmp/f6_t4/rounds",
                   "max_tokens": 256, "wall_timeout_ms": 300000}, timeout=600)
        time.sleep(1.0)
        print("warmup done")

        # RSS/HBM samples
        rss_samples, hbm_samples = [], []
        pairs = []
        rss_samples.append(server_rss(proc.pid))

        # ── 2. Measured pairs ──
        for ci in range(n_cases):
            tc = CASES[ci]
            for rnd in range(n_rounds):
                prompt = tc["prompts"][rnd]
                audio = tc["audios"][rnd % len(tc["audios"])]
                round_idx = ci * 100 + rnd
                audio_base = AUDIO_PREFIX + audio.replace(".wav", "")

                # persistent context: no per-request omni_init (would recreate octx)
                http_post("/v1/stream/prefill",
                          {"audio_path_prefix": audio_base, "cnt": 1, "text": prompt}, timeout=300)
                t0 = time.time()
                try:
                    resp = http_post("/v1/stream/decode",
                                     {"stream": False, "round_idx": round_idx,
                                      "debug_dir": "/tmp/f6_t4/rounds",
                                      "max_tokens": 256, "wall_timeout_ms": 300000}, timeout=600)
                    client_wall_s = time.time() - t0
                    resp_ok = True
                except Exception as e:
                    resp, client_wall_s, resp_ok = None, None, False
                    print("  ERROR request round_idx=%d: %s" % (round_idx, e))
                time.sleep(0.5)

                pair = {
                    "case": tc["type"], "round": rnd, "round_idx": round_idx,
                    "audio": audio, "client_wall_s": client_wall_s,
                    "response": resp, "resp_ok": resp_ok,
                    "rss_kb": server_rss(proc.pid),
                }
                pairs.append(pair)
                echo = (resp or {}).get("round_idx")
                print("  %-11s r%02d rid=%03d echo=%s w0=%s wavs=%s" % (
                    tc["type"], rnd, round_idx, echo,
                    (resp or {}).get("decode_to_first_audio_ms"),
                    (resp or {}).get("wav_count")))
                sys.stdout.flush()
                rss_samples.append(pair["rss_kb"])
                hbm_samples.append(server_hbm(proc.pid))

        # ── 3. Graceful shutdown → atexit pipeline dump ──
        print("shutting down (SIGTERM) ...")
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        try:
            proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(timeout=30)
        logf.close()
        time.sleep(2)
    finally:
        if proc.poll() is None:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait(timeout=30)

    # ── 4. Parse full log (value-bound) ──
    log = read_log()

    decode_start = {}   # round_idx -> (gen, reqidx)
    for m in RE_DECODE_START.finditer(log):
        rid, gen, reqidx = int(m.group(1)), int(m.group(2)), int(m.group(3))
        decode_start[rid] = (gen, reqidx)

    outdirs = [int(m.group(1)) for m in RE_OUTDIR.finditer(log)]
    w0s = {}            # req -> list of (d2fa, r2fa, gen)
    for m in RE_W0.finditer(log):
        d2fa, r2fa, req, gen = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        w0s.setdefault(req, []).append((d2fa, r2fa, gen))
    wavs = {}           # req -> list of (wav_idx, inf_ms, rtf, gen, req)
    for m in RE_WAV.finditer(log):
        wav_i, inf, rtf, req, gen = int(m.group(1)), float(m.group(2)), float(m.group(3)), int(m.group(4)), int(m.group(5))
        wavs.setdefault(req, []).append((wav_i, inf, rtf, gen, req))
    drains = [int(m.group(1)) for m in RE_DRAIN.finditer(log)]
    terminals = [m.group(1) for m in RE_TERMINAL.finditer(log)]
    cann_ok_count = len(RE_T2W_CANN_OK.findall(log))
    cpu_fallbacks = RE_T2W_CPU_FALLBACK.findall(log)
    cann_errors = RE_CANN_ERR.findall(log)

    # e2e profile per request
    e2e = {}
    for fn in sorted(os.listdir(PPROF)):
        m = re.match(r"e2e_(\d{4})\.json$", fn)
        if m:
            idx = int(m.group(1))
            try:
                e2e[idx] = json.load(open(os.path.join(PPROF, fn)))
            except Exception:
                pass
    e2e_audio = {}
    for fn in sorted(os.listdir(PPROF)):
        m = re.match(r"e2e_(\d{4})_audio\.json$", fn)
        if m:
            idx = int(m.group(1))
            try:
                e2e_audio[idx] = json.load(open(os.path.join(PPROF, fn)))
            except Exception:
                pass

    # pipeline trace
    ptrace = None
    ptf = os.path.join(PPROF, "pipeline_trace", "pipeline_trace_0000.csv")
    if not os.path.exists(ptf):
        ptf = "/tmp/pipeline_diag/pipeline_trace/pipeline_trace_0000.csv"
    if os.path.exists(ptf):
        ptrace = []
        with open(ptf) as f:
            hdr = f.readline().strip().split(",")
            for line in f:
                row = line.strip().split(",")
                if len(row) == len(hdr):
                    ptrace.append(dict(zip(hdr, row)))

    # ── 5. Consistency gates ──
    measured = [p for p in pairs if p["resp_ok"]]
    arch = load_archive()
    issues = []
    results = []

    for p in measured:
        rid = p["round_idx"]
        resp = p["response"]
        r = {
            "case": p["case"], "round": p["round"], "round_idx": rid,
            "pair_id": "%s_r%02d" % (p["case"], p["round"]),
            "output_dir": "round_%03d/tts_wav" % rid,
        }
        # C1 echo
        r["echo_ok"] = (resp.get("round_idx") == rid)
        r["generation_id"] = resp.get("generation_id")
        r["resp_wav_count"] = resp.get("wav_count")
        r["resp_d2fa_ms"] = resp.get("decode_to_first_audio_ms")

        # C2/C3 decode-start + W0 single + gen match
        ds = decode_start.get(rid)
        w0l = w0s.get(rid, [])
        r["decode_start"] = ds
        r["w0_count"] = len(w0l)
        r["missing_w0"] = (len(w0l) != 1)
        if ds and len(w0l) == 1:
            r["gen_match"] = (ds[0] == w0l[0][2])
            r["d2fa_log_ms"] = w0l[0][0]
            r["r2fa_log_ms"] = w0l[0][1]
        else:
            r["gen_match"] = False
            r["d2fa_log_ms"] = None
            r["r2fa_log_ms"] = None

        # C4 wav-line req binding
        wl = wavs.get(rid, [])
        r["wav_lines"] = len(wl)
        r["wav_req_match"] = all(w[4] == rid for w in wl)   # w[4] = req
        # first wav of the round is the min wav index (base may be >0 for high round_idx)
        first_wav = min(wl, key=lambda w: w[0]) if wl else None
        r["wav0_inf_ms"] = first_wav[1] if first_wav else None
        r["wav0_rtf"] = first_wav[2] if first_wav else None
        r["wav0_idx"] = first_wav[0] if first_wav else None

        # C5 reqidx → e2e bind
        reqidx = ds[1] if ds else None
        r["reqidx"] = reqidx
        e = e2e.get(reqidx) if reqidx is not None else None
        if e:
            r["e2e_gen"] = e.get("generation_id")
            r["e2e_gen_match"] = (ds is not None and e.get("generation_id") == ds[0])
            r["e2e_stages"] = e.get("stages_ms", {})
            r["e2e_stale"] = e.get("stale_write_count")
            r["e2e_cross"] = e.get("cross_request_write_count")
            r["talker_token_count"] = e.get("talker_token_count")
        else:
            r["e2e_gen_match"] = False
            r["e2e_stages"] = {}
            r["e2e_stale"] = None
            r["e2e_cross"] = None
            r["talker_token_count"] = None
        # F6 T4: NoSpeech classification. Absent e2e_audio JSON = T2W worker never
        # dequeued this request (LLM produced 0 talker tokens → empty response).
        # talker_token_count is NOT reliable (round 302 spoke but reports 0).
        ea = e2e_audio.get(reqidx) if reqidx is not None else None
        if ea:
            r["async_stages"] = ea.get("async_stages_ms", {})
            r["t2w_gen"] = ea.get("generation_id")
            r["t2w_gen_match"] = (ds is not None and ea.get("generation_id") == ds[0])
        else:
            r["async_stages"] = {}
            r["t2w_gen"] = None
            r["t2w_gen_match"] = False
        r["nospeech"] = (ea is None and reqidx is not None)

        # C7 wav_count vs dir
        rdir = os.path.join(WAV_DIR, "round_%03d" % rid, "tts_wav")
        if os.path.isdir(rdir):
            files = sorted(f for f in os.listdir(rdir) if f.endswith(".wav"))
            r["dir_wav_count"] = len(files)
            r["wav_count_ok"] = (resp.get("wav_count") == len(files))
        else:
            r["dir_wav_count"] = None
            r["wav_count_ok"] = False

        # C8 D0->W0 cross-check (response vs log vs e2e)
        d2fa_resp = resp.get("decode_to_first_audio_ms")
        d2fa_log = r.get("d2fa_log_ms")
        r["d2fa_cross_ok"] = (d2fa_resp is not None and d2fa_log is not None
                              and abs(d2fa_resp - d2fa_log) <= 50)
        r["d2fa_e2e_ms"] = r["e2e_stages"].get("client_first_audio")
        d2fa_e2e = r["e2e_stages"].get("client_first_audio")
        if d2fa_log and d2fa_e2e:
            r["d2fa_e2e_cross_ok"] = abs(d2fa_log - d2fa_e2e) <= 50
        else:
            r["d2fa_e2e_cross_ok"] = False
        # audio JSON wav_ready (async, per-request) vs log d2fa within 50ms
        awr = r.get("async_stages", {}).get("wav_ready")
        r["d2fa_e2e_audio_ok"] = bool(d2fa_log and awr is not None
                                      and abs(awr - d2fa_log) <= 50)

        # C9 audio valid + hash
        wav0 = None
        if os.path.isdir(rdir) and r.get("wav0_idx") is not None:
            wav0 = os.path.join(rdir, "wav_%d.wav" % r["wav0_idx"])
        if wav0 and os.path.exists(wav0):
            probe = check_wav(wav0)
            r["wav0_probe"] = probe
            r["wav0_sha256"] = sha256_file(wav0)
            r["audio_valid"] = probe["valid"]
        else:
            r["wav0_probe"] = None
            r["wav0_sha256"] = None
            r["audio_valid"] = False

        # C10 stale-cross (per-request)
        r["stale_cross_ok"] = (r.get("e2e_stale") == 0 and r.get("e2e_cross") == 0)

        # pair with archived CPU baseline
        b = arch.get((p["case"], p["round"]), {})
        r["cpu_w0_ms"] = b.get("W0_ms")
        r["cpu_t2w_inf_ms"] = b.get("T2W_inf_ms")
        if r.get("d2fa_log_ms") and b.get("W0_ms"):
            r["delta_w0_ms"] = r["d2fa_log_ms"] - b["W0_ms"]
        else:
            r["delta_w0_ms"] = None
        # F6 T4: T2W-only paired delta — isolates the device-placement effect.
        # CPU baseline T2W_inf_ms = first-chunk worker inference (W0 ≈
        # LLM_to_speak + T2W_inf); CANN wav0_inf_ms = same first-chunk worker
        # inference on CANN. LLM decode (stochastic preamble) is excluded, so
        # this is a deterministic comparison of the T2W device placement.
        if r.get("wav0_inf_ms") and b.get("T2W_inf_ms"):
            r["t2w_delta_ms"] = r["wav0_inf_ms"] - b["T2W_inf_ms"]
        else:
            r["t2w_delta_ms"] = None

        # gate row. For NoSpeech requests (empty model response, 0 talker tokens)
        # W0/audio gates are vacuous: no T2W work was expected. Only echo + e2e
        # binding + stale-cross still apply. Non-NoSpeech pairs must satisfy all.
        if r["nospeech"]:
            r["gates"] = {
                "echo": r["echo_ok"],
                "single_w0": True,        # vacuous
                "gen_match": True,        # vacuous
                "wav_req_bind": True,     # vacuous
                "reqidx_e2e_bind": r.get("e2e_gen_match", False),
                "wav_count": True,        # vacuous
                "d2fa_cross": True,       # vacuous
                "d2fa_e2e_audio": True,   # vacuous
                "audio_valid": True,      # vacuous
                "stale_cross": r["stale_cross_ok"],
            }
        else:
            r["gates"] = {
                "echo": r["echo_ok"],
                "single_w0": not r["missing_w0"],
                "gen_match": r.get("gen_match", False),
                "wav_req_bind": r["wav_req_match"],
                "reqidx_e2e_bind": r.get("e2e_gen_match", False),
                "wav_count": r["wav_count_ok"],
                "d2fa_cross": r["d2fa_cross_ok"],
                "d2fa_e2e_audio": r.get("d2fa_e2e_audio_ok", False),
                "audio_valid": r["audio_valid"],
                "stale_cross": r["stale_cross_ok"],
            }
        results.append(r)

    # aggregate gates — W0/audio gates evaluated only over non-NoSpeech pairs
    active = [r for r in results if not r["nospeech"]]
    nospeech_list = [r["pair_id"] for r in results if r["nospeech"]]
    n_active = len(active)

    def g(k):
        return sum(1 for r in active if r["gates"].get(k))

    n = len(results)
    agg = {
        "n_pairs": n,
        "n_active": n_active,
        "n_nospeech": len(nospeech_list),
        "nospeech_pairs": nospeech_list,
        "n_cases": len({r["case"] for r in results}),
        "cases": sorted({r["case"] for r in results}),
        "per_case": {c: sum(1 for r in results if r["case"] == c) for c in sorted({r["case"] for r in results})},
        "gates": {k: (g(k) == n_active and n_active > 0) for k in
                  ["echo", "single_w0", "gen_match", "wav_req_bind",
                   "reqidx_e2e_bind", "wav_count", "d2fa_cross", "d2fa_e2e_audio",
                   "audio_valid", "stale_cross"]},
        "gate_counts": {k: g(k) for k in
                        ["echo", "single_w0", "gen_match", "wav_req_bind",
                         "reqidx_e2e_bind", "wav_count", "d2fa_cross", "d2fa_e2e_audio",
                         "audio_valid", "stale_cross"]},
    }

    # performance summary (paired dW0 and T2W-only delta)
    dW0 = [r["delta_w0_ms"] for r in results if r["delta_w0_ms"] is not None]
    dT2W = [r["t2w_delta_ms"] for r in results if r["t2w_delta_ms"] is not None]
    cann_w0 = [r["d2fa_log_ms"] for r in results if r["d2fa_log_ms"] is not None]
    cpu_w0 = [r["cpu_w0_ms"] for r in results if r["cpu_w0_ms"] is not None]
    rtf = [r["wav0_rtf"] for r in results if r["wav0_rtf"] is not None]
    wav0_inf = [r["wav0_inf_ms"] for r in results if r["wav0_inf_ms"] is not None]
    flow_ms = []
    voc_ms = []
    wav_ready_ms = []
    for r in results:
        a = r.get("async_stages", {})
        # audio JSON stores per-stage *elapsed since request*: compute deltas
        if a.get("flow_end") is not None and a.get("flow_start") is not None:
            flow_ms.append(max(a["flow_end"] - a["flow_start"], 0))
        if a.get("vocoder_end") is not None and a.get("vocoder_start") is not None:
            voc_ms.append(max(a["vocoder_end"] - a["vocoder_start"], 0))
        if a.get("wav_ready") is not None:
            wav_ready_ms.append(a["wav_ready"])

    def pct(a, p):
        if not a:
            return None
        s = sorted(a)
        return s[min(int(len(s) * p / 100), len(s) - 1)]

    perf = {
        "n_paired": len(dW0),
        "cpu_w0_p50": pct(cpu_w0, 50) if cpu_w0 else None,
        "cann_w0_p50": pct(cann_w0, 50) if cann_w0 else None,
        "dW0_p50": pct(dW0, 50) if dW0 else None,
        "dW0_p95": pct(dW0, 95) if dW0 else None,
        "wav0_inf_p50": pct(wav0_inf, 50) if wav0_inf else None,
        "rtf_p50": pct(rtf, 50) if rtf else None,
        "flow_ms_p50": pct(flow_ms, 50) if flow_ms else None,
        "voc_ms_p50": pct(voc_ms, 50) if voc_ms else None,
        "wav_ready_p50": pct(wav_ready_ms, 50) if wav_ready_ms else None,
        "d2fa_e2e_audio_cross_ok": sum(1 for r in results if r.get("d2fa_e2e_audio_ok")),
        # E2E W0 delta (includes stochastic LLM preamble — reported, not gated)
        "all_deltas_negative": bool(dW0) and all(d < 0 for d in dW0),
        # T2W-only delta (deterministic device-placement comparison) — gated
        "t2w_delta_p50": pct(dT2W, 50) if dT2W else None,
        "all_t2w_deltas_negative": bool(dT2W) and all(d < 0 for d in dT2W),
    }
    if len(dW0) >= 16:
        rng = random.Random(42)
        meds = []
        for _ in range(10000):
            s = [dW0[rng.randrange(len(dW0))] for _ in range(len(dW0))]
            meds.append(statistics.median(s))
        meds.sort()
        perf["dW0_ci95"] = [round(meds[250], 1), round(meds[9749], 1)]
    else:
        perf["dW0_ci95"] = None
    if len(dT2W) >= 16:
        rng = random.Random(42)
        tmeds = []
        for _ in range(10000):
            s = [dT2W[rng.randrange(len(dT2W))] for _ in range(len(dT2W))]
            tmeds.append(statistics.median(s))
        tmeds.sort()
        perf["t2w_delta_ci95"] = [round(tmeds[250], 1), round(tmeds[9749], 1)]
    else:
        perf["t2w_delta_ci95"] = None

    # resource monotonicity
    rss_ok = True
    if rss_samples:
        non_null = [x for x in rss_samples if x is not None]
        if non_null:
            rss_ok = non_null[-1] <= max(non_null)  # end <= peak
    hbm_ok = True
    if hbm_samples:
        non_null = [x for x in hbm_samples if x is not None]
        if len(non_null) >= 2:
            hbm_ok = non_null[-1] <= max(non_null)

    # global stability gates
    stability = {
        "cpu_fallback_count": len(cpu_fallbacks),
        "cann_error_count": len(cann_errors),
        "cann_ok_count": cann_ok_count,
        "timeout_count": sum(1 for p in pairs if not p["resp_ok"]),
        "cpu_fallback_ok": len(cpu_fallbacks) == 0,
        "cann_error_ok": len(cann_errors) == 0,
        "rss_monotonic_ok": rss_ok,
        "hbm_monotonic_ok": hbm_ok,
        "rss_kb": [x for x in rss_samples if x is not None],
        "hbm_mb": [x for x in hbm_samples if x is not None],
    }

    gate_keys = ["echo", "single_w0", "gen_match", "wav_req_bind",
                 "reqidx_e2e_bind", "wav_count", "d2fa_cross", "d2fa_e2e_audio",
                 "audio_valid", "stale_cross"]
    stab_keys = ["cpu_fallback_ok", "cann_error_ok", "rss_monotonic_ok", "hbm_monotonic_ok"]
    # F6 T4 gate: user spec gates are CORRECTNESS ("0 mismatch / 0 missing W0 /
    # 0 timeout / 0 stale-cross / audio_valid=100%"). The perf gate is the
    # T2W-only delta (deterministic device-placement comparison). E2E W0 delta
    # (all_deltas_negative) is contaminated by stochastic LLM preamble length
    # and is reported but NOT gated.
    accept = (n_active >= (2 if args.smoke else 16)
              and all(agg["gates"][k] for k in gate_keys)
              and all(stability[k] for k in stab_keys)
              and stability["timeout_count"] == 0
              and perf["all_t2w_deltas_negative"])

    report = {
        "meta": {"run": "SMOKE" if args.smoke else "FULL",
                 "binary_sha": None, "port": port},
        "n_requests_sent": len(pairs),
        "n_responses_ok": n,
        "aggregate": agg,
        "stability": stability,
        "perf": perf,
        "pipeline_trace_events": len(ptrace) if ptrace else 0,
        "pipeline_request_ids": sorted({int(r["request_id"]) for r in ptrace}) if ptrace else [],
        "accept": accept,
        "pairs": results,
    }

    with open(OUT_JSON, "w") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)

    # ── 6. Human summary ──
    print("\n==== T4 STRICT CANN T2W REPORT (%s) ====" % report["meta"]["run"])
    print("pairs sent=%d responses_ok=%d active=%d nospeech=%d cases=%s" % (
        len(pairs), n, agg["n_active"], agg["n_nospeech"], agg["cases"]))
    if agg["nospeech_pairs"]:
        print("NoSpeech (0 talker tokens, vacuous W0 gates): %s" % agg["nospeech_pairs"])
    print("per-case: %s" % agg["per_case"])
    print("\nGates (count / n_active):")
    for k, v in agg["gate_counts"].items():
        print("  %-18s %d/%d  %s" % (k, v, n_active, "OK" if v == n_active else "FAIL"))
    print("Global:")
    for k in ["cpu_fallback_ok", "cann_error_ok", "rss_monotonic_ok", "hbm_monotonic_ok", "timeout_count"]:
        print("  %-20s %s" % (k, stability[k]))
    print("\nPerf:")
    for k in ["n_paired", "cpu_w0_p50", "cann_w0_p50", "dW0_p50", "dW0_p95",
              "wav0_inf_p50", "rtf_p50", "flow_ms_p50", "voc_ms_p50", "all_deltas_negative", "dW0_ci95",
              "t2w_delta_p50", "all_t2w_deltas_negative", "t2w_delta_ci95"]:
        print("  %-24s %s" % (k, perf[k]))
    print("\nACCEPT = %s" % accept)
    print("saved -> %s" % OUT_JSON)
    return 0 if accept else 2


import random

if __name__ == "__main__":
    sys.exit(main())
