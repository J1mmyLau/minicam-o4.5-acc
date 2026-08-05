#!/usr/bin/env python3
"""check_baseline_candidate_symmetry.py — baseline/candidate 对称性检查

比较 ${run_dir}/baseline/manifest.json 与 ${run_dir}/candidate/manifest.json 的关键字段：
  data_sha(dataset) / n_measured+request_ids(case count) / seed+warmup+sample_rate(sampling) /
  model_path+model_sha(model) / text_dir+data_sha(prompt) / stats_code_sha(统计代码) / server_port。
任一不一致 → 打印差异 + 退出 1；manifest 缺失 → 退出 2。

用法：check_baseline_candidate_symmetry.py <run_dir>
"""
import csv, json, os, sys

FIELDS = [
    "data_sha", "model_path", "model_sha", "stats_code_sha",
    "n_measured", "warmup", "seed", "sample_rate", "text_dir", "server_port",
]


def read_csv_request_ids(csv_path):
    ids = set()
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("request_id") is not None and row["request_id"] != "":
                ids.add(int(row["request_id"]))
    return ids


def main():
    if "--help" in sys.argv or "-h" in sys.argv or len(sys.argv) < 2:
        print(__doc__.strip())
        print("usage: check_baseline_candidate_symmetry.py <run_dir>")
        return 0 if ("--help" in sys.argv or "-h" in sys.argv) else 2
    run_dir = sys.argv[1]
    bm = os.path.join(run_dir, "baseline", "manifest.json")
    cm = os.path.join(run_dir, "candidate", "manifest.json")
    if not os.path.exists(bm) or not os.path.exists(cm):
        print(f"[SYMMETRY_BLOCKED] 需要 baseline+candidate 两份 manifest:\n  {bm}\n  {cm}",
              file=sys.stderr)
        return 2
    with open(bm) as f:
        b = json.load(f)
    with open(cm) as f:
        c = json.load(f)

    fails = []
    for k in FIELDS:
        bv, cv = b.get(k), c.get(k)
        if str(bv) != str(cv):
            fails.append((k, bv, cv))

    # request_ids（来自 raw CSV，case count 的另一层校验）
    bcsv = os.path.join(run_dir, "baseline", "out", "chunk_rtf_raw.csv")
    ccsv = os.path.join(run_dir, "candidate", "out", "chunk_rtf_raw.csv")
    if os.path.exists(bcsv) and os.path.exists(ccsv):
        bid = read_csv_request_ids(bcsv)
        cid = read_csv_request_ids(ccsv)
        if bid != cid:
            fails.append(("request_ids", sorted(bid), sorted(cid)))
    else:
        fails.append(("raw_chunk_csv", "missing", "missing"))

    if fails:
        for k, bv, cv in fails:
            print(f"[SYMMETRY_FAIL] {k}: baseline={bv!r} candidate={cv!r}", file=sys.stderr)
        print("SYMMETRY=FAIL", file=sys.stderr)
        return 1

    print(f"SYMMETRY=PASS run_dir={run_dir} fields={len(FIELDS)}+request_ids")
    return 0


if __name__ == "__main__":
    sys.exit(main())
