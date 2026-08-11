#!/usr/bin/env python3 -u
"""F6 Phase 3 Step 9: Static prefix E2E A/B — MISS vs HIT, 30 matched pairs.

Design:
  - 5 test cases (0,1,3,4,5 — skip 2 which has long responses)
  - 6 matched pairs per case = 30 total pairs
  - Per case: Prime once (cache=1, populates), then 6 × (A→B)
    - A: OMNI_KV_CACHE_REUSE=0 (cache disabled, full prefill = MISS baseline)
    - B: OMNI_KV_CACHE_REUSE=1 (cache enabled, reuses primed cache = HIT)
  - Measures: request_to_first_audio_ms, prefill_ms, decode_to_first_audio_ms
  - E2E profiling enabled to verify no stale/cross writes (R7/R9 check)

Binary: build-f6-phase3-relwithdebinfo (SHA 35fd85a5 matched to handoff)
"""
import json, os, shutil, subprocess, sys, time
from pathlib import Path

BINARY = "/workspace/llama.cpp-omni-f6/build-f6-phase3-relwithdebinfo/bin/llama-omni-cli"
MODEL  = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf"
TEST_PREFIX = "/workspace/llama.cpp-omni-f6/tools/omni/assets/test_case/omni_test_case/omni_test_case_"
OUTDIR  = "/tmp/f6_step9_static_prefix_ab"
LOGDIR  = f"{OUTDIR}/logs"
CACHE_DIR = f"{OUTDIR}/kv_cache"
E2E_DIR = f"{OUTDIR}/e2e_profiles"

CASES = [0, 1, 3, 4, 5]   # 5 cases (skip case 2)
PAIRS_PER_CASE = 6          # 5 × 6 = 30 matched pairs
PER_RUN_TIMEOUT = 180       # 3 min per run

os.makedirs(LOGDIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(E2E_DIR, exist_ok=True)


def run_cli(case_id, cache_enabled, e2e_dir, label):
    """Run llama-omni-cli for a single test case. Returns timing dict."""
    env = os.environ.copy()
    env["OMNI_T2W_DEVICE"] = "cann-flow-only"
    env["OMP_NUM_THREADS"] = "8"
    env["OMNI_T2W_DRAIN_TIMEOUT_MS"] = "30000"
    env["OMNI_KV_CACHE_PATH"] = CACHE_DIR
    if cache_enabled:
        env["OMNI_KV_CACHE_REUSE"] = "1"
    # E2E profiling for R7/R9 verification
    env["OMNI_E2E_PROFILE"] = "1"
    env["OMNI_E2E_PROFILE_DIR"] = e2e_dir

    stdout_log = f"{LOGDIR}/{label}_stdout.log"
    stderr_log = f"{LOGDIR}/{label}_stderr.log"

    t0 = time.time()
    try:
        proc = subprocess.run(
            [BINARY, "-m", MODEL, "-ngl", "0", "--omni",
             "--test", TEST_PREFIX, "1", "--test-start", str(case_id)],
            env=env, capture_output=True, timeout=PER_RUN_TIMEOUT,
            cwd=OUTDIR,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        return {
            "label": label, "case_id": case_id, "cache_enabled": cache_enabled,
            "elapsed_s": round(elapsed, 3), "returncode": -1,
            "valid": False, "invalid_reason": "timeout",
            "request_fa_ms": None, "decode_fa_ms": None, "prefill_ms": None,
            "cache_hit": 0, "cache_miss": 0, "reused_tokens": 0,
            "wav_count": 0, "terminal": "TIMEOUT",
        }
    except Exception as e:
        elapsed = time.time() - t0
        return {
            "label": label, "case_id": case_id, "cache_enabled": cache_enabled,
            "elapsed_s": round(elapsed, 3), "returncode": -2,
            "valid": False, "invalid_reason": f"exception:{e}",
            "request_fa_ms": None, "decode_fa_ms": None, "prefill_ms": None,
            "cache_hit": 0, "cache_miss": 0, "reused_tokens": 0,
            "wav_count": 0, "terminal": "EXCEPTION",
        }
    elapsed = time.time() - t0

    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")

    with open(stdout_log, "w") as f:
        f.write(stdout)
    with open(stderr_log, "w") as f:
        f.write(stderr)

    # Parse metrics
    import re

    # request_to_first_audio: second number after | (ms)
    rfa_match = re.search(r'\|\s*(\d+)ms\s*\(request_to_first_audio\)', stdout)
    rfa_ms = int(rfa_match.group(1)) if rfa_match else None

    # decode_to_first_audio: first number (首响时间)
    dfa_match = re.search(r'首响时间[^:]*:\s*(\d+)', stdout)
    dfa_ms = int(dfa_match.group(1)) if dfa_match else None

    # prefill time (seconds in log)
    pf_match = re.search(r'prefill \d+ \(audio\+vision\)\s*:\s*([0-9.]+)', stdout)
    prefill_ms = float(pf_match.group(1)) * 1000 if pf_match else None

    # KV cache stats (stderr)
    cache_hit = int(re.search(r'cache_hits:\s*(\d+)', stderr).group(1)) if re.search(r'cache_hits:\s*(\d+)', stderr) else 0
    cache_miss = int(re.search(r'cache_misses:\s*(\d+)', stderr).group(1)) if re.search(r'cache_misses:\s*(\d+)', stderr) else 0
    reused_tokens = int(re.search(r'tokens_reused:\s*(\d+)', stderr).group(1)) if re.search(r'tokens_reused:\s*(\d+)', stderr) else 0

    # WAV count — parse from terminal line: "AUDIO_SUCCESS (3 WAV(s))"
    wav_match = re.search(r'AUDIO_SUCCESS\s*\((\d+)\s*WAV', stdout)
    if wav_match:
        wav_count = int(wav_match.group(1))
    else:
        # Fallback: count T2W file save lines
        wav_count = len(re.findall(r'T2W.*wav_\d+', stdout))

    # T2W terminal
    term_match = re.search(r'T2W terminal:\s*(\w+)', stdout)
    terminal = term_match.group(1) if term_match else "UNKNOWN"

    # Validity
    valid = True
    invalid_reason = ""
    if proc.returncode != 0:
        valid = False
        invalid_reason = f"rc_{proc.returncode}"
    elif proc.returncode == 0 and wav_count == 0:
        valid = False
        invalid_reason = "rc0_without_audio"
    elif terminal in ("DRAIN_TIMEOUT", "PIPELINE_FAILURE", "OUTPUT_BLOCKED"):
        valid = False
        invalid_reason = terminal.lower()

    return {
        "label": label, "case_id": case_id, "cache_enabled": cache_enabled,
        "elapsed_s": round(elapsed, 3), "returncode": proc.returncode,
        "valid": valid, "invalid_reason": invalid_reason,
        "request_fa_ms": rfa_ms, "decode_fa_ms": dfa_ms, "prefill_ms": prefill_ms,
        "cache_hit": cache_hit, "cache_miss": cache_miss, "reused_tokens": reused_tokens,
        "wav_count": wav_count, "terminal": terminal,
    }


def check_e2e_profiles(e2e_dir):
    """Verify E2E profiles for R7/R9 correctness."""
    sync_profiles = sorted(Path(e2e_dir).glob("e2e_*.json"))
    sync_no_audio = [f for f in sync_profiles if "_audio" not in f.name]
    if not sync_no_audio:
        return {"stale": -1, "cross": -1, "missing_flow": -1, "n_profiles": 0}

    stale = cross = missing_flow = 0
    for sf in sync_no_audio:
        try:
            data = json.loads(sf.read_text())
            stale += data.get("stale_write_count", 0)
            cross += data.get("cross_request_write_count", 0)
            stages = data.get("stages_ms", {})
            if "flow_start" not in stages or stages.get("flow_start", 0) <= 0:
                missing_flow += 1
        except Exception:
            pass
    return {
        "stale": stale, "cross": cross, "missing_flow": missing_flow,
        "n_profiles": len(sync_no_audio),
    }


def main():
    print(f"F6 Phase 3 Step 9: Static Prefix E2E A/B")
    print(f"  Binary: {BINARY}")
    print(f"  Cases: {CASES}")
    print(f"  Pairs per case: {PAIRS_PER_CASE}")
    print(f"  Total matched pairs: {len(CASES) * PAIRS_PER_CASE}")
    print(f"  Output: {OUTDIR}")
    print()

    all_runs = []
    e2e_results = []

    for case_idx, case_id in enumerate(CASES):
        case_e2e_dir = f"{E2E_DIR}/case{case_id}"
        os.makedirs(case_e2e_dir, exist_ok=True)

        # ── Prime: populate cache ──
        # Clear any previous cache for this case
        for f in Path(CACHE_DIR).glob("*.bin"):
            f.unlink()
        for f in Path(case_e2e_dir).glob("*.json"):
            f.unlink()

        print(f"── Case {case_id} ({case_idx+1}/{len(CASES)}) ──")
        prime_label = f"case{case_id}_PRIME"
        prime_result = run_cli(case_id, cache_enabled=True,
                               e2e_dir=case_e2e_dir, label=prime_label)
        prime_e2e = check_e2e_profiles(case_e2e_dir)
        print(f"  PRIME: {'OK' if prime_result['valid'] else 'FAIL'} "
              f"rfa={prime_result['request_fa_ms']}ms prefill={prime_result['prefill_ms']:.0f}ms "
              f"(cache_miss={prime_result['cache_miss']}) "
              f"e2e:[stale={prime_e2e['stale']},cross={prime_e2e['cross']}]")

        # Clear e2e profiles between prime and test (prime is warmup)
        for f in Path(case_e2e_dir).glob("*.json"):
            f.unlink()

        # ── A/B pairs ──
        for pair in range(PAIRS_PER_CASE):
            # Clear e2e profiles between runs
            for f in Path(case_e2e_dir).glob("*.json"):
                f.unlink()

            # Arm A: MISS (cache disabled = always full prefill)
            label_a = f"case{case_id}_p{pair}_A_MISS"
            result_a = run_cli(case_id, cache_enabled=False,
                               e2e_dir=case_e2e_dir, label=label_a)
            e2e_a = check_e2e_profiles(case_e2e_dir)

            # Clear e2e profiles
            for f in Path(case_e2e_dir).glob("*.json"):
                f.unlink()

            # Arm B: HIT (cache enabled, should hit from prime or previous B)
            label_b = f"case{case_id}_p{pair}_B_HIT"
            result_b = run_cli(case_id, cache_enabled=True,
                               e2e_dir=case_e2e_dir, label=label_b)
            e2e_b = check_e2e_profiles(case_e2e_dir)

            # Determine if B was actually a HIT or MISS
            b_hit_status = "HIT" if result_b["reused_tokens"] > 0 else "MISS"

            a_ok = "OK" if result_a["valid"] else "FAIL"
            b_ok = "OK" if result_b["valid"] else "FAIL"
            rfa_delta = ""
            if result_a["request_fa_ms"] and result_b["request_fa_ms"]:
                rfa_delta = f"Δ={result_a['request_fa_ms'] - result_b['request_fa_ms']}ms"
            pf_delta = ""
            if result_a["prefill_ms"] and result_b["prefill_ms"]:
                pf_delta = f"Δpf={result_a['prefill_ms'] - result_b['prefill_ms']:.0f}ms"

            a_rfa_str = f"{result_a['request_fa_ms']}ms" if result_a['request_fa_ms'] else "N/A"
            a_pf_str = f"{result_a['prefill_ms']:.0f}ms" if result_a['prefill_ms'] else "N/A"
            b_rfa_str = f"{result_b['request_fa_ms']}ms" if result_b['request_fa_ms'] else "N/A"
            b_pf_str = f"{result_b['prefill_ms']:.0f}ms" if result_b['prefill_ms'] else "N/A"
            print(f"  [{pair+1:2d}/{PAIRS_PER_CASE}] "
                  f"A(MISS):{a_ok} rfa={a_rfa_str} pf={a_pf_str} "
                  f"e2e:[s={e2e_a['stale']},x={e2e_a['cross']}] | "
                  f"B({b_hit_status}):{b_ok} rfa={b_rfa_str} pf={b_pf_str} "
                  f"reused={result_b['reused_tokens']} "
                  f"e2e:[s={e2e_b['stale']},x={e2e_b['cross']}] "
                  f"| {rfa_delta} {pf_delta}")

            all_runs.append({"pair": pair, "case_id": case_id, "A": result_a, "B": result_b})
            e2e_results.append({"pair": pair, "case_id": case_id,
                                "e2e_a": e2e_a, "e2e_b": e2e_b,
                                "b_hit_status": b_hit_status})

            # Early exit on consistent failure
            fail_count = sum(1 for r in all_runs[-6:] if not r["A"]["valid"] or not r["B"]["valid"])
            if len(all_runs) >= 3 and fail_count >= 3:
                print(f"  WARNING: {fail_count}/3 recent failures — continuing but check logs")

    # ── Final Summary ──
    print(f"\n{'='*60}")
    print(f"F6 Phase 3 Step 9: Static Prefix E2E A/B — RESULTS")
    print(f"{'='*60}")

    valid_a = [r for r in all_runs if r["A"]["valid"]]
    valid_b = [r for r in all_runs if r["B"]["valid"]]
    paired = [(r["A"], r["B"]) for r in all_runs if r["A"]["valid"] and r["B"]["valid"]]

    print(f"Total pairs attempted: {len(all_runs)}")
    print(f"Valid A: {len(valid_a)}/{len(all_runs)}")
    print(f"Valid B: {len(valid_b)}/{len(all_runs)}")
    print(f"Fully valid pairs: {len(paired)}/{len(all_runs)}")

    # Timing analysis
    a_rfa = sorted([a["request_fa_ms"] for a, _ in paired if a["request_fa_ms"]])
    b_rfa = sorted([b["request_fa_ms"] for _, b in paired if b["request_fa_ms"]])
    a_pf = sorted([a["prefill_ms"] for a, _ in paired if a["prefill_ms"]])
    b_pf = sorted([b["prefill_ms"] for _, b in paired if b["prefill_ms"]])
    b_reused = [b["reused_tokens"] for _, b in paired]

    def p50(vals): return sorted(vals)[len(vals)//2] if vals else None
    def avg(vals): return sum(vals)/len(vals) if vals else None

    print(f"\nTiming (valid pairs, n={len(paired)}):")
    if a_rfa:
        print(f"  A (MISS): request_fa p50={p50(a_rfa)}ms, avg={avg(a_rfa):.0f}ms")
        print(f"  B (HIT):  request_fa p50={p50(b_rfa)}ms, avg={avg(b_rfa):.0f}ms")
        rfa_deltas = sorted([a["request_fa_ms"] - b["request_fa_ms"] for a, b in paired
                             if a["request_fa_ms"] and b["request_fa_ms"]])
        if rfa_deltas:
            print(f"  Δ request_fa p50={p50(rfa_deltas)}ms (improvement)")
    if a_pf:
        print(f"  A (MISS): prefill p50={p50(a_pf):.0f}ms, avg={avg(a_pf):.0f}ms")
        print(f"  B (HIT):  prefill p50={p50(b_pf):.0f}ms, avg={avg(b_pf):.0f}ms")
        if b_pf and b_pf[0] is not None:
            pf_ratio = avg(a_pf) / avg(b_pf) if avg(b_pf) and avg(b_pf) > 0 else float('inf')
            print(f"  Prefill speedup: {pf_ratio:.0f}×")
    if b_reused:
        print(f"  B reused tokens: p50={p50(b_reused)}, avg={avg(b_reused):.0f}, min={min(b_reused)}, max={max(b_reused)}")

    # E2E Stage Correctness (R7/R9 verification)
    all_stale = sum(e["e2e_a"]["stale"] + e["e2e_b"]["stale"] for e in e2e_results if e["e2e_a"]["stale"] >= 0)
    all_cross = sum(e["e2e_a"]["cross"] + e["e2e_b"]["cross"] for e in e2e_results if e["e2e_a"]["cross"] >= 0)

    # HIT-rate check
    hits = sum(1 for e in e2e_results if e["b_hit_status"] == "HIT")
    misses = sum(1 for e in e2e_results if e["b_hit_status"] == "MISS")

    print(f"\nE2E Profile Verification (R7/R9):")
    print(f"  Total stale writes: {all_stale}")
    print(f"  Total cross-request writes: {all_cross}")
    print(f"  B HIT-rate: {hits}/{hits+misses} ({100*hits/(hits+misses):.0f}%)")

    # Gate checks
    print(f"\nGate Checks:")
    checks = [
        ("Valid pairs >= 30", len(paired), 30, ">="),
        ("Stale writes == 0", all_stale, 0, "=="),
        ("Cross-request writes == 0", all_cross, 0, "=="),
        ("B HIT rate >= 80%", hits / max(hits + misses, 1), 0.80, ">="),
        ("Prefill improvement >= 100×", pf_ratio if 'pf_ratio' in dir() else 0, 100, ">="),
        ("A request_fa > B request_fa (p50)", 1 if a_rfa and b_rfa and p50(a_rfa) and p50(b_rfa) and p50(a_rfa) > p50(b_rfa) else 0, 1, "=="),
    ]

    all_pass = True
    for name, actual, expected, op in checks:
        if op == ">=":
            passed = actual >= expected
        elif op == "==":
            passed = actual == expected
        elif op == ">":
            passed = actual > expected
        else:
            passed = False
        flag = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        if isinstance(actual, float):
            print(f"  [{flag}] {name}: {actual:.1f} (expected {op} {expected})")
        else:
            print(f"  [{flag}] {name}: {actual} (expected {op} {expected})")

    # Save report
    report = {
        "test": "F6_Step9_StaticPrefix_E2E_AB",
        "binary": BINARY,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_pairs": len(paired),
        "n_total": len(all_runs),
        "cases": CASES,
        "timing": {
            "a_rfa_p50": p50(a_rfa), "b_rfa_p50": p50(b_rfa),
            "a_prefill_p50": p50(a_pf), "b_prefill_p50": p50(b_pf),
            "rfa_improvement_p50": p50(rfa_deltas) if 'rfa_deltas' in dir() and rfa_deltas else None,
        },
        "e2e": {"stale_writes": all_stale, "cross_writes": all_cross},
        "checks": {c[0]: {"actual": c[1], "expected": c[2], "passed": c[1] >= c[2] if c[3] == ">=" else c[1] == c[2]} for c in checks},
        "passed": all_pass,
    }
    report_path = f"{OUTDIR}/STEP9_REPORT.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Save detailed results
    detailed_path = f"{OUTDIR}/STEP9_DETAILED.json"
    with open(detailed_path, "w") as f:
        json.dump({"runs": all_runs, "e2e": e2e_results}, f, indent=2, default=str)

    print(f"\nReport: {report_path}")
    print(f"Detailed: {detailed_path}")
    print(f"\nStep 9: {'PASS' if all_pass else 'FAIL'}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
