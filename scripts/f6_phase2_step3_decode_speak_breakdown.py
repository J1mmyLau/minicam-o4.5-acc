#!/usr/bin/env python3
"""
F6 Phase 2 — Step 3: Decode→Speak segment breakdown from S13 log.

Decomposes the request's speak path into the sub-segments that ARE
instrumented in the S13 log:

  D0           "stream_decode 开始"
  prep         "assistant prompt 完成"          (LLM pre-decode: prompt append/KV reuse)
  speak        first "LLM->TTS:"               (first speak-token commit to TTS queue)
  audio_start  first "TTS Simplex Phase1: token 1/500"  (TTS audio-decoder begins)
  chunk_ready  "yield 25 tokens 到 T2W"        (first 25 audio tokens generated)
  t2w_start    first "T2W(C++) dequeued"       (T2W worker picks up the chunk)
  t2w_inf      first "T2W线程: wav_0.wav ... inference=Xms"  (flow+vocoder for chunk 0)
  W0           "首响时间 ... decode_to_first_audio=Xms"

Sub-segment spans (all ms, relative to D0 unless noted):
  decode_prepare     = prep    - D0          (~21ms: prompt append, no re-prefill; KV HIT)
  decode_to_speak    = speak   - D0          (p50 142ms: the Phase-2 "LLM Decode→Speak Token")
  speak_to_audio     = audio_start - speak   (TTS queue + audio model/sampler setup)
  tts_audio_gen      = chunk_ready - audio_start (TTS audio decoder: 25 tokens)
  queue_to_t2w       = t2w_start - chunk_ready   (T2W queue hand-off)
  t2w_inference      = t2w_inf value             (flow+vocoder, the 93% cost)

Internal decode-loop categories (MAIN_LLM_FORWARD/LOGITS/SAMPLING/TOKEN_COMMIT/
STOP_CHECK/TALKER_TRIGGER_CHECK/THREAD_WAKE/QUEUE_WAIT/CV_WAIT/STREAM_SYNC/
ALLOCATION/UNKNOWN) are NOT instrumented in the S13 log — documented as
DEFER under Amdahl (see doc; total segment = 2.9% of W0).
"""

import re
import json
import statistics
import sys

LOG = "docs/f6-s13-closure/raw-data/step7/s13_step7_full_server.log"
FINAL_JSON = "docs/f6-s13-closure/raw-data/step7/s13_step7_final.json"
OUT_JSON = "docs/f6-s13-closure/phase2/step3_decode_speak_breakdown.json"


def wall_to_sod(wall_str):
    parts = wall_str.split(":")
    h, mi = int(parts[0]), int(parts[1])
    s_ms = parts[2].split(".")
    s = int(s_ms[0])
    ms = int(s_ms[1]) if len(s_ms) > 1 else 0
    return h * 3600 + mi * 60 + s + ms / 1000.0


def parse_requests(log):
    lines = log.splitlines()
    reqs = []
    cur = None
    for l in lines:
        m = re.match(r"(\d{2}:\d{2}:\d{2}\.\d{3})\s+(.*)", l)
        if not m:
            continue
        wall_str, body = m.group(1), m.group(2)
        sod = wall_to_sod(wall_str)

        if "stream_decode 开始" in body:
            if cur is not None:
                reqs.append(cur)
            cur = {
                "D0": sod, "prep": None, "speak": None,
                "audio_start": None, "chunk_ready": None,
                "t2w_start": None, "t2w_inf": None, "W0": None,
            }
        elif cur is not None:
            if cur["prep"] is None and "assistant prompt 完成" in body:
                cur["prep"] = sod
            elif cur["speak"] is None and "LLM->TTS:" in body:
                cur["speak"] = sod
            elif cur["audio_start"] is None and "TTS Simplex Phase1: token 1/500" in body:
                cur["audio_start"] = sod
            elif cur["chunk_ready"] is None and "yield 25 tokens 到 T2W" in body:
                cur["chunk_ready"] = sod
            elif cur["t2w_start"] is None and "T2W(C++) dequeued" in body:
                cur["t2w_start"] = sod
            elif cur["t2w_inf"] is None and "T2W线程" in body and "wav_0.wav" in body:
                mi = re.search(r"([\d.]+)ms\s+inference", body)
                if mi:
                    cur["t2w_inf"] = float(mi.group(1))
            elif cur["W0"] is None and "首响时间" in body:
                mw = re.search(r"First Audio Response\):\s*(\d+)ms", body)
                if mw:
                    cur["W0"] = int(mw.group(1))
    if cur is not None:
        reqs.append(cur)
    return reqs


def pct(arr, p):
    if not arr:
        return None
    a = sorted(arr)
    return a[min(int(len(a) * p / 100), len(a) - 1)]


def stats(arr, label):
    if not arr:
        print("  %-22s n=0" % label)
        return
    print("  %-22s n=%3d  p50=%7.0f  p90=%7.0f  p95=%7.0f  p99=%7.0f  max=%7.0f" % (
        label, len(arr), statistics.median(arr), pct(arr, 90),
        pct(arr, 95), pct(arr, 99), max(arr)))


def main():
    log = open(LOG, encoding="utf-8", errors="replace").read()
    reqs = parse_requests(log)
    fin = json.load(open(FINAL_JSON))
    results = fin["all_results"]
    if len(reqs) > len(results):
        reqs = reqs[len(reqs) - len(results):]

    rows = []
    for i, (r, res) in enumerate(zip(reqs, results)):
        def span(ks):
            """ms from D0 to marker ks (list of keys); None if any missing."""
            sod = r.get(ks[0])
            if sod is None:
                return None
            return (sod - r["D0"]) * 1000.0

        row = {
            "order": i + 1,
            "category": res.get("category"),
            "audio": res.get("audio"),
            "decode_prepare_ms": span(["prep"]),
            "decode_to_speak_ms": span(["speak"]),          # == LLM→speak
            "speak_to_audio_ms": (
                (r["audio_start"] - r["speak"]) * 1000.0
                if r["audio_start"] and r["speak"] else None),
            "tts_audio_gen_ms": (
                (r["chunk_ready"] - r["audio_start"]) * 1000.0
                if r["chunk_ready"] and r["audio_start"] else None),
            "queue_to_t2w_ms": (
                (r["t2w_start"] - r["chunk_ready"]) * 1000.0
                if r["t2w_start"] and r["chunk_ready"] else None),
            "t2w_inference_ms": r["t2w_inf"],
            "W0_ms": r["W0"],
        }
        rows.append(row)

    json.dump(rows, open(OUT_JSON, "w"), indent=1, ensure_ascii=False)

    def col(key, label):
        vals = [b[key] for b in rows if b.get(key) is not None]
        stats(vals, label)

    print("=" * 76)
    print("SPEAK-PATH SEGMENT BREAKDOWN (S13 log, n=%d requests)" % len(rows))
    print("=" * 76)
    print("\n── Pooled (all 4 case types) ──")
    col("decode_prepare_ms", "prep: D0→prompt done")
    col("decode_to_speak_ms", "decode→speak commit")
    col("speak_to_audio_ms", "speak→TTS audio start")
    col("tts_audio_gen_ms", "TTS audio-gen (25 toks)")
    col("queue_to_t2w_ms", "queue→T2W dequeued")
    col("t2w_inference_ms", "T2W inference (chunk0)")
    col("W0_ms", "W0 (decode→first audio)")

    print("\n── By case type (p50, ms) ──")
    header = "  %-11s %8s %10s %10s %10s %10s %10s %8s" % (
        "cat", "prep", "decode→spk", "spk→aud", "aud-gen", "q→t2w", "t2w_inf", "W0")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for c in ["short_cn", "long_cn", "english", "number_mix"]:
        sub = [b for b in rows if b["category"] == c]
        def med(key):
            vals = [b[key] for b in sub if b.get(key) is not None]
            return statistics.median(vals) if vals else float("nan")
        print("  %-11s %8.0f %10.0f %10.0f %10.0f %10.0f %10.0f %8.0f" % (
            c, med("decode_prepare_ms"), med("decode_to_speak_ms"),
            med("speak_to_audio_ms"), med("tts_audio_gen_ms"),
            med("queue_to_t2w_ms"), med("t2w_inference_ms"), med("W0_ms")))

    print("\n── Amdahl cap of the decode→speak segment ──")
    ws = [b["W0_ms"] for b in rows if b.get("W0_ms")]
    ds = [b["decode_to_speak_ms"] for b in rows if b.get("decode_to_speak_ms")]
    if ws and ds:
        print("  W0 p50 = %.0f ms ; decode→speak p50 = %.0f ms (%.1f%%)" % (
            statistics.median(ws), statistics.median(ds),
            100 * statistics.median(ds) / statistics.median(ws)))
        print("  Even at zero cost, decode→speak frees <= %.0f ms of W0." % statistics.median(ds))
    print("\nSaved %d rows -> %s" % (len(rows), OUT_JSON))
    return 0


if __name__ == "__main__":
    sys.exit(main())
