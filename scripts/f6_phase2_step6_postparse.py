#!/usr/bin/env python3
"""
F6 Phase 2 — Step 6: robust order-based post-parser for the CANN-T2W A/B.

The live harness (f6_phase2_step6_cann_t2w_ab.py) segments the server log by
byte offset, but the async T2W drain + worker restart between requests races
the 0.5s flush window, so a few rows get wrong/None W0 attribution.

This parser instead aligns by ORDER using authoritative markers:
  * "T2W线程(C++): 新输出目录 ./tools/omni/output/round_<N>/tts_wav"  → round start
  * "首响时间 (First Audio Response): Xms (decode_to_first_audio)"     → W0
  * "T2W线程: wav_... inference=Xms | RTF=..."                          → chunk-0 T2W
  * "T2W drain: complete (wav_count=K, ...)"                            → wav count

Request order (server log) = [warmup] + [short_cn r00..r07, long_cn r00..r07,
english r00..r07, number_mix r00..r07] because decodes are sequential and each
queues exactly one generation (33 decode starts == 33 首响 == 33 round starts).

Output: docs/f6-s13-closure/phase2/step6_cann_t2w_ab.json (32 rows, overwrites
the harness JSON which may hold shifted/None attributions).
"""

import json
import os
import re
import statistics
import sys

LOG = "/tmp/f6_p2_step6/cann_t2w_srv.log"
ARCHIVE_JSON = "docs/f6-s13-closure/phase2/step2_latency_budget.json"
OUT_JSON = "docs/f6-s13-closure/phase2/step6_cann_t2w_ab.json"
WAV_ROOT = "/workspace/llama.cpp-omni-f6/tools/omni/output"

CASES = ["short_cn", "long_cn", "english", "number_mix"]
N_ROUNDS = 8


def parse(log_path):
    lines = open(log_path, encoding="utf-8", errors="replace").read().splitlines()
    rounds = []          # ordered round records
    cur = None
    for l in lines:
        # round start (authoritative boundary)
        m = re.search(r"T2W线程\(C\+\+\): 新输出目录 ./tools/omni/output/round_(\d+)/tts_wav", l)
        if m:
            if cur is not None:
                rounds.append(cur)
            cur = {"dir": m.group(1), "w0": None, "wav0_inf": None, "rtf": None,
                   "wav_count": None, "queue_wait": None, "wav0_name": None}
            continue
        if cur is None:
            continue
        if cur["w0"] is None:
            m2 = re.search(r"首响时间 \(First Audio Response\):\s*(\d+)ms", l)
            if m2:
                cur["w0"] = int(m2.group(1))
        if cur["wav0_inf"] is None:
            m3 = re.search(r"T2W线程: (wav_\d+\.wav).*?([\d.]+)ms\s+inference\s*\|\s*RTF=([\d.]+).*?queue_wait=([\d.]+)ms", l)
            if m3:
                cur["wav0_name"], cur["wav0_inf"], cur["rtf"], cur["queue_wait"] = \
                    m3.group(1), float(m3.group(2)), float(m3.group(3)), float(m3.group(4))
        m4 = re.search(r"T2W drain: complete \(wav_count=(\d+)", l)
        if m4 and cur["wav_count"] is None:
            cur["wav_count"] = int(m4.group(1))
    if cur is not None:
        rounds.append(cur)
    return rounds


def main():
    rounds = parse(LOG)
    print("Ordered round records parsed: %d (expect 33 = 1 warmup + 32)" % len(rounds))
    if len(rounds) < 33:
        print("ERROR: expected >=33 rounds, aborting"); return 1

    # Drop warmup (first round = round_9999). Then map in order to pairs.
    measured = rounds[1:33] if rounds[0]["dir"] == "9999" else rounds[0:32]

    arch = json.load(open(ARCHIVE_JSON))
    baseline = {}
    for e in arch:
        rnd = (e["order"] - 1) % 30
        baseline[(e["category"], rnd)] = e

    pairs = []
    i = 0
    for ci, case in enumerate(CASES):
        for rnd in range(N_ROUNDS):
            r = measured[i]; i += 1
            b = baseline.get((case, rnd), {})
            pairs.append({
                "case": case, "round": rnd,
                "cpu_w0_ms": b.get("W0_ms"),
                "cann_w0_ms": r["w0"],
                "delta_w0_ms": (r["w0"] - b["W0_ms"]) if (r["w0"] and b.get("W0_ms")) else None,
                "cpu_wav0_inf_ms": b.get("T2W_inf_ms"),
                "cann_wav0_inf_ms": r["wav0_inf"],
                "rtf": r["rtf"],
                "wav_count": r["wav_count"],
                "queue_wait_ms": r["queue_wait"],
                "dir": r["dir"], "wav0_name": r["wav0_name"],
            })
            print("  %-11s r%02d cpu_W0=%8s cann_W0=%8s dW0=%8s inf:%s->%s rtf=%s wavs=%s" % (
                case, rnd, b.get("W0_ms"), r["w0"],
                pairs[-1]["delta_w0_ms"] if pairs[-1]["delta_w0_ms"] is not None else "-",
                str(b.get("T2W_inf_ms")), r["wav0_inf"], r["rtf"], r["wav_count"]))

    json.dump(pairs, open(OUT_JSON, "w"), indent=1, ensure_ascii=False)

    # ---- Analysis ----
    valid = [p for p in pairs if p["cann_w0_ms"] and p["cpu_w0_ms"]]

    def pct(a, p):
        s = sorted(a)
        return s[min(int(len(s) * p / 100), len(s) - 1)]

    def show(label, arr):
        if not arr:
            print("  %-16s n=0" % label); return
        print("  %-16s n=%3d p50=%8.1f p90=%8.1f p95=%8.1f p99=%8.1f max=%8.1f" % (
            label, len(arr), statistics.median(arr), pct(arr, 90), pct(arr, 95),
            pct(arr, 99), max(arr)))

    cpu_w0 = [p["cpu_w0_ms"] for p in valid]
    cann_w0 = [p["cann_w0_ms"] for p in valid]
    dW0 = [p["delta_w0_ms"] for p in valid if p["delta_w0_ms"] is not None]
    print("\n=== RESULTS (n=%d valid matched pairs) ===" % len(valid))
    show("CPU W0 (arch S13)", cpu_w0)
    show("CANN T2W W0", cann_w0)
    show("dW0 (CANN-CPU)", dW0)
    if dW0 and cpu_w0:
        print("  median W0: %.0f -> %.0f ms  (%.1f%% reduction)" % (
            statistics.median(cpu_w0), statistics.median(cann_w0),
            100 * (1 - statistics.median(cann_w0) / statistics.median(cpu_w0))))

    print("\n  per-case median W0 (CPU -> CANN) and T2W wav0 inference:")
    for c in CASES:
        sub = [p for p in valid if p["case"] == c]
        if not sub:
            continue
        mc = statistics.median([p["cann_w0_ms"] for p in sub])
        mb = statistics.median([p["cpu_w0_ms"] for p in sub])
        inf_c = [p["cann_wav0_inf_ms"] for p in sub if p["cann_wav0_inf_ms"]]
        inf_b = [p["cpu_wav0_inf_ms"] for p in sub if p["cpu_wav0_inf_ms"]]
        rtf_c = [p["rtf"] for p in sub if p["rtf"]]
        print("  %-11s n=%2d  W0 %7.0f -> %6.0f ms (%.1f%% cut)   inf %s -> %s ms   rtf %s" % (
            c, len(sub), mb, mc, 100 * (1 - mc / mb) if mb else 0,
            (("%.0f" % statistics.median(inf_b)) if inf_b else "-"),
            (("%.0f" % statistics.median(inf_c)) if inf_c else "-"),
            (("%.2f" % statistics.median(rtf_c)) if rtf_c else "-")))

    # bootstrap 95% CI on median dW0
    import random
    if dW0:
        rnd = random.Random(42)
        meds = []
        for _ in range(10000):
            sample = [dW0[rnd.randrange(len(dW0))] for _ in range(len(dW0))]
            meds.append(statistics.median(sample))
        meds.sort()
        lo, hi = meds[250], meds[9750]
        print("\n  Bootstrap 95%% CI on median dW0: [%.0f, %.0f] ms (n_boot=10000)" % (lo, hi))

    # audio quality: check first wav of each round dir is valid 16-bit PCM
    import wave
    ok, bad = 0, []
    srs = set(); sws = set()
    for p in pairs:
        d = os.path.join(WAV_ROOT, "round_%s" % p["dir"], "tts_wav")
        if not os.path.isdir(d):
            bad.append((p["case"], p["round"], "no dir"))
            continue
        wavs = sorted(f for f in os.listdir(d) if f.endswith(".wav"))
        if not wavs:
            bad.append((p["case"], p["round"], "empty dir")); continue
        w0 = os.path.join(d, wavs[0])
        try:
            w = wave.open(w0, "rb")
            sr, sw, nch, nf = w.getframerate(), w.getsampwidth(), w.getnchannels(), w.getnframes()
            w.close()
            srs.add(sr); sws.add(sw); ok += 1
        except Exception as ex:
            bad.append((p["case"], p["round"], str(ex)))
    print("\n  WAV probe: %d/%d valid PCM, sample_rates=%s sampwidth=%s" % (ok, len(pairs), srs, sws))
    if bad:
        print("  unprobed: %s" % bad[:10])

    print("\nSaved -> %s" % OUT_JSON)
    return 0


if __name__ == "__main__":
    sys.exit(main())
