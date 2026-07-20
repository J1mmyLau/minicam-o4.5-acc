#!/usr/bin/env python3
"""
Parse benchmark JSONL results into CSV and JSON summary.

Usage:
    python3 parse_results.py results/benchmark_c1_n20.jsonl results/benchmark_c2_n20.jsonl ...
"""

import csv
import json
import statistics
import sys
from pathlib import Path


def parse_jsonl(path: str) -> list[dict]:
    results = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return results


def compute_stats(values: list[float]) -> dict:
    if not values:
        return {}
    v = [x for x in values if x > 0]
    if not v:
        return {}
    v.sort()
    return {
        "count": len(v),
        "median": round(statistics.median(v), 2),
        "p90": round(v[int(len(v) * 0.9)], 2) if len(v) >= 10 else None,
        "p99": round(v[int(len(v) * 0.99)], 2) if len(v) >= 100 else None,
        "mean": round(statistics.mean(v), 2),
        "stdev": round(statistics.stdev(v), 2) if len(v) > 1 else 0,
        "min": round(min(v), 2),
        "max": round(max(v), 2),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: parse_results.py <file1.jsonl> [file2.jsonl ...]")
        sys.exit(1)

    all_measured = []

    for fpath in sys.argv[1:]:
        results = parse_jsonl(fpath)
        measured = [r for r in results if "measured" in r.get("session_id", "")]
        warmup = [r for r in results if "warmup" in r.get("session_id", "")]

        # Per-file summary
        ttft = [r["ttft_ms"] for r in measured if r["success"]]
        fa = [r["first_audio_ms"] for r in measured if r["success"]]
        e2e = [r["e2e_ms"] for r in measured if r["success"]]
        success_count = sum(1 for r in measured if r["success"])

        basename = Path(fpath).stem
        print(f"\n=== {basename} ===")
        print(f"  Measured: {len(measured)}, Success: {success_count}/{len(measured)}")
        print(f"  TTFT (ms):      median={compute_stats(ttft).get('median', 'N/A')}")
        print(f"  First Audio (ms): median={compute_stats(fa).get('median', 'N/A')}")
        print(f"  E2E (ms):       median={compute_stats(e2e).get('median', 'N/A')}")

        all_measured.extend(measured)

    # Aggregate CSV
    csv_path = "summary.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "session_id", "success", "ttft_ms", "first_audio_ms",
            "e2e_ms", "chunk_count", "error"
        ])
        for r in all_measured:
            writer.writerow([
                r["session_id"], r["success"], r.get("ttft_ms", 0),
                r.get("first_audio_ms", 0), r.get("e2e_ms", 0),
                r.get("chunk_count", 0), r.get("error", "")
            ])
    print(f"\nCSV: {csv_path} ({len(all_measured)} rows)")

    # JSON summary
    json_path = "summary.json"
    summary = {
        "total_measured": len(all_measured),
        "success_count": sum(1 for r in all_measured if r["success"]),
        "ttft_ms": compute_stats([r["ttft_ms"] for r in all_measured if r["success"]]),
        "first_audio_ms": compute_stats([r["first_audio_ms"] for r in all_measured if r["success"]]),
        "e2e_ms": compute_stats([r["e2e_ms"] for r in all_measured if r["success"]]),
    }
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()
