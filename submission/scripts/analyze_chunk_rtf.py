#!/usr/bin/env python3
"""analyze_chunk_rtf.py — 逐 chunk RTF 离线分析（不改推理路径）

解析冻结候选 server 日志中的逐 chunk 计时行：
    T2W线程: wav_1002.wav | 1.00s audio | 232.4ms inference | RTF=0.23 | t=1744ms | queue_wait=110.5ms | req=1 gen=1
配套行：
    🎉 首响时间 (First Audio Response): 1269ms (decode_to_first_audio) | 0ms (request_to_first_audio) | req=1 gen=1
    T2W drain: complete (wav_count=12, notify=1 poll=0 fast=0 gen=1)

输出：chunk_rtf_raw.csv + chunk_rtf_summary.json
规范：docs/competition-submission/CHUNK_RTF_MEASUREMENT_SPEC.md
用法：python3 analyze_chunk_rtf.py <server.log> <run_id> --out <dir> [--binary-sha X] [--model-sha Y]
"""
import argparse, csv, json, os, re, statistics, sys

CHUNK_RE = re.compile(
    r"T2W线程: wav_(\d+)\.wav \| ([\d.]+)s audio \| ([\d.]+)ms inference \| RTF=([\d.]+)"
    r" \| t=(\d+)ms \| queue_wait=([\d.]+)ms \| req=(\d+) gen=(\d+)"
)
FIRST_AUDIO_RE = re.compile(
    r"首响时间 \(First Audio Response\): (\d+)ms \(decode_to_first_audio\) \| (\d+)ms \(request_to_first_audio\) \| req=(\d+) gen=(\d+)"
)
DRAIN_RE = re.compile(r"T2W drain: complete \(wav_count=\d+.*?gen=(\d+)\)")
SAMPLE_RATE = 24000  # 模型输出采样率（以 wav 头核对）

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("run_id")
    ap.add_argument("--out", default=".")
    ap.add_argument("--binary-sha", default="")
    ap.add_argument("--model-sha", default="")
    ap.add_argument("--server-pid", default="")
    a = ap.parse_args()

    # 解析 drain 行确定各 gen 的最后 chunk
    drain_gens = set()
    with open(a.log, errors="replace") as f:
        for line in f:
            m = DRAIN_RE.search(line)
            if m:
                drain_gens.add(int(m.group(1)))

    rows = []
    first_audio = {}
    with open(a.log, errors="replace") as f:
        for line in f:
            m = FIRST_AUDIO_RE.search(line)
            if m:
                first_audio[(int(m.group(3)), int(m.group(4)))] = {
                    "decode_to_first_audio_ms": int(m.group(1)),
                    "request_to_first_audio_ms": int(m.group(2)),
                }
            m = CHUNK_RE.search(line)
            if not m:
                continue
            wavnum, adur_s, infer_ms, rtf, t_ms, qw_ms, req, gen = m.groups()
            req, gen = int(req), int(gen)
            chunk_index = int(wavnum) % 1000  # wav_1002 → chunk 2（文件名规则 req*1000+idx）
            audio_ms = round(float(adur_s) * 1000.0, 3)
            compute_ms = float(infer_ms)
            computed_rtf = round(compute_ms / audio_ms, 6) if audio_ms > 0 else None
            rows.append({
                "run_id": a.run_id,
                "request_id": req,
                "chunk_index": chunk_index,
                "is_first_chunk": chunk_index == 0,
                "is_final_chunk": gen in drain_gens and chunk_index == 0,  # 单 chunk gen 判定；多 chunk gen 见下
                "chunk_compute_begin_ns": None,   # 日志无精确 begin；仅时间线分析
                "chunk_compute_end_ns": None,
                "chunk_compute_ms": compute_ms,
                "sample_count": int(audio_ms * SAMPLE_RATE / 1000.0),
                "sample_rate": SAMPLE_RATE,
                "audio_duration_ms": audio_ms,
                "chunk_rtf": computed_rtf,
                "chunk_rtf_log": float(rtf),      # 服务器打印值（交叉核对）
                "t_cumulative_ms": int(t_ms),
                "queue_wait_ms": float(qw_ms),
                "decode_to_first_audio_ms": first_audio.get((req, gen), {}).get("decode_to_first_audio_ms"),
                "valid_audio": True,
                "error": "",
                "server_pid": a.server_pid,
                "binary_sha": a.binary_sha,
                "model_sha": a.model_sha,
            })

    if not rows:
        print("NO_CHUNK_EVIDENCE — 日志中未找到 T2W线程 chunk 行（确认 use_tts=True 且服务端生成音频）", file=sys.stderr)
        sys.exit(2)

    # 多 chunk gen 的 final chunk = 该 gen 的 max chunk_index
    gen_max = {}
    for r in rows:
        gen_max[(r["request_id"], r["chunk_index"],)] = r  # 占位，重算
    per_gen = {}
    for r in rows:
        per_gen.setdefault(r["request_id"], {}).setdefault("max_idx", -1)
        per_gen[r["request_id"]]["max_idx"] = max(per_gen[r["request_id"]]["max_idx"], r["chunk_index"])
    for r in rows:
        r["is_final_chunk"] = (r["chunk_index"] == per_gen[r["request_id"]]["max_idx"])

    # 交叉核对日志 RTF vs 计算 RTF
    mism = [r for r in rows if r["chunk_rtf"] is not None and abs(r["chunk_rtf"] - r["chunk_rtf_log"]) > 0.02]
    if mism:
        print(f"WARN: {len(mism)} 行日志 RTF 与计算 RTF 偏差 >0.02（检查 duration 舍入）", file=sys.stderr)

    os.makedirs(a.out, exist_ok=True)
    csv_path = os.path.join(a.out, "chunk_rtf_raw.csv")
    cols = ["run_id","request_id","chunk_index","is_first_chunk","is_final_chunk",
            "chunk_compute_begin_ns","chunk_compute_end_ns","chunk_compute_ms",
            "sample_count","sample_rate","audio_duration_ms","chunk_rtf",
            "valid_audio","error","server_pid","binary_sha","model_sha"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    rtf = [r["chunk_rtf"] for r in rows if r["valid_audio"] and r["chunk_rtf"] is not None]
    def st(x):
        return {
            "count": len(x), "mean": round(statistics.mean(x), 4) if x else None,
            "p50": round(statistics.median(x), 4) if x else None,
            "p90": round(sorted(x)[max(0, int(0.9*len(x))-1)], 4) if x else None,
            "p95": round(sorted(x)[max(0, int(0.95*len(x))-1)], 4) if x else None,
            "p99": round(sorted(x)[max(0, int(0.99*len(x))-1)], 4) if x else None,
            "max": round(max(x), 4) if x else None,
        }
    first = [r["chunk_rtf"] for r in rows if r["is_first_chunk"] and r["valid_audio"] and r["chunk_rtf"] is not None]
    middle = [r["chunk_rtf"] for r in rows if not r["is_first_chunk"] and not r["is_final_chunk"] and r["valid_audio"] and r["chunk_rtf"] is not None]
    final = [r["chunk_rtf"] for r in rows if r["is_final_chunk"] and r["valid_audio"] and r["chunk_rtf"] is not None]
    excluded = [r for r in rows if not r["valid_audio"]]
    summary = {
        "run_id": a.run_id,
        "metric": "per-audio-chunk RTF = chunk_compute_ms / audio_duration_ms",
        "source": "frozen server log T2W线程 lines (binary db258375…)",
        "requests": len({r["request_id"] for r in rows}),
        "chunks_total": len(rows),
        "chunks_valid": len(rtf),
        "all_chunks": st(rtf),
        "first_chunk": st(first),
        "middle_chunk": st(middle),
        "final_chunk": st(final),
        "invalid_excluded_count": len(excluded),
        "exclusion_reasons": sorted({r["error"] for r in excluded}),
        "decode_to_first_audio_p50_ms": statistics.median([r["decode_to_first_audio_ms"] for r in rows if r.get("decode_to_first_audio_ms")]) if any(r.get("decode_to_first_audio_ms") for r in rows) else None,
        "binary_sha": a.binary_sha,
        "model_sha": a.model_sha,
        "note": "official 计时口径以 Starter Kit 为准；本文件为内部采集规范产物",
    }
    sum_path = os.path.join(a.out, "chunk_rtf_summary.json")
    with open(sum_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"CSV: {csv_path}\nJSON: {sum_path}")

if __name__ == "__main__":
    main()
