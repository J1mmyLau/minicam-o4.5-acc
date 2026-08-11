#!/usr/bin/env python3
"""T7+T8 Robust v3: Save raw WS events to JSONL. Separate server-side vs client-side verdicts.

T7A (server-side): WAV count>0, chunk continuity, valid WAVs, 24kHz, no empty, no DRAIN_TIMEOUT, context REUSABLE, health
T7B (client-side): WS audio delta count, response.done.audio presence, bytes, base64 validity
T8: Cross-session isolation (text, audio, WAV dirs)
"""

import asyncio, json, websockets, time, sys, os, glob, struct, subprocess, base64, shutil

SERVER = "ws://localhost:8080/backend"
RUN_DIR = "/workspace/llama.cpp-omni-session-fix/demo_runs/overnight_20260806"
WAV_OUT_BASE = "/tmp/omni_ws"

T7_OUT = f"{RUN_DIR}/phase5_t7_tts"
T8_OUT = f"{RUN_DIR}/phase6_t8_isolation"
os.makedirs(T7_OUT, exist_ok=True)
os.makedirs(T8_OUT, exist_ok=True)

SERVER_LOG = f"{RUN_DIR}/phase2_isolation/server.log"


def server_log_checkpoint(tag):
    """Read-only checkpoint of server log counters."""
    ck = {"tag": tag, "drain_timeout": 0, "errors": 0, "warnings": 0, "last_ctx": ""}
    if not os.path.exists(SERVER_LOG):
        ck["note"] = "LOG_NOT_FOUND"
        return ck
    try:
        r = subprocess.run(
            f"grep -c 'DRAIN_TIMEOUT' {SERVER_LOG} 2>/dev/null || echo 0",
            shell=True, capture_output=True, text=True, timeout=5)
        ck["drain_timeout"] = int(r.stdout.strip() or 0)
    except:
        pass
    try:
        r = subprocess.run(
            f"grep 'context_state\\|REUSABLE\\|NOT_REUSABLE\\|KV cache' {SERVER_LOG} 2>/dev/null | tail -5",
            shell=True, capture_output=True, text=True, timeout=5)
        ck["last_ctx"] = r.stdout.strip()
    except:
        pass
    return ck


def server_health():
    try:
        r = subprocess.run("curl -s --max-time 5 http://localhost:8080/health",
                           shell=True, capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception as e:
        return f"FAIL:{e}"


def inspect_wav_dir(session_dir):
    """Inspect a single session's tts_wav directory. Returns structured dict."""
    tts_wav = os.path.join(session_dir, "tts_wav")
    result = {
        "session_dir": session_dir,
        "tts_wav_exists": os.path.isdir(tts_wav),
        "wav_count": 0, "wav_total_bytes": 0, "wav_total_duration_s": 0.0,
        "chunk_min": None, "chunk_max": None, "chunk_missing": [],
        "bad_files": [], "sample_rates": set(), "wav_dir": tts_wav,
    }
    if not result["tts_wav_exists"]:
        return result

    wavs = sorted(glob.glob(os.path.join(tts_wav, "wav_*.wav")))
    result["wav_count"] = len(wavs)

    if not wavs:
        return result

    # Chunk indices
    nums = []
    for w in wavs:
        try:
            nums.append(int(os.path.basename(w).replace("wav_", "").replace(".wav", "")))
        except:
            pass
    if nums:
        result["chunk_min"] = min(nums)
        result["chunk_max"] = max(nums)
        result["chunk_missing"] = sorted(set(range(min(nums), max(nums) + 1)) - set(nums))

    for w in wavs:
        sz = os.path.getsize(w)
        result["wav_total_bytes"] += sz
        if sz == 0:
            result["bad_files"].append(f"{os.path.basename(w)}:empty")
            continue
        try:
            with open(w, "rb") as f:
                riff = f.read(4)
                if riff != b"RIFF":
                    result["bad_files"].append(f"{os.path.basename(w)}:bad_header={riff!r}")
                    continue
                f.seek(24)
                sr = struct.unpack("<I", f.read(4))[0]
                result["sample_rates"].add(sr)
                f.seek(40)
                data_sz = struct.unpack("<I", f.read(4))[0]
                dur = data_sz / (sr * 2)  # 16-bit mono
                result["wav_total_duration_s"] += dur
        except Exception as e:
            result["bad_files"].append(f"{os.path.basename(w)}:{e}")

    return result


def find_session_wav_dirs(base_dir):
    """Find all session round directories with tts_wav subdirs, sorted by mtime."""
    sessions = []
    if not os.path.isdir(base_dir):
        return sessions
    for entry in os.listdir(base_dir):
        ep = os.path.join(base_dir, entry)
        if not os.path.isdir(ep):
            continue
        for sub in os.listdir(ep):
            sp = os.path.join(ep, sub)
            tts_wav = os.path.join(sp, "tts_wav")
            if os.path.isdir(tts_wav):
                sessions.append({"path": sp, "mtime": os.path.getmtime(sp)})
    sessions.sort(key=lambda x: x["mtime"])
    return sessions


async def tts_session(session_label, prompt, timeout=300, raw_log_path=None):
    """Run one TTS session. Saves ALL raw WS events to JSONL."""
    t0 = time.time()
    rec = {
        "label": session_label,
        "prompt_preview": prompt[:80],
        "session_id": None,
        "error": None,
        "dur_s": 0.0,
        # Text
        "text_streaming": "",
        "text_done": "",
        # WS audio deltas
        "ws_audio_delta_count": 0,
        "ws_audio_delta_bytes": 0,
        "ws_audio_delta_b64_samples": [],  # first 3 b64 lengths
        # Events
        "event_types_seen": [],
        "event_count": 0,
        # response.done
        "response_done_received": False,
        "response_done_raw": None,  # complete JSON as dict
        "response_done_audio_present": False,
        "response_done_audio_bytes": 0,
        "response_done_audio_base64_valid": None,
        "response_done_audio_base64_decode_error": None,
        # Filesystem WAV
        "filesystem_wav_count": 0,
        "filesystem_wav_total_bytes": 0,
        "filesystem_wav_total_duration_s": 0.0,
    }

    # Open raw JSONL log if path given
    raw_fh = open(raw_log_path, "w") if raw_log_path else None

    try:
        async with websockets.connect(SERVER, ping_interval=None, close_timeout=10) as ws:
            # Init
            init_msg = {"type": "session.init",
                        "payload": {"mode": "turn_based", "use_tts_template": True, "tts_gpu_layers": 99}}
            await ws.send(json.dumps(init_msg, ensure_ascii=False))
            msg = await asyncio.wait_for(ws.recv(), timeout=60)
            r = json.loads(msg)
            etype = r.get("type", "?")
            rec["event_types_seen"].append(etype)
            if raw_fh:
                raw_fh.write(json.dumps(r, ensure_ascii=False) + "\n")

            if etype != "session.created":
                rec["error"] = f"init_rejected:{etype}:{r.get('reason','')}"
                rec["dur_s"] = round(time.time() - t0, 3)
                return rec

            rec["session_id"] = r.get("session_id", "")

            # Input
            inp_msg = {"type": "input.append",
                       "input": {"messages": [{"role": "user", "content": prompt}],
                                 "streaming": True, "use_tts_template": True}}
            await ws.send(json.dumps(inp_msg, ensure_ascii=False))

            # Read all events
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                r = json.loads(msg)
                etype = r.get("type", "?")
                rec["event_types_seen"].append(etype)
                rec["event_count"] += 1
                if raw_fh:
                    raw_fh.write(json.dumps(r, ensure_ascii=False) + "\n")

                if etype == "response.output.delta":
                    kind = r.get("kind", "text")
                    if kind == "text":
                        rec["text_streaming"] += (r.get("text") or "")
                    elif kind == "audio":
                        # Field name is "audio" (not "audio_b64") — server convention
                        audio_data = r.get("audio") or ""
                        if audio_data:
                            rec["ws_audio_delta_count"] += 1
                            rec["ws_audio_delta_bytes"] += len(str(audio_data))
                            if len(rec["ws_audio_delta_b64_samples"]) < 3:
                                rec["ws_audio_delta_b64_samples"].append(len(str(audio_data)))

                elif etype == "response.output.audio.delta":
                    # Field name is "audio" (not "audio_b64") — server convention
                    audio_data = r.get("audio") or ""
                    if audio_data:
                        rec["ws_audio_delta_count"] += 1
                        rec["ws_audio_delta_bytes"] += len(str(audio_data))
                        if len(rec["ws_audio_delta_b64_samples"]) < 3:
                            rec["ws_audio_delta_b64_samples"].append(len(str(audio_data)))

                elif etype == "response.done":
                    rec["response_done_received"] = True
                    rec["response_done_raw"] = r  # save complete JSON

                    td = r.get("text") or ""
                    rec["text_done"] = td
                    if not rec["text_streaming"] and td:
                        rec["text_streaming"] = td

                    audio_val = r.get("audio")
                    if audio_val is not None and audio_val != "":
                        rec["response_done_audio_present"] = True
                        rec["response_done_audio_bytes"] = len(str(audio_val))
                        # Try base64 decode
                        try:
                            decoded = base64.b64decode(audio_val)
                            rec["response_done_audio_base64_valid"] = True
                            rec["response_done_audio_pcm_bytes"] = len(decoded)
                        except Exception as e:
                            rec["response_done_audio_base64_valid"] = False
                            rec["response_done_audio_base64_decode_error"] = str(e)[:200]
                    break

                elif etype == "session.closed":
                    rec["error"] = f"session.closed:{r.get('reason','?')}"
                    break

                elif etype == "error":
                    rec["error"] = f"error:{r.get('message','?')}"
                    break

                if rec["event_count"] > 5000:
                    rec["error"] = "event_overflow"
                    break

    except Exception as e:
        rec["error"] = f"exception:{str(e)[:200]}"
    finally:
        if raw_fh:
            raw_fh.close()

    rec["dur_s"] = round(time.time() - t0, 3)

    return rec


def judge_t7a_server(rec, wav_info, drain_checkpoint_before, drain_checkpoint_after):
    """T7A: Server-side TTS generation gate."""
    checks = {}
    # 1. WAV count > 0
    wav_count = wav_info.get("wav_count", 0)
    checks["WAV_COUNT_GT_0"] = ("PASS" if wav_count > 0 else "FAIL", wav_count)
    # 2. Chunk continuity
    missing = wav_info.get("chunk_missing", [])
    checks["CHUNK_CONTINUITY"] = ("PASS" if len(missing) == 0 else "FAIL", missing)
    # 3. All WAVs valid (RIFF header, non-empty)
    bad = wav_info.get("bad_files", [])
    checks["ALL_WAV_VALID"] = ("PASS" if len(bad) == 0 else "FAIL", bad)
    # 4. 24kHz sample rate
    srs = wav_info.get("sample_rates", set())
    checks["SAMPLE_RATE_24K"] = ("PASS" if srs == {24000} else "FAIL" if 24000 not in srs else "PARTIAL", sorted(srs))
    # 5. No empty files
    checks["NO_EMPTY_WAV"] = ("PASS" if len(bad) == 0 else "FAIL", bad)
    # 6. No DRAIN_TIMEOUT
    dt_after = int(drain_checkpoint_after.get("drain_timeout", 0))
    dt_before = int(drain_checkpoint_before.get("drain_timeout", 0))
    new_drain_timeouts = max(0, dt_after - dt_before)
    checks["NO_DRAIN_TIMEOUT"] = ("PASS" if new_drain_timeouts == 0 else "FAIL",
                                   f"before={dt_before} after={dt_after} new={new_drain_timeouts}")
    # 7. Context REUSABLE after last WAV
    ctx_lines = drain_checkpoint_after.get("last_ctx", "")
    checks["CONTEXT_REUSABLE"] = ("PASS" if "KV cache cleared" in ctx_lines else "INCONCLUSIVE", ctx_lines[:200])

    all_pass = all(v[0] == "PASS" for v in checks.values())
    return all_pass, checks


def judge_t7b_client(rec):
    """T7B: Client-side audio delivery gate."""
    checks = {}
    # WS audio deltas
    adc = rec.get("ws_audio_delta_count", 0)
    adb = rec.get("ws_audio_delta_bytes", 0)
    checks["WS_AUDIO_DELTA_COUNT"] = adc
    checks["WS_AUDIO_DELTA_BYTES"] = adb
    checks["WS_INCREMENTAL_STREAMING"] = "YES" if adc > 0 else "NO"

    # response.done audio
    checks["RESPONSE_DONE_RECEIVED"] = rec.get("response_done_received", False)
    checks["RESPONSE_DONE_AUDIO_PRESENT"] = rec.get("response_done_audio_present", False)
    checks["RESPONSE_DONE_AUDIO_BYTES"] = rec.get("response_done_audio_bytes", 0)
    checks["RESPONSE_DONE_AUDIO_BASE64_VALID"] = rec.get("response_done_audio_base64_valid")

    # Determine delivery mode
    if adc > 0:
        checks["CLIENT_AUDIO_DELIVERY_MODE"] = "WS_INCREMENTAL_STREAMING"
        checks["NOTE"] = "response.done.audio=null is EXPECTED in streaming mode (audio already delivered via deltas)"
    elif rec.get("response_done_audio_present"):
        if rec.get("response_done_audio_base64_valid"):
            checks["CLIENT_AUDIO_DELIVERY_MODE"] = "BATCH_AT_RESPONSE_DONE"
        else:
            checks["CLIENT_AUDIO_DELIVERY_MODE"] = "BATCH_AT_RESPONSE_DONE_B64_INVALID"
    else:
        checks["CLIENT_AUDIO_DELIVERY_MODE"] = "NO_CLIENT_AUDIO"

    # Client audio delivered?
    # In WS_INCREMENTAL_STREAMING mode, audio is delivered via deltas; response.done.audio=null is expected.
    has_client_audio = (adc > 0) or (rec.get("response_done_audio_present") and rec.get("response_done_audio_base64_valid"))
    checks["CLIENT_AUDIO_DELIVERED"] = has_client_audio

    return checks


def print_t7_verdict(label, t7a_pass, t7a_checks, t7b_checks, wav_info, rec):
    print(f"\n{'='*60}")
    print(f"  {label} VERDICT")
    print(f"{'='*60}")
    print(f"  T7A (Server-side TTS generation): {'PASS' if t7a_pass else 'FAIL'}")
    for k, v in t7a_checks.items():
        if isinstance(v, tuple):
            print(f"    {k}: {v[0]} ({v[1]})")
        else:
            print(f"    {k}: {v}")
    print(f"\n  T7B (Client-side audio delivery):")
    for k, v in t7b_checks.items():
        print(f"    {k}: {v}")
    print(f"\n  Filesystem WAVs: count={wav_info.get('wav_count',0)} "
          f"bytes={wav_info.get('wav_total_bytes',0)} "
          f"dur={wav_info.get('wav_total_duration_s',0):.1f}s")
    print(f"  Text: len_streaming={len(rec.get('text_streaming',''))} "
          f"len_done={len(rec.get('text_done',''))}")
    if rec.get("error"):
        print(f"  ERROR: {rec['error']}")


async def main():
    # === Pre-flight ===
    print("=== Pre-flight ===")
    health0 = server_health()
    print(f"  Health: {health0}")
    if "FAIL" in health0:
        print("  FATAL: Server not healthy")
        sys.exit(1)

    drain_cp0 = server_log_checkpoint("pre_t7")
    print(f"  DRAIN_TIMEOUT before: {drain_cp0.get('drain_timeout', '?')}")

    # Find existing WAV dirs before test (to isolate new ones)
    pre_sessions = find_session_wav_dirs(WAV_OUT_BASE)
    pre_dirs = {s["path"] for s in pre_sessions}
    print(f"  Existing WAV session dirs: {len(pre_dirs)}")

    # ================================================================
    # T7: TTS Safety Regression
    # ================================================================
    print(f"\n{'='*60}")
    print("T7: TTS Safety Regression")
    print(f"{'='*60}")

    t7_cases = [
        ("T7-S", "用三句话介绍一下北京。"),
        ("T7-M", "请详细介绍人工智能的发展历史，包括早期的图灵测试、专家系统、机器学习革命和深度学习时代。"),
        ("T7-L", "请用中文详细讲解以下内容：第一，什么是深度学习神经网络；"
                  "第二，卷积神经网络和循环神经网络的区别；第三，Transformer架构的核心创新；"
                  "第四，大语言模型的训练方法；第五，AI在医疗、教育和自动驾驶中的应用。"
                  "请尽可能详细地展开每个部分，使用具体的例子和数据。"),
    ]

    t7_results = []
    all_t7a_pass = True

    for label, prompt in t7_cases:
        print(f"\n--- {label} ---")
        raw_log = f"{T7_OUT}/{label}_raw_ws_events.jsonl"

        rec = await tts_session(label, prompt, raw_log_path=raw_log)

        # Find new WAV session dirs
        post_sessions = find_session_wav_dirs(WAV_OUT_BASE)
        new_dirs = [s for s in post_sessions if s["path"] not in pre_dirs]

        # Pick the most recent new dir
        wav_info = {"wav_count": 0, "note": "no_new_wav_dir_found"}
        if new_dirs:
            newest = new_dirs[-1]  # sorted by mtime
            wav_info = inspect_wav_dir(newest["path"])

        drain_cp_after = server_log_checkpoint(f"post_{label}")

        # Judge
        t7a_pass, t7a_checks = judge_t7a_server(rec, wav_info, drain_cp0, drain_cp_after)
        t7b_checks = judge_t7b_client(rec)

        entry = {
            "label": label,
            "rec": rec,
            "wav_info": wav_info,
            "t7a_pass": t7a_pass,
            "t7a_checks": t7a_checks,
            "t7b_checks": t7b_checks,
            "drain_checkpoint": drain_cp_after,
        }
        t7_results.append(entry)

        print_t7_verdict(label, t7a_pass, t7a_checks, t7b_checks, wav_info, rec)
        if not t7a_pass:
            all_t7a_pass = False

        # Save per-session result immediately
        with open(f"{T7_OUT}/{label}_result.json", "w") as f:
            json.dump({k: v for k, v in entry.items() if k != "rec"}, f,
                      indent=2, default=str, ensure_ascii=False)
        # Save rec separately (it's large)
        with open(f"{T7_OUT}/{label}_rec.json", "w") as f:
            json.dump(rec, f, indent=2, default=str, ensure_ascii=False)

        await asyncio.sleep(3)

    # T7 overall
    drain_cp_t7 = server_log_checkpoint("post_t7_all")
    health_t7 = server_health()

    print(f"\n{'='*60}")
    print("T7 OVERALL SUMMARY")
    print(f"{'='*60}")
    print(f"  T7A (Server-side TTS generation): {'PASS' if all_t7a_pass else 'FAIL'}")
    for e in t7_results:
        print(f"    {e['label']}: T7A={'PASS' if e['t7a_pass'] else 'FAIL'} "
              f"WAVs={e['wav_info'].get('wav_count',0)} "
              f"WS_deltas={e['rec'].get('ws_audio_delta_count',0)} "
              f"done_audio={e['rec'].get('response_done_audio_present',False)} "
              f"mode={e['t7b_checks'].get('CLIENT_AUDIO_DELIVERY_MODE','?')}")
    print(f"  DRAIN_TIMEOUT: {drain_cp_t7.get('drain_timeout', '?')}")
    print(f"  Health: {health_t7}")

    # Save T7 full results (without raw recs — those are saved separately)
    t7_save = []
    for e in t7_results:
        t7_save.append({
            "label": e["label"],
            "t7a_pass": e["t7a_pass"],
            "t7a_checks": e["t7a_checks"],
            "t7b_checks": e["t7b_checks"],
            "wav_info": e["wav_info"],
            "drain_checkpoint": e["drain_checkpoint"],
            "summary": {
                "text_len": len(e["rec"].get("text_streaming", "")),
                "ws_audio_delta_count": e["rec"].get("ws_audio_delta_count", 0),
                "done_audio_present": e["rec"].get("response_done_audio_present", False),
                "done_audio_bytes": e["rec"].get("response_done_audio_bytes", 0),
                "error": e["rec"].get("error"),
                "dur_s": e["rec"].get("dur_s", 0),
            }
        })
    with open(f"{T7_OUT}/t7_summary.json", "w") as f:
        json.dump(t7_save, f, indent=2, default=str, ensure_ascii=False)

    if not all_t7a_pass:
        print("\nT7A FAILED — stopping before T8")
        return False

    # ================================================================
    # T8: Next-Session Isolation
    # ================================================================
    print(f"\n{'='*60}")
    print("T8: TTS Next-Session Isolation")
    print(f"{'='*60}")

    t8_results = []
    all_t8_pass = True

    for interval_ms in [100, 500, 1000]:
        print(f"\n--- T8: interval={interval_ms}ms ---")
        drain_before = server_log_checkpoint(f"pre_t8_{interval_ms}ms")

        # Session A
        raw_a = f"{T8_OUT}/T8_A_{interval_ms}ms_raw_ws_events.jsonl"
        rec_a = await tts_session(f"T8-A-{interval_ms}ms",
            "请介绍一下苹果公司的历史，包括乔布斯创立公司、推出Macintosh、"
            "被逐出公司、回归后推出iPod和iPhone等重要里程碑。",
            raw_log_path=raw_a)

        await asyncio.sleep(max(interval_ms / 1000.0, 0.1))

        # Session B
        raw_b = f"{T8_OUT}/T8_B_{interval_ms}ms_raw_ws_events.jsonl"
        rec_b = await tts_session(f"T8-B-{interval_ms}ms",
            "什么是黑洞？请用简单的语言解释黑洞的形成、事件视界和霍金辐射。",
            raw_log_path=raw_b)

        drain_after = server_log_checkpoint(f"post_t8_{interval_ms}ms")

        # Find all new WAV dirs since this pair started
        post_sessions_pair = find_session_wav_dirs(WAV_OUT_BASE)
        new_dirs_pair = [s for s in post_sessions_pair if s["path"] not in pre_dirs]
        # Last 2 are A and B (A first, B second)
        wav_a = inspect_wav_dir(new_dirs_pair[-2]["path"]) if len(new_dirs_pair) >= 2 else {"wav_count": 0, "note": "not_found"}
        wav_b = inspect_wav_dir(new_dirs_pair[-1]["path"]) if len(new_dirs_pair) >= 1 else {"wav_count": 0, "note": "not_found"}

        # Isolation checks
        a_text = rec_a.get("text_streaming", "") or rec_a.get("text_done", "")
        b_text = rec_b.get("text_streaming", "") or rec_b.get("text_done", "")
        apple_kw = ["苹果", "iPhone", "乔布斯", "iPod", "Macintosh"]
        apple_in_b = any(kw in b_text for kw in apple_kw)
        blackhole_kw = ["黑洞", "霍金", "事件视界"]
        blackhole_in_a = any(kw in a_text for kw in blackhole_kw)

        drain_new = max(0, int(drain_after.get("drain_timeout", 0)) - int(drain_before.get("drain_timeout", 0)))

        pair = {
            "interval_ms": interval_ms,
            "A": {
                "label": rec_a.get("label"), "text_len": len(a_text),
                "ws_audio_delta_count": rec_a.get("ws_audio_delta_count", 0),
                "done_audio_present": rec_a.get("response_done_audio_present", False),
                "error": rec_a.get("error"),
                "wav_count": wav_a.get("wav_count", 0),
                "wav_dir": wav_a.get("wav_dir", "?"),
            },
            "B": {
                "label": rec_b.get("label"), "text_len": len(b_text),
                "ws_audio_delta_count": rec_b.get("ws_audio_delta_count", 0),
                "done_audio_present": rec_b.get("response_done_audio_present", False),
                "error": rec_b.get("error"),
                "wav_count": wav_b.get("wav_count", 0),
                "wav_dir": wav_b.get("wav_dir", "?"),
            },
            "isolation": {
                "apple_in_b": apple_in_b,
                "blackhole_in_a": blackhole_in_a,
                "text_isolation": "PASS" if (not apple_in_b and not blackhole_in_a) else "FAIL",
                "wav_dirs_distinct": "PASS" if (wav_a.get("wav_dir") != wav_b.get("wav_dir")) else "FAIL",
                "drain_timeout_new": drain_new,
            }
        }
        pair["isolation"]["all_pass"] = (
            pair["isolation"]["text_isolation"] == "PASS" and
            pair["isolation"]["wav_dirs_distinct"] == "PASS" and
            drain_new == 0 and
            rec_a.get("error") is None and
            rec_b.get("error") is None
        )
        t8_results.append(pair)

        print(f"  A: text_len={len(a_text)} wavs={wav_a.get('wav_count',0)} "
              f"done_audio={rec_a.get('response_done_audio_present',False)} err={rec_a.get('error','none')}")
        print(f"  B: text_len={len(b_text)} wavs={wav_b.get('wav_count',0)} "
              f"done_audio={rec_b.get('response_done_audio_present',False)} err={rec_b.get('error','none')}")
        print(f"  isolation: text={'PASS' if not apple_in_b else 'FAIL'} "
              f"wav_dirs={'PASS' if wav_a.get('wav_dir')!=wav_b.get('wav_dir') else 'FAIL'} "
              f"drain={drain_new}")

        if not pair["isolation"]["all_pass"]:
            all_t8_pass = False

        # Save individual pair
        with open(f"{T8_OUT}/T8_pair_{interval_ms}ms.json", "w") as f:
            json.dump(pair, f, indent=2, default=str, ensure_ascii=False)

        await asyncio.sleep(3)

    # T8 summary
    health_t8 = server_health()
    drain_final = server_log_checkpoint("post_t8_all")

    print(f"\n{'='*60}")
    print("T8 OVERALL SUMMARY")
    print(f"{'='*60}")
    for p in t8_results:
        iso = p["isolation"]
        print(f"  interval={p['interval_ms']}ms: "
              f"text_iso={iso['text_isolation']} "
              f"wav_iso={iso['wav_dirs_distinct']} "
              f"drain_new={iso['drain_timeout_new']} "
              f"OVERALL={'PASS' if iso['all_pass'] else 'FAIL'}")
    print(f"  T8_OVERALL={'PASS' if all_t8_pass else 'FAIL'}")
    print(f"  Final DRAIN_TIMEOUT: {drain_final.get('drain_timeout', '?')}")
    print(f"  Final Health: {health_t8}")

    with open(f"{T8_OUT}/t8_summary.json", "w") as f:
        json.dump(t8_results, f, indent=2, default=str, ensure_ascii=False)

    # Final gate
    print(f"\n{'='*60}")
    print(f"FINAL GATE STATUS")
    print(f"{'='*60}")
    print(f"  T7A_SERVER_TTS: {'PASS' if all_t7a_pass else 'FAIL'}")
    print(f"  T7B_CLIENT_AUDIO: SEE_PER_CASE (check t7_summary.json)")
    print(f"  T8_ISOLATION: {'PASS' if all_t8_pass else 'FAIL'}")
    print(f"  DRAIN_TIMEOUT: {'PASS' if int(drain_final.get('drain_timeout',0))==0 else 'FAIL'}")
    final_pass = all_t7a_pass and all_t8_pass and int(drain_final.get("drain_timeout", 0)) == 0
    print(f"  OVERALL: {'PASS' if final_pass else 'FAIL'}")

    return final_pass


result = asyncio.run(main())
print(f"\nEXIT={'PASS' if result else 'FAIL'}")
sys.exit(0 if result else 1)
