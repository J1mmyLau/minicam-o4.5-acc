#!/usr/bin/env python3
"""check_no_private_paths.py — 提交包私有路径审计

扫描 submission/scripts、submission/config、submission/environment 下的脚本/配置，
禁止字面量：/workspace/、/home/、/tmp/（仅代码行；注释行与文档示例路径豁免）。
docs/competition-submission/ 仅 warn（文档允许示例路径）。
退出码：0=干净；1=发现私有路径。
"""
import os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SCAN_DIRS = [
    os.path.join(ROOT, "submission", "scripts"),
    os.path.join(ROOT, "submission", "config"),
    os.path.join(ROOT, "submission", "environment"),
]
DOC_DIR = os.path.join(ROOT, "docs", "competition-submission")
PATTERNS = ["/workspace/", "/home/", "/tmp/"]
EXTS = (".sh", ".py", ".env", ".txt")


def is_code_line(line):
    s = line.strip()
    return bool(s) and not s.startswith("#") and not s.startswith('"""')


def collect(d, out):
    if not os.path.isdir(d):
        return
    for root, _dirs, files in os.walk(d):
        for fn in files:
            if fn.endswith(EXTS):
                out.append(os.path.join(root, fn))


def scan_files(paths):
    hits = []
    for p in paths:
        if not os.path.isfile(p):
            continue
        with open(p, errors="replace") as f:
            for i, line in enumerate(f, 1):
                if is_code_line(line) and any(pat in line for pat in PATTERNS):
                    hits.append((p, i, line.strip()))
    return hits


def main():
    verbose = "--verbose" in sys.argv
    scripts = []
    for d in SCAN_DIRS:
        collect(d, scripts)
    code_hits = scan_files(scripts)
    docs = []
    collect(DOC_DIR, docs)
    doc_hits = scan_files(docs)
    for p, i, s in code_hits:
        print(f"[PRIVATE_PATH] {os.path.relpath(p, ROOT)}:{i}: {s}")
    for p, i, s in doc_hits:
        print(f"[WARN_DOC] {os.path.relpath(p, ROOT)}:{i}: {s}")
    if verbose and not code_hits:
        print("PRIVATE_PATH_SCAN=clean (submission scripts/config/env, 代码行)")
    print("PRIVATE_PATH_SCAN=PASS" if not code_hits else "PRIVATE_PATH_SCAN=FAIL")
    return 0 if not code_hits else 1


if __name__ == "__main__":
    sys.exit(main())
