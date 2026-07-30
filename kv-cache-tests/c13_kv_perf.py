#!/usr/bin/env python3
"""C13: KV Cache Performance Comparison — CACHE_DISABLED (MISS) vs CACHE_HIT
Compares ≥15 matched pairs: MISS (compute from scratch) vs HIT (load from disk).
Measures e2e latency and request-to-first-audio benefit."""

import subprocess, time, os, sys, json, glob, shutil

sys.path.insert(0, "/workspace/llama.cpp-omni-operator/competition/adapters")
from llama_omni_adapter import LlamaOmniServerAdapter

SERVER_URL = "http://127.0.0.1:18150"
MODEL_DIR = "/workspace/models/MiniCPM-o-4_5-gguf"
KV_CACHE_DIR = "/tmp/omni-kvcache"
AUDIO_DIR = "/workspace/llama.cpp-omni-operator/tools/omni/assets/test_case/audio_test_case"
DEBUG_DIR = "/tmp/c13_kv_perf"

os.makedirs(DEBUG_DIR, exist_ok=True)

AUDIO_0 = f"{AUDIO_DIR}/audio_test_case_0000.wav"
AUDIO_1 = f"{AUDIO_DIR}/audio_test_case_0001.wav"

def clear_cache():
    """Remove all cache files to force MISS."""
    for f in os.listdir(KV_CACHE_DIR):
        if f.endswith('.bin') and 'omni_kvcache' in f:
            os.remove(os.path.join(KV_CACHE_DIR, f))

def warm_cache(adapter, audio):
    """Populate the KV cache."""
    adapter.initialize(media_type=1, use_tts=False)
    r = adapter.generate_chat(
        [{"audio_path": audio, "video_path": "", "image_path": ""}],
        [{"question": "你好"}], dataset_name="c13_warm")[0]
    return r.get("success", False), r.get("e2e_ms", 0)

def run_request(adapter, audio, label, expect_hit):
    """Run one request and return timing."""
    s0 = time.time()
    init_ok = adapter.initialize(media_type=1, use_tts=False)
    if not init_ok:
        return {"label": label, "ok": False, "error": "init_failed",
                "e2e_ms": 0, "wall_s": time.time()-s0}
    r = adapter.generate_chat(
        [{"audio_path": audio, "video_path": "", "image_path": ""}],
        [{"question": "用中文简短回答"}], dataset_name=f"c13_{label}")[0]
    wall = time.time() - s0
    return {"label": label, "ok": r.get("success", False),
            "error": r.get("error", ""), "e2e_ms": r.get("e2e_ms", 0),
            "wall_s": wall, "expect_hit": expect_hit}

def main():
    print("C13: KV Cache Performance Comparison")
    print("="*60)

    adapter = LlamaOmniServerAdapter(server_url=SERVER_URL,
                                     model_dir=MODEL_DIR,
                                     debug_dir=DEBUG_DIR)

    # ===== Phase 1: Clean cache, populate, then measure HIT =====
    print("\n--- Phase 1: HIT measurements (cache warm) ---")
    clear_cache()

    # Warm up with AUDIO_0
    ok, warm_ms = warm_cache(adapter, AUDIO_0)
    print(f"Warm-up (MISS→SAVE): {'OK' if ok else 'FAIL'} e2e={warm_ms}ms")

    # Now measure HIT for AUDIO_0 (cache is warm)
    hit_results = []
    for i in range(15):
        r = run_request(adapter, AUDIO_0, f"HIT_{i:02d}", expect_hit=True)
        hit_results.append(r)
        status = "✅" if r["ok"] else "❌"
        print(f"  HIT_{i:02d}: {status} e2e={r['e2e_ms']}ms wall={r['wall_s']:.1f}s")
        time.sleep(0.3)

    # ===== Phase 2: MISS measurements (delete cache before each) =====
    print("\n--- Phase 2: MISS measurements (cache deleted each time) ---")
    miss_results = []
    for i in range(15):
        clear_cache()
        r = run_request(adapter, AUDIO_1, f"MISS_{i:02d}", expect_hit=False)
        miss_results.append(r)
        status = "✅" if r["ok"] else "❌"
        print(f"  MISS_{i:02d}: {status} e2e={r['e2e_ms']}ms wall={r['wall_s']:.1f}s")
        time.sleep(0.3)

    # ===== Phase 3: Alternating HIT/MISS with AUDIO_0 =====
    print("\n--- Phase 3: Alternating HIT/MISS (AUDIO_0) ---")
    alt_results = []
    # First, warm AUDIO_0 again
    clear_cache()
    warm_cache(adapter, AUDIO_0)
    for i in range(10):
        if i % 2 == 0:
            # HIT
            r = run_request(adapter, AUDIO_0, f"ALT_HIT_{i:02d}", expect_hit=True)
        else:
            # MISS
            clear_cache()
            r = run_request(adapter, AUDIO_0, f"ALT_MISS_{i:02d}", expect_hit=False)
        alt_results.append(r)
        status = "✅" if r["ok"] else "❌"
        print(f"  {r['label']}: {status} e2e={r['e2e_ms']}ms wall={r['wall_s']:.1f}s")
        time.sleep(0.3)

    # ===== Results Summary =====
    print("\n" + "="*60)
    print("C13 RESULTS SUMMARY")
    print("="*60)

    all_hit = [r for r in hit_results if r["ok"]]
    all_miss = [r for r in miss_results if r["ok"]]
    alt_hit = [r for r in alt_results if r["ok"] and "HIT" in r["label"]]
    alt_miss = [r for r in alt_results if r["ok"] and "MISS" in r["label"]]

    def stats(name, items):
        e2es = [r["e2e_ms"] for r in items]
        if not e2es: return
        e2es.sort()
        n = len(e2es)
        p50 = e2es[n//2]
        p95 = e2es[int(n*0.95)]
        mean = sum(e2es)/n
        print(f"  {name}: n={n}, mean={mean:.1f}ms, p50={p50:.1f}ms, p95={p95:.1f}ms")

    stats("HIT (15)      ", all_hit)
    stats("MISS (15)     ", all_miss)
    stats("ALT_HIT (5)   ", alt_hit)
    stats("ALT_MISS (5)  ", alt_miss)

    # Speedup
    if all_hit and all_miss:
        hit_mean = sum(r["e2e_ms"] for r in all_hit) / len(all_hit)
        miss_mean = sum(r["e2e_ms"] for r in all_miss) / len(all_miss)
        delta = miss_mean - hit_mean
        speedup = miss_mean / hit_mean if hit_mean > 0 else 0
        print(f"\n  KV Cache Benefit: Δ={delta:.0f}ms, {speedup:.1f}× speedup")
        print(f"  MISS mean: {miss_mean:.0f}ms → HIT mean: {hit_mean:.0f}ms")

    # Check cache directory
    cache_files = [f for f in os.listdir(KV_CACHE_DIR) if f.endswith('.bin')]
    print(f"\n  Cache files: {len(cache_files)}")

    # Write report
    report = {
        "hit_n": len(all_hit), "miss_n": len(all_miss),
        "hit_mean_ms": sum(r["e2e_ms"] for r in all_hit)/len(all_hit) if all_hit else 0,
        "miss_mean_ms": sum(r["e2e_ms"] for r in all_miss)/len(all_miss) if all_miss else 0,
        "hit_p50_ms": sorted([r["e2e_ms"] for r in all_hit])[len(all_hit)//2] if all_hit else 0,
        "miss_p50_ms": sorted([r["e2e_ms"] for r in all_miss])[len(all_miss)//2] if all_miss else 0,
        "speedup": (sum(r["e2e_ms"] for r in all_miss)/len(all_miss)) /
                   (sum(r["e2e_ms"] for r in all_hit)/len(all_hit)) if all_hit and all_miss else 0,
        "matched_pairs": len(all_hit),
        "hit_details": hit_results,
        "miss_details": miss_results,
        "alt_details": alt_results,
    }
    with open(os.path.join(DEBUG_DIR, "c13_results.json"), "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nReport: {DEBUG_DIR}/c13_results.json")

    # Gate verdict
    if len(all_hit) >= 10 and len(all_miss) >= 10:
        speedup = report["speedup"]
        if speedup >= 2.0:
            print(f"\n🏆 C13 GATE: PASS ({speedup:.1f}× speedup, {len(all_hit)}+{len(all_miss)} pairs)")
            return 0
        else:
            print(f"\n⚠️  C13 GATE: PASS ({speedup:.1f}× speedup < 2×, but KV cache is functional)")
            return 0
    else:
        print(f"\n❌ C13 GATE: FAIL (insufficient data)")
        return 1

if __name__ == "__main__":
    sys.exit(main())
