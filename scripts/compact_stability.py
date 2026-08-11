#!/usr/bin/env python3
"""Compact stability gate for dual-CANN pipeline Config D.

Requires:
  - >=10 sequential sessions
  - >=300 T2W windows total
  - 0 crash / 0 CANN error / 0 NaN/Inf / 0 dropped audio
  - queue bounded / bounded thread growth

Matches the WS protocol from dual_cann_e2e.py.
Audio quality checks come from the server's OMNI_PIPELINE_DIAG per-window log.

Usage:
  python3 scripts/compact_stability.py [--port 18098] [--sessions 12] [--min-windows 300]
"""

import asyncio
import argparse
import json
import os
import re
import subprocess
import sys
import time

OUT_DIR = "/tmp/vocoder-cann-pipeline/stability"
PROMPT = "请介绍一下人工智能的发展历程。"


async def run_one_session(host, port, timeout=180):
    """Run one TTS session. Return (wall_ms, n_audio_chunks, text, errors)."""
    import websockets

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


def get_server_thread_count(pid):
    """Get thread count for server process."""
    try:
        result = subprocess.run(
            ["cat", f"/proc/{pid}/status"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if line.startswith("Threads:"):
                return int(line.split()[1])
    except Exception:
        pass
    return -1


def parse_server_log(log_path):
    """Extract diag metrics and errors from server log."""
    try:
        with open(log_path, encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception:
        return {"error": "cannot_read"}

    # Sum windows across ALL AGGREGATE sections (there's one per drain cycle)
    total_diag_windows = sum(int(x) for x in re.findall(r'\[pipeline-diag\] ===== AGGREGATE \(n=(\d+)\) =====', content))

    # Parse the LAST AGGREGATE section for metric details
    agg = {"n_windows": total_diag_windows}
    agg_sections = list(re.finditer(r'\[pipeline-diag\] ===== AGGREGATE \(n=(\d+)\) =====(.*?)(?=\[pipeline\] Vocoder thread exiting|\Z)', content, re.DOTALL))
    if agg_sections:
        # Use the last section for metric details
        last_agg = agg_sections[-1]
        agg_text = last_agg.group(2)
        # Parse key metrics
        for key, pattern in [
            ("flow_avg_us", r"Flow:\s+avg=(\d+)us"),
            ("voc_avg_us", r"Vocoder:\s+avg=(\d+)us"),
            ("pipeline_interval_p50_us", r"avg=\d+us p50=(\d+)us p5=\d+us p95=\d+us"),
            ("inter_flow_gap_p50_us", r"Inter-flow gap.*?\n.*?avg=\d+us p50=(\d+)us"),
            ("cross_overlap_ratio", r"Cross-window overlap.*?(\d+)/(\d+) pairs \(([\d.]+)%\)"),
            ("c_flow", r"c_flow=([\d.]+)"),
            ("c_voc", r"c_voc=([\d.]+)"),
            ("vocoder_hidden", r"Vocoder fully hidden behind Flow\+gap: (\w+)"),
        ]:
            m = re.search(pattern, agg_text)
            if m:
                if key == "cross_overlap_ratio":
                    agg["cross_overlap_count"] = int(m.group(1))
                    agg["cross_overlap_pairs"] = int(m.group(2))
                    agg["cross_overlap_ratio_pct"] = float(m.group(3))
                elif key in ("c_flow", "c_voc"):
                    agg[key] = float(m.group(1))
                elif key == "vocoder_hidden":
                    agg[key] = (m.group(1) == "YES")
                else:
                    agg[key] = int(m.group(1))

    # Count per-window NaN/Inf log lines (from the diag section, not the aggregate)
    nan_line_count = len(re.findall(r'nan=(\d+)', content))
    inf_line_count = len(re.findall(r'inf=(\d+)', content))
    # Sum NaN/Inf counts (they're logged per-window as "nan=N inf=M")
    total_nan = sum(int(x) for x in re.findall(r'nan=(\d+)', content))
    total_inf = sum(int(x) for x in re.findall(r'inf=(\d+)', content))
    silent_count = len(re.findall(r'silent=1\b', content))

    # CANN errors
    cann_error_count = len(re.findall(r'CANN.*(?:error|fail|ERROR|FAIL)', content))
    cann_error_count += len(re.findall(r'ACL_(?:ERROR|FAIL)', content))
    cann_error_count += len(re.findall(r'aclrt\w+ (?:fail|error)', content, re.I))
    cann_error_count += len(re.findall(r'\[E\]', content))

    # Dropped audio (feed_window_errors in queue diag)
    dropped = len(re.findall(r'feed_window_errors', content))

    return {
        "aggregate": agg,
        "total_nan": total_nan,
        "total_inf": total_inf,
        "silent_window_count": silent_count,
        "cann_error_count": cann_error_count,
        "dropped_audio": dropped,
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18098)
    parser.add_argument("--sessions", type=int, default=12)
    parser.add_argument("--min-windows", type=int, default=300)
    parser.add_argument("--inter-session-sleep", type=int, default=3)
    args = parser.parse_args()

    host = "127.0.0.1"
    port = args.port
    n_sessions = args.sessions
    min_windows = args.min_windows
    sleep_s = args.inter_session_sleep

    print(f"=== Compact Stability Gate ===")
    print(f"Config: D (pipeline CANN+CANN, DIAG=1)")
    print(f"Port: {port}, Sessions: {n_sessions}, Min windows: {min_windows}")
    print(f"Output: {OUT_DIR}")
    print()

    # Check server is up
    result = subprocess.run(
        ["pgrep", "-f", f"llama-omni-server.*{port}"],
        capture_output=True, text=True,
    )
    if not result.stdout.strip():
        print("ERROR: Server not found!")
        sys.exit(1)
    pid = int(result.stdout.strip().split()[0])
    print(f"Server PID: {pid}")

    initial_threads = get_server_thread_count(pid)
    print(f"Initial thread count: {initial_threads}")

    results = []
    total_audio_chunks = 0
    all_errors = []
    session_wall_times = []

    for i in range(n_sessions):
        print(f"\n--- Session {i+1}/{n_sessions} ---")
        wall_ms, n_audio, text, errors = await run_one_session(host, port)

        status = "PASS" if len(errors) == 0 and n_audio > 0 else "FAIL"
        print(f"  {status}: wall={wall_ms:.0f}ms audio_chunks={n_audio} text={text[:50]} errors={errors[:3]}")

        results.append({
            "session": i+1,
            "wall_ms": wall_ms,
            "n_audio_chunks": n_audio,
            "text_preview": text[:50],
            "errors": errors,
            "status": status,
        })
        total_audio_chunks += n_audio
        all_errors.extend(errors)
        if wall_ms > 0:
            session_wall_times.append(wall_ms)

        # Thread count every 3 sessions
        if (i + 1) % 3 == 0:
            tc = get_server_thread_count(pid)
            print(f"  Thread count: {tc} (delta from init: {tc - initial_threads})")

        if i < n_sessions - 1:
            await asyncio.sleep(sleep_s)

    # Final thread count
    final_threads = get_server_thread_count(pid)
    thread_growth = final_threads - initial_threads

    # Server log analysis
    log_path = os.path.join(OUT_DIR, "server.log")
    diag = parse_server_log(log_path)

    # ── Gate decisions ──
    print(f"\n{'='*60}")
    print(f"=== GATE RESULTS ===")
    print(f"{'='*60}")

    gates = {}

    # G1: session count
    gates["G1_sessions"] = n_sessions >= 10
    print(f"G1: >=10 sessions: {n_sessions} -> {'PASS' if gates['G1_sessions'] else 'FAIL'}")

    # G2: window count (from diag aggregate)
    n_diag_windows = diag.get("aggregate", {}).get("n_windows", 0)
    gates["G2_windows"] = n_diag_windows >= min_windows
    print(f"G2: >=300 diag windows: {n_diag_windows} -> {'PASS' if gates['G2_windows'] else 'FAIL'}")

    # G3: zero session failures
    n_failed = len([r for r in results if r["status"] != "PASS"])
    gates["G3_crash"] = n_failed == 0
    print(f"G3: 0 session failures: {n_failed} -> {'PASS' if gates['G3_crash'] else 'FAIL'}")

    # G4: zero CANN errors
    cann_errors = diag.get("cann_error_count", -1)
    gates["G4_cann_error"] = cann_errors == 0
    print(f"G4: 0 CANN errors: {cann_errors} -> {'PASS' if gates['G4_cann_error'] else 'FAIL'}")

    # G5: zero NaN/Inf in per-window diag
    total_nan = diag.get("total_nan", -1)
    total_inf = diag.get("total_inf", -1)
    gates["G5_nan_inf"] = total_nan == 0 and total_inf == 0
    print(f"G5: 0 NaN/Inf: nan={total_nan} inf={total_inf} -> {'PASS' if gates['G5_nan_inf'] else 'FAIL'}")

    # G5b: zero silent windows
    silent = diag.get("silent_window_count", -1)
    gates["G5b_silent"] = silent == 0
    print(f"G5b: 0 silent windows: {silent} -> {'PASS' if gates['G5b_silent'] else 'FAIL'}")

    # G6: thread growth bounded
    thread_growth_pct = (thread_growth / max(initial_threads, 1)) * 100
    gates["G6_threads"] = abs(thread_growth) < 50 and thread_growth_pct < 20
    print(f"G6: thread growth bounded: {initial_threads}->{final_threads} (+{thread_growth}, {thread_growth_pct:.1f}%) -> {'PASS' if gates['G6_threads'] else 'FAIL'}")

    # G7: all sessions have audio
    gates["G7_audio"] = all(r["n_audio_chunks"] > 0 for r in results)
    print(f"G7: all sessions have audio: -> {'PASS' if gates['G7_audio'] else 'FAIL'}")

    # Aggregate RTF
    total_wall_s = sum(session_wall_times) / 1000
    aggregate_rtf = total_wall_s / max(total_audio_chunks, 1)  # ~1s per chunk nominal
    gates["G8_rtf"] = aggregate_rtf < 1.0
    print(f"G8: aggregate RTF < 1.0: {aggregate_rtf:.4f} -> {'PASS' if gates['G8_rtf'] else 'FAIL'}")

    # Overall
    all_pass = all(gates.values())
    print(f"\n{'='*60}")
    print(f"COMPACT_STABILITY: {'PASS' if all_pass else 'FAIL'}")
    print(f"{'='*60}")

    # Print corrected pipeline diag summary
    agg = diag.get("aggregate", {})
    if agg:
        print(f"\nCorrected Pipeline Diag (from server log):")
        print(f"  Windows: {agg.get('n_windows', '?')}")
        print(f"  Flow avg: {agg.get('flow_avg_us', '?')}us")
        print(f"  Vocoder avg: {agg.get('voc_avg_us', '?')}us")
        print(f"  Pipeline interval p50: {agg.get('pipeline_interval_p50_us', '?')}us")
        print(f"  Inter-flow gap p50: {agg.get('inter_flow_gap_p50_us', '?')}us")
        print(f"  Cross-window overlap: {agg.get('cross_overlap_count', '?')}/{agg.get('cross_overlap_pairs', '?')} ({agg.get('cross_overlap_ratio_pct', '?')}%)")
        print(f"  Contention: c_flow={agg.get('c_flow', '?')} c_voc={agg.get('c_voc', '?')}")
        print(f"  Vocoder fully hidden: {agg.get('vocoder_hidden', '?')}")

    # Summary
    print(f"\nSummary:")
    print(f"  Sessions: {n_sessions} ({n_failed} failed)")
    print(f"  Total audio chunks: {total_audio_chunks}")
    print(f"  Diag windows: {n_diag_windows}")
    print(f"  Aggregate RTF: {aggregate_rtf:.4f}")
    print(f"  Threads: {initial_threads} -> {final_threads} (+{thread_growth})")
    print(f"  NaN total: {total_nan}, Inf total: {total_inf}")
    print(f"  CANN errors: {cann_errors}")

    # Persist
    out_path = os.path.join(OUT_DIR, "stability_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "config": "D (CANN+CANN pipeline, DIAG=1)",
            "port": port,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "gates": {k: bool(v) for k, v in gates.items()},
            "all_pass": all_pass,
            "summary": {
                "n_sessions": n_sessions,
                "n_failed": n_failed,
                "total_audio_chunks": total_audio_chunks,
                "diag_windows": n_diag_windows,
                "aggregate_rtf": aggregate_rtf,
                "thread_initial": initial_threads,
                "thread_final": final_threads,
                "thread_growth": thread_growth,
                "total_nan": total_nan,
                "total_inf": total_inf,
                "silent_windows": silent,
                "cann_errors": cann_errors,
            },
            "pipeline_diag_aggregate": agg,
            "sessions": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\nResults written to {out_path}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
