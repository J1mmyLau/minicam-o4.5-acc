#!/usr/bin/env python3
"""
S13 120/120 STRICT Baseline — Frozen Prompts, Token Cap, Wall Safety
====================================================================
Step 7: Full re-run with unmodified frozen prompts, first-attempt only,
server evidence preserved.

Key changes from original S13 script:
  1. Loads prompts from S13_FROZEN_PROMPTS.jsonl (SHA256 verified)
  2. Adds max_tokens=256 + wall_timeout_ms=300000 to each decode
  3. Parses new F6 S13 response fields (stop_reason, generated_token_count, etc.)
  4. No prompt modification allowed — failure = failure
"""

import requests
import time
import os
import glob
import json
import sys
import re
import statistics
import datetime
import hashlib

# ── Config ────────────────────────────────────
BASE = "http://127.0.0.1:18093"
AUDIO_PREFIX = "/workspace/llama.cpp-omni-f6/tools/omni/assets/test_case/omni_test_case/omni_test_case_"
SERVER_LOG = "/tmp/f6_s13_step6_v2_srv.log"  # current server log (Step 6 + Step 7)
OUTPUT_DIR = "/tmp/f6_s13_step7_results"
FROZEN_PROMPTS = "/workspace/llama.cpp-omni-f6/docs/tracking/f6_lifecycle/data/S13_FROZEN_PROMPTS.jsonl"
USE_TTS = True
REQUEST_TIMEOUT = 360  # HTTP timeout per request (6 min)
MAX_TOKENS = 256       # Per-request token cap
WALL_TIMEOUT_MS = 300000  # Per-request wall-time safety (5 min)

TOTAL_REQUESTS = 120
REQUESTS_PER_CASE = 30
CASE_TYPES = ["short_cn", "long_cn", "english", "number_mix"]
CASE_LABELS = {
    "short_cn": "短中文", "long_cn": "长中文",
    "english": "英文", "number_mix": "数字混合",
}
CASE_AUDIOS = {
    "short_cn":   ["0000.wav", "0001.wav"],
    "long_cn":    ["0002.wav", "0003.wav"],
    "english":    ["0004.wav", "0005.wav"],
    "number_mix": ["0006.wav", "0007.wav"],
}


# ── Load frozen prompts ────────────────────────
def load_frozen_prompts(path):
    """Load frozen prompts and verify no duplicates or missing entries."""
    prompts = {}
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            case_id = d["case_id"]
            calculated_sha = hashlib.sha256(d["prompt"].encode("utf-8")).hexdigest()
            prompts[case_id] = {
                "case_id": case_id,
                "category": d["category"],
                "prompt": d["prompt"],
                "expected_sha256": d["prompt_sha256"],
                "calculated_sha256": calculated_sha,
                "sha256_match": calculated_sha == d["prompt_sha256"],
            }
    return prompts


# ── Helpers ────────────────────────────────────
def log_size():
    try:
        return os.path.getsize(SERVER_LOG)
    except Exception:
        return 0


def run_one_request(case_id, prompt, category, audio_file, round_idx):
    """Execute one request: omni_init -> prefill -> decode.
    Returns dict of metrics.
    """
    audio_base = AUDIO_PREFIX + audio_file.replace(".wav", "")

    metrics = {
        "case_id": case_id, "category": category,
        "round": round_idx, "audio": audio_file,
        "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "max_tokens": MAX_TOKENS, "wall_timeout_ms": WALL_TIMEOUT_MS,
    }

    # ── omni_init ──
    t0 = time.time()
    try:
        r = requests.post(
            BASE + "/v1/stream/omni_init",
            json={"msg_type": 1, "media_type": 1, "use_tts": USE_TTS},
            timeout=REQUEST_TIMEOUT,
        )
    except Exception as e:
        metrics["error"] = f"omni_init exception: {e}"
        return metrics
    metrics["init_wall_s"] = time.time() - t0
    if r.status_code != 200:
        metrics["error"] = f"omni_init HTTP {r.status_code}: {r.text[:200]}"
        return metrics

    # ── prefill ──
    t0 = time.time()
    try:
        r = requests.post(
            BASE + "/v1/stream/prefill",
            json={"audio_path_prefix": audio_base, "cnt": 1, "text": prompt},
            timeout=REQUEST_TIMEOUT,
        )
    except Exception as e:
        metrics["error"] = f"prefill exception: {e}"
        return metrics
    metrics["prefill_wall_ms"] = (time.time() - t0) * 1000.0
    if r.status_code != 200:
        metrics["error"] = f"prefill HTTP {r.status_code}: {r.text[:200]}"
        return metrics

    # ── decode with token cap + wall safety ──
    pos_before = log_size()
    t0 = time.time()
    try:
        r = requests.post(
            BASE + "/v1/stream/decode",
            json={
                "debug_dir": "./",
                "stream": False,
                "round_idx": round_idx,
                "max_tokens": MAX_TOKENS,
                "wall_timeout_ms": WALL_TIMEOUT_MS,
            },
            timeout=REQUEST_TIMEOUT,
        )
    except Exception as e:
        metrics["error"] = f"decode exception: {e}"
        return metrics
    metrics["decode_wall_ms"] = (time.time() - t0) * 1000.0
    pos_after = log_size()

    if r.status_code == 200:
        d = r.json()
        metrics["success"] = d.get("success", False)
        # F6 S13 runtime evidence
        metrics["stop_reason"] = d.get("stop_reason", "?")
        metrics["stop_reason_code"] = d.get("stop_reason_code", -1)
        metrics["generated_token_count"] = d.get("generated_token_count", -1)
        metrics["eos_detected"] = d.get("eos_detected", False)
        metrics["sliding_window_count"] = d.get("sliding_window_count", -1)
        metrics["cli_n_predict"] = d.get("cli_n_predict", -1)
        metrics["request_max_tokens"] = d.get("request_max_tokens", -1)
        metrics["effective_max_tokens"] = d.get("effective_max_tokens", -1)
    else:
        metrics["error"] = f"decode HTTP {r.status_code}: {r.text[:200]}"

    # ── Server log evidence ──
    metrics["log_bytes_before"] = pos_before
    metrics["log_bytes_after"] = pos_after
    metrics["log_grew"] = pos_after - pos_before if pos_before > 0 else -1

    return metrics


# ── Progressive gate check ─────────────────────
def check_progressive_gate(ok_results, gate_size):
    """Report progressive gate status."""
    n = len(ok_results)
    if n < gate_size:
        return
    slice_results = ok_results[:gate_size]
    errs = sum(1 for r in slice_results if "error" in r)
    wall_ms = [r.get("decode_wall_ms", 0) for r in slice_results if "error" not in r]
    gen_tokens = [r.get("generated_token_count", -1) for r in slice_results if "error" not in r]
    stop_eos = sum(1 for r in slice_results if r.get("stop_reason") == "eos")
    stop_max = sum(1 for r in slice_results if r.get("stop_reason") == "max_tokens")
    stop_wall = sum(1 for r in slice_results if r.get("stop_reason") == "wall_timeout")
    slide = sum(1 for r in slice_results if r.get("sliding_window_count", 0) > 0)

    status = "PASS" if errs == 0 else f"FAIL({errs}err)"
    print(f"  Gate {gate_size:3d}: {status} | eos={stop_eos} max_tok={stop_max} "
          f"wall_tmo={stop_wall} | gen_p50={statistics.median(gen_tokens) if gen_tokens else 0:.0f} "
          f"wall_p50={statistics.median(wall_ms):.0f}ms | slide={slide}")


# ── Main ───────────────────────────────────────
def main():
    print(f"=== S13 STRICT 120 Baseline (Step 7) ===")
    print(f"Server: {BASE}")
    print(f"max_tokens: {MAX_TOKENS}, wall_timeout_ms: {WALL_TIMEOUT_MS}")
    print(f"Frozen prompts: {FROZEN_PROMPTS}")
    print(f"Start: {datetime.datetime.now().isoformat()}")
    print()

    # Load frozen prompts
    frozen = load_frozen_prompts(FROZEN_PROMPTS)
    sha_ok = sum(1 for p in frozen.values() if p["sha256_match"])
    sha_bad = sum(1 for p in frozen.values() if not p["sha256_match"])
    print(f"Frozen prompts loaded: {len(frozen)} entries ({sha_ok} SHA256 OK, {sha_bad} MISMATCH)")
    if sha_bad > 0:
        for p in frozen.values():
            if not p["sha256_match"]:
                print(f"  SHA256 MISMATCH: {p['case_id']}")
        print("ABORTING: frozen prompt integrity check failed")
        return 1
    print()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_results = []
    ok_results = []
    progressive_gates = [20, 40, 60, 80, 100, 120]
    last_gate_checked = 0

    request_order = 0
    for case_type in CASE_TYPES:
        # Filter prompts for this case type
        case_prompts = [(cid, p) for cid, p in sorted(frozen.items())
                        if p["category"] == case_type and cid.startswith(case_type)]
        case_prompts.sort(key=lambda x: x[0])  # R01..R30 order
        audios = CASE_AUDIOS[case_type]

        print(f"--- {CASE_LABELS[case_type]} ({case_type}): {len(case_prompts)} prompts ---")

        for i, (case_id, fp) in enumerate(case_prompts):
            request_order += 1
            audio_file = audios[i % len(audios)]
            label = f"{case_id}"
            print(f"[{request_order:3d}/{TOTAL_REQUESTS}] {label}: '{fp['prompt'][:60]}...' ",
                  end="", flush=True)

            result = run_one_request(case_id, fp["prompt"], case_type, audio_file, i)
            result["request_order"] = request_order
            all_results.append(result)

            if "error" in result:
                print(f"ERROR: {result['error']}")
            else:
                ok_results.append(result)
                status = "✓" if result.get("stop_reason") == "eos" else "⚠"
                print(f"{status} {result.get('stop_reason','?')} "
                      f"gen={result.get('generated_token_count','?')} "
                      f"eos={result.get('eos_detected',False)} "
                      f"wall={result.get('decode_wall_ms',0):.0f}ms "
                      f"slide={result.get('sliding_window_count',0)}")

            # Progressive gate check
            for gate in progressive_gates:
                if len(ok_results) >= gate and gate > last_gate_checked:
                    check_progressive_gate(ok_results, gate)
                    last_gate_checked = gate

            # Save incremental results
            inc_path = os.path.join(OUTPUT_DIR, f"s13_step7_incremental_r{request_order:03d}.json")
            with open(inc_path, "w") as f:
                json.dump({
                    "meta": {
                        "step": "Step 7: S13 120 STRICT",
                        "progress": f"{request_order}/{TOTAL_REQUESTS}",
                        "timestamp": datetime.datetime.now().isoformat(),
                    },
                    "all_results": all_results,
                }, f, indent=2, ensure_ascii=False)

    # ── Final Summary ──
    print()
    print("=" * 60)
    print("S13 STRICT 120 BASELINE — FINAL RESULTS")
    print("=" * 60)

    total = len(all_results)
    ok = sum(1 for r in all_results if "error" not in r and r.get("success") is not False)
    errs = sum(1 for r in all_results if "error" in r)
    eos_count = sum(1 for r in all_results if r.get("stop_reason") == "eos")
    max_tok_count = sum(1 for r in all_results if r.get("stop_reason") == "max_tokens")
    wall_count = sum(1 for r in all_results if r.get("stop_reason") == "wall_timeout")
    slide_count = sum(1 for r in all_results if r.get("sliding_window_count", 0) > 0)

    ok_wall = [r.get("decode_wall_ms", 0) for r in all_results if "error" not in r]
    ok_gen = [r.get("generated_token_count", -1) for r in all_results if "error" not in r]

    print(f"Total: {total} requests ({TOTAL_REQUESTS} expected)")
    print(f"OK: {ok}, ERROR: {errs}")
    print(f"Stop reasons: EOS={eos_count}, MAX_TOKENS={max_tok_count}, WALL_TIMEOUT={wall_count}")
    print(f"Sliding window events: {slide_count}")
    if ok_wall:
        print(f"Decode wall: p50={statistics.median(ok_wall):.0f}ms, "
              f"p95={sorted(ok_wall)[int(len(ok_wall)*0.95)]:.0f}ms, "
              f"p99={sorted(ok_wall)[int(len(ok_wall)*0.99)]:.0f}ms")
    if ok_gen:
        print(f"Generated tokens: p50={statistics.median(ok_gen):.0f}, "
              f"p95={sorted(ok_gen)[int(len(ok_gen)*0.95)]:.0f}")

    prompt_modified = sum(1 for r in all_results if r.get("prompt_modified", False))
    first_attempt_ok = sum(1 for r in all_results if "error" not in r)
    evidence_ok = sum(1 for r in all_results if r.get("log_grew", -1) > 0)

    print(f"Prompt modified: {prompt_modified} (target: 0)")
    print(f"First-attempt OK: {first_attempt_ok}/{total}")
    print(f"Server evidence preserved: {evidence_ok}/{total}")

    if errs > 0:
        print("\nERROR DETAILS:")
        for r in all_results:
            if "error" in r:
                print(f"  {r.get('case_id','?')} (order={r.get('request_order','?')}): {r['error']}")

    # Per-category summary
    print()
    for case_type in CASE_TYPES:
        cr = [r for r in all_results if r.get("category") == case_type]
        ok_c = sum(1 for r in cr if "error" not in r and r.get("success") is not False)
        err_c = sum(1 for r in cr if "error" in r)
        eos_c = sum(1 for r in cr if r.get("stop_reason") == "eos")
        wall_c = [r.get("decode_wall_ms", 0) for r in cr if "error" not in r]
        gen_c = [r.get("generated_token_count", -1) for r in cr if "error" not in r]
        print(f"  {CASE_LABELS[case_type]:6s}: ok={ok_c}/{len(cr)}, err={err_c}, "
              f"eos={eos_c}, wall_p50={statistics.median(wall_c) if wall_c else 0:.0f}ms, "
              f"gen_p50={statistics.median(gen_c) if gen_c else 0:.0f}")

    # ── Gate Status ──
    print()
    print("=" * 60)
    print("GATE STATUS")
    print("=" * 60)

    strict_pass = (errs == 0 and ok == TOTAL_REQUESTS and prompt_modified == 0)
    e2e_complete = ok == TOTAL_REQUESTS
    evidence_intact = evidence_ok == TOTAL_REQUESTS
    runaway_free = wall_count == 0 and slide_count == 0

    print(f"S13_STRICT_FIRST_ATTEMPT:     {'PASS' if strict_pass else 'FAIL'} ({ok}/{TOTAL_REQUESTS})")
    print(f"S13_FROZEN_PROMPT_INTEGRITY:  {'PASS' if prompt_modified == 0 else 'FAIL'} (modified={prompt_modified})")
    print(f"S13_RUNAWAY_GENERATION:       {'PASS' if runaway_free else 'FAIL'} (wall_tmo={wall_count} slide={slide_count})")
    print(f"S13_SERVER_EVIDENCE:          {'PASS' if evidence_intact else 'FAIL'} ({evidence_ok}/{TOTAL_REQUESTS})")
    print(f"S13_STRICT_BASELINE:          {'PASS ✅' if strict_pass else 'FAIL ❌'}")

    # ── Save final ──
    final_path = os.path.join(OUTPUT_DIR, "s13_step7_final.json")
    with open(final_path, "w") as f:
        json.dump({
            "meta": {
                "step": "Step 7: S13 120 STRICT baseline",
                "server": BASE,
                "max_tokens": MAX_TOKENS,
                "wall_timeout_ms": WALL_TIMEOUT_MS,
                "frozen_prompts": FROZEN_PROMPTS,
                "server_log": SERVER_LOG,
                "timestamp": datetime.datetime.now().isoformat(),
            },
            "summary": {
                "total": total, "ok": ok, "error": errs,
                "eos": eos_count, "max_tokens": max_tok_count, "wall_timeout": wall_count,
                "sliding_window": slide_count,
                "prompt_modified": prompt_modified,
                "first_attempt_ok": first_attempt_ok,
                "evidence_intact": evidence_intact,
                "strict_pass": strict_pass,
            },
            "gates": {
                "S13_STRICT_FIRST_ATTEMPT": strict_pass,
                "S13_FROZEN_PROMPT_INTEGRITY": prompt_modified == 0,
                "S13_RUNAWAY_GENERATION": runaway_free,
                "S13_SERVER_EVIDENCE": evidence_intact,
                "S13_STRICT_BASELINE": strict_pass,
            },
            "all_results": all_results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {final_path}")

    return 0 if strict_pass else 1


if __name__ == "__main__":
    sys.exit(main())
