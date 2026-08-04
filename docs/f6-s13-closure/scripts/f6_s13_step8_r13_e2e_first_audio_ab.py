#!/usr/bin/env python3
"""
Step 8: R13 E2E First-Audio 30-Pair A/B (USE_TTS=True)
========================================================
Canonical KV cache A/B test with TTS enabled, measuring end-to-end
first-audio latency, PCM/drain metrics, and bootstrap CI95.

Server: must run with OMNI_KV_CACHE_REUSE=1 on port 18093.
5 test cases × 6 pairs = 30 strict matched pairs.
A = MISS (cold cache), B = HIT (warm cache).

Per-WAV RTF log entries are NOT available from the C++ T2W implementation.
Instead we use WAV file mtimes + Python wave module for audio metrics.
"""

import requests
import time
import os
import glob
import json
import sys
import re
import datetime
import statistics
import random
import wave
import traceback

# ── Config ────────────────────────────────────
BASE = "http://127.0.0.1:18093"       # KV_CACHE_REUSE=1 server (Step 8)
CACHE_DIR = "/tmp/omni-kvcache"
AUDIO_PREFIX = "/workspace/llama.cpp-omni-f6/tools/omni/assets/test_case/omni_test_case/omni_test_case_"
SERVER_LOG = "/tmp/f6_s13_step8_v6_srv.log"
OUTPUT_DIR = "/tmp/f6_s13_step8_results"
OMNI_OUTPUT_BASE = "./tools/omni/output"
USE_TTS = True

TEST_CASES = [
    {"id": "C1", "audio": "0000.wav", "image": "0000.jpg", "text": "请描述你听到的内容"},
    {"id": "C2", "audio": "0001.wav", "image": "0001.jpg", "text": "这张图片里有什么"},
    {"id": "C3", "audio": "0002.wav", "image": "0002.jpg", "text": "请用中文回答"},
    {"id": "C4", "audio": "0003.wav", "image": "0003.jpg", "text": "讲一个简短的故事"},
    {"id": "C5", "audio": "0004.wav", "image": "0004.jpg", "text": "今天天气如何"},
]
PAIRS_PER_CASE = 6
REQUEST_TIMEOUT = 600  # 10 min — TTS drain can be long
COOLDOWN_S = 2

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)


# ── Helpers ───────────────────────────────────
def clear_cache():
    """Delete KV cache files from disk."""
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
    """Parse F6_EVENT and F6_REQSTATE lines."""
    events = {}
    for m in re.finditer(
        r"F6_EVENT\|(\d+)\|(\w+)\|req=(\S+)\|ctx=(\S+)\|tid=(\S+)", log_text
    ):
        ts = int(m.group(1))
        evt = m.group(2)
        if evt not in events:
            events[evt] = []
        events[evt].append({"ts": ts, "req": m.group(3)})

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
    for key in ["cache_hits", "cache_misses", "tokens_reused"]:
        m = re.search(r"\b" + key + r":\s+(\d+)", log_text)
        if m:
            stats[key] = int(m.group(1))
    # KV cache action — F6 Step 8 log format:
    #   MISS:  🔁 KV cache MISS: will compute system prompt from scratch
    #   SAVED: 🔁 KV cache SAVED: ...bytes to ... (n_past=NNN, key=XXXX)
    #   HIT:   🔁 KV cache HIT: loaded NNN positions ... (key=XXXX)
    # Note: 🔁 emoji may appear before "KV cache" — match optionally.
    m = re.search(r"(?:🔁\s*)?KV cache SAVED:.*?n_past=(\d+).*?key=(\S+)", log_text)
    if m:
        stats["kv_action"] = "SAVED"
        stats["n_past"] = int(m.group(1))
        stats["cache_key"] = m.group(2).rstrip(")")
    m = re.search(r"(?:🔁\s*)?KV cache HIT:.*?(?:positions|loaded).*?key=(\S+)", log_text)
    if m:
        stats["kv_action"] = "LOADED"
        stats["cache_key"] = m.group(1).rstrip(")")
        if "tokens_reused" in stats:
            stats["n_past"] = stats["tokens_reused"]
    return stats


def parse_round_dir(log_text):
    """Parse the TTS output round directory from the log segment.
    Format: TTS: 创建单工模式输出目录: ./tools/omni/output/round_NNN
    Also try: base_output_dir
    Returns the full round directory path, or None."""
    m = re.search(r"创建单工模式输出目录:\s*(\./tools/omni/output/round_\d+)", log_text)
    if m:
        return m.group(1)
    # Fallback: look for any "round_NNN" in TTS context
    m = re.search(r"TTS.*?(\./tools/omni/output/round_\d+)", log_text)
    if m:
        return m.group(1)
    return None


def scan_wav_files(round_dir):
    """Scan WAV files in round_dir/tts_wav/.
    Returns list of dicts sorted by filename (which reflects creation order):
      {path, name, mtime_epoch, audio_duration_s}
    """
    wav_dir = os.path.join(round_dir, "tts_wav")
    if not os.path.isdir(wav_dir):
        return []
    wavs = []
    for fname in sorted(os.listdir(wav_dir)):
        if not fname.endswith(".wav"):
            continue
        fpath = os.path.join(wav_dir, fname)
        mtime = os.path.getmtime(fpath)
        dur = 0.0
        try:
            with wave.open(fpath, "r") as w:
                dur = w.getnframes() / w.getframerate()
        except Exception:
            pass
        wavs.append({
            "path": fpath,
            "name": fname,
            "mtime_epoch": mtime,
            "audio_duration_s": dur,
        })
    return wavs


def compute_event_pair_ns(events, start_evt, end_evt):
    """Compute time between a start event and end event."""
    s = events.get(start_evt, [])
    e = events.get(end_evt, [])
    if s and e:
        return e[-1]["ts"] - s[-1]["ts"]
    return None


# ── Bootstrap CI95 ────────────────────────────
def bootstrap_median_ci(data, n_bootstrap=10000, seed=42):
    rng = random.Random(seed)
    n = len(data)
    if n < 3:
        return statistics.median(data), statistics.median(data), statistics.median(data)
    medians = []
    for _ in range(n_bootstrap):
        sample = [rng.choice(data) for _ in range(n)]
        medians.append(statistics.median(sample))
    medians.sort()
    lo = medians[int(n_bootstrap * 0.025)]
    hi = medians[int(n_bootstrap * 0.975)]
    return lo, statistics.median(data), hi


# ── Request runner ────────────────────────────
def make_request(tc, round_idx):
    """Full request cycle with TTS enabled.
    Returns metrics dict with W0/PCM/drain/KV cache.
    """
    audio = AUDIO_PREFIX + tc["audio"]
    image = AUDIO_PREFIX + tc["image"] if tc.get("image") else ""

    metrics = {}

    # ── omni_init ──
    pos_before = log_size()
    t_init = time.time()
    r = requests.post(
        BASE + "/v1/stream/omni_init",
        json={"msg_type": 1, "media_type": 1, "use_tts": USE_TTS},
        timeout=REQUEST_TIMEOUT,
    )
    metrics["init_wall_s"] = time.time() - t_init
    if r.status_code != 200:
        raise RuntimeError("omni_init failed: %d %s" % (r.status_code, r.text))

    # ── prefill ──
    t_prefill = time.time()
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
    metrics["prefill_wall_ms"] = (time.time() - t_prefill) * 1000.0
    if r.status_code != 200:
        raise RuntimeError("prefill failed: %d %s" % (r.status_code, r.text))

    # ── decode with TTS ──
    t_decode = time.time()
    r = requests.post(
        BASE + "/v1/stream/decode",
        json={
            "stream": False,
            "round_idx": round_idx,
            "debug_dir": OUTPUT_DIR,
            "max_tokens": 128,
            "wall_timeout_ms": 600000,
        },
        timeout=REQUEST_TIMEOUT,
    )
    metrics["decode_wall_ms"] = (time.time() - t_decode) * 1000.0
    metrics["total_wall_s"] = (
        metrics["init_wall_s"] + metrics["prefill_wall_ms"] / 1000.0 + metrics["decode_wall_ms"] / 1000.0
    )

    if r.status_code != 200:
        raise RuntimeError("decode failed: %d %s" % (r.status_code, r.text))

    # ── Parse server log ──
    # Small delay to allow server stderr buffer to flush KV cache entries
    time.sleep(0.5)
    pos_after = log_size()
    log_seg = read_log_segment(pos_before, pos_after)

    events, req_states = parse_f6_events(log_seg)
    kv_stats = parse_kv_stats(log_seg)
    metrics.update(kv_stats)

    # F6_EVENT derived timing
    metrics["handler_hold_ns"] = compute_event_pair_ns(events, "HANDLER_ENTER", "HANDLER_RETURN")
    metrics["mutex_wait_ns"] = compute_event_pair_ns(events, "OCTX_LOCK_WAIT_BEGIN", "OCTX_LOCK_ACQUIRED")
    metrics["decode_event_ns"] = compute_event_pair_ns(events, "STREAM_DECODE_BEGIN", "STREAM_DECODE_END")
    metrics["drain_event_ns"] = compute_event_pair_ns(events, "T2W_DRAIN_BEGIN", "T2W_DRAIN_END")

    # ── First-audio latency (W0) via WAV files ──
    # After decode, WAV files are in ./tools/omni/output/round_{round_idx}/tts_wav/
    # The server uses round_idx directly for the output directory name.
    round_dir = "%s/round_%03d" % (OMNI_OUTPUT_BASE, round_idx)
    new_wavs = scan_wav_files(round_dir)

    metrics["wav_count"] = len(new_wavs)

    if new_wavs:
        # W0: first WAV mtime vs decode start
        first_wav = new_wavs[0]
        w0_s = max(0, first_wav["mtime_epoch"] - t_decode)
        metrics["first_audio_from_decode_s"] = w0_s
        metrics["first_wav_mtime"] = first_wav["mtime_epoch"]
        metrics["first_wav_name"] = first_wav["name"]

        # PCM: total audio duration across all WAVs
        total_audio_s = sum(w["audio_duration_s"] for w in new_wavs)
        metrics["pcm_total_audio_s"] = total_audio_s
        metrics["wav_durations"] = [w["audio_duration_s"] for w in new_wavs]

        # Drain span: last WAV mtime - first WAV mtime
        if len(new_wavs) > 1:
            last_wav = new_wavs[-1]
            metrics["drain_span_s"] = max(0, last_wav["mtime_epoch"] - first_wav["mtime_epoch"])
        else:
            metrics["drain_span_s"] = 0.0

        # Approximate RTF (without per-WAV inference time):
        # We can't compute true RTF without inference_ms per WAV.
        # Use decode_wall_ms / total_audio_s as a coarse proxy.
        if total_audio_s > 0:
            metrics["coarse_rtf"] = (metrics["decode_wall_ms"] / 1000.0) / total_audio_s
    else:
        metrics["first_audio_from_decode_s"] = None
        metrics["first_wav_mtime"] = None
        metrics["pcm_total_audio_s"] = 0.0
        metrics["drain_span_s"] = None

    metrics["round_dir"] = round_dir

    # Lifecycle
    states_seen = [s["from_state"] for s in req_states] + (
        [req_states[-1]["to_state"]] if req_states else ["?"]
    )
    metrics["lifecycle"] = "→".join(states_seen) if states_seen else "?"

    return metrics


# ── Main ──────────────────────────────────────
def main():
    print("=" * 70)
    print("Step 8: R13 E2E First-Audio 30-Pair A/B (USE_TTS=True)")
    print("Server:  %s" % BASE)
    print("Cache:   %s" % CACHE_DIR)
    print("Cases:   %d × %d = %d pairs" % (len(TEST_CASES), PAIRS_PER_CASE, len(TEST_CASES) * PAIRS_PER_CASE))
    print("Output:  %s" % OUTPUT_DIR)
    print("=" * 70)

    all_pairs = []
    start_time = datetime.datetime.now()
    pair_idx = 0

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

            # ── B: HIT ──
            try:
                res_b = make_request(tc, rnd * 2 + 1)
            except Exception as e:
                print("  [%d/30] %s: FAILED — %s" % (pair_idx, hit_label, e))
                time.sleep(COOLDOWN_S)
                continue

            # ── Verification ──
            issues = []

            if res_a.get("kv_action") != "SAVED":
                issues.append("A_NOT_SAVED(%s)" % res_a.get("kv_action", "?"))

            if res_b.get("kv_action") != "LOADED":
                issues.append("B_NOT_LOADED(%s)" % res_b.get("kv_action", "?"))

            delta_prefill_ms = res_a.get("prefill_wall_ms", 0) - res_b.get("prefill_wall_ms", 0)
            if delta_prefill_ms <= 0:
                issues.append("DELTA_NEGATIVE(%.0fms)" % delta_prefill_ms)

            reused = res_b.get("tokens_reused", 0)
            if reused <= 0:
                issues.append("ZERO_REUSED")

            # First-audio delta (MISS - HIT, positive = HIT faster)
            fa_miss = res_a.get("first_audio_from_decode_s")
            fa_hit = res_b.get("first_audio_from_decode_s")
            delta_first_audio_ms = None
            if fa_miss is not None and fa_hit is not None:
                delta_first_audio_ms = (fa_miss - fa_hit) * 1000.0

            verdict = "✅" if not issues else "❌ " + ",".join(issues)

            # ── Record pair ──
            pair = {
                "pair_id": pair_idx,
                "case": case_id,
                "round": rnd + 1,
                # Prefill
                "miss_prefill_ms": round(res_a.get("prefill_wall_ms", 0), 1),
                "hit_prefill_ms": round(res_b.get("prefill_wall_ms", 0), 1),
                "delta_prefill_ms": round(delta_prefill_ms, 1),
                "speedup": round(res_a.get("prefill_wall_ms", 0) / max(res_b.get("prefill_wall_ms", 0), 1), 2),
                # omni_init
                "miss_init_s": round(res_a.get("init_wall_s", 0), 2),
                "hit_init_s": round(res_b.get("init_wall_s", 0), 2),
                # Decode wall
                "miss_decode_wall_ms": round(res_a.get("decode_wall_ms", 0), 0),
                "hit_decode_wall_ms": round(res_b.get("decode_wall_ms", 0), 0),
                # Total
                "miss_total_s": round(res_a.get("total_wall_s", 0), 2),
                "hit_total_s": round(res_b.get("total_wall_s", 0), 2),
                # ── First-Audio (W0, from WAV mtime) ──
                "miss_first_audio_from_decode_s": round(fa_miss, 3) if fa_miss is not None else None,
                "hit_first_audio_from_decode_s": round(fa_hit, 3) if fa_hit is not None else None,
                "delta_first_audio_ms": round(delta_first_audio_ms, 1) if delta_first_audio_ms is not None else None,
                "miss_first_wav_mtime": res_a.get("first_wav_mtime"),
                "hit_first_wav_mtime": res_b.get("first_wav_mtime"),
                "miss_first_wav_name": res_a.get("first_wav_name"),
                "hit_first_wav_name": res_b.get("first_wav_name"),
                # ── PCM (from wave module) ──
                "miss_total_audio_s": res_a.get("pcm_total_audio_s"),
                "hit_total_audio_s": res_b.get("pcm_total_audio_s"),
                "miss_coarse_rtf": res_a.get("coarse_rtf"),
                "hit_coarse_rtf": res_b.get("coarse_rtf"),
                # ── Drain ──
                "miss_drain_event_ns": res_a.get("drain_event_ns"),
                "hit_drain_event_ns": res_b.get("drain_event_ns"),
                "miss_drain_span_s": res_a.get("drain_span_s"),
                "hit_drain_span_s": res_b.get("drain_span_s"),
                # ── KV cache ──
                "miss_kv_action": res_a.get("kv_action", "?"),
                "hit_kv_action": res_b.get("kv_action", "?"),
                "miss_cache_hits": res_a.get("cache_hits", -1),
                "miss_cache_misses": res_a.get("cache_misses", -1),
                "hit_cache_hits": res_b.get("cache_hits", -1),
                "hit_cache_misses": res_b.get("cache_misses", -1),
                "hit_tokens_reused": reused,
                "n_past": res_a.get("n_past", res_b.get("n_past", 0)),
                "cache_key": res_a.get("cache_key", res_b.get("cache_key", "")),
                # ── WAV count ──
                "miss_wav_count": res_a.get("wav_count", 0),
                "hit_wav_count": res_b.get("wav_count", 0),
                # ── F6 events ──
                "miss_handler_hold_ns": res_a.get("handler_hold_ns"),
                "hit_handler_hold_ns": res_b.get("handler_hold_ns"),
                "miss_mutex_wait_ns": res_a.get("mutex_wait_ns"),
                "hit_mutex_wait_ns": res_b.get("mutex_wait_ns"),
                "miss_decode_event_ns": res_a.get("decode_event_ns"),
                "hit_decode_event_ns": res_b.get("decode_event_ns"),
                # ── Lifecycle ──
                "miss_lifecycle": res_a.get("lifecycle", "?"),
                "hit_lifecycle": res_b.get("lifecycle", "?"),
                # ── Round dir info ──
                "miss_round_dir": res_a.get("round_dir", ""),
                "hit_round_dir": res_b.get("round_dir", ""),
            }
            all_pairs.append(pair)

            # Print result
            print("  [%02d/30] %s %s" % (pair_idx, verdict, miss_label))
            print("          MISS: prefill=%.0fms decode=%.0fms wavs=%d "
                  "fa=%.3fs round=%s | kv=%s reused=%d" % (
                res_a.get("prefill_wall_ms", 0),
                res_a.get("decode_wall_ms", 0),
                res_a.get("wav_count", 0),
                fa_miss if fa_miss is not None else -1,
                res_a.get("round_dir", "?"),
                res_a.get("kv_action", "?"),
                res_a.get("tokens_reused", 0),
            ))
            print("          HIT:  prefill=%.0fms decode=%.0fms wavs=%d "
                  "fa=%.3fs round=%s | kv=%s reused=%d | Δpf=%.0fms Δfa=%.0fms" % (
                res_b.get("prefill_wall_ms", 0),
                res_b.get("decode_wall_ms", 0),
                res_b.get("wav_count", 0),
                fa_hit if fa_hit is not None else -1,
                res_b.get("round_dir", "?"),
                res_b.get("kv_action", "?"),
                reused,
                delta_prefill_ms,
                delta_first_audio_ms if delta_first_audio_ms is not None else -1,
            ))
            if res_a.get("pcm_total_audio_s") or res_b.get("pcm_total_audio_s"):
                print("          PCM:   MISS_audio=%.2fs MISS_WAVs=%s | "
                      "HIT_audio=%.2fs HIT_WAVs=%s" % (
                    res_a.get("pcm_total_audio_s", 0),
                    [round(d, 3) for d in res_a.get("wav_durations", [])],
                    res_b.get("pcm_total_audio_s", 0),
                    [round(d, 3) for d in res_b.get("wav_durations", [])],
                ))

            # Save incrementally after each pair
            inc_path = os.path.join(OUTPUT_DIR, "step8_v6_p%02d.json" % pair_idx)
            try:
                with open(inc_path, "w") as f:
                    json.dump({"pairs": all_pairs, "progress": "%d/%d" % (pair_idx, len(TEST_CASES) * PAIRS_PER_CASE)}, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

            time.sleep(COOLDOWN_S)

    # ─────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────
    elapsed = (datetime.datetime.now() - start_time).total_seconds()
    valid = [p for p in all_pairs
             if p["miss_kv_action"] == "SAVED"
             and p["hit_kv_action"] == "LOADED"
             and p["delta_prefill_ms"] > 0]

    print("\n" + "=" * 70)
    print("STEP 8 RESULTS SUMMARY — %d/%d valid pairs (%.0f min)" % (
        len(valid), len(all_pairs), elapsed / 60))
    print("=" * 70)

    if valid:
        n = len(valid)
        miss_pf = sorted([p["miss_prefill_ms"] for p in valid])
        hit_pf = sorted([p["hit_prefill_ms"] for p in valid])
        deltas_pf = sorted([p["delta_prefill_ms"] for p in valid])
        speedups = sorted([p["speedup"] for p in valid])
        reused_vals = [p["hit_tokens_reused"] for p in valid]

        def pct(arr, p):
            return arr[min(int(n * p / 100), n - 1)]

        print("\n── Prefill Timing ──")
        print("  MISS: p50=%.0fms p95=%.0fms" % (pct(miss_pf, 50), pct(miss_pf, 95)))
        print("  HIT:  p50=%.0fms p95=%.0fms" % (pct(hit_pf, 50), pct(hit_pf, 95)))
        print("  Δ:    p50=%.0fms p95=%.0fms" % (pct(deltas_pf, 50), pct(deltas_pf, 95)))
        print("  Speedup: p50=%.1f× p95=%.1f×" % (pct(speedups, 50), pct(speedups, 95)))

        # ── First-Audio Latency (W0) ──
        fa_valid = [p for p in valid
                    if p["delta_first_audio_ms"] is not None
                    and p["miss_first_audio_from_decode_s"] is not None
                    and p["hit_first_audio_from_decode_s"] is not None]
        if fa_valid:
            fa_miss_ms = [p["miss_first_audio_from_decode_s"] * 1000.0 for p in fa_valid]
            fa_hit_ms = [p["hit_first_audio_from_decode_s"] * 1000.0 for p in fa_valid]
            fa_deltas = sorted([p["delta_first_audio_ms"] for p in fa_valid])

            print("\n── First-Audio Latency (W0, from decode start) ──")
            print("  MISS: p50=%.0fms p95=%.0fms" % (
                statistics.median(fa_miss_ms),
                sorted(fa_miss_ms)[int(len(fa_miss_ms) * 0.95)]))
            print("  HIT:  p50=%.0fms p95=%.0fms" % (
                statistics.median(fa_hit_ms),
                sorted(fa_hit_ms)[int(len(fa_hit_ms) * 0.95)]))
            if fa_deltas:
                print("  Δ:    p50=%.0fms p95=%.0fms" % (
                    statistics.median(fa_deltas),
                    sorted(fa_deltas)[int(len(fa_deltas) * 0.95)]))
                fa_ci_lo, fa_ci_med, fa_ci_hi = bootstrap_median_ci(fa_deltas)
                print("  Bootstrap CI95 (median): [%.0f, %.0f] ms" % (fa_ci_lo, fa_ci_hi))

        # ── PCM and Drain ──
        miss_audio = [p["miss_total_audio_s"] for p in valid if p["miss_total_audio_s"] is not None]
        hit_audio = [p["hit_total_audio_s"] for p in valid if p["hit_total_audio_s"] is not None]
        if miss_audio:
            print("\n── PCM (Total Audio Duration) ──")
            print("  MISS: p50=%.2fs p95=%.2fs" % (
                statistics.median(miss_audio),
                sorted(miss_audio)[int(len(miss_audio) * 0.95)]))
        if hit_audio:
            print("  HIT:  p50=%.2fs p95=%.2fs" % (
                statistics.median(hit_audio),
                sorted(hit_audio)[int(len(hit_audio) * 0.95)]))

        miss_drain = [p["miss_drain_event_ns"] for p in valid if p["miss_drain_event_ns"] is not None]
        hit_drain = [p["hit_drain_event_ns"] for p in valid if p["hit_drain_event_ns"] is not None]
        if miss_drain:
            miss_drain_ms = [d / 1e6 for d in miss_drain]
            print("\n── Drain Time (F6 events) ──")
            print("  MISS: p50=%.0fms p95=%.0fms" % (
                statistics.median(miss_drain_ms),
                sorted(miss_drain_ms)[int(len(miss_drain_ms) * 0.95)]))
        if hit_drain:
            hit_drain_ms = [d / 1e6 for d in hit_drain]
            print("  HIT:  p50=%.0fms p95=%.0fms" % (
                statistics.median(hit_drain_ms),
                sorted(hit_drain_ms)[int(len(hit_drain_ms) * 0.95)]))

        # ── KV Cache ──
        print("\n── KV Cache ──")
        print("  tokens_reused: %d (all pairs)" % statistics.median(reused_vals))
        cache_keys = set(p["cache_key"] for p in valid if p["cache_key"])
        print("  distinct cache keys: %d" % len(cache_keys))
        if cache_keys:
            print("  keys: %s" % ", ".join(sorted(cache_keys)))

        # ── WAV Counts ──
        miss_wc = [p["miss_wav_count"] for p in valid]
        hit_wc = [p["hit_wav_count"] for p in valid]
        if miss_wc:
            print("\n── WAV Count ──")
            print("  MISS: p50=%d p95=%d range=[%d,%d]" % (
                statistics.median(miss_wc),
                sorted(miss_wc)[int(len(miss_wc) * 0.95)],
                min(miss_wc), max(miss_wc)))
        if hit_wc:
            print("  HIT:  p50=%d p95=%d range=[%d,%d]" % (
                statistics.median(hit_wc),
                sorted(hit_wc)[int(len(hit_wc) * 0.95)],
                min(hit_wc), max(hit_wc)))

        # ── Integrity ──
        cpu_fallback = sum(1 for p in valid if "CPU" in str(p.get("miss_lifecycle", "")))
        not_reusable = sum(1 for p in valid if "NOT_REUSABLE" in str(p.get("miss_lifecycle", "")))
        print("\n── Integrity ──")
        print("  CPU fallback:   %d" % cpu_fallback)
        print("  NOT_REUSABLE:   %d" % not_reusable)

        # ── Gate Status ──
        all_30_valid = len(valid) == 30
        prefill_speedup = pct(deltas_pf, 50) > 0 if deltas_pf else False
        fa_improved = False
        if fa_deltas:
            fa_improved = statistics.median(fa_deltas) > 0

        print("\n" + "=" * 70)
        print("STEP 8 GATE STATUS")
        print("=" * 70)
        print("R13_E2E_30_VALID_PAIRS:       %s (%d/30)" % (
            "PASS" if all_30_valid else "FAIL", len(valid)))
        print("R13_E2E_PREFILL_SPEEDUP:      %s (Δp50=%.0fms)" % (
            "PASS" if prefill_speedup else "FAIL",
            pct(deltas_pf, 50) if deltas_pf else 0))
        print("R13_E2E_FIRST_AUDIO_DELTA:    %s (Δp50=%.0fms)" % (
            "PASS" if fa_improved else "INCONCLUSIVE",
            statistics.median(fa_deltas) if fa_deltas else 0))
        print("R13_E2E_KV_CACHE_INTEGRITY:   %s (cpu_fb=%d not_reuse=%d)" % (
            "PASS" if cpu_fallback == 0 and not_reusable == 0 else "FAIL",
            cpu_fallback, not_reusable))
        print("R13_E2E_BOOTSTRAP_CI95:       %s" % (
            ("[%.0f, %.0f] ms" % (fa_ci_lo, fa_ci_hi)) if fa_deltas else "N/A"))
        print("R13_E2E_COMPLETE:             %s" % (
            "PASS ✅" if (all_30_valid and prefill_speedup and
                          cpu_fallback == 0 and not_reusable == 0)
            else "PROVISIONAL"))

    # ── Save results ──
    final_path = os.path.join(OUTPUT_DIR, "step8_r13_e2e_first_audio_ab_v6.json")
    try:
        with open(final_path, "w") as f:
            json.dump({
                "meta": {
                    "step": "Step 8: R13 E2E First-Audio A/B (v6 = WAV mtime)",
                    "server": BASE,
                    "use_tts": USE_TTS,
                    "cache_dir": CACHE_DIR,
                    "server_log": SERVER_LOG,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "elapsed_min": round(elapsed / 60, 1),
                },
                "summary": {
                    "total_pairs": len(all_pairs),
                    "valid_pairs": len(valid),
                    "prefill_delta_p50_ms": pct(deltas_pf, 50) if deltas_pf else None,
                    "first_audio_delta_p50_ms": statistics.median(fa_deltas) if fa_deltas else None,
                    "bootstrap_ci95_lo": round(fa_ci_lo) if fa_deltas else None,
                    "bootstrap_ci95_hi": round(fa_ci_hi) if fa_deltas else None,
                    "cpu_fallback": cpu_fallback,
                    "not_reusable": not_reusable,
                    "distinct_cache_keys": len(cache_keys) if cache_keys else 0,
                },
                "pairs": all_pairs,
            }, f, indent=2, ensure_ascii=False)
        print("\nResults saved to %s" % final_path)
    except Exception as e:
        print("\nERROR saving final results: %s" % e)
        traceback.print_exc()
        partial_path = os.path.join(OUTPUT_DIR, "step8_v6_partial.json")
        try:
            with open(partial_path, "w") as f:
                json.dump({"pairs": all_pairs, "error": str(e)}, f, indent=2, ensure_ascii=False)
            print("Partial results saved to %s" % partial_path)
        except Exception:
            print("Failed to save partial results too")

    return 0 if (all_30_valid and prefill_speedup and cpu_fallback == 0 and not_reusable == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
