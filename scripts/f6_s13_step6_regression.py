#!/usr/bin/env python3
"""Step 6: Targeted regression on original frozen R23-R30 prompts.
Each prompt run 3 times with max_tokens=128, wall_timeout_ms=180000.
All must pass first-attempt.
"""

import requests, time, json, sys, os
from datetime import datetime

BASE = "http://127.0.0.1:18093"
AUDIO_PREFIX = "/workspace/llama.cpp-omni-f6/tools/omni/assets/test_case/omni_test_case/omni_test_case_"
REQUEST_TIMEOUT = 300  # HTTP timeout per request
MAX_TOKENS = 128
WALL_TIMEOUT_MS = 180000  # 3 minutes

# Original frozen prompts for R23-R30 (indices 22-29 from MIXED_PROMPTS)
R_PROMPTS = {
    "R23": "人体有206块骨头，成年人有32颗牙齿",
    "R24": "地球到月球距离约384,400公里 (238,855 miles)",
    "R25": "0.1 + 0.2 == 0.3 在浮点数运算中是False, IEEE 754精度问题",
    "R26": "中文数字一二三四五六七八九十 vs Arabic numerals 1234567890",
    "R27": "黄金分割率 φ = (1+√5)/2 ≈ 1.6180339887",
    "R28": "computer用了多少个字母？答案是8个: c-o-m-p-u-t-e-r",
    "R29": "身份证号码是18位，第17位奇数=男偶数=女",
    "R30": "九九归一(9×9=81→8+1=9)，这是数字的奇妙规律",
}

AUDIO_MAP = {
    "R23": "0006.wav", "R24": "0007.wav",
    "R25": "0006.wav", "R26": "0007.wav",
    "R27": "0006.wav", "R28": "0007.wav",
    "R29": "0006.wav", "R30": "0007.wav",
}

N_RUNS = 3


def run_one(case_id, prompt, audio_file, run_idx):
    """Run one request: omni_init → prefill → decode. Returns result dict."""
    audio_base = AUDIO_PREFIX + audio_file.replace(".wav", "")
    result = {"case_id": case_id, "run": run_idx + 1, "prompt": prompt}

    # ── omni_init ──
    t0 = time.time()
    try:
        r = requests.post(
            BASE + "/v1/stream/omni_init",
            json={"msg_type": 1, "media_type": 1, "use_tts": True},
            timeout=REQUEST_TIMEOUT,
        )
    except Exception as e:
        result["error"] = f"omni_init exception: {e}"
        return result
    result["init_s"] = time.time() - t0
    if r.status_code != 200:
        result["error"] = f"omni_init HTTP {r.status_code}: {r.text[:200]}"
        return result
    init_data = r.json()

    # ── prefill ──
    t0 = time.time()
    try:
        r = requests.post(
            BASE + "/v1/stream/prefill",
            json={"audio_path_prefix": audio_base, "cnt": 1, "text": prompt},
            timeout=REQUEST_TIMEOUT,
        )
    except Exception as e:
        result["error"] = f"prefill exception: {e}"
        return result
    result["prefill_ms"] = (time.time() - t0) * 1000.0
    if r.status_code != 200:
        result["error"] = f"prefill HTTP {r.status_code}: {r.text[:200]}"
        return result

    # ── decode with token cap ──
    t0 = time.time()
    try:
        r = requests.post(
            BASE + "/v1/stream/decode",
            json={
                "debug_dir": "./",
                "stream": False,
                "round_idx": run_idx,
                "max_tokens": MAX_TOKENS,
                "wall_timeout_ms": WALL_TIMEOUT_MS,
            },
            timeout=REQUEST_TIMEOUT,
        )
    except Exception as e:
        result["error"] = f"decode exception: {e}"
        return result
    result["decode_wall_ms"] = (time.time() - t0) * 1000.0

    if r.status_code == 200:
        d = r.json()
        result["success"] = d.get("success", False)
        result["stop_reason"] = d.get("stop_reason", "?")
        result["stop_reason_code"] = d.get("stop_reason_code", -1)
        result["generated_token_count"] = d.get("generated_token_count", -1)
        result["eos_detected"] = d.get("eos_detected", False)
        result["sliding_window_count"] = d.get("sliding_window_count", -1)
        result["cli_n_predict"] = d.get("cli_n_predict", -1)
        result["request_max_tokens"] = d.get("request_max_tokens", -1)
        result["effective_max_tokens"] = d.get("effective_max_tokens", -1)
    else:
        result["error"] = f"decode HTTP {r.status_code}: {r.text[:200]}"
    return result


def main():
    print(f"=== Step 6: Targeted Regression R23-R30 ===")
    print(f"Server: {BASE}")
    print(f"max_tokens: {MAX_TOKENS}, wall_timeout_ms: {WALL_TIMEOUT_MS}")
    print(f"Runs per prompt: {N_RUNS}")
    print(f"Start: {datetime.now().isoformat()}")
    print()

    all_results = []
    for case_id in sorted(R_PROMPTS.keys(), key=lambda x: int(x[1:])):
        prompt = R_PROMPTS[case_id]
        audio = AUDIO_MAP[case_id]
        for run_idx in range(N_RUNS):
            label = f"{case_id}-run{run_idx + 1}"
            print(f"[{label}] prompt={prompt[:60]}... ", end="", flush=True)
            result = run_one(case_id, prompt, audio, run_idx)
            all_results.append(result)

            if "error" in result:
                print(f"ERROR: {result['error']}")
            else:
                print(f"OK stop={result.get('stop_reason','?')} "
                      f"gen={result.get('generated_token_count','?')}t "
                      f"wall={result.get('decode_wall_ms',0):.0f}ms "
                      f"eos={result.get('eos_detected',False)} "
                      f"slide={result.get('sliding_window_count','?')}")

    # Summary
    print()
    ok_count = sum(1 for r in all_results if "error" not in r and r.get("success"))
    err_count = sum(1 for r in all_results if "error" in r)
    eos_count = sum(1 for r in all_results if r.get("eos_detected"))
    max_tok_count = sum(1 for r in all_results
                        if r.get("stop_reason") == "max_tokens")
    wall_count = sum(1 for r in all_results
                     if r.get("stop_reason") == "wall_timeout")

    print(f"=== SUMMARY ===")
    print(f"Total: {len(all_results)} requests ({len(R_PROMPTS)} prompts × {N_RUNS} runs)")
    print(f"OK: {ok_count}, ERROR: {err_count}")
    print(f"Stop reasons: EOS={eos_count}, MAX_TOKENS={max_tok_count}, WALL_TIMEOUT={wall_count}")

    if err_count > 0:
        print("ERROR DETAILS:")
        for r in all_results:
            if "error" in r:
                print(f"  {r['case_id']}-run{r['run']}: {r['error']}")

    # Per-prompt pass/fail
    print()
    print("Per-prompt first-attempt check:")
    all_pass = True
    for case_id in sorted(R_PROMPTS.keys(), key=lambda x: int(x[1:])):
        runs = [r for r in all_results if r["case_id"] == case_id]
        ok = sum(1 for r in runs if "error" not in r and r.get("success"))
        stop_reasons = [r.get("stop_reason", "?") for r in runs]
        gen_tokens = [r.get("generated_token_count", "?") for r in runs]
        wall_ms = [r.get("decode_wall_ms", 0) for r in runs]
        status = "PASS" if ok == N_RUNS else f"FAIL ({ok}/{N_RUNS})"
        if ok != N_RUNS:
            all_pass = False
        print(f"  {case_id}: {status} | stops={stop_reasons} | tokens={gen_tokens} | wall_ms={[f'{w:.0f}' for w in wall_ms]}")

    if all_pass:
        print(f"\n✓ ALL {len(R_PROMPTS)} PROMPTS × {N_RUNS} RUNS = {ok_count}/{len(all_results)} FIRST-ATTEMPT PASS")
    else:
        print(f"\n✗ SOME FAILURES — see above")

    # Save results
    out_path = "/tmp/f6_s13_step6_regression.json"
    with open(out_path, "w") as f:
        json.dump({
            "meta": {
                "step": "Step 6: R23-R30 targeted regression",
                "server": BASE,
                "max_tokens": MAX_TOKENS,
                "wall_timeout_ms": WALL_TIMEOUT_MS,
                "runs_per_prompt": N_RUNS,
                "timestamp": datetime.now().isoformat(),
            },
            "results": all_results,
            "summary": {
                "total": len(all_results),
                "ok": ok_count,
                "error": err_count,
                "eos": eos_count,
                "max_tokens": max_tok_count,
                "wall_timeout": wall_count,
                "all_pass": all_pass,
            }
        }, f, indent=2, ensure_ascii=False)
    print(f"Results saved to {out_path}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
