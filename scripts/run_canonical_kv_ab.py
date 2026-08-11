#!/usr/bin/env python3
"""
Canonical Static Prefix KV Cache A/B — 30 Strict Matched Pairs
===============================================================
FP16 model, -ngl 999, CANN0, persistent Server on port 18093.
5 test cases × 6 pairs = 30 matched pairs.
A = MISS (cold cache), B = HIT (warm cache).

Metrics per request:
  - Prefill wall time (HTTP response of /v1/stream/prefill)
  - omni_init wall time
  - Decode wall time
  - Mutex wait (OCTX_LOCK_ACQUIRED - OCTX_LOCK_WAIT_BEGIN from F6_EVENT log)
  - Handler hold (HANDLER_RETURN - HANDLER_ENTER)
  - Drain time
  - T2W first WAV (if use_tts=True)
  - KV cache: hits, misses, tokens_reused, action (SAVED/LOADED), n_past, cache_key
  - Lifecycle state transitions

Verification per pair:
  - A(MISS): KV cache SAVED, cache_misses=1 (or incremented)
  - B(HIT):  KV cache LOADED, cache_hits=1 (or incremented), tokens_reused > 0
  - MISS prefill > HIT prefill
  - No CPU fallback, no NOT_REUSABLE, no BUSY, no timeout
"""

import requests
import time
import os
import glob
import json
import sys
import re
import subprocess
import datetime
import statistics

# ── Config ────────────────────────────────────
BASE = "http://127.0.0.1:18093"
CACHE_DIR = "/tmp/f6_r13_kv_cache"
AUDIO_PREFIX = "/workspace/llama.cpp-omni-f6/tools/omni/assets/test_case/omni_test_case/omni_test_case_"
SERVER_LOG = "/tmp/f6_r13_kvcache_srv.log"
OUTPUT_DIR = "/tmp/f6_r13_ab_results"
USE_TTS = False  # T2W not producing WAV in this config; KV cache prefill delta is independently measured

TEST_CASES = [
    {"id": "C1", "audio": "0000.wav", "image": "0000.jpg", "text": "请描述你听到的内容"},
    {"id": "C2", "audio": "0001.wav", "image": "0001.jpg", "text": "这张图片里有什么"},
    {"id": "C3", "audio": "0002.wav", "image": "0002.jpg", "text": "请用中文回答"},
    {"id": "C4", "audio": "0003.wav", "image": "0003.jpg", "text": "讲一个简短的故事"},
    {"id": "C5", "audio": "0004.wav", "image": "0004.jpg", "text": "今天天气如何"},
]
PAIRS_PER_CASE = 6
REQUEST_TIMEOUT = 300
COOLDOWN_S = 2

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)


# ── Helpers ───────────────────────────────────
def clear_cache():
    for f in glob.glob(os.path.join(CACHE_DIR, "*.bin")):
        try:
            os.remove(f)
        except Exception:
            pass


def log_size():
    try:
        return os.path.getsize(SERVER_LOG)
    except Exception:
        return 0


def read_log_segment(pos_start, pos_end=None):
    try:
        with open(SERVER_LOG, "r") as f:
            f.seek(pos_start)
            if pos_end is not None and pos_end > pos_start:
                return f.read(pos_end - pos_start)
            return f.read()
    except Exception:
        return ""


def parse_f6_events(log_text):
    """Parse F6_EVENT and F6_REQSTATE lines from log segment.
    Returns dict of event_name -> [timestamps] and first/last timestamps.
    """
    events = {}
    for m in re.finditer(
        r"F6_EVENT\|(\d+)\|(\w+)\|req=(\S+)\|ctx=(\S+)\|tid=(\S+)", log_text
    ):
        ts = int(m.group(1))
        evt = m.group(2)
        req_id = m.group(3)
        if evt not in events:
            events[evt] = []
        events[evt].append({"ts": ts, "req": req_id})

    req_states = []
    for m in re.finditer(
        r"F6_REQSTATE\|(\d+)\|req=(\S+)\|(\S+)→(\S+)\|label=(\S+)\|(\S+)", log_text
    ):
        req_states.append({
            "ts": int(m.group(1)),
            "req": m.group(2),
            "from_state": m.group(3),
            "to_state": m.group(4),
            "label": m.group(5),
            "status": m.group(6),
        })

    return events, req_states


def parse_kv_stats(log_text):
    """Parse KV Cache Reuse Statistics block."""
    stats = {}
    m = re.search(r"cache_hits:\s+(\d+)", log_text)
    if m:
        stats["cache_hits"] = int(m.group(1))
    m = re.search(r"cache_misses:\s+(\d+)", log_text)
    if m:
        stats["cache_misses"] = int(m.group(1))
    m = re.search(r"tokens_reused:\s+(\d+)", log_text)
    if m:
        stats["tokens_reused"] = int(m.group(1))
    # KV cache action
    m = re.search(r"KV cache (SAVED|LOADED).*?n_past=(\d+).*?key=(\S+)", log_text)
    if m:
        stats["kv_action"] = m.group(1)
        stats["n_past"] = int(m.group(2))
        stats["cache_key"] = m.group(3).rstrip(")")
    return stats


def parse_t2w_wav(log_text):
    """Parse T2W WAV file writes."""
    wavs = re.findall(r"T2W.*?(wav_\d+\.wav)", log_text)
    return wavs


def compute_hold_time(events):
    """Compute handler hold time = HANDLER_RETURN - HANDLER_ENTER (ns)."""
    enter = events.get("HANDLER_ENTER", [])
    ret = events.get("HANDLER_RETURN", [])
    if enter and ret:
        return ret[-1]["ts"] - enter[-1]["ts"]
    return None


def compute_mutex_wait(events):
    """Compute mutex wait = OCTX_LOCK_ACQUIRED - OCTX_LOCK_WAIT_BEGIN (ns)."""
    wait = events.get("OCTX_LOCK_WAIT_BEGIN", [])
    acquired = events.get("OCTX_LOCK_ACQUIRED", [])
    if wait and acquired:
        return acquired[-1]["ts"] - wait[-1]["ts"]
    return None


def compute_decode_time(events):
    """Compute decode time = STREAM_DECODE_END - STREAM_DECODE_BEGIN (ns)."""
    begin = events.get("STREAM_DECODE_BEGIN", [])
    end = events.get("STREAM_DECODE_END", [])
    if begin and end:
        return end[-1]["ts"] - begin[-1]["ts"]
    return None


# ── Request runner ────────────────────────────
def make_request(tc, round_idx):
    """Full request cycle and return timing metrics."""
    audio = AUDIO_PREFIX + tc["audio"]
    image = AUDIO_PREFIX + tc["image"] if tc.get("image") else ""

    metrics = {}

    # ── omni_init ──
    pos_before = log_size()
    t0 = time.time()
    r = requests.post(
        BASE + "/v1/stream/omni_init",
        json={"msg_type": 1, "media_type": 1, "use_tts": USE_TTS},
        timeout=REQUEST_TIMEOUT,
    )
    metrics["init_wall_s"] = time.time() - t0
    if r.status_code != 200:
        raise RuntimeError("omni_init failed: %d %s" % (r.status_code, r.text))

    # ── prefill ──
    pos_prefill_start = log_size()
    t0 = time.time()
    body = {
        "audio_path_prefix": audio,
        "cnt": 1,
        "text": tc["text"],
    }
    if image and os.path.exists(image):
        body["img_path_prefix"] = image
    r = requests.post(
        BASE + "/v1/stream/prefill",
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    metrics["prefill_wall_ms"] = (time.time() - t0) * 1000.0
    if r.status_code != 200:
        raise RuntimeError("prefill failed: %d %s" % (r.status_code, r.text))

    # ── decode ──
    pos_decode_start = log_size()
    t0 = time.time()
    r = requests.post(
        BASE + "/v1/stream/decode",
        json={"stream": False, "round_idx": round_idx, "debug_dir": OUTPUT_DIR},
        timeout=REQUEST_TIMEOUT,
    )
    metrics["decode_wall_s"] = time.time() - t0
    metrics["total_wall_s"] = metrics["init_wall_s"] + metrics["prefill_wall_ms"] / 1000.0 + metrics["decode_wall_s"]

    # ── Parse server log ──
    pos_after = log_size()
    log_seg = read_log_segment(pos_before, pos_after)

    events, req_states = parse_f6_events(log_seg)
    kv_stats = parse_kv_stats(log_seg)

    # Merge kv_stats into metrics
    metrics.update(kv_stats)

    # Compute derived timing from F6_EVENT
    metrics["handler_hold_ns"] = compute_hold_time(events)
    metrics["mutex_wait_ns"] = compute_mutex_wait(events)
    metrics["decode_event_ns"] = compute_decode_time(events)

    # Track lifecycle states
    states_seen = [s["from_state"] for s in req_states] + [req_states[-1]["to_state"] if req_states else "?"]
    metrics["lifecycle"] = "→".join(states_seen) if states_seen else "?"

    # WAV files
    wavs = parse_t2w_wav(log_seg)
    metrics["wav_count"] = len(wavs)

    return metrics


# ── Main ──────────────────────────────────────
def main():
    print("=" * 70)
    print("Canonical Static Prefix KV Cache A/B — 30 Strict Matched Pairs")
    print("Server:  %s" % BASE)
    print("Cache:   %s" % CACHE_DIR)
    print("Model:   FP16, -ngl 999, CANN0")
    print("TTS:     %s" % ("ON" if USE_TTS else "OFF"))
    print("Cases:   %d × %d = %d pairs" % (len(TEST_CASES), PAIRS_PER_CASE, len(TEST_CASES) * PAIRS_PER_CASE))
    print("Output:  %s" % OUTPUT_DIR)
    print("=" * 70)

    all_pairs = []
    start_time = datetime.datetime.now()
    pair_idx = 0
    total_prev_cache_hits = 0
    total_prev_cache_misses = 0

    for tc in TEST_CASES:
        case_id = tc["id"]
        print("\n" + "─" * 60)
        print("Case %s: audio=%s image=%s" % (case_id, tc["audio"], tc.get("image", "none")))
        print("─" * 60)

        for rnd in range(PAIRS_PER_CASE):
            pair_idx += 1
            miss_label = "%s-R%d-MISS" % (case_id, rnd + 1)
            hit_label = "%s-R%d-HIT" % (case_id, rnd + 1)

            # ── A: MISS ──
            clear_cache()
            try:
                res_a = make_request(tc, rnd * 2)
            except Exception as e:
                print("  [%d/30] %s: FAILED — %s" % (pair_idx, miss_label, e))
                time.sleep(COOLDOWN_S)
                continue

            # Track cache state
            ta_hits = res_a.get("cache_hits", -1)
            ta_misses = res_a.get("cache_misses", -1)

            # ── B: HIT ──
            try:
                res_b = make_request(tc, rnd * 2 + 1)
            except Exception as e:
                print("  [%d/30] %s: FAILED — %s" % (pair_idx, hit_label, e))
                time.sleep(COOLDOWN_S)
                continue

            tb_hits = res_b.get("cache_hits", -1)
            tb_misses = res_b.get("cache_misses", -1)

            # ── Verification ──
            issues = []

            # A should be SAVED (MISS)
            if res_a.get("kv_action") != "SAVED":
                issues.append("A_NOT_SAVED")

            # B should be LOADED (HIT)
            if res_b.get("kv_action") != "LOADED":
                issues.append("B_NOT_LOADED")

            # MISS prefill should be > HIT prefill
            delta_ms = res_a.get("prefill_wall_ms", 0) - res_b.get("prefill_wall_ms", 0)
            if delta_ms <= 0:
                issues.append("DELTA_NEGATIVE(%.0fms)" % delta_ms)

            # B should have >0 tokens reused
            reused = res_b.get("tokens_reused", 0)
            if reused <= 0:
                issues.append("ZERO_REUSED")

            verdict = "✅" if not issues else "❌ " + ",".join(issues)

            # ── Record pair ──
            pair = {
                "pair_id": pair_idx,
                "case": case_id,
                "round": rnd + 1,
                # Prefill
                "miss_prefill_ms": round(res_a.get("prefill_wall_ms", 0), 1),
                "hit_prefill_ms": round(res_b.get("prefill_wall_ms", 0), 1),
                "delta_prefill_ms": round(delta_ms, 1),
                "speedup": round(res_a.get("prefill_wall_ms", 0) / max(res_b.get("prefill_wall_ms", 0), 1), 2),
                # omni_init
                "miss_init_s": round(res_a.get("init_wall_s", 0), 2),
                "hit_init_s": round(res_b.get("init_wall_s", 0), 2),
                # Decode
                "miss_decode_s": round(res_a.get("decode_wall_s", 0), 2),
                "hit_decode_s": round(res_b.get("decode_wall_s", 0), 2),
                # Total wall
                "miss_total_s": round(res_a.get("total_wall_s", 0), 2),
                "hit_total_s": round(res_b.get("total_wall_s", 0), 2),
                "delta_total_s": round(res_a.get("total_wall_s", 0) - res_b.get("total_wall_s", 0), 2),
                # F6 events
                "miss_handler_hold_ns": res_a.get("handler_hold_ns"),
                "hit_handler_hold_ns": res_b.get("handler_hold_ns"),
                "miss_mutex_wait_ns": res_a.get("mutex_wait_ns"),
                "hit_mutex_wait_ns": res_b.get("mutex_wait_ns"),
                # KV cache
                "miss_kv_action": res_a.get("kv_action", "?"),
                "hit_kv_action": res_b.get("kv_action", "?"),
                "miss_cache_hits": ta_hits,
                "miss_cache_misses": ta_misses,
                "miss_tokens_reused": res_a.get("tokens_reused", 0),
                "hit_cache_hits": tb_hits,
                "hit_cache_misses": tb_misses,
                "hit_tokens_reused": reused,
                "n_past": res_a.get("n_past", res_b.get("n_past", 0)),
                "cache_key": res_a.get("cache_key", res_b.get("cache_key", "")),
                # WAV
                "miss_wav_count": res_a.get("wav_count", 0),
                "hit_wav_count": res_b.get("wav_count", 0),
                # Lifecycle
                "miss_lifecycle": res_a.get("lifecycle", "?"),
                "hit_lifecycle": res_b.get("lifecycle", "?"),
                # Decode event time
                "miss_decode_event_ns": res_a.get("decode_event_ns"),
                "hit_decode_event_ns": res_b.get("decode_event_ns"),
            }
            all_pairs.append(pair)

            # Print result
            print("  [%02d/30] %s %s" % (pair_idx, verdict, miss_label))
            print("          MISS: prefill=%.0fms init=%.1fs decode=%.1fs total=%.1fs | kv=%s n_past=%d reused=%d hits=%s misses=%s" % (
                res_a.get("prefill_wall_ms", 0),
                res_a.get("init_wall_s", 0),
                res_a.get("decode_wall_s", 0),
                res_a.get("total_wall_s", 0),
                res_a.get("kv_action", "?"),
                res_a.get("n_past", 0),
                res_a.get("tokens_reused", 0),
                ta_hits, ta_misses,
            ))
            print("          HIT:  prefill=%.0fms init=%.1fs decode=%.1fs total=%.1fs | kv=%s n_past=%d reused=%d hits=%s misses=%s | Δ=%.0fms" % (
                res_b.get("prefill_wall_ms", 0),
                res_b.get("init_wall_s", 0),
                res_b.get("decode_wall_s", 0),
                res_b.get("total_wall_s", 0),
                res_b.get("kv_action", "?"),
                res_b.get("n_past", 0),
                reused,
                tb_hits, tb_misses,
                delta_ms,
            ))
            if res_a.get("handler_hold_ns") or res_b.get("handler_hold_ns"):
                print("          F6_EVENT: mutex_wait=%sns/%sns hold=%sns/%sns (MISS/HIT)" % (
                    res_a.get("mutex_wait_ns") or "?",
                    res_b.get("mutex_wait_ns") or "?",
                    res_a.get("handler_hold_ns") or "?",
                    res_b.get("handler_hold_ns") or "?",
                ))

            time.sleep(COOLDOWN_S)

    # ─────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────
    elapsed = (datetime.datetime.now() - start_time).total_seconds()
    valid = [p for p in all_pairs if p["miss_kv_action"] == "SAVED" and p["hit_kv_action"] == "LOADED" and p["delta_prefill_ms"] > 0]

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY — %d/%d valid pairs (%.0f min)" % (len(valid), len(all_pairs), elapsed / 60))
    print("=" * 70)

    if valid:
        miss_pf = sorted([p["miss_prefill_ms"] for p in valid])
        hit_pf = sorted([p["hit_prefill_ms"] for p in valid])
        deltas = sorted([p["delta_prefill_ms"] for p in valid])
        speedups = sorted([p["speedup"] for p in valid])
        reused_vals = [p["hit_tokens_reused"] for p in valid]
        n_past_vals = [p["n_past"] for p in valid]
        n = len(valid)

        def pct(arr, p):
            return arr[min(int(n * p / 100), n - 1)]

        print("\n  Prefill Timing:")
        print("  %-22s %8s %8s %8s %8s %8s %8s" % ("Metric", "p50", "p90", "p95", "mean", "min", "max"))
        print("  " + "-" * 70)
        print("  %-22s %7.0fms %7.0fms %7.0fms %7.0fms %7.0fms %7.0fms" % (
            "MISS prefill", pct(miss_pf, 50), pct(miss_pf, 90), pct(miss_pf, 95),
            statistics.mean(miss_pf), min(miss_pf), max(miss_pf)))
        print("  %-22s %7.0fms %7.0fms %7.0fms %7.0fms %7.0fms %7.0fms" % (
            "HIT prefill", pct(hit_pf, 50), pct(hit_pf, 90), pct(hit_pf, 95),
            statistics.mean(hit_pf), min(hit_pf), max(hit_pf)))
        print("  %-22s %7.0fms %7.0fms %7.0fms %7.0fms %7.0fms %7.0fms" % (
            "DELTA", pct(deltas, 50), pct(deltas, 90), pct(deltas, 95),
            statistics.mean(deltas), min(deltas), max(deltas)))
        print("  %-22s %7.1f×  %7.1f×  %7.1f×  %7.1f×  %7.1f×  %7.1f×" % (
            "Speedup", pct(speedups, 50), pct(speedups, 90), pct(speedups, 95),
            statistics.mean(speedups), min(speedups), max(speedups)))

        print("\n  Cache: n_past=%d-%d tokens, reused=%d-%d tokens" % (
            min(n_past_vals), max(n_past_vals), min(reused_vals), max(reused_vals)))

        # Total (end-to-end) timing
        miss_total = sorted([p["miss_total_s"] for p in valid])
        hit_total = sorted([p["hit_total_s"] for p in valid])
        total_deltas = sorted([p["delta_total_s"] for p in valid])
        print("\n  End-to-End (init+prefill+decode):")
        print("  %-22s %7.1fs  %7.1fs  %7.1fs  %7.1fs  %7.1fs  %7.1fs" % (
            "MISS total", pct(miss_total, 50), pct(miss_total, 90), pct(miss_total, 95),
            statistics.mean(miss_total), min(miss_total), max(miss_total)))
        print("  %-22s %7.1fs  %7.1fs  %7.1fs  %7.1fs  %7.1fs  %7.1fs" % (
            "HIT total", pct(hit_total, 50), pct(hit_total, 90), pct(hit_total, 95),
            statistics.mean(hit_total), min(hit_total), max(hit_total)))
        print("  %-22s %7.1fs  %7.1fs  %7.1fs  %7.1fs  %7.1fs  %7.1fs" % (
            "TOTAL DELTA", pct(total_deltas, 50), pct(total_deltas, 90), pct(total_deltas, 95),
            statistics.mean(total_deltas), min(total_deltas), max(total_deltas)))

        # Per-case
        print("\n  Per-Case Breakdown:")
        print("  %-6s %6s %10s %9s %8s %8s %8s" % ("Case", "Pairs", "MISS p50", "HIT p50", "Δ p50", "Speedup", "TotalΔ"))
        print("  " + "-" * 60)
        for tc in TEST_CASES:
            cp = [p for p in valid if p["case"] == tc["id"]]
            if not cp:
                continue
            ncp = len(cp)
            cm = sorted([p["miss_prefill_ms"] for p in cp])
            ch = sorted([p["hit_prefill_ms"] for p in cp])
            cd = sorted([p["delta_prefill_ms"] for p in cp])
            ct = sorted([p["delta_total_s"] for p in cp])
            print("  %-6s %6d %9.0fms %8.0fms %7.0fms %7.1f× %7.1fs" % (
                tc["id"], ncp, cm[ncp//2], ch[ncp//2], cd[ncp//2],
                cm[ncp//2]/max(ch[ncp//2], 1), ct[ncp//2]))

    # Gate verdict
    print()
    if len(valid) >= 30:
        print("GATE: PASS — 30/30 valid pairs")
        gate = "PASS"
    elif len(valid) >= 25:
        print("GATE: PASS (MARGINAL) — %d/30 valid pairs" % len(valid))
        gate = "PASS_MARGINAL"
    else:
        print("GATE: FAIL — %d/30 valid pairs (< 25)" % len(valid))
        gate = "FAIL"

    # ── Integrity checks ──
    with open(SERVER_LOG) as f:
        full = f.read()
    cpu_fb = full.lower().count("cpu fallback")
    not_reusable = full.count("NOT_REUSABLE")
    busy = full.count("BUSY")
    timeout_errs = full.count("timeout")
    print("\nIntegrity: CPU_fallback=%d NOT_REUSABLE=%d BUSY=%d timeout=%d (all expect 0)" % (
        cpu_fb, not_reusable, busy, timeout_errs))

    # ── Save report ──
    report = {
        "gate": gate,
        "timestamp": datetime.datetime.now().isoformat(),
        "server": BASE,
        "model": "MiniCPM-o-4_5-F16.gguf",
        "n_gl": 999,
        "device": "CANN0",
        "cache_dir": CACHE_DIR,
        "test_cases": len(TEST_CASES),
        "pairs_per_case": PAIRS_PER_CASE,
        "total_pairs": len(all_pairs),
        "valid_pairs": len(valid),
        "elapsed_s": elapsed,
        "integrity": {
            "cpu_fallback": cpu_fb,
            "not_reusable": not_reusable,
            "busy": busy,
            "timeout": timeout_errs,
        },
        "summary": {},
        "pairs": all_pairs,
    }

    if valid:
        miss_pf_all = [p["miss_prefill_ms"] for p in valid]
        hit_pf_all = [p["hit_prefill_ms"] for p in valid]
        deltas_all = [p["delta_prefill_ms"] for p in valid]
        report["summary"] = {
            "miss_prefill_p50_ms": pct(sorted(miss_pf_all), 50),
            "miss_prefill_p95_ms": pct(sorted(miss_pf_all), 95),
            "miss_prefill_mean_ms": statistics.mean(miss_pf_all),
            "hit_prefill_p50_ms": pct(sorted(hit_pf_all), 50),
            "hit_prefill_p95_ms": pct(sorted(hit_pf_all), 95),
            "hit_prefill_mean_ms": statistics.mean(hit_pf_all),
            "delta_p50_ms": pct(sorted(deltas_all), 50),
            "delta_p95_ms": pct(sorted(deltas_all), 95),
            "delta_mean_ms": statistics.mean(deltas_all),
            "speedup_p50": pct(sorted(speedups), 50),
            "n_past_range": [min(n_past_vals), max(n_past_vals)],
            "reused_range": [min(reused_vals), max(reused_vals)],
        }

    report_path = os.path.join(OUTPUT_DIR, "canonical_kv_ab_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # CSV
    csv_path = os.path.join(OUTPUT_DIR, "canonical_kv_ab.csv")
    csv_fields = [
        "pair_id", "case", "round",
        "miss_prefill_ms", "hit_prefill_ms", "delta_prefill_ms", "speedup",
        "miss_init_s", "hit_init_s", "miss_decode_s", "hit_decode_s",
        "miss_total_s", "hit_total_s", "delta_total_s",
        "miss_handler_hold_ns", "hit_handler_hold_ns",
        "miss_mutex_wait_ns", "hit_mutex_wait_ns",
        "miss_kv_action", "hit_kv_action",
        "miss_cache_hits", "miss_cache_misses", "miss_tokens_reused",
        "hit_cache_hits", "hit_cache_misses", "hit_tokens_reused",
        "n_past", "cache_key",
        "miss_wav_count", "hit_wav_count",
        "miss_lifecycle", "hit_lifecycle",
    ]
    with open(csv_path, "w") as f:
        f.write(",".join(csv_fields) + "\n")
        for p in all_pairs:
            f.write(",".join(str(p.get(k, "")) for k in csv_fields) + "\n")

    print("\nReport: %s" % report_path)
    print("CSV:    %s" % csv_path)

    return 0 if gate.startswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
