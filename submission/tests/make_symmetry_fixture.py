#!/usr/bin/env python3
"""make_symmetry_fixture.py — 生成对称性 fixture 并验证 check_baseline_candidate_symmetry.py

在 submission/tests/_out/symmetry/ 下构造 matching / mismatched / missing 三例，
分别断言退出码 0 / 1 / 2。_out 为临时产物，由 run_selftest.sh 结束后清理。
"""
import csv, json, os, shutil, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CHECKER = os.path.join(ROOT, "submission", "scripts", "check_baseline_candidate_symmetry.py")
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out", "symmetry")

MANIFEST = dict(
    run_id="fixture", source_commit="abc", candidate_source_commit="fd3dd36",
    binary_sha="aaa", model_sha="model123", model_path="/data/model.gguf",
    data_sha="data456", text_dir="/data/texts", stats_code_sha="stat789",
    n_measured="3", warmup="0", seed="0", sample_rate="24000", server_port="18093",
)


def write_manifest(mode_dir, overrides):
    m = dict(MANIFEST)
    m["mode"] = "baseline" if "baseline" in mode_dir else "candidate"
    m.update(overrides)
    os.makedirs(mode_dir, exist_ok=True)
    with open(os.path.join(mode_dir, "manifest.json"), "w") as f:
        json.dump(m, f, indent=2, sort_keys=True)


def write_csv(mode_dir, ids):
    os.makedirs(os.path.join(mode_dir, "out"), exist_ok=True)
    with open(os.path.join(mode_dir, "out", "chunk_rtf_raw.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["run_id", "request_id", "chunk_index", "valid_audio"])
        w.writeheader()
        for rid in ids:
            w.writerow({"run_id": "x", "request_id": rid, "chunk_index": 0, "valid_audio": "True"})


def check(run_dir, expected):
    p = subprocess.run([sys.executable, CHECKER, run_dir], capture_output=True, text=True)
    ok = p.returncode == expected
    print(f"[{'PASS' if ok else 'FAIL'}] {os.path.basename(run_dir)}: rc={p.returncode} expected={expected}")
    if not ok:
        print(p.stdout + p.stderr)
    return ok


def main():
    shutil.rmtree(BASE, ignore_errors=True)
    results = []
    # matching：字段一致 + request_ids 一致 → 0
    d = os.path.join(BASE, "matching")
    write_manifest(os.path.join(d, "baseline"), {})
    write_manifest(os.path.join(d, "candidate"), {})
    write_csv(os.path.join(d, "baseline"), [1, 2, 3])
    write_csv(os.path.join(d, "candidate"), [1, 2, 3])
    results.append(check(d, 0))
    # mismatched：data_sha / n_measured / request_ids 不同 → 1
    d = os.path.join(BASE, "mismatched")
    write_manifest(os.path.join(d, "baseline"), {})
    write_manifest(os.path.join(d, "candidate"), dict(data_sha="DIFFERENT", n_measured="5"))
    write_csv(os.path.join(d, "baseline"), [1, 2, 3])
    write_csv(os.path.join(d, "candidate"), [1, 2, 3, 4, 5])
    results.append(check(d, 1))
    # missing：仅 baseline → 2
    d = os.path.join(BASE, "missing")
    write_manifest(os.path.join(d, "baseline"), {})
    write_csv(os.path.join(d, "baseline"), [1, 2, 3])
    results.append(check(d, 2))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
