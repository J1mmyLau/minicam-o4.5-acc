#!/usr/bin/env python3
"""Phase 1c aggregation: parse benchmark CSV, compute per-shape speedups
   and model-weighted aggregation using exact per-layer call counts."""

import csv
import sys
import math
from collections import defaultdict

# ── Per-layer call counts (from real model graph) ──
# S1=Q, S2=K, S3=V, S4=O, S5=gate, S6=up, S7=down — each called once per layer
LAYER_CALL_COUNT = {f"S{i}": 1 for i in range(1, 8)}  # S1..S7 = 1 each
PRIMARY_SHAPES = [f"S{i}" for i in range(1, 8)]  # S1..S7 for Phase 2 gate

# ── Parse ──
def load_csv(path):
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/phase1c_aggregate.py <results.csv>")
        sys.exit(1)

    rows = load_csv(sys.argv[1])
    print(f"Loaded {len(rows)} rows from {sys.argv[1]}")

    # Index: (shape_id, path, metric) → Stats
    data = {}
    for r in rows:
        key = (r["shape_id"].strip(), r["path"].strip(), r["metric"].strip())
        data[key] = {
            "mean_us": float(r["mean_us"]),
            "p50_us": float(r["p50_us"]),
            "p90_us": float(r["p90_us"]),
            "p99_us": float(r["p99_us"]),
            "std_us": float(r["std_us"]),
            "cv":    float(r["cv"]),
            "wp_ms": float(r.get("weight_preprocess_ms", 0) or 0),
        }

    shapes_seen = sorted(set(k[0] for k in data))
    paths_seen  = sorted(set(k[1] for k in data))
    print(f"Shapes: {shapes_seen}")
    print(f"Paths:  {paths_seen}")
    print()

    # ── Per-shape speedup table ──
    print("=" * 110)
    print(f"{'Shape':<20} {'p50_V2':>10} {'p50_F16_ND':>10} {'p50_F16_NZ':>10} {'p50_W8A8':>10} "
          f"{'W8A8/vsV2':>10} {'vsF16_ND':>10} {'vsF16_NZ':>10}  {'ActScale%':>10} {'Quant%':>8} {'Matmul%':>8}")
    print("-" * 110)

    per_shape_speedups = {}
    for shape_id in shapes_seen:
        v2_key    = (shape_id, "V2", "V2_TOTAL_US")
        f16nz_key = (shape_id, "F16_NZ", "F16_TOTAL_US")
        f16nd_key = (shape_id, "F16_ND", "F16_TOTAL_US")
        w8_key    = (shape_id, "W8A8", "T_W8A8_TOTAL_US")
        as_key    = (shape_id, "W8A8", "T_ACT_SCALE_US")
        q_key     = (shape_id, "W8A8", "T_QUANTIZE_US")
        m_key     = (shape_id, "W8A8", "T_MATMUL_US")

        v2_p50    = data[v2_key]["p50_us"]    if v2_key    in data else None
        f16nz_p50 = data[f16nz_key]["p50_us"] if f16nz_key in data else None
        f16nd_p50 = data[f16nd_key]["p50_us"] if f16nd_key in data else None
        w8_p50    = data[w8_key]["p50_us"]    if w8_key    in data else None
        as_p50    = data[as_key]["p50_us"]    if as_key    in data else 0
        q_p50     = data[q_key]["p50_us"]     if q_key     in data else 0
        m_p50     = data[m_key]["p50_us"]     if m_key     in data else 0

        if v2_p50 and w8_p50:
            su_v2    = v2_p50 / w8_p50
            su_f16nd = (f16nd_p50 / w8_p50) if f16nd_p50 else None
            su_f16nz = (f16nz_p50 / w8_p50) if f16nz_p50 else None
            as_pct   = (as_p50 / w8_p50 * 100) if w8_p50 > 0 else 0
            q_pct    = (q_p50  / w8_p50 * 100) if w8_p50 > 0 else 0
            m_pct    = (m_p50  / w8_p50 * 100) if w8_p50 > 0 else 0
            per_shape_speedups[shape_id] = su_v2

            print(f"{shape_id:<20} {v2_p50:>10.1f} {f16nd_p50 or 0:>10.1f} {f16nz_p50 or 0:>10.1f} {w8_p50:>10.1f} "
                  f"{su_v2:>10.2f}× {su_f16nd or 0:>10.2f}× {su_f16nz or 0:>10.2f}×  "
                  f"{as_pct:>9.1f}% {q_pct:>7.1f}% {m_pct:>7.1f}%")
        else:
            print(f"{shape_id:<20} {'N/A':>10} {'N/A':>10} {'N/A':>10} {'N/A':>10}")

    print("=" * 110)
    print()

    # ── W8A8 decomposition average ──
    print("W8A8 decomposition (avg across all shapes):")
    for metric in ["T_ACT_SCALE_US", "T_QUANTIZE_US", "T_MATMUL_US", "T_W8A8_TOTAL_US"]:
        vals = [data[(s, "W8A8", metric)]["p50_us"] for s in shapes_seen if (s, "W8A8", metric) in data]
        if vals:
            print(f"  {metric}: mean_p50={sum(vals)/len(vals):.1f}us  min={min(vals):.1f}  max={max(vals):.1f}")
    print()

    # ── Model-weighted aggregation (S1..S7 only) ──
    print("=" * 70)
    print("MODEL-WEIGHTED AGGREGATION (S1-S7, call count = 1 per shape)")
    print("-" * 70)

    v2_weighted   = sum(data.get((s, "V2", "V2_TOTAL_US"), {}).get("p50_us", 0) for s in PRIMARY_SHAPES)
    f16nd_weighted = sum(data.get((s, "F16_ND", "F16_TOTAL_US"), {}).get("p50_us", 0) for s in PRIMARY_SHAPES)
    f16nz_weighted = sum(data.get((s, "F16_NZ", "F16_TOTAL_US"), {}).get("p50_us", 0) for s in PRIMARY_SHAPES)
    w8a8_weighted = sum(data.get((s, "W8A8", "T_W8A8_TOTAL_US"), {}).get("p50_us", 0) for s in PRIMARY_SHAPES)
    w8a8_kernel_weighted = sum(
        data.get((s, "W8A8", "T_QUANTIZE_US"), {}).get("p50_us", 0) +
        data.get((s, "W8A8", "T_MATMUL_US"), {}).get("p50_us", 0)
        for s in PRIMARY_SHAPES)

    print(f"  MODEL_WEIGHTED_V2_US       = {v2_weighted:.1f}")
    print(f"  MODEL_WEIGHTED_F16_ND_US   = {f16nd_weighted:.1f}")
    print(f"  MODEL_WEIGHTED_F16_NZ_US   = {f16nz_weighted:.1f}")
    print(f"  MODEL_WEIGHTED_W8A8_US     = {w8a8_weighted:.1f}")
    print(f"  MODEL_WEIGHTED_W8A8_KERNEL = {w8a8_kernel_weighted:.1f} (Quantize+Matmul only)")
    print()

    if v2_weighted > 0 and w8a8_weighted > 0:
        mw_speedup    = v2_weighted / w8a8_weighted
        mw_speedup_k  = v2_weighted / w8a8_kernel_weighted if w8a8_kernel_weighted > 0 else 0
        print(f"  MODEL_WEIGHTED_SPEEDUP (V2/W8A8)        = {mw_speedup:.2f}×")
        print(f"  MODEL_WEIGHTED_SPEEDUP (V2/W8A8_KERNEL) = {mw_speedup_k:.2f}×")
    if f16nd_weighted > 0 and w8a8_weighted > 0:
        print(f"  MODEL_WEIGHTED_SPEEDUP (F16_ND/W8A8)    = {f16nd_weighted/w8a8_weighted:.2f}×")
    if f16nz_weighted > 0 and w8a8_weighted > 0:
        print(f"  MODEL_WEIGHTED_SPEEDUP (F16_NZ/W8A8)    = {f16nz_weighted/w8a8_weighted:.2f}×")
    print()

    # Geomean speedup (secondary metric)
    valid_speedups = [v for v in per_shape_speedups.values() if v > 0]
    if valid_speedups:
        log_sum = sum(math.log(v) for v in valid_speedups)
        geo_mean = math.exp(log_sum / len(valid_speedups))
        print(f"  GEOMEAN_SPEEDUP (W8A8 vs V2, {'S1-S7' if all(s in per_shape_speedups for s in PRIMARY_SHAPES) else 'all shapes'}) = {geo_mean:.2f}×")
    print("=" * 70)
    print()

    # ── Decision gates ──
    print("DECISION GATES:")
    print(f"  Gate 1 (Correctness): NOT_YET_CHECKED (requires test-backend-ops validation)")
    print(f"  Gate 2 (Per-shape): ", end="")
    flags = [s for s, su in per_shape_speedups.items() if su < 1.0]
    if not flags:
        print("PASS (all shapes speedup >= 1.0×)")
    else:
        print(f"FLAG {len(flags)} shapes: {flags}")
    print(f"  Gate 3 (Model-weighted): ", end="")
    if mw_speedup >= 1.20:
        print(f"PASS ({mw_speedup:.2f}× >= 1.20 → PROCEED_TO_PHASE2)")
    elif mw_speedup >= 1.00:
        print(f"FLAG ({mw_speedup:.2f}× >= 1.00 < 1.20 → NEEDS_OPTIMIZATION)")
    else:
        print(f"FAIL ({mw_speedup:.2f}× < 1.00 → BLOCKED)")
    print()

    # ── Weight preprocessing ──
    wp_vals = [data.get((s, "W8A8", "T_W8A8_TOTAL_US"), {}).get("wp_ms", 0) for s in shapes_seen]
    wp_vals = [v for v in wp_vals if v > 0]
    if wp_vals:
        print(f"WEIGHT_PREPROCESS (ONE_TIME_LOAD): mean={sum(wp_vals)/len(wp_vals):.1f}ms  "
              f"min={min(wp_vals):.1f}ms  max={max(wp_vals):.1f}ms")
        print("  (excluded from steady-state T_W8A8_TOTAL)")

if __name__ == "__main__":
    main()
