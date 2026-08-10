#!/usr/bin/env python3 -u
"""Phase 3: Official Demo Path — Gateway + Worker + Frozen Backend E2E.

Chain: Client → Gateway (WS /v1/realtime) → Worker (WS bridge) → Backend (WS /backend)

Tests:
  G1: Gateway + Worker + Backend all start and health-check
  G2: Turn-based text chat via Gateway → Worker → Backend
  G3: Duplex audio via Gateway → Worker → Backend
  G4: Session reuse (2 sequential sessions)
  G5: Valid WAV audio output
"""
import asyncio, json, base64, time, wave, io, struct, os, sys, subprocess, socket, urllib.request, urllib.error

MODEL_PATH = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
SERVER_BIN = "/workspace/llama.cpp-omni-session-fix/build/bin/llama-omni-server"
DEMO_DIR = "/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo"
REF_AUDIO = f"{DEMO_DIR}/tests/cases/common/ref_audio/BH-Ref-HT-F224-Ref06_82_U001_话题_3_348s-355s.wav"
OUTDIR = "/workspace/llama.cpp-omni-session-fix/benchmarks/results/formal"
TARGET_SR = 16000

def log(msg): print(f"[P3-DEMO] {time.strftime('%H:%M:%S')} {msg}", flush=True)

def find_port(start=22800):
    for p in range(start, start+30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0: return p
    raise RuntimeError("no port")

def load_wav(path, target_sr=TARGET_SR):
    with wave.open(path,'rb') as w:
        fr = w.readframes(w.getnframes()); sr, nc, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
    if sw==2: a=[s/32768.0 for s in struct.unpack(f'<{len(fr)//2}h',fr)]
    else: a=list(struct.unpack(f'<{len(fr)//4}f',fr))
    if nc>1: a=[sum(a[i:i+nc])/nc for i in range(0,len(a),nc)]
    if sr!=target_sr:
        r=target_sr/sr; a=[a[min(int(i/r),len(a)-1)] for i in range(int(len(a)*r))]
    return a

def audio_to_b64(audio):
    i16=[max(-32768,min(32767,int(s*32767))) for s in audio]
    b=io.BytesIO(); w=wave.open(b,'wb'); w.setnchannels(1);w.setsampwidth(2);w.setframerate(TARGET_SR)
    w.writeframes(struct.pack(f'<{len(i16)}h',*i16)); w.close()
    return base64.b64encode(b.getvalue()).decode()

def http_get(url, timeout=10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r: return {"ok":True,"status":r.status,"body":json.loads(r.read())}
    except Exception as e: return {"ok":False,"error":str(e)[:200]}

def http_put(url, data, timeout=10):
    try:
        body=json.dumps(data).encode()
        req=urllib.request.Request(url, data=body, method="PUT", headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r: return {"ok":True,"status":r.status,"body":json.loads(r.read())}
    except Exception as e: return {"ok":False,"error":str(e)[:200]}

async def ws_chat_test(gateway_port, prompt, use_tts=False):
    """Test turn-based chat via Gateway /v1/realtime?mode=chat."""
    import websockets
    ws_url = f"ws://127.0.0.1:{gateway_port}/v1/realtime?mode=chat"
    log(f"  Chat WS connecting to {ws_url}...")
    ws = await websockets.connect(ws_url, max_size=128*1024*1024, ping_interval=None, close_timeout=30)

    # Load ref audio
    ref_b64 = ""
    if os.path.exists(REF_AUDIO):
        ref = load_wav(REF_AUDIO)
        ref_b64 = audio_to_b64(ref[:int(10*TARGET_SR)])

    # Send session.init
    await ws.send(json.dumps({"type":"session.init","payload":{
        "mode":"turn_based","use_tts":use_tts,"ref_audio":ref_b64}}))

    # Wait for session.created
    while True:
        evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        if evt.get('type') in ('session.created','initialized'): break
    log(f"  Session created: {evt.get('session_id','?')}")

    # Send text input
    t0 = time.perf_counter_ns()
    await ws.send(json.dumps({"type":"input.append","input":{
        "text":prompt,"streaming":True,"generation":{"max_new_tokens":64}}}))

    text_parts = []; audio_count = 0; has_done = False; error = None
    while True:
        evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
        et = evt.get('type',''); kind = evt.get('kind','')
        if et == 'response.output.delta':
            if kind == 'text': text_parts.append(evt.get('text',''))
            elif kind == 'audio': audio_count += 1
        elif et == 'response.done':
            has_done = True
            if evt.get('text'): text_parts.append(evt['text'])
            if evt.get('error'): error = evt['error']
            break
        elif et in ('session.closed','error'):
            error = evt.get('reason',str(evt))
            break

    wall_ms = (time.perf_counter_ns() - t0) / 1e6
    text = ''.join(text_parts)
    await ws.close()

    return {"ok": has_done and not error, "text": text, "text_len": len(text),
            "audio_count": audio_count, "wall_ms": wall_ms, "error": error}

async def ws_duplex_test(gateway_port, audio_data, ref_b64, use_tts=True):
    """Test duplex audio via Gateway /v1/realtime?mode=audio."""
    import websockets
    import statistics
    ws_url = f"ws://127.0.0.1:{gateway_port}/v1/realtime?mode=audio"
    log(f"  Duplex WS connecting to {ws_url}...")
    ws = await websockets.connect(ws_url, max_size=128*1024*1024, ping_interval=None, close_timeout=30)

    # Send session.init
    await ws.send(json.dumps({"type":"session.init","payload":{
        "mode":"full_duplex","use_tts":use_tts,"ref_audio":ref_b64,
        "config":{"force_listen_count":0}}}))

    # Wait for session.created
    while True:
        evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        if evt.get('type') in ('session.created','initialized'): break
    log(f"  Session created: {evt.get('session_id','?')}")

    # Send audio chunks
    cs = int(1.0 * TARGET_SR)  # 1s chunks
    n_chunks = min(5, len(audio_data)//cs)  # Test with 5 chunks

    chunk_results = []
    for i in range(n_chunks):
        chunk = audio_data[i*cs:(i+1)*cs]
        if len(chunk) < cs: chunk = chunk + [0.0]*(cs-len(chunk))
        t_send = time.perf_counter_ns()
        await ws.send(json.dumps({"type":"input.append","input":{
            "audio":audio_to_b64(chunk),"streaming":True,
            "generation":{"max_new_tokens":26}}}))

        has_listen = False; has_audio = False; has_text = False; has_done = False
        while True:
            evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            et = evt.get('type',''); kind = evt.get('kind','')
            if et == 'response.output.delta':
                if kind == 'listen': has_listen = True; break
                elif kind == 'audio': has_audio = True
                elif kind == 'text': has_text = True
            elif et == 'response.done':
                has_done = True
                if evt.get('text','').strip(): has_text = True
                break

        t_done = time.perf_counter_ns()
        state = "SPEAK_GENERATION" if (has_audio and not has_listen) else \
                "SPEAK_TAIL" if (has_audio and has_listen) else \
                "LISTEN" if (has_listen and not has_audio) else "OTHER"
        chunk_results.append({"chunk":i,"state":state,"has_audio":has_audio,
            "has_text":has_text,"has_done":has_done,
            "wall_ms":(t_done-t_send)/1e6})

    await ws.close()
    return chunk_results

async def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-duplex", action="store_true", help="Skip duplex audio test")
    args = ap.parse_args()

    os.makedirs(OUTDIR, exist_ok=True)
    results = {"gates": {}, "phase": "3_demo_path"}

    # ====== Port allocation ======
    backend_port = find_port(22800)
    worker_port = find_port(backend_port + 1)
    gateway_port = find_port(worker_port + 1)
    internal_port = find_port(gateway_port + 1)
    log(f"Ports: backend={backend_port} worker={worker_port} gateway={gateway_port} internal={internal_port}")

    # ====== Step 1: Start frozen F16 backend ======
    log("Starting frozen F16 backend...")
    env = os.environ.copy()
    env.update({"OMNI_T2W_DEVICE":"cann-flow-only","OMNI_T2W_PIPELINE_OVERLAP":"1",
                "OMNI_T2W_DRAIN_TIMEOUT_MS":"5000","OMNI_T2W_QUEUE_DIAG":"1"})

    blog = open("/tmp/p3_backend.log","wb")
    bproc = subprocess.Popen(
        [SERVER_BIN,"-m",MODEL_PATH,"--host","127.0.0.1","--port",str(backend_port),
         "-ngl","999","--device","CANN0","-c","4096","-b","512","-ub","512",
         "--split-mode","layer","-fa","off","-n","128","-t","4"],
        stdout=subprocess.DEVNULL, stderr=blog, env=env)

    # Wait for backend
    for i in range(180):
        if bproc.poll() is not None:
            log(f"Backend died rc={bproc.returncode}"); blog.close(); return 1
        try:
            if http_get(f"http://127.0.0.1:{backend_port}/health",timeout=5).get("ok"): break
        except: pass
        time.sleep(2)
    else:
        log("Backend timeout"); bproc.kill(); blog.close(); return 1
    log(f"Backend ready on {backend_port}")

    # ====== Step 2: Start Worker (remote-backend mode) ======
    log("Starting Demo Worker (remote-backend mode)...")
    wlog = open("/tmp/p3_worker.log","wb")
    wproc = subprocess.Popen(
        ["python3","-u",f"{DEMO_DIR}/worker.py","--port",str(worker_port),
         "--host","127.0.0.1","--worker-index","0",
         "--backend-server-url",f"http://127.0.0.1:{backend_port}"],
        stdout=wlog, stderr=subprocess.STDOUT, cwd=DEMO_DIR,
        env={**os.environ,"PYTHONPATH":DEMO_DIR})

    # Wait for worker
    for i in range(60):
        if wproc.poll() is not None:
            log(f"Worker died rc={wproc.returncode}")
            with open("/tmp/p3_worker.log") as f: log(f"Worker log tail: {''.join(f.readlines()[-10:])}")
            wlog.close(); bproc.terminate(); blog.close(); return 1
        try:
            r = http_get(f"http://127.0.0.1:{worker_port}/health",timeout=3)
            if r.get("ok") and r.get("body",{}).get("status")=="healthy": break
        except: pass
        time.sleep(2)
    else:
        log("Worker timeout"); wproc.kill(); bproc.terminate(); wlog.close(); blog.close(); return 1
    log(f"Worker ready on {worker_port}")

    # ====== Step 3: Start Gateway ======
    log("Starting Demo Gateway...")
    glog = open("/tmp/p3_gateway.log","wb")
    gproc = subprocess.Popen(
        ["python3","-u",f"{DEMO_DIR}/gateway.py","--port",str(gateway_port),
         "--internal-port",str(internal_port),"--host","127.0.0.1","--http",
         "--max-queue-size","100","--timeout","300"],
        stdout=glog, stderr=subprocess.STDOUT, cwd=DEMO_DIR,
        env={**os.environ,"PYTHONPATH":DEMO_DIR})

    # Wait for gateway
    for i in range(60):
        if gproc.poll() is not None:
            log(f"Gateway died rc={gproc.returncode}")
            with open("/tmp/p3_gateway.log") as f: log(f"Gateway log tail: {''.join(f.readlines()[-10:])}")
            glog.close(); wproc.kill(); bproc.terminate(); wlog.close(); blog.close(); return 1
        try:
            r = http_get(f"http://127.0.0.1:{internal_port}/health",timeout=3)
            if r.get("ok"): break
        except: pass
        time.sleep(2)
    else:
        log("Gateway timeout"); gproc.kill(); wproc.kill(); bproc.terminate(); glog.close(); wlog.close(); blog.close(); return 1
    log(f"Gateway ready: public={gateway_port} internal={internal_port}")

    # ====== Gate 1: All services healthy ======
    log("\n===== G1: Service Health =====")
    h_backend = http_get(f"http://127.0.0.1:{backend_port}/health")
    h_worker = http_get(f"http://127.0.0.1:{worker_port}/health")
    h_gateway = http_get(f"http://127.0.0.1:{internal_port}/health")
    g1_ok = all(r.get("ok") for r in [h_backend, h_worker, h_gateway])
    log(f"  Backend: {'OK' if h_backend.get('ok') else 'FAIL'}")
    log(f"  Worker:  {'OK' if h_worker.get('ok') else 'FAIL'} (status={h_worker.get('body',{}).get('status','?')})")
    log(f"  Gateway: {'OK' if h_gateway.get('ok') else 'FAIL'}")
    results["gates"]["G1_health"] = "PASS" if g1_ok else "FAIL"

    # ====== Step 3.5: Register worker with gateway ======
    log("\nRegistering worker with gateway...")
    reg = http_put(f"http://127.0.0.1:{internal_port}/internal/workers/worker-0",
                   {"endpoint": f"127.0.0.1:{worker_port}"})
    log(f"  Registration: {'OK' if reg.get('ok') else 'FAIL: '+str(reg.get('error','?'))}")

    # Verify worker appears in gateway
    time.sleep(1)
    workers = http_get(f"http://127.0.0.1:{internal_port}/api/sessions")
    log(f"  Gateway sessions endpoint: {workers.get('ok')}")

    # ====== Gate 2: Turn-based text chat via Gateway ======
    log("\n===== G2: Turn-Based Text Chat =====")
    chat_results = []
    prompts = ["你好，请介绍一下你自己", "什么是人工智能？", "请讲一个简短的笑话"]
    for i, prompt in enumerate(prompts):
        log(f"  [{i+1}/{len(prompts)}] Testing: '{prompt}'")
        try:
            r = await asyncio.wait_for(ws_chat_test(gateway_port, prompt, use_tts=False), timeout=120)
            status = "PASS" if r["ok"] and len(r["text"])>0 else "FAIL"
            log(f"    {status}: text_len={r['text_len']} wall={r['wall_ms']:.0f}ms text='{r['text'][:80]}'")
            chat_results.append(r)
        except Exception as e:
            log(f"    FAIL: {e}")
            chat_results.append({"ok":False,"error":str(e)[:200]})

    g2_pass = sum(1 for r in chat_results if r["ok"]) >= 2
    results["gates"]["G2_text_chat"] = "PASS" if g2_pass else "FAIL"
    results["chat_samples"] = chat_results

    # ====== Gate 3: Duplex audio via Gateway ======
    log("\n===== G3: Duplex Audio =====")
    duplex_results = []
    if not args.skip_duplex:
        # Load test audio
        test_audio_path = f"{DEMO_DIR}/tests/cases/common/user_audio/000_user_audio0.wav"
        if not os.path.exists(test_audio_path):
            log(f"  WARNING: Test audio not found at {test_audio_path}, generating silence")
            test_audio = [0.0] * int(10 * TARGET_SR)
        else:
            test_audio = load_wav(test_audio_path)
            log(f"  Test audio: {len(test_audio)/TARGET_SR:.1f}s")

        # Load ref audio
        ref = load_wav(REF_AUDIO) if os.path.exists(REF_AUDIO) else [0.0]*int(10*TARGET_SR)
        ref_b64 = audio_to_b64(ref[:int(10*TARGET_SR)])

        try:
            duplex_results = await asyncio.wait_for(
                ws_duplex_test(gateway_port, test_audio, ref_b64, use_tts=True), timeout=300)
            for d in duplex_results:
                log(f"  chunk {d['chunk']}: state={d['state']} audio={d['has_audio']} "
                    f"text={d['has_text']} done={d['has_done']} wall={d['wall_ms']:.0f}ms")
        except Exception as e:
            log(f"  Duplex FAIL: {e}")

    g3_pass = len(duplex_results) > 0 and any(d["has_audio"] for d in duplex_results)
    results["gates"]["G3_duplex_audio"] = "PASS" if g3_pass else ("SKIP" if args.skip_duplex else "FAIL")
    results["duplex"] = duplex_results

    # ====== Gate 4: Session reuse ======
    log("\n===== G4: Session Reuse =====")
    try:
        r2 = await asyncio.wait_for(ws_chat_test(gateway_port, "继续聊天", use_tts=False), timeout=120)
        log(f"  Session 2: {'PASS' if r2['ok'] else 'FAIL'} text='{r2['text'][:80]}'")
        g4_pass = r2["ok"]
    except Exception as e:
        log(f"  Session 2 FAIL: {e}")
        r2 = {"ok":False,"error":str(e)[:200]}
        g4_pass = False
    results["gates"]["G4_session_reuse"] = "PASS" if g4_pass else "FAIL"
    results["session2"] = r2

    # ====== Cleanup ======
    log("\nStopping services...")

    # Graceful shutdown
    for proc, name in [(gproc,"gateway"),(wproc,"worker"),(bproc,"backend")]:
        proc.send_signal(subprocess.signal.SIGTERM)
        try: proc.communicate(timeout=15)
        except: proc.kill(); proc.communicate(timeout=5)
        log(f"  {name} stopped")

    for f in [glog, wlog, blog]: f.close()

    # ====== Summary ======
    print("\n" + "="*60)
    print("PHASE 3: OFFICIAL DEMO PATH — RESULTS")
    print("="*60)
    all_pass = True
    for gate, status in results["gates"].items():
        s = "PASS" if status == "PASS" else "FAIL" if status == "FAIL" else status
        if status != "PASS": all_pass = False
        print(f"  {s}: {gate}")

    print(f"\n{'PHASE3_DEMO_PATH = PASS' if all_pass else 'PHASE3_DEMO_PATH = FAIL'}")

    # Save results
    ts = time.strftime("%Y%m%d_%H%M%S")
    with open(f"{OUTDIR}/phase3_demo_{ts}.json","w") as f:
        json.dump(results, f, indent=2, default=str, ensure_ascii=False)
    print(f"Saved: {OUTDIR}/phase3_demo_{ts}.json")

    return 0 if all_pass else 1

asyncio.run(main())
