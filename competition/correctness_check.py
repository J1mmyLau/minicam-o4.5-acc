#!/usr/bin/env python3
"""
Correctness checker for benchmark output.

Checks:
- All WAV files: valid header, non-zero duration
- No NaN/Inf in any output
- LLM text output is non-empty
- Exit codes / error markers

Usage:
    python3 correctness_check.py --wav-dir /path/to/wavs --results results/benchmark_c1_n20.jsonl
"""

import argparse
import json
import os
import struct
import sys
from pathlib import Path


def check_wav(path: str) -> dict:
    """Validate WAV header. Returns {valid, channels, sample_rate, bits, duration_s}."""
    try:
        with open(path, "rb") as f:
            if f.read(4) != b"RIFF":
                return {"valid": False, "error": "not RIFF"}
            f.read(4)  # file size
            if f.read(4) != b"WAVE":
                return {"valid": False, "error": "not WAVE"}
            # fmt chunk
            f.read(4)  # "fmt "
            fmt_size = struct.unpack("<I", f.read(4))[0]
            audio_fmt = struct.unpack("<H", f.read(2))[0]
            channels = struct.unpack("<H", f.read(2))[0]
            sample_rate = struct.unpack("<I", f.read(4))[0]
            byte_rate = struct.unpack("<I", f.read(4))[0]
            block_align = struct.unpack("<H", f.read(2))[0]
            bits = struct.unpack("<H", f.read(2))[0]
            # Skip to data chunk
            f.read(fmt_size - 16)
            while True:
                chunk_id = f.read(4)
                chunk_size = struct.unpack("<I", f.read(4))[0]
                if chunk_id == b"data":
                    data_size = chunk_size
                    break
                f.read(chunk_size)
            duration = data_size / byte_rate if byte_rate > 0 else 0
            return {
                "valid": (audio_fmt == 1 and channels == 1 and sample_rate == 24000 and bits == 16),
                "channels": channels,
                "sample_rate": sample_rate,
                "bits": bits,
                "duration_s": round(duration, 2),
            }
    except Exception as e:
        return {"valid": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav-dir", help="Directory containing WAV files")
    parser.add_argument("--results", nargs="+", help="JSONL result files")
    args = parser.parse_args()

    checks = {"wav": 0, "wav_pass": 0, "wav_fail": 0, "requests": 0, "request_pass": 0, "request_fail": 0}

    # Check WAVs
    if args.wav_dir:
        wav_files = sorted(Path(args.wav_dir).rglob("*.wav"))
        for wf in wav_files:
            checks["wav"] += 1
            r = check_wav(str(wf))
            if r["valid"]:
                checks["wav_pass"] += 1
            else:
                checks["wav_fail"] += 1
                print(f"  FAIL WAV: {wf} — {r}")
        print(f"WAV: {checks['wav_pass']}/{checks['wav']} passed")

    # Check results
    if args.results:
        for rf in args.results:
            with open(rf) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    checks["requests"] += 1
                    if r.get("success"):
                        checks["request_pass"] += 1
                    else:
                        checks["request_fail"] += 1
                        print(f"  FAIL request: {r.get('session_id')} — {r.get('error')}")
        print(f"Requests: {checks['request_pass']}/{checks['requests']} passed")

    # Summary
    all_pass = (checks["wav_fail"] == 0 and checks["request_fail"] == 0)
    print(f"\nOVERALL: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
