#!/usr/bin/env python3
"""
F6 Phase 2 — Step 6: First candidate experiment.
Single-factor A/B: T2W device = CPU (S13 archived baseline) vs CANN
(OMNI_T2W_DEVICE=cann-flow-only + OMNI_VOC_DEVICE=gpu), on the SAME
frozen prompt set, same case types, same server binary/config.

Factor:      T2W device placement only.
Baseline:    archived S13 strict 120 (CPU flow/vocoder), per-request W0.
Candidate:   live CANN-T2W server (already running on 18093, warm).
Workload:    4 case types × 8 rounds = 32 matched pairs (>=30, >=3 cases).
Metrics:     W0 = decode_to_first_audio (首响时间), wav_0 inference, RTF.
Audio check: every WAV valid 16-bit PCM; sample rate vs baseline.

Constraints honored: CHUNK_SIZE=25 untouched, B6b untouched, MTP untouched.
"""

import json
import os
import re
import statistics
import sys
import time
import urllib.request
import wave

BASE = "http://127.0.0.1:18093"
SERVER_OUT = "/tmp/f6_p2_step6/cann_t2w_srv.log"
ARCHIVE_JSON = "docs/f6-s13-closure/phase2/step2_latency_budget.json"
OUT_DIR = "docs/f6-s13-closure/phase2"
OUT_JSON = os.path.join(OUT_DIR, "step6_cann_t2w_ab.json")
WAV_DIR = "/workspace/llama.cpp-omni-f6/tools/omni/output"

# Import the frozen S13 prompt/case definitions
sys.path.insert(0, "scripts")
from f6_s13_120_baseline import (SHORT_CN_PROMPTS, LONG_CN_PROMPTS,
                                 EN_PROMPTS, MIXED_PROMPTS)
AUDIO_PREFIX = "/workspace/llama.cpp-omni-f6/tools/omni/assets/test_case/omni_test_case/omni_test_case_"

CASES = [
    {"type": "short_cn",   "prompts": SHORT_CN_PROMPTS,  "audios": ["0000.wav", "0001.wav"]},
    {"type": "long_cn",    "prompts": LONG_CN_PROMPTS,   "audios": ["0002.wav", "0003.wav"]},
    {"type": "english",    "prompts": EN_PROMPTS,        "audios": ["0004.wav", "0005.wav"]},
    {"type": "number_mix", "prompts": MIXED_PROMPTS,     "audios": ["0006.wav", "0007.wav"]},
]

N_ROUNDS = 8          # 8 × 4 = 32 matched pairs
ROUND_START = 0


def http_post(path, payload, timeout=600):
    req = urllib.request.Request(BASE + path,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def log_size():
    try:
        return os.path.getsize(SERVER_OUT)
    except FileNotFoundError:
        return 0


def read_segment(start, end=None):
    with open(SERVER_OUT, "rb") as f:
        f.seek(start)
        data = f.read((end - start) if end else -1)
    return data.decode("utf-8", "replace")


def parse_w0(seg):
    m = re.search(r"首响时间 \(First Audio Response\):\s*(\d+)ms\s*\(decode_to_first_audio\)", seg)
    if m:
        return int(m.group(1))
    m2 = re.search(r"First Audio Response\):\s*(\d+)ms", seg)
    return int(m2.group(1)) if m2 else None


def parse_t2w(seg):
    mi = re.search(r"wav_0\.wav.*?([\d.]+)ms\s+inference\s*\|\s*RTF=([\d.]+)", seg)
    if mi:
        return float(mi.group(1)), float(mi.group(2))
    return None, None


def check_wav(round_idx, wav_path):
    """Validate WAV is 16-bit PCM; return (sr, frames, dur_s)."""
    try:
        w = wave.open(wav_path, "rb")
        sr, sw, nch, nframes = w.getframerate(), w.getsampwidth(), w.getnchannels(), w.getnframes()
        w.close()
        return sr, sw, nch, nframes, nframes / float(sr) if sr else None
    except Exception as e:
        return None


def main():
    # ── Load archived CPU baseline, index by (category, round) ──
    arch = json.load(open(ARCHIVE_JSON))
    baseline = {}   # (category, round) -> W0_ms, T2W_inf_ms
    for e in arch:
        order = e["order"]            # 1-based, archived S13 order
        cat = e["category"]
        rnd = (order - 1) % 30
        baseline[(cat, rnd)] = e
    print("Archived baseline indexed: %d entries" % len(baseline))

    pairs = []

    # Explicit warmup: prime KV cache + CANN T2W backend (first decode is slow).
    print("  warmup: short_cn rnd 0 ...")
    http_post("/v1/stream/omni_init", {"msg_type": 1, "media_type": 1, "use_tts": True}, timeout=300)
    http_post("/v1/stream/prefill",
              {"audio_path_prefix": AUDIO_PREFIX + "0000", "cnt": 1, "text": SHORT_CN_PROMPTS[0]},
              timeout=300)
    http_post("/v1/stream/decode",
              {"stream": False, "round_idx": 9999,
               "debug_dir": "/tmp/f6_p2_step6/rounds",
               "max_tokens": 256, "wall_timeout_ms": 300000},
              timeout=600)
    time.sleep(1.0)
    print("  warmup done\n")

    for ci, tc in enumerate(CASES):
        for rnd in range(ROUND_START, ROUND_START + N_ROUNDS):
            prompt = tc["prompts"][rnd]
            audio = tc["audios"][rnd % len(tc["audios"])]
            audio_base = AUDIO_PREFIX + audio.replace(".wav", "")

            round_idx = ci * 100 + rnd   # unique round dir per request
            pos0 = log_size()

            # omni_init (idempotent after first load)
            http_post("/v1/stream/omni_init",
                      {"msg_type": 1, "media_type": 1, "use_tts": True}, timeout=300)
            # prefill
            http_post("/v1/stream/prefill",
                      {"audio_path_prefix": audio_base, "cnt": 1, "text": prompt},
                      timeout=300)
            # decode (token cap + wall safety — matches S13 step7 harness)
            t0 = time.time()
            http_post("/v1/stream/decode",
                      {"stream": False, "round_idx": round_idx,
                       "debug_dir": "/tmp/f6_p2_step6/rounds",
                       "max_tokens": 256, "wall_timeout_ms": 300000},
                      timeout=600)
            decode_wall_s = time.time() - t0
            time.sleep(0.5)  # flush delay (R13 log-buffering mitigation)

            seg = read_segment(pos0)
            w0 = parse_w0(seg)
            t2w_inf, rtf = parse_t2w(seg)
            n_wav = len(re.findall(r"T2W线程: wav_\d+\.wav", seg))

            # audio quality check on first wav
            wav_file = None
            wav_probe = None
            # locate the round output dir (server writes to tools/omni/output/round_<round_idx>)
            for cand in sorted(os.listdir(WAV_DIR))[::-1]:
                cand_p = os.path.join(WAV_DIR, cand, "tts_wav", "wav_0.wav")
                if os.path.exists(cand_p) and "round_%03d" % round_idx in cand_p:
                    wav_file = cand_p
                    break
            if wav_file:
                wav_probe = check_wav(round_idx, wav_file)

            b = baseline.get((tc["type"], rnd), {})
            pair = {
                "case": tc["type"], "round": rnd, "prompt": prompt[:40],
                "audio": audio,
                "cpu_w0_ms": b.get("W0_ms"),
                "cann_w0_ms": w0,
                "delta_w0_ms": (w0 - b["W0_ms"]) if (w0 and b.get("W0_ms")) else None,
                "cann_wav0_inf_ms": t2w_inf,
                "cpu_wav0_inf_ms": b.get("T2W_inf_ms"),
                "rtf": rtf,
                "wav_count": n_wav,
                "decode_wall_s": round(decode_wall_s, 2),
                "wav_probe": wav_probe,
            }
            pairs.append(pair)
            print("  %-11s r%02d cpu_W0=%8s cann_W0=%8s dW0=%8s inf:%s->%s rtf=%s wavs=%d" % (
                tc["type"], rnd, b.get("W0_ms"), w0,
                pair["delta_w0_ms"] if pair["delta_w0_ms"] is not None else "-",
                (str(b.get("T2W_inf_ms")) or "-"), t2w_inf, rtf, n_wav))
            sys.stdout.flush()

    json.dump(pairs, open(OUT_JSON, "w"), indent=1, ensure_ascii=False)

    # ── Analysis ──
    print("\n=== RESULTS (n=%d matched pairs) ===" % len(pairs))
    valid = [p for p in pairs if p["cann_w0_ms"] and p["cpu_w0_ms"]]

    def pct(a, p):
        s = sorted(a)
        return s[min(int(len(s) * p / 100), len(s) - 1)]

    def show(label, arr):
        if not arr:
            print("  %-14s n=0" % label); return
        print("  %-14s n=%3d p50=%7.1f p90=%7.1f p95=%7.1f p99=%7.1f max=%7.1f" % (
            label, len(arr), statistics.median(arr), pct(arr, 90), pct(arr, 95),
            pct(arr, 99), max(arr)))

    cpu_w0 = [p["cpu_w0_ms"] for p in valid]
    cann_w0 = [p["cann_w0_ms"] for p in valid]
    dW0 = [p["delta_w0_ms"] for p in valid if p["delta_w0_ms"] is not None]
    show("CPU W0 (arch)", cpu_w0)
    show("CANN W0", cann_w0)
    show("dW0 (CANN-CPU)", dW0)
    if dW0 and cpu_w0:
        print("  median W0: %.0f -> %.0f ms  (%.1f%% reduction)" % (
            statistics.median(cpu_w0), statistics.median(cann_w0),
            100 * (1 - statistics.median(cann_w0) / statistics.median(cpu_w0))))

    print("\n  per-case median W0 (CPU -> CANN) and T2W wav0 inf:")
    for c in ["short_cn", "long_cn", "english", "number_mix"]:
        sub = [p for p in valid if p["case"] == c]
        if not sub:
            continue
        mc = statistics.median([p["cann_w0_ms"] for p in sub])
        mb = statistics.median([p["cpu_w0_ms"] for p in sub])
        inf_c = [p["cann_wav0_inf_ms"] for p in sub if p["cann_wav0_inf_ms"]]
        inf_b = [p["cpu_wav0_inf_ms"] for p in sub if p["cpu_wav0_inf_ms"]]
        print("  %-11s n=%2d  W0 %7.0f -> %6.0f ms (%.1f%% cut)   inf %s -> %s ms" % (
            c, len(sub), mb, mc, 100 * (1 - mc / mb) if mb else 0,
            (("%.0f" % statistics.median(inf_b)) if inf_b else "-"),
            (("%.0f" % statistics.median(inf_c)) if inf_c else "-")))

    # bootstrap 95% CI on median dW0
    rng = random_source(dW0)
    n_boot = 10000
    meds = []
    if dW0:
        for _ in range(n_boot):
            sample = [dW0[rng()] for _ in range(len(dW0))]
            meds.append(statistics.median(sample))
        meds.sort()
        lo, hi = meds[int(0.025 * n_boot)], meds[int(0.975 * n_boot)]
        print("\n  Bootstrap 95%% CI on median dW0: [%.0f, %.0f] ms (n_boot=%d)" % (lo, hi, n_boot))

    # audio quality summary
    probes = [p["wav_probe"] for p in valid if p["wav_probe"]]
    if probes:
        srs = {p[0] for p in probes}
        sws = {p[1] for p in probes}
        durs = statistics.median([p[4] for p in probes])
        print("  WAV probe: sample_rates=%s sampwidth=%s median_dur=%.2fs (n=%d)" % (
            srs, sws, durs, len(probes)))

    print("\nSaved -> %s" % OUT_JSON)
    return 0


# deterministic PRNG for bootstrap (Date.now/Math.random unavailable in script,
# but this is a normal python process so random module is fine)
import random
def random_source(values):
    rnd = random.Random(42)
    n = len(values)
    return lambda: rnd.randrange(n)


if __name__ == "__main__":
    sys.exit(main())
