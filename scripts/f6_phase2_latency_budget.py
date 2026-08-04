#!/usr/bin/env python3
"""
F6 Phase 2 — Step 2: First-Audio Latency Budget from S13 120-request log.

Decomposes each request's request→W0 path using existing log markers:
  - D0            = "stream_decode 开始" wall time (decode start)
  - D_speak       = first "LLM->TTS:" wall time (speak-token commit to TTS)
  - TTS_start     = first "TTS Simplex Phase1:" wall time (audio-token gen start)
  - W0            = "首响时间 ... decode_to_first_audio=Xms" (direct)
  - T2W_inf       = first "T2W线程: wav_0.wav ... inference=Xms" (first chunk inference)
  - T2W_wav_count = count of T2W线程 wav lines

Budget decomposition (request→W0):
  prefill          = prefill_wall_ms (from JSON)
  LLM_to_speak     = D_speak - D0
  TTS_audio_gen    = TTS_start - D_speak   (approx; audio tokens for chunk 0)
  T2W_inference    = T2W_inf
  overhead         = W0 - LLM_to_speak - T2W_inference  (TTS audio-gen + queue + flow setup + write)
  (overhead ≈ TTS_audio_gen + flow/vocoder overhead + T2W submit + write)

Also computes: W0, decode_wall_ms, drain_span (first→last wav), per-category stats.
"""

import re
import json
import statistics
import sys

LOG = "docs/f6-s13-closure/raw-data/step7/s13_step7_full_server.log"
FINAL_JSON = "docs/f6-s13-closure/raw-data/step7/s13_step7_final.json"


def wall_to_sod(wall_str):
    """HH:MM:SS.mmm -> seconds since midnight."""
    parts = wall_str.split(":")
    h, mi = int(parts[0]), int(parts[1])
    s_ms = parts[2].split(".")
    s = int(s_ms[0])
    ms = int(s_ms[1]) if len(s_ms) > 1 else 0
    return h * 3600 + mi * 60 + s + ms / 1000.0


def parse_requests(log):
    """Extract per-request timing markers from the log."""
    lines = log.splitlines()
    requests = []
    cur = None

    for l in lines:
        m = re.match(r"(\d{2}:\d{2}:\d{2}\.\d{3})\s+(.*)", l)
        if not m:
            continue
        wall_str = m.group(1)
        body = m.group(2)
        sod = wall_to_sod(wall_str)

        if "stream_decode 开始" in body:
            if cur is not None:
                requests.append(cur)
            cur = {
                "D0_sod": sod,
                "D0": sod,
                "D_speak": None,
                "TTS_start": None,
                "W0_ms": None,
                "T2W_inf_ms": None,
                "T2W_t_ms": None,
                "wav_count": 0,
                "drain_span_s": 0.0,
                "last_wav_sod": None,
            }
        elif cur is not None:
            if cur["D_speak"] is None and "LLM->TTS:" in body:
                cur["D_speak"] = sod
                cur["D_speak_from_D0"] = sod - cur["D0"]
            elif cur["TTS_start"] is None and "TTS Simplex Phase1:" in body:
                cur["TTS_start"] = sod
                cur["TTS_start_from_D0"] = sod - cur["D0"]
            elif "首响时间" in body:
                # Format: 🎉 首响时间 (First Audio Response): 5121ms (decode_to_first_audio) | 0ms (request_to_first_audio)
                mw = re.search(r"First Audio Response\):\s*(\d+)ms", body)
                if mw:
                    cur["W0_ms"] = int(mw.group(1))
                mw2 = re.search(r"\|\s*(\d+)ms\s*\(request_to_first_audio\)", body)
                if mw2:
                    cur["req_to_W0_ms"] = int(mw2.group(1))
            elif "T2W线程" in body and "wav_" in body:
                mi = re.search(r"([\d.]+)ms\s+inference", body)
                mt = re.search(r"t=(\d+)ms", body)
                if cur["wav_count"] == 0:
                    if mi:
                        cur["T2W_inf_ms"] = float(mi.group(1))
                    if mt:
                        cur["T2W_t_ms"] = int(mt.group(1))
                cur["wav_count"] += 1
                cur["last_wav_sod"] = sod
            elif "F6 S13: decode complete" in body:
                md = re.search(r"generated=(\d+) tokens", body)
                if md:
                    cur["gen_tokens"] = int(md.group(1))
                cur["drain_span_s"] = (cur["last_wav_sod"] - cur["D0"]) if cur["last_wav_sod"] else None
    if cur is not None:
        requests.append(cur)
    return requests


def pct(arr, p):
    if not arr:
        return None
    a = sorted(arr)
    return a[min(int(len(a) * p / 100), len(a) - 1)]


def stats(arr, label):
    if not arr:
        print("  %-28s n=0" % label)
        return
    print("  %-28s n=%3d  p50=%8.0f  p90=%8.0f  p95=%8.0f  p99=%8.0f  max=%8.0f" % (
        label, len(arr),
        statistics.median(arr), pct(arr, 90), pct(arr, 95), pct(arr, 99), max(arr)))


def main():
    log = open(LOG, encoding="utf-8", errors="replace").read()
    reqs = parse_requests(log)
    print("Parsed %d decode requests from log" % len(reqs))

    # Load final JSON for prefill + category alignment
    fin = json.load(open(FINAL_JSON))
    results = fin["all_results"]
    # request_order is 1..N; the log requests are in same order. Align by index.
    # Log may have warmups before the 120. Match by counting non-warmup requests.
    # final JSON request_order starts at 1. We take the LAST 120 requests from log
    # (skip leading warmups) — but verify count.
    print("JSON results: %d" % len(results))
    if len(reqs) > len(results):
        print("Log has %d extra requests (warmups) — dropping leading %d" % (
            len(reqs), len(reqs) - len(results)))
        reqs = reqs[len(reqs) - len(results):]

    # Build per-request budget
    budget = []
    for i, (r, res) in enumerate(zip(reqs, results)):
        W0 = r.get("W0_ms")
        if W0 is None:
            W0 = r.get("T2W_t_ms")  # fallback: first T2W t == decode_to_first_audio
        d_speak = r.get("D_speak_from_D0")
        t2w_inf = r.get("T2W_inf_ms")
        tts_start = r.get("TTS_start_from_D0")

        entry = {
            "order": i + 1,
            "category": res.get("category"),
            "audio": res.get("audio"),
            "prefill_ms": res.get("prefill_wall_ms"),
            "decode_wall_ms": res.get("decode_wall_ms"),
            "W0_ms": W0,
            "LLM_to_speak_ms": (d_speak * 1000.0) if d_speak is not None else None,
            "TTS_start_from_D0_ms": (tts_start * 1000.0) if tts_start is not None else None,
            "T2W_inf_ms": t2w_inf,
            "wav_count": r.get("wav_count", 0),
            "gen_tokens": r.get("gen_tokens"),
            "drain_span_s": r.get("drain_span_s"),
            "overhead_ms": None,
        }
        # overhead = W0 - LLM_to_speak - T2W_inf  (includes TTS audio-gen + queue + flow setup + write)
        if W0 is not None and d_speak is not None and t2w_inf is not None:
            entry["overhead_ms"] = W0 - d_speak * 1000.0 - t2w_inf
        budget.append(entry)

    # ── Report ──
    valid = [b for b in budget if b["W0_ms"] is not None]
    print()
    print("=" * 78)
    print("REQUEST → W0 LATENCY BUDGET (from S13 log, n=%d)" % len(valid))
    print("=" * 78)

    print("\n── Request→W0 decomposition (p50 by category) ──")
    cats = ["short_cn", "long_cn", "english", "number_mix"]
    header = "  %-11s %8s %10s %10s %10s %10s %8s" % (
        "cat", "prefill", "LLM→speak", "T2W_inf", "overhead", "W0", "wavs")
    print(header)
    print("  " + "-" * (len(header) - 2))
    all_prefill, all_speak, all_inf, all_overhead, all_W0, all_wavs = [], [], [], [], [], []
    for c in cats:
        sub = [b for b in valid if b["category"] == c]
        if not sub:
            continue
        def med(key):
            vals = [b[key] for b in sub if b.get(key) is not None]
            return statistics.median(vals) if vals else float("nan")
        ovh = [b["overhead_ms"] for b in sub if b["overhead_ms"] is not None]
        all_prefill += [b["prefill_ms"] for b in sub]
        all_speak += [b["LLM_to_speak_ms"] for b in sub if b["LLM_to_speak_ms"] is not None]
        all_inf += [b["T2W_inf_ms"] for b in sub if b["T2W_inf_ms"] is not None]
        all_overhead += ovh
        all_W0 += [b["W0_ms"] for b in sub]
        all_wavs += [b["wav_count"] for b in sub]
        print("  %-11s %8.0f %10.0f %10.0f %10.0f %10.0f %8.0f" % (
            c, med("prefill_ms"), med("LLM_to_speak_ms"), med("T2W_inf_ms"),
            statistics.median(ovh) if ovh else 0, med("W0_ms"), med("wav_count")))

    print()
    print("── Pooled statistics (all categories) ──")
    stats(all_prefill, "prefill_ms")
    stats(all_speak, "LLM→speak (decode→first speak commit)")
    stats(all_inf, "T2W_inference (first chunk)")
    stats(all_overhead, "overhead (TTS audio-gen+queue+write)")
    stats(all_W0, "W0 (decode→first audio)")
    stats(all_wavs, "wav_count")

    # Budget share
    if all_W0:
        w0_med = statistics.median(all_W0)
        print("\n── Budget share of W0 (pooled median) ──")
        comps = [
            ("prefill", all_prefill),
            ("LLM→speak", all_speak),
            ("T2W_inference", all_inf),
            ("overhead", all_overhead),
        ]
        for name, arr in comps:
            if arr:
                print("  %-16s %8.0f ms  %6.1f%% of W0" % (
                    name, statistics.median(arr), 100 * statistics.median(arr) / w0_med))

        print("\n  NOTE: prefill is NOT part of W0 (W0 counts from decode start).")
        print("  request→W0 = prefill + W0 = %.0f + %.0f = %.0f ms" % (
            statistics.median(all_prefill), w0_med,
            statistics.median(all_prefill) + w0_med))

    # ── Save per-request budget as JSON ──
    import os
    out_json = "docs/f6-s13-closure/phase2/step2_latency_budget.json"
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    json.dump(budget, open(out_json, "w"), indent=1, ensure_ascii=False)
    print("\nSaved %d per-request budget rows -> %s" % (len(budget), out_json))

    # ── Full table ──
    print("\n── Per-request (first 20) ──")
    print("  %3s %-10s %8s %10s %10s %10s %10s %6s %6s" % (
        "ord", "cat", "prefill", "LLM→spk", "T2W_inf", "ovh", "W0", "wavs", "toks"))
    for b in budget[:20]:
        print("  %3d %-10s %8.0f %10.0f %10.0f %10.0f %10.0f %6d %6s" % (
            b["order"], b["category"],
            b["prefill_ms"] or 0, b["LLM_to_speak_ms"] or -1,
            b["T2W_inf_ms"] or -1, b["overhead_ms"] or -1,
            b["W0_ms"] or -1, b["wav_count"], b["gen_tokens"] or "?"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
