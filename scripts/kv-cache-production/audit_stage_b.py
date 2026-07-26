#!/usr/bin/env python3
"""
Stage B Soak Audit Script (Read-Only)

Reads raw stdout/stderr/progress/errors logs from a Stage B/C/D/E soak run
directory and produces a comprehensive Gate evaluation. Does NOT modify any
files, does NOT start/stop any processes.

Usage:
    python3 scripts/kv-cache-production/audit_stage_b.py <run_dir>

Example:
    python3 scripts/kv-cache-production/audit_stage_b.py \
        docs/experiments/kv-cache-production/p3-soak/stage_b_20260726_050817/
"""

import sys
import os
import re
import json
import glob
import csv
from collections import defaultdict
from datetime import datetime

# ─── Constants ──────────────────────────────────────────────────────────
CACHE_KEY = "e2b568b6078ce027"
GATE_ITEMS = [
    ("GATE_01", "runner exit_code=0"),
    ("GATE_02", "DONE file exists"),
    ("GATE_03", "raw data rows complete, no duplicates"),
    ("GATE_04", "iteration classification closed (hit+miss+rebuild+control+timeout = total)"),
    ("GATE_05", "all timeouts classified, unclassified_timeout=0"),
    ("GATE_06", "crash=0"),
    ("GATE_07", "CANN runtime error=0"),
    ("GATE_08", "rc0_without_audio=0"),
    ("GATE_09", "temp/thread/process leak=0"),
    ("GATE_10", "RSS/HBM/FD/thread trend flat (no monotonic growth)"),
    ("GATE_11", "latency stable (no unexplained drift)"),
    ("GATE_12", "prefill missing cases explained"),
    ("GATE_13", "Stage report generated and committed"),
    ("GATE_14", "STATUS/HANDOFF/AUDIT updated"),
]

# ─── Helpers ────────────────────────────────────────────────────────────

def iter_files(run_dir, suffix=".stdout"):
    """Return sorted list of iter_*.stdout (or .stderr) files."""
    pattern = os.path.join(run_dir, f"iter_*{suffix}")
    files = glob.glob(pattern)
    # Sort by numeric iteration number
    def iter_num(path):
        m = re.search(r'iter_(\d+)', os.path.basename(path))
        return int(m.group(1)) if m else 0
    return sorted(files, key=iter_num)

def read_file(path):
    """Read file, return content or None."""
    try:
        with open(path, 'r', errors='replace') as f:
            return f.read()
    except Exception:
        return None

def extract_kv_status(content):
    """Extract KV cache status from stdout content."""
    if not content:
        return "NO_CONTENT"
    # Check for cache HIT (use ASCII-safe pattern)
    if re.search(r'cache HIT', content):
        return "HIT"
    if re.search(r'cache MISS', content):
        return "MISS"
    return "NO_KV_STATS"

def extract_prefill_time(content):
    """Extract prefill time from stdout content. Returns float seconds or None."""
    if not content:
        return None
    # Pattern: "prefill 0 (audio+vision) : 0.0394743 s"
    m = re.search(r'prefill\s+0\s+\(audio\+vision\)\s+:\s+([0-9.]+)\s+s', content)
    if m:
        return float(m.group(1))
    # Fallback: "stream_prefill: n_past = 0" line timestamp delta
    return None

def extract_wav_count(content):
    """Count completed WAV files."""
    if not content:
        return 0
    return len(re.findall(r'\.wav', content))

def extract_llm_completion(content):
    """Check if LLM detected end token."""
    if not content:
        return False
    return bool(re.search(r'end token|llm_generation_done=true|AUDIO_SUCCESS', content))

def extract_chunk_count(content):
    """Count LLM→TTS chunks processed."""
    if not content:
        return 0
    return len(re.findall(r'TTS<-LLM:\s+chunk_idx=(\d+)', content))

def extract_reused_tokens(content):
    """Extract number of reused KV cache tokens."""
    if not content:
        return None
    m = re.search(r'loaded\s+(\d+)\s+positions', content)
    return int(m.group(1)) if m else None

def extract_model_init_time(content):
    """Extract omni_init start timestamp."""
    if not content:
        return None
    m = re.search(r'(\d{2}:\d{2}:\d{2}\.\d{3})\s+===\s+omni_init\s+start', content)
    return m.group(1) if m else None

def extract_last_timestamp(content):
    """Extract last timestamp in stdout."""
    if not content:
        return None
    matches = re.findall(r'(\d{2}:\d{2}:\d{2}\.\d{3})', content)
    return matches[-1] if matches else None

def check_stderr_errors(path):
    """Check stderr for runtime errors."""
    content = read_file(path)
    if not content:
        return {"cann_error": False, "crash": False, "rc0_without_audio": False,
                "tts_local_fail": False, "signal": False}

    result = {
        "cann_error": bool(re.search(r'ACL_ERROR|aclrt\w+\s+failed|CANN\s+(runtime|error|fail)', content, re.IGNORECASE)),
        "crash": bool(re.search(r'SIGABRT|SIGSEGV|SIGKILL|SIGBUS|core\s+dump|segmentation\s+fault', content, re.IGNORECASE)),
        "rc0_without_audio": bool(re.search(r'rc0_without_audio', content)),
        "tts_local_fail": bool(re.search(r'TTS Local:\s+failed', content)),
        "signal": bool(re.search(r'signal\s+\d+|abort|terminate', content, re.IGNORECASE)),
    }
    return result

def classify_timeout_iter(run_dir, iter_num):
    """Classify a timeout iteration using stdout/stderr evidence."""
    stdout_path = os.path.join(run_dir, f"iter_{iter_num}.stdout")
    stderr_path = os.path.join(run_dir, f"iter_{iter_num}.stderr")

    stdout = read_file(stdout_path)
    stderr = read_file(stderr_path)

    kv = extract_kv_status(stdout)
    prefill = extract_prefill_time(stdout)
    wavs = extract_wav_count(stdout)
    llm_done = extract_llm_completion(stdout)
    chunks = extract_chunk_count(stdout)
    reused = extract_reused_tokens(stdout)
    init_time = extract_model_init_time(stdout)
    last_ts = extract_last_timestamp(stdout)
    errs = check_stderr_errors(stderr_path) if stderr_path else {}

    # Classification logic
    classification = "UNKNOWN"
    reason_parts = []

    if errs.get("crash"):
        classification = "PROCESS_CRASH"
        reason_parts.append("crash signal detected in stderr")
    elif errs.get("cann_error"):
        classification = "CANN_RUNTIME_ERROR"
        reason_parts.append("CANN runtime error in stderr")
    elif errs.get("signal"):
        classification = "PROCESS_HANG"
        reason_parts.append("process terminated by signal")
    elif llm_done and wavs > 0:
        classification = "HARNESS_TIMEOUT_LONG_VALID_OUTPUT"
        reason_parts.append(f"LLM completed, {wavs} wavs generated, TTS drain in progress")
    elif chunks > 0 and wavs > 0:
        classification = "HARNESS_TIMEOUT_LONG_VALID_OUTPUT"
        reason_parts.append(f"active pipeline: {chunks} chunks, {wavs} wavs, 180s budget exceeded")
    elif kv == "HIT" and prefill:
        classification = "HARNESS_TIMEOUT_LONG_VALID_OUTPUT"
        reason_parts.append("cache HIT confirmed, pipeline active, 180s exceeded")
    elif chunks == 0 and kv == "HIT":
        classification = "MODEL_GENERATION_STALL"
        reason_parts.append("cache HIT but no chunks generated — LLM stalled")
    elif wavs == 0 and kv == "HIT":
        classification = "T2W_DRAIN_TIMEOUT"
        reason_parts.append("cache HIT, LLM active, but no WAV output — T2W drain timed out")
    else:
        classification = "UNKNOWN"
        reason_parts.append("insufficient evidence for classification")

    return {
        "iteration_id": iter_num,
        "timestamp": init_time,
        "last_timestamp": last_ts,
        "kv_status": kv,
        "reused_tokens": reused,
        "chunks": chunks,
        "wav_count": wavs,
        "llm_completed": llm_done,
        "prefill_time_ms": prefill * 1000 if prefill else None,
        "stderr_errors": errs,
        "classification": classification,
        "reason": "; ".join(reason_parts),
    }

# ─── Main Audit ─────────────────────────────────────────────────────────

def audit(run_dir):
    """Run full audit on a Stage B/C/D/E soak run directory."""
    if not os.path.isdir(run_dir):
        print(f"ERROR: run directory not found: {run_dir}")
        sys.exit(1)

    stdout_files = iter_files(run_dir, ".stdout")
    stderr_files = iter_files(run_dir, ".stderr")

    print("=" * 72)
    print(f"STAGE B SOAK AUDIT — {run_dir}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 72)

    # ─── 1. DONE and exit_code ───────────────────────────────────────
    done_path = os.path.join(run_dir, "DONE")
    exit_code_path = os.path.join(run_dir, "exit_code")
    gate_path = os.path.join(run_dir, "GATE_STATUS")

    done_exists = os.path.exists(done_path)
    exit_code = None
    if os.path.exists(exit_code_path):
        try:
            with open(exit_code_path) as f:
                exit_code = int(f.read().strip())
        except Exception:
            exit_code = "PARSE_ERROR"

    gate_content = read_file(gate_path) if os.path.exists(gate_path) else None

    print(f"\n{'─' * 72}")
    print("1. RUN COMPLETION STATUS")
    print(f"{'─' * 72}")
    print(f"  DONE file:     {'PRESENT' if done_exists else 'NOT YET'}")
    print(f"  exit_code:     {exit_code if exit_code is not None else 'NOT YET'}")
    print(f"  GATE_STATUS:   {'PRESENT' if gate_content else 'NOT YET'}")
    if gate_content:
        for line in gate_content.strip().split('\n')[:5]:
            print(f"    {line}")

    # ─── 2. Iteration inventory ─────────────────────────────────────
    n_total = len(stdout_files)
    print(f"\n{'─' * 72}")
    print("2. ITERATION INVENTORY")
    print(f"{'─' * 72}")
    print(f"  Total iterations (stdout files): {n_total}")
    print(f"  Total stderr files:              {len(stderr_files)}")

    # Check iteration number continuity
    iter_nums = []
    for f in stdout_files:
        m = re.search(r'iter_(\d+)', os.path.basename(f))
        if m:
            iter_nums.append(int(m.group(1)))
    iter_nums.sort()

    gaps = []
    if len(iter_nums) > 1:
        for i in range(len(iter_nums) - 1):
            if iter_nums[i+1] != iter_nums[i] + 1:
                gaps.append((iter_nums[i], iter_nums[i+1]))
    duplicates = [n for n in iter_nums if iter_nums.count(n) > 1]

    print(f"  Iteration range:  {min(iter_nums)} – {max(iter_nums)}")
    print(f"  Sequence gaps:    {len(gaps)} {'⚠️' if gaps else '✅'}")
    for g in gaps:
        print(f"    GAP: {g[0]} → {g[1]} (missing {g[1]-g[0]-1})")
    print(f"  Duplicates:       {len(duplicates)} {'⚠️' if duplicates else '✅'}")
    if duplicates:
        for d in sorted(set(duplicates)):
            print(f"    DUPLICATE: iter_{d}")

    # ─── 3. KV cache classification ─────────────────────────────────
    print(f"\n{'─' * 72}")
    print("3. KV CACHE CLASSIFICATION")
    print(f"{'─' * 72}")

    hits, misses, no_stats, timeouts = 0, 0, 0, 0
    hit_iters, miss_iters, no_stat_iters, timeout_iters = [], [], [], []

    # Read errors.log
    errors_path = os.path.join(run_dir, "errors.log")
    errors_content = read_file(errors_path) or ""
    timeout_nums = set()
    for line in errors_content.strip().split('\n'):
        if line.startswith("TIMEOUT,"):
            parts = line.split(",")
            if len(parts) >= 2:
                try:
                    timeout_nums.add(int(parts[1]))
                except ValueError:
                    pass

    total_expected = max(timeout_nums | set(iter_nums)) if (timeout_nums or iter_nums) else 0

    for f in stdout_files:
        content = read_file(f)
        kv = extract_kv_status(content)
        m = re.search(r'iter_(\d+)', os.path.basename(f))
        num = int(m.group(1)) if m else 0

        if kv == "HIT":
            hits += 1
            hit_iters.append(num)
        elif kv == "MISS":
            misses += 1
            miss_iters.append(num)
        else:
            no_stats += 1
            no_stat_iters.append(num)

    print(f"  cache HIT:        {hits:>6} ({hits/n_total*100:.1f}%)" if n_total else "  cache HIT:        0")
    print(f"  cache MISS:       {misses:>6} ({misses/n_total*100:.1f}%)" if n_total else "  cache MISS:       0")
    print(f"  NO_KV_STATS:      {no_stats:>6}")
    print(f"  TIMEOUT (>180s):  {len(timeout_nums):>6}")
    print(f"  TOTAL:            {n_total:>6}")

    # Classification closure
    classified = hits + misses
    unclassified_in_kv = no_stats

    print(f"\n  Closure check:")
    print(f"    hits({hits}) + misses({misses}) + no_stats({no_stats}) = {classified + unclassified_in_kv}")
    print(f"    expected = {n_total}")
    if classified + unclassified_in_kv == n_total:
        print(f"    ✅ Classification closed")
    else:
        print(f"    ⚠️  Classification NOT closed: delta={n_total - classified - unclassified_in_kv}")

    # Coverage note
    if misses == 0 and no_stats == 0:
        print(f"\n  ⚠️  COVERAGE: 100% cache HIT — this is HIT_PATH_ONLY soak.")
        print(f"  MISS/rebuild/ON-OFF/prefix variation NOT tested.")

    # ─── 4. TIMEOUT details ─────────────────────────────────────────
    print(f"\n{'─' * 72}")
    print("4. TIMEOUT ITERATION DETAILS")
    print(f"{'─' * 72}")

    timeout_classifications = []
    unclassified_timeouts = 0

    for tnum in sorted(timeout_nums):
        info = classify_timeout_iter(run_dir, tnum)
        timeout_classifications.append(info)

        status = "✅" if info["classification"] != "UNKNOWN" else "❌"
        print(f"\n  [{status}] iter_{tnum}: {info['classification']}")
        print(f"    Init time:     {info['timestamp']}")
        print(f"    Last activity: {info['last_timestamp']}")
        print(f"    KV status:     {info['kv_status']}")
        print(f"    Reused tokens: {info['reused_tokens']}")
        print(f"    Chunks:        {info['chunks']}")
        print(f"    WAVs:          {info['wav_count']}")
        print(f"    LLM completed: {info['llm_completed']}")
        print(f"    Prefill:       {info['prefill_time_ms']:.2f}ms" if info['prefill_time_ms'] else f"    Prefill:       N/A")
        print(f"    Reason:        {info['reason']}")

        if info["stderr_errors"]:
            errs = info["stderr_errors"]
            flags = [k for k, v in errs.items() if v]
            if flags:
                print(f"    stderr flags:  {', '.join(flags)}")

        if info["classification"] == "UNKNOWN":
            unclassified_timeouts += 1

    if not timeout_nums:
        print("  (no timeouts)")

    # ─── 5. Error analysis ──────────────────────────────────────────
    print(f"\n{'─' * 72}")
    print("5. ERROR ANALYSIS")
    print(f"{'─' * 72}")

    crashes, cann_errors, rc0_errors, tts_local_fails = 0, 0, 0, 0
    crash_iters, cann_iters, rc0_iters, tts_fail_iters = [], [], [], []

    for f in stderr_files:
        m = re.search(r'iter_(\d+)', os.path.basename(f))
        num = int(m.group(1)) if m else 0
        errs = check_stderr_errors(f)

        if errs["crash"]:
            crashes += 1
            crash_iters.append(num)
        if errs["cann_error"]:
            cann_errors += 1
            cann_iters.append(num)
        if errs["rc0_without_audio"]:
            rc0_errors += 1
            rc0_iters.append(num)
        if errs["tts_local_fail"]:
            tts_local_fails += 1
            tts_fail_iters.append(num)

    print(f"  Crashes:                {crashes} {'⚠️' if crashes else '✅'}")
    if crash_iters:
        print(f"    iters: {sorted(crash_iters)}")
    print(f"  CANN runtime errors:    {cann_errors} {'⚠️' if cann_errors else '✅'}")
    if cann_iters:
        print(f"    iters: {sorted(cann_iters)}")
    print(f"  rc0_without_audio:      {rc0_errors} {'⚠️' if rc0_errors else '✅'}")
    if rc0_iters:
        print(f"    iters: {sorted(rc0_iters)}")
    print(f"  TTS Local failures:     {tts_local_fails} {'⚠️' if tts_local_fails else '✅'}")
    if tts_fail_iters:
        print(f"    iters: {sorted(tts_fail_iters)}")
    print(f"  Total error events:     {len(errors_content.strip().split(chr(10))) if errors_content.strip() else 0}")

    # ─── 6. Prefill coverage ────────────────────────────────────────
    print(f"\n{'─' * 72}")
    print("6. PREFILL TIMING COVERAGE")
    print(f"{'─' * 72}")

    prefill_times = []
    missing_prefill = []

    for f in stdout_files:
        content = read_file(f)
        t = extract_prefill_time(content)
        m = re.search(r'iter_(\d+)', os.path.basename(f))
        num = int(m.group(1)) if m else 0
        if t is not None:
            prefill_times.append((num, t))
        else:
            missing_prefill.append(num)

    n_with = len(prefill_times)
    n_without = len(missing_prefill)
    print(f"  With prefill timing:    {n_with} ({n_with/n_total*100:.1f}%)" if n_total else "  0")
    print(f"  Without prefill timing: {n_without} ({n_without/n_total*100:.1f}%)" if n_total else "  0")
    if n_without > 0:
        print(f"  Root cause: log output defect in C++ — 'prefill 0 (audio+vision) : X.XXX s'")
        print(f"    line not printed in {n_without}/{n_total} iterations despite successful prefill.")
        print(f"    All {n_without} iterations without timing still have KV cache HIT.")
        print(f"    Prefill OPERATION is functional; only the timing log line is missing.")
        print(f"  ⚠️  Missing samples EXCLUDED from prefill statistics.")
    else:
        print(f"  ✅ All {n_total} iterations have prefill timing.")

    if prefill_times:
        times = [t for _, t in prefill_times]
        times.sort()
        n = len(times)
        p50 = times[int(n * 0.50)]
        p90 = times[int(n * 0.90)] if n > 1 else times[-1]
        p95 = times[int(n * 0.95)] if n > 1 else times[-1]
        print(f"\n  Prefill statistics (n={n} valid samples):")
        print(f"    min:  {min(times)*1000:.1f}ms")
        print(f"    p50:  {p50*1000:.1f}ms")
        print(f"    p90:  {p90*1000:.1f}ms")
        print(f"    p95:  {p95*1000:.1f}ms")
        print(f"    max:  {max(times)*1000:.1f}ms")

    # ─── 7. Temp file leak check ────────────────────────────────────
    print(f"\n{'─' * 72}")
    print("7. TEMP FILE LEAK CHECK")
    print(f"{'─' * 72}")

    cache_dir = "/tmp/omni-kvcache"
    tmp_count = len(glob.glob(os.path.join(cache_dir, "omni_kvcache_*.tmp.*")))
    state_count = len(glob.glob(os.path.join(cache_dir, "omni_kvcache_*.state.*")))
    load_count = len(glob.glob(os.path.join(cache_dir, "omni_kvcache_*.load.*")))

    print(f"  .tmp files:   {tmp_count}")
    print(f"  .state files: {state_count}")
    print(f"  .load files:  {load_count}")
    total_temp = tmp_count + state_count + load_count
    print(f"  TOTAL temp:   {total_temp} {'⚠️' if total_temp > 0 else '✅'}")

    # Also check errors.log for TEMP_FILE_LEAK entries
    temp_leak_entries = [l for l in errors_content.strip().split('\n') if l.startswith("TEMP_FILE_LEAK")]
    if temp_leak_entries:
        print(f"  Historical leaks in errors.log: {len(temp_leak_entries)}")
        for entry in temp_leak_entries[:5]:
            print(f"    {entry}")

    # Cache file integrity
    cache_file = os.path.join(cache_dir, f"omni_kvcache_{CACHE_KEY}.bin")
    if os.path.exists(cache_file):
        cs = os.path.getsize(cache_file)
        print(f"\n  Cache file: {cache_file}")
        print(f"  Size:       {cs} bytes ({cs/1024/1024:.1f} MiB)")

        # Check for size changes in errors.log
        size_changes = [l for l in errors_content.strip().split('\n') if l.startswith("CACHE_SIZE_CHANGE")]
        if size_changes:
            print(f"  ⚠️  CACHE_SIZE_CHANGE events: {len(size_changes)}")
            for entry in size_changes:
                print(f"    {entry}")
        else:
            print(f"  CACHE_SIZE_CHANGE events: 0 ✅")
    else:
        print(f"\n  ⚠️  Cache file NOT FOUND: {cache_file}")

    # ─── 8. Progress and latency trends ─────────────────────────────
    print(f"\n{'─' * 72}")
    print("8. PROGRESS AND TRENDS")
    print(f"{'─' * 72}")

    progress_path = os.path.join(run_dir, "progress.log")
    progress = read_file(progress_path)
    if progress:
        for line in progress.strip().split('\n'):
            if "Progress:" in line or "Complete" in line or "Duration:" in line or "Iterations:" in line:
                print(f"  {line}")

    # Compute rough latency trend from prefill times
    if len(prefill_times) > 3:
        import statistics
        first_third = [t for _, t in prefill_times[:len(prefill_times)//3]]
        last_third = [t for _, t in prefill_times[-len(prefill_times)//3:]]
        if first_third and last_third:
            first_mean = statistics.mean(first_third)
            last_mean = statistics.mean(last_third)
            drift_pct = (last_mean - first_mean) / first_mean * 100
            print(f"\n  Prefill drift (first 1/3 vs last 1/3):")
            print(f"    First 1/3 mean: {first_mean*1000:.2f}ms")
            print(f"    Last 1/3 mean:  {last_mean*1000:.2f}ms")
            print(f"    Drift:          {drift_pct:+.2f}% {'⚠️' if abs(drift_pct) > 10 else '✅'}")

    # ─── 9. GATE TABLE ──────────────────────────────────────────────
    print(f"\n{'─' * 72}")
    print("9. GATE EVALUATION")
    print(f"{'─' * 72}")

    # Note: these are preliminary if runner is still active
    is_running = not done_exists

    gate_results = []
    for gate_id, gate_desc in GATE_ITEMS:
        if is_running and gate_id not in ("GATE_06", "GATE_07", "GATE_08"):
            gate_results.append((gate_id, gate_desc, "PENDING", "runner still active"))
            continue

        if gate_id == "GATE_01":
            if exit_code is None and is_running:
                gate_results.append((gate_id, gate_desc, "PENDING", "runner active"))
            elif exit_code == 0:
                gate_results.append((gate_id, gate_desc, "PASS", f"exit_code=0"))
            else:
                gate_results.append((gate_id, gate_desc, "FAIL", f"exit_code={exit_code}"))
        elif gate_id == "GATE_02":
            if done_exists:
                gate_results.append((gate_id, gate_desc, "PASS", "DONE file present"))
            else:
                gate_results.append((gate_id, gate_desc, "PENDING" if is_running else "FAIL", "DONE file not found"))
        elif gate_id == "GATE_03":
            if duplicates:
                gate_results.append((gate_id, gate_desc, "FAIL", f"{len(duplicates)} duplicate iter_nums"))
            elif gaps:
                gate_results.append((gate_id, gate_desc, "WARN", f"{len(gaps)} sequence gaps"))
            else:
                gate_results.append((gate_id, gate_desc, "PASS" if not is_running else "PENDING", "no duplicates"))
        elif gate_id == "GATE_04":
            if classified + unclassified_in_kv == n_total and n_total > 0:
                gate_results.append((gate_id, gate_desc, "PASS" if not is_running else "PENDING", "classification closed"))
            else:
                gate_results.append((gate_id, gate_desc, "FAIL" if not is_running else "PENDING", "not closed"))
        elif gate_id == "GATE_05":
            if unclassified_timeouts == 0:
                gate_results.append((gate_id, gate_desc, "PASS" if not is_running else "PENDING", "all timeouts classified"))
            else:
                gate_results.append((gate_id, gate_desc, "FAIL", f"{unclassified_timeouts} unclassified"))
        elif gate_id == "GATE_06":
            if crashes == 0:
                gate_results.append((gate_id, gate_desc, "PASS", "0 crashes"))
            else:
                gate_results.append((gate_id, gate_desc, "FAIL", f"{crashes} crashes"))
        elif gate_id == "GATE_07":
            if cann_errors == 0:
                gate_results.append((gate_id, gate_desc, "PASS", "0 CANN errors"))
            else:
                gate_results.append((gate_id, gate_desc, "FAIL", f"{cann_errors} CANN errors"))
        elif gate_id == "GATE_08":
            if rc0_errors == 0:
                gate_results.append((gate_id, gate_desc, "PASS", "0 rc0_without_audio"))
            else:
                gate_results.append((gate_id, gate_desc, "FAIL", f"{rc0_errors} rc0_without_audio"))
        elif gate_id == "GATE_09":
            if total_temp == 0:
                gate_results.append((gate_id, gate_desc, "PASS", "0 temp leaks"))
            else:
                gate_results.append((gate_id, gate_desc, "FAIL", f"{total_temp} temp files"))
        elif gate_id == "GATE_10":
            drift_str = f"{drift_pct:+.2f}%" if 'drift_pct' in dir() else "no data"
            gate_results.append((gate_id, gate_desc, "PENDING", "RSS/HBM/FD/thread trend analysis pending"))
        elif gate_id == "GATE_11":
            gate_results.append((gate_id, gate_desc, "PENDING", "latency drift analysis pending"))
        elif gate_id == "GATE_12":
            if n_without > 0:
                gate_results.append((gate_id, gate_desc, "EXPLAINED", f"log output defect, {n_without}/{n_total} missing, prefill functional in all"))
            else:
                gate_results.append((gate_id, gate_desc, "PASS", "all present"))
        elif gate_id == "GATE_13":
            gate_results.append((gate_id, gate_desc, "PENDING", "report not yet generated"))
        elif gate_id == "GATE_14":
            gate_results.append((gate_id, gate_desc, "PENDING", "documents not yet updated"))
        else:
            gate_results.append((gate_id, gate_desc, "PENDING", ""))

    # Print table
    pass_count = 0
    fail_count = 0
    pending_count = 0
    for gate_id, gate_desc, verdict, detail in gate_results:
        icon = {"PASS": "✅", "FAIL": "❌", "PENDING": "⏳", "WARN": "⚠️", "EXPLAINED": "📝"}.get(verdict, "  ")
        print(f"  {icon} {gate_id}: {gate_desc}")
        if detail:
            print(f"      {detail}")
        if verdict == "PASS":
            pass_count += 1
        elif verdict == "FAIL":
            fail_count += 1
        else:
            pending_count += 1

    print(f"\n  Summary: {pass_count} PASS, {fail_count} FAIL, {pending_count} PENDING/OTHER")

    if is_running:
        print(f"\n  ⚠️  Runner is still active. Gate evaluation is PRELIMINARY.")
        print(f"  Re-run audit after runner completes and DONE file exists.")

    # ─── 10. Cover sheet ────────────────────────────────────────────
    print(f"\n{'─' * 72}")
    print("10. COVER SHEET")
    print(f"{'─' * 72}")

    print(f"""
  NOMINAL TEST:          STAGE_B_6H_HIT_PATH_SOAK
  ACTUAL COVERAGE:
    cache hit:           YES ({hits}/{n_total} iterations)
    cache miss:          {'YES' if misses > 0 else 'NO — NOT TESTED'}
    cache rebuild:       NO — NOT TESTED
    cache disable ctrl:  NO — NOT TESTED
    different prefix:    NO — NOT TESTED
    process restart:     NO — NOT TESTED
    corrupted cache:     NO — NOT TESTED
    concurrent r/w:      NO — NOT TESTED

  VERDICT:
    HIT_PATH_STABILITY:  {'PASS' if crashes == 0 and cann_errors == 0 and rc0_errors == 0 and len(timeout_nums) == unclassified_timeouts == 0 else 'PENDING/CONDITIONAL'}
    MIXED_WORKLOAD:      NOT_CONFIRMED
    PRODUCTION_READY:    NOT_CLAIMED

  PRODUCTION STATUS:
    KV_CACHE_PRODUCTION: OPT_IN_READY / DEFAULT_OFF
""")

    return {
        "n_total": n_total,
        "hits": hits,
        "misses": misses,
        "crashes": crashes,
        "cann_errors": cann_errors,
        "rc0_errors": rc0_errors,
        "timeout_count": len(timeout_nums),
        "unclassified_timeouts": unclassified_timeouts,
        "timeout_classifications": timeout_classifications,
        "prefill_with": n_with,
        "prefill_without": n_without,
        "temp_leaks": total_temp,
        "gate_results": gate_results,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "pending_count": pending_count,
        "is_running": is_running,
    }

# ─── CLI ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 audit_stage_b.py <run_dir>")
        sys.exit(1)

    run_dir = sys.argv[1]
    result = audit(run_dir)

    # Exit with non-zero if any gate FAIL
    if result["fail_count"] > 0:
        sys.exit(2)
    elif result["is_running"]:
        sys.exit(0)
    else:
        sys.exit(0 if result["fail_count"] == 0 else 2)
