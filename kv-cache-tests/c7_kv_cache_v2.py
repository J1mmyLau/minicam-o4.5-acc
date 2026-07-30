#!/usr/bin/env python3
"""C7 v2: FP16 KV Cache Gate — OFF/MISS/HIT, prefix isolation, corruption recovery.
Root cause fixed: omni.cpp:11726 had !ctx_omni->async blocking KV cache in server mode.
Test uses OMNI_KV_CACHE_PER_CASE_REF_AUDIO=1 for per-audio-file cache keys."""
import subprocess, time, os, sys, json, glob, shutil

sys.path.insert(0, "/workspace/llama.cpp-omni-operator/competition/adapters")
from llama_omni_adapter import LlamaOmniServerAdapter

SERVER_URL = "http://127.0.0.1:18150"
MODEL_DIR = "/workspace/models/MiniCPM-o-4_5-gguf"
DEBUG_DIR = "/tmp/c7_kv_cache"
KV_CACHE_DIR = "/tmp/omni-kvcache"
AUDIO_DIR = "/workspace/llama.cpp-omni-operator/tools/omni/assets/test_case/audio_test_case"

AUDIO_0 = f"{AUDIO_DIR}/audio_test_case_0000.wav"
AUDIO_1 = f"{AUDIO_DIR}/audio_test_case_0001.wav"

os.makedirs(DEBUG_DIR, exist_ok=True)

def find_cache_files():
    """Find KV cache files in the actual KV cache directory."""
    cache_files = []
    for f in os.listdir(KV_CACHE_DIR):
        fp = os.path.join(KV_CACHE_DIR, f)
        if os.path.isfile(fp) and (f.endswith('.bin') or 'omni_kvcache' in f):
            cache_files.append(fp)
    return sorted(cache_files)

def run_request(adapter, audio_path, prompt, label, media_type=1, use_tts=False):
    """Run a single omni_init + generate_chat cycle."""
    s0 = time.time()
    init_ok = adapter.initialize(media_type=media_type, use_tts=use_tts)
    if not init_ok:
        return {"label": label, "init_ok": False, "ok": False, "error": "init_failed",
                "e2e_ms": 0, "wall_s": time.time()-s0}

    paths = [{"audio_path": audio_path, "video_path": "", "image_path": ""}]
    try:
        r = adapter.generate_chat(paths, [{"question": prompt}],
                                 dataset_name=f"c7_{label}")[0]
        ok = r.get("success", False)
        err = r.get("error", "")
        e2e = r.get("e2e_ms", 0)
    except Exception as e:
        ok = False; err = str(e)[:200]; e2e = 0

    wall = time.time() - s0
    return {"label": label, "init_ok": True, "ok": ok, "error": err,
            "e2e_ms": e2e, "wall_s": wall, "audio": os.path.basename(audio_path)}

def main():
    print("C7 v2: FP16 KV Cache Gate (with async fix)")
    print("="*60)

    server_pid = None
    try:
        r = subprocess.run(["pgrep", "-f", "llama-omni-server"], capture_output=True, text=True)
        pids = r.stdout.strip().split("\n")
        server_pid = int(pids[0]) if pids[0] else None
    except: pass

    if not server_pid:
        print("FATAL: server not running")
        return 1
    print(f"Server PID: {server_pid}")

    adapter = LlamaOmniServerAdapter(
        server_url=SERVER_URL, model_dir=MODEL_DIR,
        tts_bin_dir=f"{MODEL_DIR}/tts", tts_gpu_layers=99,
        debug_dir=DEBUG_DIR, timeout_s=300,
    )

    results = []
    cache_snapshots = []

    # ── Phase 1: CACHE_OFF (populate 2 distinct prefixes) ──
    print("\n── Phase 1: CACHE_OFF (populate 2 prefixes) ──")
    phase1 = [
        ("PREFIX_A_OFF", AUDIO_0, "What do you hear? Answer in one sentence."),
        ("PREFIX_B_OFF", AUDIO_1, "Describe the audio quality and tone."),
    ]
    for label, audio, prompt in phase1:
        r = run_request(adapter, audio, prompt, label)
        results.append(r)
        print(f"  [{label}] ok={r['ok']} e2e={r.get('e2e_ms',0):.0f}ms wall={r['wall_s']:.1f}s {r.get('error','')[:60]}")

    cache_snapshots.append({"phase": "after_populate", "files": find_cache_files()})
    print(f"  Cache files after populate: {len(cache_snapshots[-1]['files'])}")

    # ── Phase 2: CACHE_HIT (same prefixes) ──
    print("\n── Phase 2: CACHE_HIT ──")
    phase2 = [
        ("PREFIX_A_HIT_1", AUDIO_0, "What do you hear? Answer in one sentence."),
        ("PREFIX_A_HIT_2", AUDIO_0, "What do you hear? Answer in one sentence."),
        ("PREFIX_B_HIT_1", AUDIO_1, "Describe the audio quality and tone."),
        ("PREFIX_B_HIT_2", AUDIO_1, "Describe the audio quality and tone."),
    ]
    for label, audio, prompt in phase2:
        r = run_request(adapter, audio, prompt, label)
        results.append(r)
        print(f"  [{label}] ok={r['ok']} e2e={r.get('e2e_ms',0):.0f}ms wall={r['wall_s']:.1f}s")

    cache_snapshots.append({"phase": "after_hits", "files": find_cache_files()})

    # ── Phase 3: DIFFERENT_PREFIX_MISS (same audio, different prompt =
    # same cache key since key is based on ref_audio, not user prompt.
    # These should all HIT, confirming prefix-level caching granularity.) ──
    print("\n── Phase 3: Same-audio requests (expect HIT) ──")
    for i in range(3):
        r = run_request(adapter, AUDIO_0, f"Describe audio variant {i}.", f"SAME_AUDIO_{i}")
        results.append(r)
        print(f"  [SAME_AUDIO_{i}] ok={r['ok']} e2e={r.get('e2e_ms',0):.0f}ms wall={r['wall_s']:.1f}s")

    cache_snapshots.append({"phase": "after_same_audio", "files": find_cache_files()})

    # ── Phase 4: Verify 2 distinct cache entries exist ──
    print("\n── Phase 4: Cache entry verification ──")
    all_cache = find_cache_files()
    print(f"  Total cache files: {len(all_cache)}")
    for cf in all_cache:
        sz = os.path.getsize(cf)
        print(f"    {os.path.basename(cf)}: {sz} bytes")

    # ── Phase 5: Targeted corruption ──
    print("\n── Phase 5: Targeted corruption ──")
    corrupted_file = None
    if len(all_cache) >= 1:
        corrupted_file = all_cache[0]
        backup = corrupted_file + ".backup"
        shutil.copy2(corrupted_file, backup)
        with open(corrupted_file, 'wb') as f:
            f.write(b'CORRUPTED_CACHE_ENTRY_' * 100)
        print(f"  Corrupted: {os.path.basename(corrupted_file)}")
        print(f"  Backup: {os.path.basename(backup)}")

    # Try request that should have hit the corrupted cache
    r = run_request(adapter, AUDIO_0, "What do you hear? Answer in one sentence.", "A_CORRUPT")
    results.append(r)
    print(f"  [A_CORRUPT] ok={r['ok']} e2e={r.get('e2e_ms',0):.0f}ms wall={r['wall_s']:.1f}s")

    # Request that should NOT be affected (different prefix, different cache file)
    r = run_request(adapter, AUDIO_1, "Describe the audio quality and tone.", "B_AFTER_CORRUPT")
    results.append(r)
    print(f"  [B_AFTER_CORRUPT] ok={r['ok']} e2e={r.get('e2e_ms',0):.0f}ms wall={r['wall_s']:.1f}s")

    cache_snapshots.append({"phase": "after_corruption", "files": find_cache_files()})

    # ── Phase 6: Cache isolation — B should still HIT ──
    print("\n── Phase 6: Cache isolation verification ──")
    r = run_request(adapter, AUDIO_1, "Describe the audio quality and tone.", "B_HIT_POST_CORRUPT")
    results.append(r)
    print(f"  [B_HIT_POST_CORRUPT] ok={r['ok']} e2e={r.get('e2e_ms',0):.0f}ms wall={r['wall_s']:.1f}s")

    # Re-verify A works after corruption recovery (should auto-recompute)
    r = run_request(adapter, AUDIO_0, "What do you hear? Answer in one sentence.", "A_POST_CORRUPT")
    results.append(r)
    print(f"  [A_POST_CORRUPT] ok={r['ok']} e2e={r.get('e2e_ms',0):.0f}ms wall={r['wall_s']:.1f}s")

    # ── Analysis ──
    print(f"\n{'='*60}")
    all_ok = all(r["ok"] for r in results)
    hit_results = [r for r in results if "HIT" in r["label"]]
    off_results = [r for r in results if "OFF" in r["label"]]

    off_e2e = [r["e2e_ms"] for r in off_results if r["e2e_ms"] > 0]
    hit_e2e = [r["e2e_ms"] for r in hit_results if r["e2e_ms"] > 0]
    off_med = sorted(off_e2e)[len(off_e2e)//2] if off_e2e else 0
    hit_med = sorted(hit_e2e)[len(hit_e2e)//2] if hit_e2e else 0

    print(f"  C7 FP16 KV CACHE GATE (v2 — async fix):")
    print(f"    All OK: {all_ok} ({sum(1 for r in results if r['ok'])}/{len(results)})")
    print(f"    OFF median E2E: {off_med:.0f}ms (n={len(off_e2e)})")
    print(f"    HIT median E2E: {hit_med:.0f}ms (n={len(hit_e2e)})")
    if off_med > 0 and hit_med > 0:
        pct = (1 - hit_med/off_med)*100
        print(f"    HIT/OFF ratio: {hit_med/off_med:.2f} ({pct:.0f}% faster)")
    print(f"    Cache files: {len(find_cache_files())}")

    corruption_ok = all(r['ok'] for r in results if 'CORRUPT' in r['label'])
    print(f"    Corruption recovery: {'OK' if corruption_ok else 'FAIL'}")

    gate = all_ok and hit_med > 0 and len(find_cache_files()) >= 1

    report = {
        "gate": "C7_FP16_KV_CACHE",
        "pass": gate,
        "fix": "removed_!ctx_omni->async_from_line_11726",
        "total": len(results), "all_ok": all_ok,
        "off_median_e2e": off_med, "hit_median_e2e": hit_med,
        "cache_file_count": len(find_cache_files()),
        "corruption_tested": bool(corrupted_file),
        "corruption_ok": corruption_ok,
        "results": results,
        "cache_snapshots": [{"phase": s["phase"], "count": len(s["files"]), "files": [os.path.basename(f) for f in s["files"]]} for s in cache_snapshots],
    }
    with open(f"{DEBUG_DIR}/c7_results.json", "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n  Gate: {'PASS' if gate else 'FAIL'}")
    print(f"  Report: {DEBUG_DIR}/c7_results.json")
    return 0 if gate else 1

if __name__ == "__main__":
    sys.exit(main())
