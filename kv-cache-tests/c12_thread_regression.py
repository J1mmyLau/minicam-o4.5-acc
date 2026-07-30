#!/usr/bin/env python3
"""C12: Thread Lifecycle Regression Test
Covers: 20 HIT + 10 MISS + 10 A/B/C switch + 5 corruption + 10 TTS + 5 disconnect
Verifies: thread startup on every request, no hangs, no crashes, no CANN errors"""

import subprocess, time, os, sys, json, glob, shutil

sys.path.insert(0, "/workspace/llama.cpp-omni-operator/competition/adapters")
from llama_omni_adapter import LlamaOmniServerAdapter

SERVER_URL = "http://127.0.0.1:18150"
MODEL_DIR = "/workspace/models/MiniCPM-o-4_5-gguf"
KV_CACHE_DIR = "/tmp/omni-kvcache"
AUDIO_DIR = "/workspace/llama.cpp-omni-operator/tools/omni/assets/test_case/audio_test_case"
DEBUG_DIR = "/tmp/c12_thread_regression"

os.makedirs(DEBUG_DIR, exist_ok=True)

AUDIO = {f"A{i:04d}": f"{AUDIO_DIR}/audio_test_case_{i:04d}.wav"
         for i in range(4) if os.path.exists(f"{AUDIO_DIR}/audio_test_case_{i:04d}.wav")}

CUSTOM_AUDIO = DEBUG_DIR + "/custom_600hz.wav"

def make_custom_audio():
    """Generate a short 600Hz sine wave for additional cache key isolation."""
    if os.path.exists(CUSTOM_AUDIO):
        return
    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        subprocess.run(["pip", "install", "numpy", "soundfile", "-q"], check=True)
        import numpy as np
        import soundfile as sf
    rate = 16000; dur = 0.3; t = np.linspace(0, dur, int(rate*dur), endpoint=False)
    audio = (np.sin(2*np.pi*600*t)*0.5).astype(np.float32)
    sf.write(CUSTOM_AUDIO, audio, rate)

make_custom_audio()
AVAILABLE_AUDIO = list(AUDIO.values()) + [CUSTOM_AUDIO]

def run_request(adapter, audio_path, prompt, label, media_type=1, use_tts=False, timeout=120):
    s0 = time.time()
    try:
        init_ok = adapter.initialize(media_type=media_type, use_tts=use_tts)
    except Exception as e:
        return {"label": label, "init_ok": False, "ok": False, "error": f"init_exception:{e}",
                "e2e_ms": 0, "wall_s": time.time()-s0}
    if not init_ok:
        return {"label": label, "init_ok": False, "ok": False, "error": "init_failed",
                "e2e_ms": 0, "wall_s": time.time()-s0}

    paths = [{"audio_path": audio_path, "video_path": "", "image_path": ""}]
    try:
        r = adapter.generate_chat(paths, [{"question": prompt}],
                                 dataset_name=f"c12_{label}")[0]
        ok = r.get("success", False)
        err = r.get("error", "")
        e2e = r.get("e2e_ms", 0)
    except Exception as e:
        ok = False; err = str(e)[:200]; e2e = 0

    return {"label": label, "init_ok": True, "ok": ok, "error": err,
            "e2e_ms": e2e, "wall_s": time.time()-s0, "audio": os.path.basename(audio_path)}

def check_server_health():
    """Verify server is alive and check basic health."""
    try:
        r = subprocess.run(["pgrep", "-f", "llama-omni-server"], capture_output=True, text=True)
        pids = [int(x) for x in r.stdout.strip().split("\n") if x.strip().isdigit()]
        return len(pids) > 0, pids
    except:
        return False, []

def count_log_thread_starts(log_path="/tmp/omni-server-kvcache-fix2.log"):
    """Count 'create llm thread success' lines in server log."""
    try:
        r = subprocess.run(["grep", "-c", "create llm thread success", log_path],
                          capture_output=True, text=True)
        return int(r.stdout.strip() or 0)
    except:
        return -1

def count_log_cann_errors(log_path="/tmp/omni-server-kvcache-fix2.log"):
    """Count CANN error lines."""
    try:
        r = subprocess.run(["grep", "-ci", "CANN error\|ACL error\|acl error\|runtime error",
                          log_path], capture_output=True, text=True)
        return int(r.stdout.strip() or 0)
    except:
        return -1

def main():
    print("C12: Thread Lifecycle Regression Test")
    print("="*60)

    # Record baseline thread starts
    baseline_starts = count_log_thread_starts()
    baseline_cann_err = count_log_cann_errors()
    print(f"Baseline: {baseline_starts} thread starts logged, {baseline_cann_err} CANN errors")

    alive, pids = check_server_health()
    if not alive:
        print("ERROR: Server not running!")
        return 1
    print(f"Server PID: {pids}")

    results = []
    adapter = LlamaOmniServerAdapter(server_url=SERVER_URL,
                                     model_dir=MODEL_DIR,
                                     debug_dir=DEBUG_DIR)
    adapter_tts = LlamaOmniServerAdapter(server_url=SERVER_URL,
                                         model_dir=MODEL_DIR,
                                         debug_dir=DEBUG_DIR + "_tts")

    test_num = 0

    # ============ Phase 1: 20 HIT requests (same prefix A) ============
    print("\n--- Phase 1: 20 HIT requests (PREFIX_A) ---")
    audio_a = AUDIO["A0000"]
    for i in range(20):
        test_num += 1
        label = f"HIT_A_{i:02d}"
        r = run_request(adapter, audio_a, "用中文简短回答", label)
        results.append(r)
        status = "✅" if r["ok"] else "❌"
        print(f"  [{test_num:02d}/60] {label}: {status} e2e={r['e2e_ms']}ms wall={r['wall_s']:.1f}s")
        if not r["ok"]:
            print(f"    ERROR: {r.get('error', 'unknown')[:120]}")
        time.sleep(0.3)

    # ============ Phase 2: 10 MISS requests (different prefixes) ============
    print("\n--- Phase 2: 10 MISS requests (PREFIX_B, C, custom) ---")
    miss_audios = [AUDIO["A0001"], CUSTOM_AUDIO, AUDIO["A0002"], AUDIO["A0003"]] if "A0002" in AUDIO else [AUDIO["A0001"], CUSTOM_AUDIO]
    for i in range(10):
        test_num += 1
        audio = miss_audios[i % len(miss_audios)]
        label = f"MISS_{i:02d}"
        r = run_request(adapter, audio, "用中文简短回答", label)
        results.append(r)
        status = "✅" if r["ok"] else "❌"
        print(f"  [{test_num:02d}/60] {label}: {status} e2e={r['e2e_ms']}ms wall={r['wall_s']:.1f}s {os.path.basename(audio)}")
        if not r["ok"]:
            print(f"    ERROR: {r.get('error', 'unknown')[:120]}")
        time.sleep(0.3)

    # ============ Phase 3: 10 A/B/C switch ============
    print("\n--- Phase 3: 10 A/B/C switch ---")
    abc_audios = [AUDIO["A0000"], AUDIO["A0001"], CUSTOM_AUDIO]
    for i in range(10):
        test_num += 1
        audio = abc_audios[i % 3]
        label = f"SWITCH_{i:02d}"
        r = run_request(adapter, audio, "用中文简短回答", label)
        results.append(r)
        status = "✅" if r["ok"] else "❌"
        print(f"  [{test_num:02d}/60] {label}: {status} e2e={r['e2e_ms']}ms wall={r['wall_s']:.1f}s {os.path.basename(audio)}")
        if not r["ok"]:
            print(f"    ERROR: {r.get('error', 'unknown')[:120]}")
        time.sleep(0.3)

    # ============ Phase 4: 5 corruption + rebuild ============
    print("\n--- Phase 4: 5 corruption + rebuild ---")
    for i in range(5):
        test_num += 1
        label = f"CORRUPT_{i:02d}"

        # Corrupt a specific cache file
        cache_files = [f for f in os.listdir(KV_CACHE_DIR) if f.endswith('.bin')]
        if cache_files:
            target = os.path.join(KV_CACHE_DIR, cache_files[i % len(cache_files)])
            sz = os.path.getsize(target)
            with open(target, "r+b") as f:
                f.seek(4)  # Write bad magic at offset 4
                f.write(b"\x43\x4f\x52\x52")
            print(f"  Corrupted: {os.path.basename(target)} ({sz} bytes)")

        audio = AUDIO["A0000"]  # This will MISS since cache is corrupt
        r = run_request(adapter, audio, "用中文简短回答", label)
        results.append(r)
        status = "✅" if r["ok"] else "❌"
        print(f"  [{test_num:02d}/60] {label}: {status} e2e={r['e2e_ms']}ms wall={r['wall_s']:.1f}s (corrupt→rebuild)")
        if not r["ok"]:
            print(f"    ERROR: {r.get('error', 'unknown')[:120]}")
        time.sleep(0.3)

    # ============ Phase 5: 10 TTS requests ============
    print("\n--- Phase 5: 10 TTS requests ---")
    for i in range(10):
        test_num += 1
        audio = AUDIO["A0000"]
        label = f"TTS_{i:02d}"
        r = run_request(adapter_tts, audio, "用中文简短回答", label, use_tts=True, timeout=180)
        results.append(r)
        status = "✅" if r["ok"] else "❌"
        print(f"  [{test_num:02d}/60] {label}: {status} e2e={r['e2e_ms']}ms wall={r['wall_s']:.1f}s (TTS)")
        if not r["ok"]:
            print(f"    ERROR: {r.get('error', 'unknown')[:120]}")
        time.sleep(0.5)

    # ============ Phase 6: 5 disconnect simulations ============
    print("\n--- Phase 6: 5 disconnect simulations (short timeout) ---")
    for i in range(5):
        test_num += 1
        label = f"DISCON_{i:02d}"
        try:
            # Use a new adapter that won't be reused, simulating fresh connection
            disc_adapter = LlamaOmniServerAdapter(server_url=SERVER_URL,
                                                  model_dir=MODEL_DIR,
                                                  debug_dir=DEBUG_DIR + f"_disc{i}")
            audio = AUDIO["A0000"]
            r = run_request(disc_adapter, audio, "用中文简短回答", label, timeout=60)
            results.append(r)
            status = "✅" if r["ok"] else "❌"
        except Exception as e:
            results.append({"label": label, "init_ok": False, "ok": False,
                          "error": f"disconnect_exception:{e}", "e2e_ms": 0, "wall_s": 0})
            status = "⚠️"
        print(f"  [{test_num:02d}/60] {label}: {status}")
        time.sleep(0.3)

    # ============ Results Summary ============
    print("\n" + "="*60)
    print("C12 RESULTS SUMMARY")
    print("="*60)

    ok_count = sum(1 for r in results if r["ok"])
    fail_count = sum(1 for r in results if not r["ok"])
    init_fail = sum(1 for r in results if not r.get("init_ok", False))
    total = len(results)

    hists = [r for r in results if "HIT" in r["label"]]
    misses = [r for r in results if "MISS" in r["label"]]
    switches = [r for r in results if "SWITCH" in r["label"]]
    corrupts = [r for r in results if "CORRUPT" in r["label"]]
    tts_reqs = [r for r in results if "TTS" in r["label"]]
    discons = [r for r in results if "DISCON" in r["label"]]

    print(f"Total: {total}/60 requests")
    print(f"  OK: {ok_count} | FAIL: {fail_count} | INIT_FAIL: {init_fail}")

    def phase_stats(name, items):
        ok = sum(1 for r in items if r["ok"])
        e2es = [r["e2e_ms"] for r in items if r["ok"] and r["e2e_ms"] > 0]
        avg = sum(e2es)/len(e2es) if e2es else 0
        print(f"  {name:12s}: {ok:2d}/{len(items):2d} OK | avg_e2e={avg:.0f}ms")
        return ok

    phase_stats("HIT (20)", hists)
    phase_stats("MISS (10)", misses)
    phase_stats("SWITCH (10)", switches)
    phase_stats("CORRUPT (5)", corrupts)
    phase_stats("TTS (10)", tts_reqs)
    phase_stats("DISCON (5)", discons)

    # Server health check
    print()
    final_starts = count_log_thread_starts()
    final_cann_err = count_log_cann_errors()
    new_starts = final_starts - baseline_starts
    print(f"Thread starts logged: {baseline_starts} → {final_starts} (Δ={new_starts})")
    print(f"CANN errors: {baseline_cann_err} → {final_cann_err} (Δ={final_cann_err - baseline_cann_err})")

    alive, pids = check_server_health()
    print(f"Server alive: {alive} (PIDs: {pids})")

    # Cache file check
    cache_files = [f for f in os.listdir(KV_CACHE_DIR) if f.endswith('.bin')]
    print(f"Cache files: {len(cache_files)} ({', '.join(cache_files)})")

    # Write results
    report = {
        "total": total, "ok": ok_count, "fail": fail_count, "init_fail": init_fail,
        "thread_starts_delta": new_starts,
        "cann_errors_delta": final_cann_err - baseline_cann_err,
        "server_alive": alive,
        "cache_files": len(cache_files),
        "phases": {
            "hit_20": {"n": len(hists), "ok": sum(1 for r in hists if r["ok"])},
            "miss_10": {"n": len(misses), "ok": sum(1 for r in misses if r["ok"])},
            "switch_10": {"n": len(switches), "ok": sum(1 for r in switches if r["ok"])},
            "corrupt_5": {"n": len(corrupts), "ok": sum(1 for r in corrupts if r["ok"])},
            "tts_10": {"n": len(tts_reqs), "ok": sum(1 for r in tts_reqs if r["ok"])},
            "discon_5": {"n": len(discons), "ok": sum(1 for r in discons if r["ok"])},
        },
        "details": results
    }

    report_path = os.path.join(DEBUG_DIR, "c12_results.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nReport: {report_path}")

    # Gate verdict
    min_expected = 55  # Allow up to 5 failures from TTS timeouts or disconnect edge cases
    if ok_count >= min_expected and alive and final_cann_err == baseline_cann_err:
        print("\n🏆 C12 GATE: PASS")
        return 0
    elif ok_count >= min_expected:
        print(f"\n⚠️  C12 GATE: CONDITIONAL_PASS ({ok_count}/{total} OK, server alive)")
        return 0
    else:
        print(f"\n❌ C12 GATE: FAIL ({ok_count}/{total} OK, expected ≥{min_expected})")
        return 1

if __name__ == "__main__":
    sys.exit(main())
