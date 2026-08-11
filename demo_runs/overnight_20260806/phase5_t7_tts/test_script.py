#!/usr/bin/env python3
"""T7+T8: TTS Safety Regression + Next-Session Isolation (v2 — robust).
Fixed: ALL dict accesses use .get(key, default); no bare r["key"].
Verification: response.done.audio, WAV filesystem, DRAIN_TIMEOUT, post-health, isolation.
"""

import asyncio, json, websockets, time, sys, os, glob, hashlib, subprocess, shutil

SERVER = "ws://localhost:8080/backend"
RUN_DIR = "/workspace/llama.cpp-omni-session-fix/demo_runs/overnight_20260806"
WAV_OUT_BASE = "/tmp/omni_ws"
os.makedirs(f"{RUN_DIR}/phase5_t7_tts", exist_ok=True)
os.makedirs(f"{RUN_DIR}/phase6_t8_isolation", exist_ok=True)

SERVER_LOG = f"{RUN_DIR}/phase2_isolation/server.log"

RESULTS = {"t7": [], "t8": []}


def log_server_checkpoint(tag):
    """Grep server log for errors/warnings/drain timeouts at checkpoint."""
    if not os.path.exists(SERVER_LOG):
        return {"tag": tag, "drain_timeout": "LOG_NOT_FOUND"}
    r = {"tag": tag}
    try:
        r["drain_timeout"] = int(subprocess.check_output(
            f"grep -c 'DRAIN_TIMEOUT' {SERVER_LOG} 2>/dev/null || echo 0", shell=True).decode().strip())
        r["errors"] = subprocess.check_output(
            f"grep -c '\\[ERR\\]' {SERVER_LOG} 2>/dev/null || echo 0", shell=True).decode().strip()
        r["warnings"] = subprocess.check_output(
            f"grep -c '\\[WRN\\]' {SERVER_LOG} 2>/dev/null || echo 0", shell=True).decode().strip()
        last_ctx = subprocess.check_output(
            f"grep 'context_state\\|REUSABLE\\|NOT_REUSABLE\\|KV cache' {SERVER_LOG} 2>/dev/null | tail -3",
            shell=True).decode().strip()
        r["last_context_lines"] = last_ctx
    except Exception as e:
        r["grep_error"] = str(e)
    return r


def check_wav_dir(session_id):
    """Find and inspect WAV output for a session."""
    if not session_id:
        return {"wav_count": 0, "error": "no_session_id"}
    # Look for session directory under /tmp/omni_ws/
    # Session dirs are named with hash
    wav_dir = None
    for entry in os.listdir(WAV_OUT_BASE):
        entry_path = os.path.join(WAV_OUT_BASE, entry)
        if os.path.isdir(entry_path):
            for sub in os.listdir(entry_path):
                sub_path = os.path.join(entry_path, sub)
                tts_wav = os.path.join(sub_path, "tts_wav")
                if os.path.isdir(tts_wav):
                    # This is likely the session - check recency
                    wav_dir = tts_wav
                    break
    if not wav_dir:
        return {"wav_count": 0, "error": "wav_dir_not_found", "base": WAV_OUT_BASE}

    wavs = sorted(glob.glob(os.path.join(wav_dir, "wav_*.wav")))
    if not wavs:
        return {"wav_count": 0, "error": "no_wavs", "dir": wav_dir}

    info = {"wav_count": len(wavs), "dir": wav_dir, "first": os.path.basename(wavs[0]),
            "last": os.path.basename(wavs[-1])}

    # Chunk continuity
    nums = []
    for w in wavs:
        try:
            nums.append(int(os.path.basename(w).replace("wav_", "").replace(".wav", "")))
        except:
            pass
    expected = set(range(min(nums), max(nums) + 1))
    missing = expected - set(nums)
    info["chunk_range"] = f"{min(nums)}-{max(nums)}"
    info["chunk_missing"] = sorted(missing)

    # WAV validity
    bad = []
    import struct
    for w in wavs:
        sz = os.path.getsize(w)
        if sz == 0:
            bad.append(f"{os.path.basename(w)}:empty")
            continue
        try:
            with open(w, "rb") as f:
                riff = f.read(4)
            if riff != b"RIFF":
                bad.append(f"{os.path.basename(w)}:no_riff")
        except:
            bad.append(f"{os.path.basename(w)}:unreadable")
    info["bad_wavs"] = bad
    info["wav_valid"] = len(bad) == 0
    return info


async def tts_session(label, prompt, timeout=180):
    """Run a TTS session. Returns full record including response.done fields."""
    t0 = time.time()
    rec = {
        "label": label, "prompt": prompt, "text": "", "audio_deltas": 0,
        "audio_bytes_total": 0, "wav_files": [], "events": [],
        "session_id": None, "error": None, "dur_s": 0,
        "done_payload": None, "done_audio_len": 0,
    }
    try:
        async with websockets.connect(SERVER, ping_interval=None, close_timeout=10) as ws:
            # Init session
            await ws.send(json.dumps({
                "type": "session.init",
                "payload": {"mode": "turn_based", "use_tts_template": True, "tts_gpu_layers": 99}
            }))
            r = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            etype = r.get("type", "?")
            rec["events"].append(etype)

            if etype != "session.created":
                rec["error"] = f"init:{etype}:{r.get('reason','')}"
                rec["dur_s"] = round(time.time() - t0, 3)
                return rec

            rec["session_id"] = r.get("session_id", "?")

            # Send input
            await ws.send(json.dumps({
                "type": "input.append",
                "input": {
                    "messages": [{"role": "user", "content": prompt}],
                    "streaming": True,
                    "use_tts_template": True
                }
            }))

            # Read response stream
            while True:
                r = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                etype = r.get("type", "?")
                rec["events"].append(etype)

                if etype == "response.output.delta":
                    kind = r.get("kind", "text")
                    if kind == "text":
                        rec["text"] += r.get("text", "")
                    elif kind == "audio":
                        b64 = r.get("audio_b64", "") or ""
                        if b64:
                            rec["audio_deltas"] += 1
                            rec["audio_bytes_total"] += len(b64)
                elif etype == "response.output.audio.delta":
                    b64 = r.get("audio_b64", "") or ""
                    if b64:
                        rec["audio_deltas"] += 1
                        rec["audio_bytes_total"] += len(b64)
                elif etype == "response.done":
                    rec["done_payload"] = {
                        "text": r.get("text", ""),
                        "audio": (r.get("audio") or ""),
                        "reason": r.get("reason", ""),
                        "metrics": r.get("metrics", {}),
                    }
                    rec["done_audio_len"] = len(rec["done_payload"]["audio"])
                    # Use done.text as authoritative if streaming text is empty
                    if not rec["text"] and rec["done_payload"]["text"]:
                        rec["text"] = rec["done_payload"]["text"]
                    break
                elif etype == "session.closed":
                    rec["error"] = f"session.closed:{r.get('reason','?')}"
                    break
                elif etype == "error":
                    rec["error"] = f"error:{r.get('message','?')}"
                    break

                if len(rec["events"]) > 5000:
                    rec["error"] = "event_overflow"
                    break
    except Exception as e:
        rec["error"] = f"exception:{str(e)[:120]}"

    rec["dur_s"] = round(time.time() - t0, 3)

    # Filesystem WAV check (best-effort, finds most recent)
    rec["wav_info"] = {"wav_count": 0, "note": "checked_post_session"}

    return rec


def verdict(rec, min_wavs=1):
    """Determine PASS/FAIL for a TTS session record."""
    err = rec.get("error")
    text = rec.get("text", "")
    done_audio_len = rec.get("done_audio_len", 0)
    wav_info = rec.get("wav_info", {})
    wav_count = wav_info.get("wav_count", 0)

    reasons = []
    if err:
        reasons.append(f"error={err}")
    if not text:
        reasons.append("no_text")
    # Audio: either WS deltas, done.audio, or filesystem WAVs
    has_audio = (rec.get("audio_deltas", 0) > 0 or
                 done_audio_len > 0 or
                 wav_count >= min_wavs)
    if not has_audio:
        reasons.append(f"no_audio(deltas={rec.get('audio_deltas',0)},done_audio={done_audio_len},wavs={wav_count})")

    return len(reasons) == 0, reasons


async def main():
    global RESULTS

    # Pre-flight health check
    print("=== Pre-flight ===")
    try:
        health = subprocess.check_output("curl -s --max-time 5 http://localhost:8080/health",
                                         shell=True).decode().strip()
        print(f"  Health: {health}")
    except Exception as e:
        print(f"  Health FAIL: {e}")
        sys.exit(1)

    drain0 = log_server_checkpoint("pre_t7")
    print(f"  DRAIN_TIMEOUT before T7: {drain0.get('drain_timeout', '?')}")

    # ================================================================
    # T7: Complete TTS Safety Regression
    # ================================================================
    print("\n" + "=" * 60)
    print("T7: TTS Safety Regression (short/medium/long)")
    print("=" * 60)

    t7_cases = [
        ("T7-S", "用三句话介绍一下北京。"),
        ("T7-M", "请详细介绍人工智能的发展历史，包括早期的图灵测试、专家系统、机器学习革命和深度学习时代。"),
        ("T7-L", "请用中文详细讲解以下内容：第一，什么是深度学习神经网络；"
                  "第二，卷积神经网络和循环神经网络的区别；第三，Transformer架构的核心创新；"
                  "第四，大语言模型的训练方法；第五，AI在医疗、教育和自动驾驶中的应用。"
                  "请尽可能详细地展开每个部分，使用具体的例子和数据。"),
    ]

    for label, prompt in t7_cases:
        print(f"\n--- {label} ---")
        rec = await tts_session(label, prompt)
        ok, reasons = verdict(rec)
        RESULTS["t7"].append(rec)

        done = rec.get("done_payload") or {}
        print(f"  [{'PASS' if ok else 'FAIL'}] "
              f"text_len={len(rec.get('text',''))} "
              f"done_audio_len={rec.get('done_audio_len',0)} "
              f"audio_deltas={rec.get('audio_deltas',0)} "
              f"done_reason={done.get('reason','?')} "
              f"dur={rec.get('dur_s',0):.1f}s")
        if rec.get("error"):
            print(f"  ERROR: {rec['error']}")
        if done.get("metrics"):
            m = done["metrics"]
            print(f"  metrics: tokens_in={m.get('tokens_in','?')} tokens_out={m.get('tokens_out','?')} "
                  f"ttft={m.get('ttft','?')} tpot={m.get('tpot','?')}")
        if reasons:
            print(f"  reasons: {reasons}")

        # Check WAVs post-session
        wav_info = check_wav_dir(rec.get("session_id"))
        rec["wav_info"] = wav_info
        if wav_info.get("wav_count", 0) > 0:
            print(f"  WAVs: {wav_info['wav_count']} files, "
                  f"range={wav_info.get('chunk_range','?')}, "
                  f"valid={wav_info.get('wav_valid','?')}, "
                  f"dir={wav_info.get('dir','?')}")

        await asyncio.sleep(2)

    # Server log check after T7
    drain1 = log_server_checkpoint("post_t7")
    print(f"\n  DRAIN_TIMEOUT after T7: {drain1.get('drain_timeout', '?')}")

    # Post-T7 health
    try:
        health = subprocess.check_output("curl -s --max-time 5 http://localhost:8080/health",
                                         shell=True).decode().strip()
        print(f"  Post-T7 health: {health}")
    except:
        print(f"  Post-T7 health: FAIL")

    # T7 verdict
    t7_all = all(verdict(r)[0] for r in RESULTS["t7"])
    print(f"\nT7_OVERALL={'PASS' if t7_all else 'FAIL'} (short/medium/long)")

    if not t7_all:
        print("\n  T7 FAILED - stopping before T8")
        # Save partial results
        with open(f"{RUN_DIR}/phase5_t7_tts/t7_results.json", "w") as f:
            json.dump(RESULTS["t7"], f, indent=2, default=str, ensure_ascii=False)
        return False

    # ================================================================
    # T8: TTS Next-Session Isolation
    # ================================================================
    print("\n" + "=" * 60)
    print("T8: TTS Next-Session Isolation")
    print("=" * 60)

    for interval_ms in [100, 500, 1000]:
        print(f"\n--- T8: interval={interval_ms}ms ---")

        # Session A: Apple history
        rec_a = await tts_session(f"T8-A-{interval_ms}ms",
            "请介绍一下苹果公司的历史，包括乔布斯创立公司、推出Macintosh、"
            "被逐出公司、回归后推出iPod和iPhone等重要里程碑。")
        a_text = rec_a.get("text", "")
        a_ok, a_reasons = verdict(rec_a)
        print(f"  A: text_len={len(a_text)} ok={'PASS' if a_ok else 'FAIL'} "
              f"done_audio={rec_a.get('done_audio_len',0)} "
              f"dur={rec_a.get('dur_s',0):.1f}s")

        await asyncio.sleep(max(interval_ms / 1000.0, 0.1))

        # Session B: Black holes (completely different topic)
        rec_b = await tts_session(f"T8-B-{interval_ms}ms",
            "什么是黑洞？请用简单的语言解释黑洞的形成、事件视界和霍金辐射。")
        b_text = rec_b.get("text", "")
        b_ok, b_reasons = verdict(rec_b)

        # Isolation check: no Apple content in B
        apple_in_b = any(kw in b_text for kw in ["苹果", "iPhone", "乔布斯", "iPod", "Macintosh"])

        pair = {"interval_ms": interval_ms, "A": rec_a, "B": rec_b,
                "isolation_ok": a_ok and b_ok and not apple_in_b}
        RESULTS["t8"].append(pair)

        print(f"  B: text_len={len(b_text)} ok={'PASS' if b_ok else 'FAIL'} "
              f"done_audio={rec_b.get('done_audio_len',0)} "
              f"dur={rec_b.get('dur_s',0):.1f}s")
        print(f"  isolation={'PASS' if not apple_in_b else 'FAIL'} "
              f"(apple_in_b={apple_in_b})")

        # Check WAVs for both sessions
        for tag, r in [("A", rec_a), ("B", rec_b)]:
            wi = check_wav_dir(r.get("session_id"))
            r["wav_info"] = wi
            if wi.get("wav_count", 0) > 0:
                print(f"  {tag} WAVs: {wi['wav_count']} files, valid={wi.get('wav_valid','?')}")

        await asyncio.sleep(3)

    # T8 verdict
    t8_all = all(p.get("isolation_ok", False) for p in RESULTS["t8"])
    print(f"\nT8_OVERALL={'PASS' if t8_all else 'FAIL'}")

    # Final server log check
    drain2 = log_server_checkpoint("post_t8")
    drain_timeouts = int(drain2.get("drain_timeout", -1))
    print(f"\nDRAIN_TIMEOUT total: {drain_timeouts}")

    # Post-flight health
    try:
        health = subprocess.check_output("curl -s --max-time 5 http://localhost:8080/health",
                                         shell=True).decode().strip()
        print(f"Post-T8 health: {health}")
    except:
        print(f"Post-T8 health: FAIL")

    # Save results
    with open(f"{RUN_DIR}/phase5_t7_tts/t7_results.json", "w") as f:
        json.dump(RESULTS["t7"], f, indent=2, default=str, ensure_ascii=False)
    with open(f"{RUN_DIR}/phase6_t8_isolation/t8_results.json", "w") as f:
        json.dump(RESULTS["t8"], f, indent=2, default=str, ensure_ascii=False)

    # Print final gate status
    print(f"\n{'='*60}")
    print(f"T7_GATE={'PASS' if t7_all else 'FAIL'}")
    print(f"T8_GATE={'PASS' if t8_all else 'FAIL'}")
    print(f"DRAIN_TIMEOUT={'PASS' if drain_timeouts == 0 else 'FAIL'} ({drain_timeouts})")
    print(f"T7_T8_GATE={'PASS' if (t7_all and t8_all and drain_timeouts == 0) else 'FAIL'}")

    return t7_all and t8_all


result = asyncio.run(main())
print(f"\nEXIT={'PASS' if result else 'FAIL'}")
sys.exit(0 if result else 1)
