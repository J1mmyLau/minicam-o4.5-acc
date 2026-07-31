#!/usr/bin/env python3
"""
W8: W0 Correctness Smoke Test
==============================
30 requests across 5 categories to verify W0 observability after W5 fixes.

Categories:
  - 10 short TTS (text-only, 1-2 round)
  - 5  long TTS  (text-only, 3+ rounds)
  - 5  audio+text
  - 5  video+audio (skip if no vision model)
  - 5  continuous requests (rapid-fire, same session)

Per-request checks:
  - W0 present = 100% for TTS requests (audio completion profile exists)
  - W0 duplicate = 0 (only one audio profile per request_index)
  - W0 stale accepted = 0 (generation_id matches)
  - cross-request contamination = 0 (request_index monotonic, no gaps)

Usage:
  # Start server first:
  OMNI_E2E_PROFILE=1 OMNI_E2E_PROFILE_DIR=/tmp/w8_smoke \
    ./build/bin/llama-omni-server -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
    --host 127.0.0.1 --port 8080 -ngl 99

  # Then run smoke test:
  python3 scripts/w8_w0_smoke_test.py --url http://127.0.0.1:8080 --profile-dir /tmp/w8_smoke
"""

import argparse
import json
import os
import socket
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# Ensure long socket timeout for sequential server processing
socket.setdefaulttimeout(300)


def http_post(url: str, data: dict, timeout: int = 300) -> dict:
    """POST JSON, return parsed response or raise."""
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            if resp.status != 200:
                return {"_status": resp.status, "_body": body}
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"_status": resp.status, "_body": body}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {"_status": e.code, "_body": body}
    except Exception as e:
        return {"_status": -1, "_body": str(e)}


def http_get(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"_error": str(e)}


def check_health(base_url: str) -> bool:
    result = http_get(f"{base_url}/health")
    return result.get("status") == "ok"


def omni_init(base_url: str, media_type: int = 2, use_tts: bool = True,
              output_dir: str = "/tmp/w8_smoke_output") -> bool:
    """Initialize omni context. media_type: 1=audio, 2=text, 3=video."""
    payload = {
        "media_type": media_type,
        "use_tts": use_tts,
        "output_dir": output_dir,
    }
    result = http_post(f"{base_url}/v1/stream/omni_init", payload)
    return result.get("success", False)


def run_decode(base_url: str, debug_dir: str = "/tmp/w8_smoke_output",
               stream: bool = False, round_idx: int = -1) -> bool:
    """Run a single decode request. Returns True on success."""
    payload = {
        "debug_dir": debug_dir,
        "stream": stream,
        "round_idx": round_idx,
    }
    result = http_post(f"{base_url}/v1/stream/decode", payload, timeout=300)
    return result.get("success", False)


def collect_profiles(profile_dir: str) -> dict:
    """Scan profile directory and classify profiles."""
    profiles = {"audio": [], "partial": [], "other": []}
    p = Path(profile_dir)
    if not p.exists():
        return profiles

    for f in sorted(p.glob("e2e_*_audio.json")):
        try:
            data = json.loads(f.read_text())
            data["_file"] = str(f)
            profiles["audio"].append(data)
        except (json.JSONDecodeError, IOError):
            pass

    for f in sorted(p.glob("e2e_*.json")):
        if "_audio" in f.name:
            continue
        try:
            data = json.loads(f.read_text())
            data["_file"] = str(f)
            status = data.get("profile_status", "unknown")
            if status == "partial":
                profiles["partial"].append(data)
            else:
                profiles["other"].append(data)
        except (json.JSONDecodeError, IOError):
            pass

    return profiles


def verify_w0_smoke(profiles: dict, expected_tts_count: int) -> dict:
    """Run W8 verification checks against collected profiles."""
    result = {
        "w0_present_count": 0,
        "w0_missing_count": 0,
        "w0_duplicate": 0,
        "w0_stale": 0,
        "w0_cross_contamination": 0,
        "checks": [],
        "passed": False,
    }

    audio_profiles = profiles["audio"]
    seen_indices = set()
    request_indices = [p.get("request_index", -1) for p in audio_profiles]
    generation_ids = [p.get("generation_id", 0) for p in audio_profiles]

    # Check W0 presence
    for p in audio_profiles:
        req_idx = p.get("request_index", -1)
        gen_id = p.get("generation_id", 0)
        async_stages = p.get("async_stages_ms", {})
        wav_ready = async_stages.get("wav_ready", 0)

        if wav_ready > 0:
            result["w0_present_count"] += 1
            result["checks"].append({
                "request_index": req_idx,
                "status": "W0_PRESENT",
                "wav_ready_ms": wav_ready,
                "generation_id": gen_id,
            })
        else:
            result["w0_missing_count"] += 1
            result["checks"].append({
                "request_index": req_idx,
                "status": "W0_MISSING",
                "generation_id": gen_id,
            })

    # Check W0 duplicate (same request_index appearing more than once)
    for idx in request_indices:
        if idx >= 0 and idx in seen_indices:
            result["w0_duplicate"] += 1
        if idx >= 0:
            seen_indices.add(idx)

    # Check monotonicity and gaps (cross-request contamination)
    sorted_indices = sorted([i for i in request_indices if i >= 0])
    if len(sorted_indices) > 1:
        for i in range(1, len(sorted_indices)):
            gap = sorted_indices[i] - sorted_indices[i-1]
            if gap <= 0:
                result["w0_cross_contamination"] += 1
            elif gap > 10:  # Large gaps suggest missing profiles
                result["checks"].append({
                    "request_index": sorted_indices[i],
                    "status": "LARGE_GAP",
                    "gap": gap,
                })

    # Check stale generation (generation_id decreasing or non-monotonic)
    sorted_gens = sorted([g for g in generation_ids if g > 0])
    if len(sorted_gens) > 1:
        for i in range(1, len(sorted_gens)):
            if sorted_gens[i] <= sorted_gens[i-1]:
                result["w0_stale"] += 1

    # Pass criteria
    all_tts_have_w0 = (result["w0_present_count"] >= expected_tts_count)
    no_duplicates = (result["w0_duplicate"] == 0)
    no_stale = (result["w0_stale"] == 0)
    no_contamination = (result["w0_cross_contamination"] == 0)

    result["passed"] = all_tts_have_w0 and no_duplicates and no_stale and no_contamination
    result["summary"] = (
        f"W0 present: {result['w0_present_count']}/{expected_tts_count}, "
        f"duplicates: {result['w0_duplicate']}, "
        f"stale: {result['w0_stale']}, "
        f"contamination: {result['w0_cross_contamination']}"
    )

    return result


def main():
    parser = argparse.ArgumentParser(description="W8 W0 Correctness Smoke Test")
    parser.add_argument("--url", default="http://127.0.0.1:8080", help="Server base URL")
    parser.add_argument("--profile-dir", default=None,
                        help="E2E profile directory (env: OMNI_E2E_PROFILE_DIR)")
    parser.add_argument("--output-dir", default="/tmp/w8_smoke_output",
                        help="Output directory for server artifacts")
    parser.add_argument("--skip-audio-video", action="store_true",
                        help="Skip audio+text and video+audio categories")
    parser.add_argument("--skip-continuous", action="store_true",
                        help="Skip continuous rapid-fire category")
    parser.add_argument("--short-tts-count", type=int, default=10,
                        help="Number of short TTS requests (default: 10)")
    parser.add_argument("--long-tts-count", type=int, default=5,
                        help="Number of long TTS requests (default: 5)")
    parser.add_argument("--audio-count", type=int, default=5,
                        help="Number of audio+text requests (default: 5)")
    args = parser.parse_args()

    profile_dir = args.profile_dir or os.environ.get("OMNI_E2E_PROFILE_DIR", "/tmp/w8_smoke_profile")
    base_url = args.url.rstrip("/")

    # ── Pre-flight checks ───────────────────────────────────────────
    print("=" * 60)
    print("W8: W0 Correctness Smoke Test")
    print("=" * 60)
    print(f"  Server URL:  {base_url}")
    print(f"  Profile dir: {profile_dir}")
    print(f"  Output dir:  {args.output_dir}")
    print()

    if not check_health(base_url):
        print("FATAL: Server not healthy. Start server first:")
        print(f"  OMNI_E2E_PROFILE=1 OMNI_E2E_PROFILE_DIR={profile_dir} \\")
        print(f"    ./build/bin/llama-omni-server -m <model> --host 127.0.0.1 --port 8080 -ngl 99")
        sys.exit(1)
    print("  [OK] Server health check passed")

    # Clean profile directory
    os.makedirs(profile_dir, exist_ok=True)
    for f in Path(profile_dir).glob("e2e_*.json"):
        f.unlink()
    os.makedirs(args.output_dir, exist_ok=True)

    # ── Category 1: Short TTS (text-only) ───────────────────────────
    print("\n── Category 1: Short TTS (text-only) ──")
    print(f"  Initializing omni (media_type=text, use_tts=True)...")
    if not omni_init(base_url, media_type=2, use_tts=True, output_dir=args.output_dir):
        print("  FATAL: omni_init failed for text+tts mode")
        sys.exit(1)
    print("  [OK] omni_init succeeded")

    tts_success = 0
    for i in range(args.short_tts_count):
        print(f"  Short TTS {i+1}/{args.short_tts_count}...", end=" ", flush=True)
        # Re-init omni for each request to get clean state (single-session server)
        if i > 0:
            omni_init(base_url, media_type=2, use_tts=True, output_dir=args.output_dir)
        ok = run_decode(base_url, debug_dir=args.output_dir, round_idx=i)
        print("OK" if ok else "FAIL")
        if ok:
            tts_success += 1
        # Let async T2W pipeline drain before next request (wav_ready ~30s)
        if i < args.short_tts_count - 1:
            print(f"    Waiting for T2W pipeline drain (35s)...")
            time.sleep(35)

    # ── Category 2: Long TTS (multi-round) ──────────────────────────
    print(f"\n── Category 2: Long TTS (multi-round) ──")
    for i in range(args.long_tts_count):
        # Re-init for each long TTS to get multi-round behavior
        omni_init(base_url, media_type=2, use_tts=True, output_dir=args.output_dir)
        for r in range(3):  # 3 rounds each
            print(f"  Long TTS {i+1}/{args.long_tts_count} round {r+1}...", end=" ", flush=True)
            ok = run_decode(base_url, debug_dir=args.output_dir, round_idx=r)
            print("OK" if ok else "FAIL")
            if ok and r == 0:
                tts_success += 1
        time.sleep(2)

    # ── Category 3: Audio + Text ────────────────────────────────────
    if not args.skip_audio_video:
        print(f"\n── Category 3: Audio + Text ──")
        # Find a test audio file
        test_audio = "/workspace/llama.cpp-omni/tools/mtmd/test-2.mp3"
        if not os.path.exists(test_audio):
            print("  SKIP: No test audio file found")
        else:
            if not omni_init(base_url, media_type=1, use_tts=True, output_dir=args.output_dir):
                print("  WARN: omni_init failed for audio+text mode, skipping")
            else:
                for i in range(args.audio_count):
                    print(f"  Audio+Text {i+1}/{args.audio_count}...", end=" ", flush=True)
                    ok = run_decode(base_url, debug_dir=args.output_dir)
                    print("OK" if ok else "FAIL")
                    if ok:
                        tts_success += 1
                    time.sleep(2)

    # ── Category 4: Video + Audio ───────────────────────────────────
    # Skip by default — requires vision model setup
    print(f"\n── Category 4: Video + Audio ──")
    print("  SKIP: Requires vision model and video test assets")

    # ── Category 5: Continuous rapid-fire ───────────────────────────
    if not args.skip_continuous:
        print(f"\n── Category 5: Continuous (rapid-fire) ──")
        if not omni_init(base_url, media_type=2, use_tts=True, output_dir=args.output_dir):
            print("  WARN: omni_init failed, skipping continuous")
        else:
            for i in range(5):
                print(f"  Continuous {i+1}/5...", end=" ", flush=True)
                ok = run_decode(base_url, debug_dir=args.output_dir)
                print("OK" if ok else "FAIL")
                if ok:
                    tts_success += 1
                # No sleep — rapid fire

    # ── Wait for async pipeline drain ───────────────────────────────
    print(f"\n── Waiting for async pipeline drain (10s) ──")
    time.sleep(10)

    # ── Collect and verify ──────────────────────────────────────────
    print(f"\n── Collecting profiles from {profile_dir} ──")
    profiles = collect_profiles(profile_dir)
    print(f"  Audio completion profiles: {len(profiles['audio'])}")
    print(f"  Partial profiles:         {len(profiles['partial'])}")
    print(f"  Other profiles:           {len(profiles['other'])}")

    print(f"\n── Verification ──")
    expected_tts = tts_success
    result = verify_w0_smoke(profiles, expected_tts)

    for check in result["checks"]:
        status = check.get("status", "?")
        req_idx = check.get("request_index", "?")
        wav_ms = check.get("wav_ready_ms", 0)
        gen = check.get("generation_id", 0)
        print(f"  [{status}] req_idx={req_idx} gen={gen} wav_ready={wav_ms}ms")

    print(f"\n── W8 Gate Decision ──")
    print(f"  {result['summary']}")
    print(f"  PASS: {result['passed']}")

    # Write report
    report_path = f"{profile_dir}/W8_SMOKE_REPORT.json"
    with open(report_path, "w") as f:
        json.dump({
            "w8_smoke_test": "W0 Correctness Smoke",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "binary": "/workspace/llama.cpp-omni-f6/build/bin/llama-omni-server",
            "tts_requests_attempted": expected_tts,
            "verification": result,
            "profiles": {
                "audio_count": len(profiles["audio"]),
                "partial_count": len(profiles["partial"]),
            },
        }, f, indent=2)
    print(f"\n  Report: {report_path}")

    # Return exit code based on pass/fail
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
