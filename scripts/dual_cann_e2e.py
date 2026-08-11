#!/usr/bin/env python3
"""Phase 5: Dual-CANN Pipeline E2E Promotion Gate — Config D vs A.

Config A (frozen baseline): OVERLAP=1, Flow=CANN, Vocoder=CPU
Config D (candidate):        OVERLAP=1, Flow=CANN, Vocoder=CANN + DIAG=1

Protocol:
  - Same binary, model, workload, warmup policy
  - A first, then D (adjacent, same environment)
  - Warmup=2, measured=30 per config
  - RTF = client_wall_ms / (n_audio_chunks * 1000ms nominal)
  - Parse OMNI_PIPELINE_DIAG_FILE CSV for Config D per-window analysis

Usage:
  python3 dual_cann_e2e.py --model .../F16.gguf --runs 30
"""
import asyncio
import csv
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import websockets


SERVER_BIN = "/workspace/llama.cpp-omni-vocoder-cann-pipeline/build/bin/llama-omni-server"
MODEL = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
OUT_DIR = "/tmp/vocoder-cann-pipeline/e2e"

CONFIGS = {
    "A": {
        "desc": "Pipeline CANN+CPU (frozen baseline)",
        "env": {
            "OMNI_T2W_PIPELINE_OVERLAP": "1",
            "OMNI_T2W_DEVICE": "cann-flow-only",
            # OMNI_VOC_DEVICE unset → defaults to CPU under CANN
        },
        "port": 18097,
        "diag": False,
    },
    "D": {
        "desc": "Pipeline CANN+CANN (dual-CANN candidate)",
        "env": {
            "OMNI_T2W_PIPELINE_OVERLAP": "1",
            "OMNI_T2W_DEVICE": "cann-flow-only",
            "OMNI_VOC_DEVICE": "gpu",
            "OMNI_PIPELINE_DIAG": "1",
            "OMNI_PIPELINE_DIAG_FILE": f"{OUT_DIR}/D_diag.csv",
        },
        "port": 18098,
        "diag": True,
    },
}

PROMPT = "请用中文说一段关于人工智能未来发展的简短介绍。"


def start_server(config_name, log_path):
    """Start llama-omni-server with given config, return Popen."""
    cfg = CONFIGS[config_name]
    env = os.environ.copy()
    env.update(cfg["env"])

    cmd = [
        SERVER_BIN,
        "-m", MODEL,
        "--host", "127.0.0.1",
        "--port", str(cfg["port"]),
        "-ngl", "999",
        "--device", "CANN0",
        "--ctx-size", "4096",
        "--batch-size", "512",
        "--ubatch-size", "512",
        "--split-mode", "layer",
        "-t", "4",
    ]

    log_f = open(log_path, "w")
    proc = subprocess.Popen(
        cmd, env=env, stdout=log_f, stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )
    return proc


def wait_ready(port, timeout=120):
    """Poll /health until OK."""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health", timeout=5
            )
            if r.status == 200:
                data = json.loads(r.read())
                if data.get("status") == "ok":
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


async def run_one_session(host, port, timeout=180):
    """Run one TTS session. Return (wall_ms, n_audio_chunks, text, errors)."""
    url = f"ws://{host}:{port}/backend"
    t_start = time.time()
    n_audio = 0
    all_text = []
    errors = []

    try:
        async with websockets.connect(
            url, ping_interval=None, close_timeout=10
        ) as ws:
            # Init
            await ws.send(json.dumps({
                "type": "session.init",
                "payload": {"mode": "turn_based", "use_tts_template": True},
            }))
            r = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            if r.get("type") != "session.created":
                errors.append(f"init:{r.get('type','?')}")
                return (time.time() - t_start) * 1000, 0, "", errors

            # Input
            await ws.send(json.dumps({
                "type": "input.append",
                "input": {
                    "messages": [{"role": "user", "content": PROMPT}],
                    "streaming": True,
                    "use_tts_template": True,
                },
            }))

            # Stream
            while True:
                r = json.loads(await asyncio.wait_for(
                    ws.recv(), timeout=timeout - (time.time() - t_start)
                ))
                etype = r.get("type", "?")
                if etype == "response.output.delta":
                    if r.get("kind") == "text":
                        all_text.append(r.get("text", ""))
                    elif r.get("kind") == "audio":
                        n_audio += 1
                elif etype in ("response.done", "session.closed", "error"):
                    break

    except asyncio.TimeoutError:
        errors.append("timeout")
    except Exception as e:
        errors.append(str(e)[:150])

    wall_ms = (time.time() - t_start) * 1000
    return wall_ms, n_audio, "".join(all_text)[:100], errors


def extract_server_placement(log_path):
    """Extract backend placement info from server log."""
    info = {
        "vocoder_init": "unknown",
        "flow_init": "unknown",
        "pipeline_overlap": "unknown",
        "cann_errors": 0,
    }
    with open(log_path, encoding='utf-8', errors='replace') as f:
        for line in f:
            if "voc_hg2_model: init_backend" in line:
                if "CANN0" in line:
                    info["vocoder_init"] = "CANN"
                elif "CPU" in line:
                    info["vocoder_init"] = "CPU"
            if "flowGGUFModelLoader: init_backend" in line:
                if "CANN0" in line:
                    info["flow_init"] = "CANN"
            if "T2W pipeline overlap: ENABLED" in line:
                info["pipeline_overlap"] = "ENABLED"
            elif "T2W pipeline overlap: DISABLED" in line:
                info["pipeline_overlap"] = "DISABLED"
            if re.search(r"CANN.*(?:error|fail)", line, re.I):
                info["cann_errors"] += 1
    return info


def parse_pipeline_diag_csv(csv_path):
    """Parse OMNI_PIPELINE_DIAG_FILE CSV into list of window dicts."""
    windows = []
    if not os.path.exists(csv_path):
        return windows
    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            windows.append({
                "window_idx": int(row["window_idx"]),
                "generation_id": int(row["generation_id"]),
                "flow_start_ns": int(row["flow_start_ns"]),
                "flow_end_ns": int(row["flow_end_ns"]),
                "voc_start_ns": int(row["voc_start_ns"]),
                "voc_end_ns": int(row["voc_end_ns"]),
                "flow_us": int(row["flow_us"]),
                "voc_us": int(row["voc_us"]),
            })
    return windows


def analyze_pipeline_diag(windows):
    """Compute pipeline metrics from diag data.

    Corrected 2026-08-11: distinguishes three levels:
      L1) Per-window computation: Flow[i] duration, Vocoder[i] duration, max(Flow,Voc)
      L2) Cross-window overlap: Flow[i+1] || Vocoder[i] (correct pipeline pairing)
      L3) Pipeline interval: Flow[i+1].start - Flow[i].start (true steady-state gate)
         = Flow_computation + inter_flow_gap (token-wait + thread overhead)

    L1 is useful for micro-optimization but L3 is what determines throughput.
    """
    n = len(windows)
    if n < 2:
        return {"error": "too few windows", "n": n}

    flow_times = [w["flow_us"] for w in windows]
    voc_times = [w["voc_us"] for w in windows]

    # ── L1: Per-window computation ──
    per_window_critical_us = [max(w["flow_us"], w["voc_us"]) for w in windows]
    serial_equiv_us = [w["flow_us"] + w["voc_us"] for w in windows]

    # ── L2: Cross-window overlap: Flow[i+1] vs Vocoder[i] ──
    cross_overlap_count = 0
    cross_overlap_us_list = []
    for i in range(n - 1):
        if windows[i+1]["flow_start_ns"] < windows[i]["voc_end_ns"]:
            cross_overlap_count += 1
            overlap_us = (windows[i]["voc_end_ns"] - windows[i+1]["flow_start_ns"]) / 1000
            cross_overlap_us_list.append(overlap_us)

    # ── L3: Pipeline interval (true steady-state) + inter-flow gap ──
    pipeline_intervals_us = []
    inter_flow_gaps_us = []
    for i in range(n - 1):
        pipeline_intervals_us.append(
            (windows[i+1]["flow_start_ns"] - windows[i]["flow_start_ns"]) / 1000)
        inter_flow_gaps_us.append(
            (windows[i+1]["flow_start_ns"] - windows[i]["flow_end_ns"]) / 1000)
    pi_sorted = sorted(pipeline_intervals_us)
    gap_sorted = sorted(inter_flow_gaps_us)
    pi_n = len(pi_sorted)

    # ── Contention: APPROXIMATE from first/last window heuristic ──
    uncontended_flow = (flow_times[0] + flow_times[-1]) / 2 if n > 2 else flow_times[0]
    uncontended_voc = (voc_times[0] + voc_times[-1]) / 2 if n > 2 else voc_times[0]
    mean_flow = sum(flow_times) / n
    mean_voc = sum(voc_times) / n
    c_flow = (mean_flow / uncontended_flow - 1.0) if uncontended_flow > 0 else 0.0
    c_voc = (mean_voc / uncontended_voc - 1.0) if uncontended_voc > 0 else 0.0

    # ── Bottleneck: who dominates the pipeline interval? ──
    gap_p50 = gap_sorted[pi_n // 2] if pi_n > 0 else 0
    pi_p50 = pi_sorted[pi_n // 2] if pi_n > 0 else 0
    vocoder_hidden = (mean_voc < mean_flow + gap_p50)

    return {
        "n_windows": n,
        # L1: per-window computation
        "flow_us": {
            "mean": mean_flow,
            "p50": sorted(flow_times)[n//2],
            "min": min(flow_times),
            "max": max(flow_times),
        },
        "voc_us": {
            "mean": mean_voc,
            "p50": sorted(voc_times)[n//2],
            "min": min(voc_times),
            "max": max(voc_times),
        },
        "per_window_critical_us": {
            "mean": sum(per_window_critical_us) / n,
            "p50": sorted(per_window_critical_us)[n//2],
            "note": "max(Flow_i,Voc_i) — NOT the pipeline interval; ignores inter-flow gaps",
        },
        # L2: cross-window overlap
        "cross_window_overlap": {
            "count": cross_overlap_count,
            "total_pairs": n - 1,
            "ratio": cross_overlap_count / (n - 1) if n > 1 else 0,
            "avg_overlap_us": (sum(cross_overlap_us_list) / len(cross_overlap_us_list))
                              if cross_overlap_us_list else 0,
            "note": "Flow[i+1] vs Vocoder[i] — correct pipeline pairing",
        },
        # L3: pipeline interval + inter-flow gap
        "pipeline_interval_us": {
            "mean": sum(pipeline_intervals_us) / pi_n if pi_n > 0 else 0,
            "p50": pi_p50,
            "p5": pi_sorted[pi_n // 20] if pi_n >= 20 else (pi_sorted[0] if pi_n > 0 else 0),
            "p95": pi_sorted[pi_n * 95 // 100] if pi_n >= 20 else (pi_sorted[-1] if pi_n > 0 else 0),
            "note": "Flow[i+1].start - Flow[i].start — true steady-state throughput gate",
        },
        "inter_flow_gap_us": {
            "mean": sum(inter_flow_gaps_us) / pi_n if pi_n > 0 else 0,
            "p50": gap_p50,
            "note": "Flow[i+1].start - Flow[i].end — token-wait + thread overhead",
        },
        # Contention (APPROXIMATE)
        "contention": {
            "c_flow": c_flow,
            "c_voc": c_voc,
            "flow_dual_cann_p50_us": sorted(flow_times)[n//2],
            "flow_uncontended_est_us": uncontended_flow,
            "voc_dual_cann_p50_us": sorted(voc_times)[n//2],
            "voc_uncontended_est_us": uncontended_voc,
            "note": "APPROXIMATE — uncontended est from first+last window avg",
        },
        "bottleneck": {
            "vocoder_fully_hidden": vocoder_hidden,
            "dominant_stage": "Flow" if mean_flow > mean_voc else "Vocoder",
            "note": "gain source: replacing CPU vocoder (432ms) with CANN vocoder (113ms) shifts bottleneck from Vocoder→Flow+token_wait",
        },
        "speedup_vs_serial": (sum(serial_equiv_us) / sum(per_window_critical_us))
                             if sum(per_window_critical_us) > 0 else 0,
    }


def stats(values):
    """Compute mean, p50, p90, std, min, max."""
    if not values:
        return {}
    sv = sorted(values)
    n = len(sv)
    mean = sum(sv) / n
    var = sum((v - mean) ** 2 for v in sv) / n
    return {
        "n": n,
        "mean": mean,
        "p50": sv[n // 2],
        "p90": sv[int(n * 0.9)],
        "std": var ** 0.5,
        "min": sv[0],
        "max": sv[-1],
    }


async def run_config(config_name, n_warmup=2, n_measured=30):
    """Run one config: start server, warmup, N measured sessions, stop server."""
    cfg = CONFIGS[config_name]
    os.makedirs(OUT_DIR, exist_ok=True)

    # Clear diag CSV for Config D
    if cfg["diag"]:
        diag_path = cfg["env"]["OMNI_PIPELINE_DIAG_FILE"]
        if os.path.exists(diag_path):
            os.remove(diag_path)

    log_path = f"{OUT_DIR}/{config_name}_server.log"

    print(f"\n{'='*60}")
    print(f"Config {config_name}: {cfg['desc']}")
    print(f"Port: {cfg['port']}, Warmup={n_warmup}, Measured={n_measured}")
    print(f"{'='*60}")

    # Start server
    print(f"[{config_name}] Starting server...")
    proc = start_server(config_name, log_path)
    time.sleep(3)

    if not wait_ready(cfg["port"]):
        print(f"[{config_name}] ERROR: server failed to start")
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        return None

    print(f"[{config_name}] Server ready")

    results = []
    host = "127.0.0.1"

    for phase, n_sessions, label in [
        ("warmup", n_warmup, "Warmup"),
        ("measured", n_measured, "Measured"),
    ]:
        print(f"\n[{config_name}] {label} ({n_sessions} sessions)...")
        for i in range(n_sessions):
            wall_ms, n_chunks, text, errors = await run_one_session(
                host, cfg["port"]
            )
            ok = len(errors) == 0 and n_chunks > 0
            status = "✓" if ok else f"✗ ({';'.join(errors[:2])})"
            print(
                f"  [{config_name}] {label[0]}{i+1:02d}: "
                f"wall={wall_ms:.0f}ms chunks={n_chunks} {status}"
            )
            if phase == "measured":
                results.append({
                    "config": config_name,
                    "session": i,
                    "wall_ms": wall_ms,
                    "n_chunks": n_chunks,
                    "text": text,
                    "errors": errors,
                    "ok": ok,
                })
            await asyncio.sleep(1.0)

    # Stop server
    print(f"\n[{config_name}] Stopping server...")
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait()

    # Extract placement info
    placement = extract_server_placement(log_path)

    # Parse pipeline diag for Config D
    diag_analysis = None
    if cfg["diag"]:
        diag_path = cfg["env"]["OMNI_PIPELINE_DIAG_FILE"]
        if os.path.exists(diag_path):
            diag_windows = parse_pipeline_diag_csv(diag_path)
            if diag_windows:
                diag_analysis = analyze_pipeline_diag(diag_windows)
                print(f"\n[{config_name}] Pipeline Diag:")
                print(f"  Windows: {diag_analysis['n_windows']}")
                print(f"  Flow: mean={diag_analysis['flow_us']['mean']:.0f}us p50={diag_analysis['flow_us']['p50']:.0f}us")
                print(f"  Vocoder: mean={diag_analysis['voc_us']['mean']:.0f}us p50={diag_analysis['voc_us']['p50']:.0f}us")
                print(f"  Pipeline interval p50: {diag_analysis['pipeline_interval_us']['p50']:.0f}us (true steady-state gate)")
                print(f"  Inter-flow gap p50: {diag_analysis['inter_flow_gap_us']['p50']:.0f}us (token-wait + overhead)")
                print(f"  Cross-window overlap: {diag_analysis['cross_window_overlap']['count']}/{diag_analysis['cross_window_overlap']['total_pairs']} ({diag_analysis['cross_window_overlap']['ratio']:.1%})")
                print(f"  Contention: c_flow={diag_analysis['contention']['c_flow']:.3f} (flow_dual={diag_analysis['contention']['flow_dual_cann_p50_us']:.0f}us uncontended_est={diag_analysis['contention']['flow_uncontended_est_us']:.0f}us)")

    # Compute RTF stats
    # Use nominal audio: n_chunks * 1.0s per chunk
    valid = [r for r in results if r["ok"] and r["n_chunks"] >= 3]

    # Aggregate RTF = total_wall / total_nominal_audio
    total_wall = sum(r["wall_ms"] for r in valid)
    total_chunks = sum(r["n_chunks"] for r in valid)
    aggregate_rtf = (total_wall / 1000.0) / total_chunks if total_chunks > 0 else float("inf")

    per_session_rtfs = []
    for r in valid:
        audio_s = r["n_chunks"] * 1.0  # nominal 1s per chunk
        rtf = (r["wall_ms"] / 1000.0) / audio_s if audio_s > 0 else float("inf")
        per_session_rtfs.append(rtf)
        r["rtf"] = rtf

    summary = {
        "config": config_name,
        "desc": cfg["desc"],
        "sessions_total": len(results),
        "sessions_valid": len(valid),
        "sessions_errors": len(results) - len(valid),
        "aggregate_rtf": aggregate_rtf,
        "total_wall_ms": total_wall,
        "total_chunks": total_chunks,
        "per_session_rtf": stats(per_session_rtfs),
        "wall_ms": stats([r["wall_ms"] for r in valid]),
        "chunks": stats([r["n_chunks"] for r in valid]),
        "placement": placement,
        "pipeline_diag": diag_analysis,
    }

    print(f"\n[{config_name}] Summary:")
    print(f"  Sessions: {len(valid)}/{len(results)} valid")
    print(f"  Aggregate RTF: {aggregate_rtf:.4f}")
    if per_session_rtfs:
        s = stats(per_session_rtfs)
        print(f"  Per-session RTF: mean={s['mean']:.4f} p50={s['p50']:.4f} p90={s['p90']:.4f}")
    print(f"  Placement: Flow={placement['flow_init']} Vocoder={placement['vocoder_init']} Overlap={placement['pipeline_overlap']}")
    print(f"  CANN errors: {placement['cann_errors']}")

    # Save
    out_path = f"{OUT_DIR}/{config_name}_results.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Saved: {out_path}")

    return summary


async def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=30, help="Measured sessions per config")
    ap.add_argument("--warmup", type=int, default=2, help="Warmup sessions per config")
    ap.add_argument("--configs", default="A,D", help="Which configs to run")
    args = ap.parse_args()

    summaries = {}
    for cfg_name in args.configs.split(","):
        cfg_name = cfg_name.strip()
        if cfg_name not in CONFIGS:
            print(f"Unknown config: {cfg_name}")
            continue
        s = await run_config(cfg_name, args.warmup, args.runs)
        if s:
            summaries[cfg_name] = s
        # Cool-down between configs
        if len(summaries) < len(args.configs.split(",")):
            print("\nCooling down 30s between configs...")
            await asyncio.sleep(30)

    # Compare
    if "A" in summaries and "D" in summaries:
        sa, sd = summaries["A"], summaries["D"]
        print(f"\n{'='*60}")
        print("FINAL COMPARISON: Config D (dual-CANN) vs Config A (CANN+CPU)")
        print(f"{'='*60}")

        ra = sa["aggregate_rtf"]
        rd = sd["aggregate_rtf"]
        e2e_speedup = ra / rd if rd > 0 else 0
        e2e_pct = (1 - e2e_speedup) * 100 if e2e_speedup > 0 else float("nan")

        print(f"\nA_ACTUAL_LOCAL_SPEAK_RTF (aggregate) = {ra:.4f}")
        print(f"D_ACTUAL_LOCAL_SPEAK_RTF (aggregate) = {rd:.4f}")
        print(f"ACTUAL_E2E_SPEEDUP = {e2e_speedup:.3f}× ({e2e_pct:+.1f}%)")

        # Per-session
        if sa["per_session_rtf"] and sd["per_session_rtf"]:
            print(f"\nA per-session RTF: mean={sa['per_session_rtf']['mean']:.4f} p50={sa['per_session_rtf']['p50']:.4f} p90={sa['per_session_rtf']['p90']:.4f}")
            print(f"D per-session RTF: mean={sd['per_session_rtf']['mean']:.4f} p50={sd['per_session_rtf']['p50']:.4f} p90={sd['per_session_rtf']['p90']:.4f}")

        # Pipeline diag
        if sd["pipeline_diag"]:
            diag = sd["pipeline_diag"]
            print(f"\nPipeline Diag (Config D):")
            print(f"  Windows: {diag['n_windows']}")
            print(f"  Flow: mean={diag['flow_us']['mean']:.0f}us p50={diag['flow_us']['p50']:.0f}us")
            print(f"  Vocoder: mean={diag['voc_us']['mean']:.0f}us p50={diag['voc_us']['p50']:.0f}us")
            print(f"  Pipeline interval p50: {diag['pipeline_interval_us']['p50']:.0f}us")
            print(f"  Inter-flow gap p50: {diag['inter_flow_gap_us']['p50']:.0f}us")
            print(f"  Cross-window overlap: {diag['cross_window_overlap']['count']}/{diag['cross_window_overlap']['total_pairs']} ({diag['cross_window_overlap']['ratio']:.1%})")

        # Placement
        print(f"\nPlacement:")
        print(f"  A: Flow={sa['placement']['flow_init']} Vocoder={sa['placement']['vocoder_init']} Overlap={sa['placement']['pipeline_overlap']}")
        print(f"  D: Flow={sd['placement']['flow_init']} Vocoder={sd['placement']['vocoder_init']} Overlap={sd['placement']['pipeline_overlap']}")

        # Promotion decision
        threshold = 0.95  # 5% improvement
        promoted = e2e_speedup > 0 and rd < ra * threshold
        print(f"\n{'='*60}")
        print(f"PROMOTION: {'YES' if promoted else 'NO'}")
        print(f"Threshold: D RTF < A RTF × {threshold} ({ra*threshold:.4f})")
        print(f"Actual:    D RTF = {rd:.4f}")
        print(f"{'='*60}")

        # Save comparison
        comparison = {
            "A_AGGREGATE_RTF": ra,
            "D_AGGREGATE_RTF": rd,
            "E2E_SPEEDUP": e2e_speedup,
            "E2E_SPEEDUP_PCT": e2e_pct,
            "PROMOTED": promoted,
            "A_per_session": sa["per_session_rtf"],
            "D_per_session": sd["per_session_rtf"],
            "A_placement": sa["placement"],
            "D_placement": sd["placement"],
            "D_pipeline_diag": sd["pipeline_diag"],
        }
        comp_path = f"{OUT_DIR}/comparison.json"
        with open(comp_path, "w") as f:
            json.dump(comparison, f, indent=2, ensure_ascii=False, default=str)
        print(f"\nComparison saved: {comp_path}")


if __name__ == "__main__":
    asyncio.run(main())
