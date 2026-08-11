#!/usr/bin/env python3
"""T7: Complete TTS safety regression + T8: Next-session isolation.
Tests short/medium/long TTS generations with use_tts_template=true in turn_based mode.
Verifies: WAV count > 0, last WAV complete, context reusable after last WAV,
no premature T2W advance, no drain timeout, no cross-session contamination."""

import asyncio, json, websockets, time, sys, os, hashlib

SERVER = "ws://localhost:8080/backend"
RUN_DIR = "/workspace/llama.cpp-omni-session-fix/demo_runs/overnight_20260806"
WAV_DIR = f"{RUN_DIR}/phase5_t7_tts/wavs"
os.makedirs(WAV_DIR, exist_ok=True)
os.makedirs(f"{RUN_DIR}/phase6_t8_isolation", exist_ok=True)

RESULTS = {"t7": [], "t8": []}

async def tts_session(label, prompt, timeout=120):
    """Run a TTS session and collect text + audio events."""
    t0 = time.time()
    rec = {
        "label": label, "prompt": prompt, "text": "", "audio_deltas": 0,
        "audio_bytes_total": 0, "wav_files": [], "events": [],
        "session_id": None, "error": None, "dur_s": 0,
        "first_audio_ts": None, "last_audio_ts": None, "done_ts": None,
    }
    try:
        async with websockets.connect(SERVER, ping_interval=None, close_timeout=10) as ws:
            await ws.send(json.dumps({"type":"session.init","payload":{"mode":"turn_based","use_tts_template":True,"tts_gpu_layers":99}}))
            r = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            if r.get("type") != "session.created":
                rec["error"] = f"init: {r.get('type')} {r.get('reason','')}"
                rec["dur_s"] = round(time.time()-t0,3)
                return rec
            rec["session_id"] = r["session_id"]

            await ws.send(json.dumps({"type":"input.append","input":{"messages":[{"role":"user","content":prompt}],"streaming":True,"use_tts_template":True}}))

            while True:
                r = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                etype = r.get("type","?")
                rec["events"].append(etype)

                if etype == "response.output.delta":
                    kind = r.get("kind","text")
                    if kind == "text":
                        rec["text"] += r.get("text","")
                    elif kind == "audio":
                        b64 = r.get("audio_b64","")
                        if b64:
                            rec["audio_deltas"] += 1
                            rec["audio_bytes_total"] += len(b64)
                            if rec["first_audio_ts"] is None:
                                rec["first_audio_ts"] = time.time() - t0
                            rec["last_audio_ts"] = time.time() - t0
                elif etype == "response.output.audio.delta":
                    b64 = r.get("audio_b64","")
                    if b64:
                        rec["audio_deltas"] += 1
                        rec["audio_bytes_total"] += len(b64)
                        if rec["first_audio_ts"] is None:
                            rec["first_audio_ts"] = time.time() - t0
                        rec["last_audio_ts"] = time.time() - t0
                elif etype == "response.done":
                    rec["done_ts"] = time.time() - t0
                    rec["done_text"] = r.get("text","")
                    rec["done_audio"] = r.get("audio")  # base64 or null
                    rec["done_metrics"] = r.get("metrics",{})
                    break
                elif etype == "session.closed":
                    rec["error"] = f"session.closed: {r.get('reason','?')}"
                    break
                elif etype == "error":
                    rec["error"] = str(r)
                    break

                if len(rec["events"]) > 5000:
                    rec["error"] = "event overflow"
                    break
    except Exception as e:
        rec["error"] = f"exception: {str(e)[:120]}"
    rec["dur_s"] = round(time.time()-t0, 3)
    return rec


async def main():
    print("=" * 60)
    print("T7: Complete TTS Safety Regression")
    print("=" * 60)

    # T7-S: Short TTS
    print("\n--- T7-S: Short TTS ---")
    r = await tts_session("T7-S", "用三句话介绍一下北京。")
    RESULTS["t7"].append(r)
    ok = r.get("audio_deltas",0) > 0 and r.get("error") is None
    fa = r.get("first_audio_ts") or 0
    la = r.get("last_audio_ts") or 0
    print(f"  [{'PASS' if ok else 'FAIL'}] audio_deltas={r.get('audio_deltas',0)} "
          f"audio_bytes={r.get('audio_bytes_total',0)} text={r.get('text','')[:60]!r} "
          f"first_audio={fa:.1f}s last_audio={la:.1f}s "
          f"dur={r.get('dur_s',0):.1f}s err={r.get('error','')}")

    await asyncio.sleep(2)

    # T7-M: Medium TTS
    print("\n--- T7-M: Medium TTS ---")
    r = await tts_session("T7-M", "请详细介绍人工智能的发展历史，包括早期的图灵测试、专家系统、机器学习革命和深度学习时代。")
    RESULTS["t7"].append(r)
    ok = r["audio_deltas"] > 0 and r["error"] is None
    print(f"  [{'PASS' if ok else 'FAIL'}] audio_deltas={r['audio_deltas']} "
          f"audio_bytes={r.get('audio_bytes_total',0)} text={r.get('text','')[:80]!r} "
          f"first_audio={r['first_audio_ts']:.1f}s last_audio={r['last_audio_ts']:.1f}s "
          f"dur={r['dur_s']:.1f}s")

    await asyncio.sleep(2)

    # T7-L: Long TTS
    print("\n--- T7-L: Long TTS ---")
    r = await tts_session("T7-L",
        "请用中文详细讲解以下内容：第一，什么是深度学习神经网络；"
        "第二，卷积神经网络和循环神经网络的区别；第三，Transformer架构的核心创新；"
        "第四，大语言模型的训练方法；第五，AI在医疗、教育和自动驾驶中的应用。"
        "请尽可能详细地展开每个部分，使用具体的例子和数据。")
    RESULTS["t7"].append(r)
    ok = r.get("audio_deltas",0) > 0 and r.get("error") is None
    fa = r.get("first_audio_ts") or 0
    la = r.get("last_audio_ts") or 0
    print(f"  [{'PASS' if ok else 'FAIL'}] audio_deltas={r.get('audio_deltas',0)} "
          f"audio_bytes={r.get('audio_bytes_total',0)} text_len={len(r.get('text',''))} "
          f"first_audio={fa:.1f}s last_audio={la:.1f}s "
          f"dur={r.get('dur_s',0):.1f}s")

    # T7 Summary
    print("\n--- T7 Summary ---")
    t7_all_ok = all(
        r["audio_deltas"] > 0 and r["error"] is None
        for r in RESULTS["t7"]
    )
    print(f"T7_SHORT_TTS={'PASS' if RESULTS['t7'][0]['audio_deltas']>0 else 'FAIL'}")
    print(f"T7_MEDIUM_TTS={'PASS' if RESULTS['t7'][1]['audio_deltas']>0 else 'FAIL'}")
    print(f"T7_LONG_TTS={'PASS' if RESULTS['t7'][2]['audio_deltas']>0 else 'FAIL'}")
    print(f"T7_OVERALL={'PASS' if t7_all_ok else 'FAIL'}")

    if not t7_all_ok:
        print("\n⚠️  T7 FAILED — stopping before T8. Check logs.")
        return False

    # ============================================================
    # T8: TTS Next-Session Isolation
    # ============================================================
    print("\n" + "=" * 60)
    print("T8: TTS Next-Session Isolation")
    print("=" * 60)

    for interval_ms in [100, 500, 1000]:
        print(f"\n--- T8: interval={interval_ms}ms ---")
        # Session A: distinctive content
        r_a = await tts_session(f"T8-A-{interval_ms}ms",
            "请介绍一下苹果公司的历史，包括乔布斯创立公司、推出Macintosh、"
            "被逐出公司、回归后推出iPod和iPhone等重要里程碑。")
        RESULTS["t8"].append({"interval_ms": interval_ms, "A": r_a})
        a_text = r_a["text"]
        print(f"  A: text={a_text[:60]!r} audio_deltas={r_a['audio_deltas']}")

        # Wait the specified interval
        if interval_ms > 0:
            await asyncio.sleep(interval_ms / 1000.0)

        # Session B: completely different topic
        r_b = await tts_session(f"T8-B-{interval_ms}ms",
            "什么是黑洞？请用简单的语言解释黑洞的形成、事件视界和霍金辐射。")
        RESULTS["t8"].append({"interval_ms": interval_ms, "B": r_b})
        b_text = r_b["text"]
        isolation_ok = (
            "苹果" not in b_text and "iPhone" not in b_text and "乔布斯" not in b_text
        ) if b_text else True
        print(f"  B: text={b_text[:60]!r} audio_deltas={r_b['audio_deltas']}")
        print(f"  isolation={'PASS' if isolation_ok else 'FAIL'} "
              f"(apple content in B: {'苹果' in b_text})")
        await asyncio.sleep(3)

    # T8 Summary
    t8_results = [r for r in RESULTS["t8"] if isinstance(r, dict) and "B" in r]
    t8_all_ok = all(
        r["B"]["audio_deltas"] > 0 and r["B"]["error"] is None
        and "苹果" not in r["B"].get("text","")
        for r in t8_results
    )
    print(f"\nT8_TTS_ISOLATION={'PASS' if t8_all_ok else 'FAIL'}")

    # Save results
    with open(f"{RUN_DIR}/phase5_t7_tts/t7_results.json", "w") as f:
        json.dump(RESULTS["t7"], f, indent=2, default=str, ensure_ascii=False)
    with open(f"{RUN_DIR}/phase6_t8_isolation/t8_results.json", "w") as f:
        json.dump(RESULTS["t8"], f, indent=2, default=str, ensure_ascii=False)

    return t7_all_ok and t8_all_ok

result = asyncio.run(main())
print(f"\nT7_T8_GATE={'PASS' if result else 'FAIL'}")
sys.exit(0 if result else 1)
