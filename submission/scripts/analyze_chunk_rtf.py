#!/usr/bin/env python3
"""analyze_chunk_rtf.py — 逐 chunk RTF 离线分析（不改推理路径）

解析冻结候选 server 日志中的逐 chunk 计时行：
    T2W线程: wav_1002.wav | 1.00s audio | 232.4ms inference | RTF=0.23 | t=1744ms | queue_wait=110.5ms | req=1 gen=1
配套行：
    🎉 首响时间 (First Audio Response): 1269ms (decode_to_first_audio) | 0ms (request_to_first_audio) | req=1 gen=1
    T2W drain: complete (wav_count=12, notify=1 poll=0 fast=0 gen=1)

对每个 chunk 做真实 valid_audio 判定（见 validate_chunk / EXCLUSION_REASONS）。
排除/样本/分桶规则 = INTERNAL_VALIDATION_POLICY（非 OFFICIAL_REQUIREMENT，官方口径以 Starter Kit 为准）。

输出：chunk_rtf_raw.csv + chunk_rtf_summary.json
规范：docs/competition-submission/CHUNK_RTF_MEASUREMENT_SPEC.md
用法：python3 analyze_chunk_rtf.py <server.log> <run_id> --out <dir> [--binary-sha X] [--model-sha Y] [--mode M] [--sample-rate 24000] [--wav-dir D]
"""
import argparse, csv, json, math, os, re, statistics, sys, wave
from collections import Counter

CHUNK_RE = re.compile(
    r"T2W线程: wav_(\d+)\.wav \| ([\d.]+)s audio \| ([\d.]+)ms inference \| RTF=([\d.]+)"
    r" \| t=(\d+)ms \| queue_wait=([\d.]+)ms \| req=(\d+) gen=(\d+)"
)
FIRST_AUDIO_RE = re.compile(
    r"首响时间 \(First Audio Response\): (\d+)ms \(decode_to_first_audio\) \| (\d+)ms \(request_to_first_audio\) \| req=(\d+) gen=(\d+)"
)
DRAIN_RE = re.compile(r"T2W drain: complete \(wav_count=\d+.*?gen=(\d+)\)")

DEFAULT_SAMPLE_RATE = 24000            # MiniCPM-o TTS WAV 采样率
VALID_SAMPLE_RATES = {24000}           # 已知合法采样率；官方口径以 Starter Kit 为准
MIN_FINAL_DURATION_MS = 50.0           # 尾 chunk 疑似截断阈值（启发式）

EXCLUSION_REASONS = [
    "EMPTY_PAYLOAD", "ZERO_SAMPLES", "INVALID_SAMPLE_RATE", "DECODE_FAILURE",
    "NAN_INF", "MISSING_REQUEST_ID", "MISSING_CHUNK_INDEX", "INVALID_TIMESTAMP",
    "DUPLICATE_CHUNK", "TRUNCATED_CHUNK",
]

CSV_COLS = [
    "run_id", "request_id", "generation", "chunk_index", "is_first_chunk", "is_final_chunk",
    "chunk_compute_begin_ns", "chunk_compute_end_ns", "chunk_compute_ms",
    "sample_count", "sample_rate", "audio_duration_ms", "chunk_rtf",
    "valid_audio", "exclusion_reason", "error", "server_pid", "binary_sha", "model_sha",
]


def _is_nan_or_inf(v):
    try:
        f = float(v)
        return math.isnan(f) or math.isinf(f)
    except (TypeError, ValueError):
        return False


def parse_log(log_path, sample_rate=DEFAULT_SAMPLE_RATE):
    """把 server 日志解析为 chunk 行（raw，未校验）。供 main() 与单元测试复用。"""
    drain_gens = set()
    with open(log_path, errors="replace") as f:
        for line in f:
            m = DRAIN_RE.search(line)
            if m:
                drain_gens.add(int(m.group(1)))

    first_audio = {}
    with open(log_path, errors="replace") as f:
        for line in f:
            m = FIRST_AUDIO_RE.search(line)
            if m:
                first_audio[(int(m.group(3)), int(m.group(4)))] = {
                    "decode_to_first_audio_ms": int(m.group(1)),
                    "request_to_first_audio_ms": int(m.group(2)),
                }

    rows = []
    with open(log_path, errors="replace") as f:
        for line in f:
            m = CHUNK_RE.search(line)
            if not m:
                continue
            wavnum, adur_s, infer_ms, rtf, t_ms, qw_ms, req, gen = m.groups()
            req, gen = int(req), int(gen)
            chunk_index = int(wavnum) % 1000  # 文件名规则 req*1000+idx；wav_1002 → chunk 2
            audio_ms = round(float(adur_s) * 1000.0, 3)
            compute_ms = float(infer_ms)
            computed_rtf = round(compute_ms / audio_ms, 6) if audio_ms > 0 else None
            rows.append({
                "run_id": None,                       # main() 回填
                "request_id": req,
                "generation": gen,
                "chunk_index": chunk_index,
                "is_first_chunk": chunk_index == 0,
                "is_final_chunk": None,               # 下推：per (req, gen) max
                "chunk_compute_begin_ns": None,
                "chunk_compute_end_ns": None,
                "chunk_compute_ms": compute_ms,
                "sample_count": int(audio_ms * sample_rate / 1000.0),
                "sample_rate": sample_rate,
                "audio_duration_ms": audio_ms,
                "chunk_rtf": computed_rtf,
                "chunk_rtf_log": float(rtf),
                "t_cumulative_ms": int(t_ms),
                "queue_wait_ms": float(qw_ms),
                "decode_to_first_audio_ms": first_audio.get((req, gen), {}).get("decode_to_first_audio_ms"),
                "valid_audio": None,                  # 由 validate_chunk 判定
                "exclusion_reason": "",
                "error": "",
                "server_pid": None,
                "binary_sha": None,
                "model_sha": None,
            })

    # is_final_chunk = per (request, generation) 最大 chunk_index
    per_key_max = {}
    for r in rows:
        k = (r["request_id"], r["generation"])
        per_key_max[k] = max(per_key_max.get(k, -1), r["chunk_index"])
    for r in rows:
        r["is_final_chunk"] = (r["chunk_index"] == per_key_max[(r["request_id"], r["generation"])])
    return rows


def validate_chunk(row, seen_keys, wav_dir=None, valid_sample_rates=VALID_SAMPLE_RATES,
                   min_final_duration_ms=MIN_FINAL_DURATION_MS):
    """对单个 chunk 做真实有效性判定，写入 row["valid_audio"]/["exclusion_reason"]/["error"]。

    排除原因见 EXCLUSION_REASONS。本规则 = INTERNAL_VALIDATION_POLICY（非 OFFICIAL_REQUIREMENT）。
    """
    reasons = []
    compute = row.get("chunk_compute_ms")
    rtf = row.get("chunk_rtf")
    sr = row.get("sample_rate")
    sc = row.get("sample_count")
    dur = row.get("audio_duration_ms")
    req = row.get("request_id")
    cidx = row.get("chunk_index")
    t = row.get("t_cumulative_ms")
    qw = row.get("queue_wait_ms")

    if compute is None:
        reasons.append("EMPTY_PAYLOAD")
    elif _is_nan_or_inf(compute):
        reasons.append("NAN_INF")
    elif compute < 0:
        reasons.append("INVALID_TIMESTAMP")

    if dur is None or dur <= 0:
        reasons.append("EMPTY_PAYLOAD")

    if sr is None or sr <= 0:
        reasons.append("INVALID_SAMPLE_RATE")
    elif valid_sample_rates and sr not in valid_sample_rates:
        reasons.append("INVALID_SAMPLE_RATE")

    if sc is None or sc <= 0:
        reasons.append("ZERO_SAMPLES")

    if rtf is None or _is_nan_or_inf(rtf):
        reasons.append("NAN_INF")

    if req is None:
        reasons.append("MISSING_REQUEST_ID")
    if cidx is None or cidx < 0:
        reasons.append("MISSING_CHUNK_INDEX")
    if t is not None and _is_nan_or_inf(t):
        reasons.append("INVALID_TIMESTAMP")
    if qw is not None and _is_nan_or_inf(qw):
        reasons.append("INVALID_TIMESTAMP")

    # 重复 chunk：同 (request, generation, chunk_index) 出现两次 → 第二次 DUPLICATE_CHUNK
    key = (req, row.get("generation"), cidx)
    if req is not None and cidx is not None:
        if key in seen_keys:
            reasons.append("DUPLICATE_CHUNK")
        else:
            seen_keys.add(key)

    # PCM/WAV 可解析（best effort：仅当对应 wav 文件存在时跨查；缺失不判定失败）
    if wav_dir and req is not None and cidx is not None:
        wav_path = os.path.join(wav_dir, f"wav_{req * 1000 + cidx}.wav")
        if os.path.exists(wav_path):
            try:
                with wave.open(wav_path) as w:
                    rate = w.getframerate()
                    frames = w.getnframes()
                    if rate != sr:
                        reasons.append("INVALID_SAMPLE_RATE")
                    if frames <= 0:
                        reasons.append("ZERO_SAMPLES")
                    row["wav_frames"] = frames
                    row["wav_rate"] = rate
            except Exception:
                reasons.append("DECODE_FAILURE")

    # 疑似截断：尾 chunk 时长异常短（启发式）
    if row.get("is_final_chunk") and dur is not None and 0 < dur < min_final_duration_ms:
        reasons.append("TRUNCATED_CHUNK")

    row["valid_audio"] = not reasons
    row["exclusion_reason"] = "|".join(dict.fromkeys(reasons))
    row["error"] = row["exclusion_reason"]
    return row


def compute_summary(rows, run_id, source_note, binary_sha="", model_sha=""):
    def st(x):
        return {
            "count": len(x), "mean": round(statistics.mean(x), 4) if x else None,
            "p50": round(statistics.median(x), 4) if x else None,
            "p90": round(sorted(x)[max(0, int(0.9 * len(x)) - 1)], 4) if x else None,
            "p95": round(sorted(x)[max(0, int(0.95 * len(x)) - 1)], 4) if x else None,
            "p99": round(sorted(x)[max(0, int(0.99 * len(x)) - 1)], 4) if x else None,
            "max": round(max(x), 4) if x else None,
        }

    valid = [r for r in rows if r.get("valid_audio") and r.get("chunk_rtf") is not None]
    rtf = [r["chunk_rtf"] for r in valid]
    first = [r["chunk_rtf"] for r in valid if r["is_first_chunk"]]
    middle = [r["chunk_rtf"] for r in valid if not r["is_first_chunk"] and not r["is_final_chunk"]]
    final = [r["chunk_rtf"] for r in valid if r["is_final_chunk"]]
    invalid = [r for r in rows if not r.get("valid_audio")]
    reason_counts = Counter()
    for r in invalid:
        for reason in (r.get("exclusion_reason") or "").split("|"):
            if reason:
                reason_counts[reason] += 1

    total = len(rows)
    n_valid = len(valid)
    n_invalid = total - n_valid
    return {
        "run_id": run_id,
        "metric": "per-audio-chunk RTF = chunk_compute_ms / audio_duration_ms",
        "source": source_note,
        "requests": len({r["request_id"] for r in rows}),
        "chunks_total": total,
        "chunks_valid": n_valid,
        "chunks_invalid": n_invalid,
        "exclusion_rate": round(n_invalid / total, 6) if total else None,
        "exclusion_reason_counts": dict(reason_counts),
        "all_chunks": st(rtf),
        "first_chunk": st(first),
        "middle_chunk": st(middle),
        "final_chunk": st(final),
        "decode_to_first_audio_p50_ms": statistics.median(
            [r["decode_to_first_audio_ms"] for r in rows if r.get("decode_to_first_audio_ms")]) if any(
            r.get("decode_to_first_audio_ms") for r in rows) else None,
        "binary_sha": binary_sha,
        "model_sha": model_sha,
        "validation_policy": "INTERNAL_VALIDATION_POLICY",
        "note": "official 计时口径/样本数/排除规则/权重以 Starter Kit 为准；本文件为内部采集规范产物",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("run_id")
    ap.add_argument("--out", default=".")
    ap.add_argument("--binary-sha", default="")
    ap.add_argument("--model-sha", default="")
    ap.add_argument("--server-pid", default="")
    ap.add_argument("--mode", default="")
    ap.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    ap.add_argument("--warmup", type=int, default=0,
                    help="丢弃前 WARMUP 个 distinct request_id 对应的 chunk（预热请求不计入统计）")
    ap.add_argument("--wav-dir", default="", help="wav 文件目录（存在时做 PCM/WAV 跨查）")
    a = ap.parse_args()

    rows = parse_log(a.log, sample_rate=a.sample_rate)
    if not rows:
        print("NO_CHUNK_EVIDENCE — 日志中未找到 T2W线程 chunk 行（确认 use_tts=True 且服务端生成音频）", file=sys.stderr)
        sys.exit(2)

    if a.warmup > 0:
        first_ids = set(sorted({r["request_id"] for r in rows})[: a.warmup])
        before = len(rows)
        rows = [r for r in rows if r["request_id"] not in first_ids]
        print(f"warmup: dropped {before - len(rows)} rows (请求 {sorted(first_ids)} 不计入统计)", file=sys.stderr)

    seen = set()
    for r in rows:
        r["run_id"] = a.run_id
        r["server_pid"] = a.server_pid
        r["binary_sha"] = a.binary_sha
        r["model_sha"] = a.model_sha
        validate_chunk(r, seen, wav_dir=a.wav_dir or None)

    mism = [r for r in rows if r.get("chunk_rtf") is not None and abs(r["chunk_rtf"] - r["chunk_rtf_log"]) > 0.02]
    if mism:
        print(f"WARN: {len(mism)} 行日志 RTF 与计算 RTF 偏差 >0.02（检查 duration 舍入）", file=sys.stderr)

    os.makedirs(a.out, exist_ok=True)
    csv_path = os.path.join(a.out, "chunk_rtf_raw.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    summary = compute_summary(rows, a.run_id,
                              f"frozen server log T2W线程 lines (mode={a.mode or 'unknown'}, binary 4694cb58…)",
                              binary_sha=a.binary_sha, model_sha=a.model_sha)
    summary["mode"] = a.mode
    sum_path = os.path.join(a.out, "chunk_rtf_summary.json")
    with open(sum_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"CSV: {csv_path}\nJSON: {sum_path}")


if __name__ == "__main__":
    main()
