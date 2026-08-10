#!/usr/bin/env python3 -u
"""Phase 2 v2: LOCAL_BEST_EFFORT RTF — use response.done for full pipeline timing."""
import asyncio, json, base64, time, wave, io, struct, os, sys, subprocess, socket, statistics, tempfile

MODEL_PATH = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
SERVER_BIN = "/workspace/llama.cpp-omni-session-fix/build/bin/llama-omni-server"
VIDEO = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5/assets/omni_duplex1.mp4"
REF_AUDIO = "/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/cases/common/ref_audio/BH-Ref-HT-F224-Ref06_82_U001_话题_3_348s-355s.wav"
TARGET_SR = 16000; CHUNK_S = 1.0; OUTDIR = "/workspace/llama.cpp-omni-session-fix/benchmarks/results/formal"

def find_port(start=22610):
    for p in range(start, start+30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0: return p
    raise RuntimeError("no port")

def load_wav(path):
    with wave.open(path,'rb') as w:
        fr = w.readframes(w.getnframes()); sr, nc, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
    if sw==2: a=[s/32768.0 for s in struct.unpack(f'<{len(fr)//2}h',fr)]
    else: a=list(struct.unpack(f'<{len(fr)//4}f',fr))
    if nc>1: a=[sum(a[i:i+nc])/nc for i in range(0,len(a),nc)]
    if sr!=TARGET_SR:
        r=TARGET_SR/sr; a=[a[min(int(i/r),len(a)-1)] for i in range(int(len(a)*r))]
    return a

def extract_audio(video_path):
    with tempfile.NamedTemporaryFile(suffix=".wav",delete=False) as t: wp=t.name
    subprocess.run(["ffmpeg","-y","-i",video_path,"-ac","1","-ar",str(TARGET_SR),"-f","wav",wp],capture_output=True)
    a=load_wav(wp); os.unlink(wp); return a

def chunk_b64(chunk):
    i16=[max(-32768,min(32767,int(s*32767))) for s in chunk]
    b=io.BytesIO(); w=wave.open(b,'wb'); w.setnchannels(1);w.setsampwidth(2);w.setframerate(TARGET_SR)
    w.writeframes(struct.pack(f'<{len(i16)}h',*i16)); w.close()
    return base64.b64encode(b.getvalue()).decode()

async def run(port, pipeline):
    audio=extract_audio(VIDEO); cs=int(CHUNK_S*TARGET_SR); tc=len(audio)//cs
    ref=load_wav(REF_AUDIO) if os.path.exists(REF_AUDIO) else [0.0]*int(10*TARGET_SR)
    ref_b64=chunk_b64(ref[:int(10*TARGET_SR)])

    ws=await asyncio.wait_for(__import__('websockets').connect(
        f"ws://127.0.0.1:{port}/backend",max_size=128*1024*1024,ping_interval=None,close_timeout=30),30)
    await ws.send(json.dumps({"type":"session.init","payload":{
        "mode":"full_duplex","use_tts":True,"ref_audio":ref_b64,"config":{"force_listen_count":0}}}))
    while True:
        evt=json.loads(await asyncio.wait_for(ws.recv(),timeout=60))
        if evt.get('type')=='session.created': break

    results=[]
    for i in range(tc):
        start=i*cs; c=audio[start:start+cs]
        if len(c)<cs: c=c+[0.0]*(cs-len(c))
        t_send=time.perf_counter_ns()
        await ws.send(json.dumps({"type":"input.append","input":{"audio":chunk_b64(c),"streaming":True,"generation":{"max_new_tokens":26}}}))

        state="OTHER"; t_last_audio=None; t_done=None; t_first_audio=None; audio_count=0; has_listen=False; has_text=False
        while True:
            evt=json.loads(await asyncio.wait_for(ws.recv(),timeout=60))
            et=evt.get('type',''); kind=evt.get('kind','')
            if et=='response.output.delta':
                if kind=='listen': has_listen=True; break
                elif kind=='audio':
                    if t_first_audio is None: t_first_audio=time.perf_counter_ns()
                    t_last_audio=time.perf_counter_ns(); audio_count+=1
                elif kind=='text': has_text=True
            elif et=='response.done':
                t_done=time.perf_counter_ns()
                if evt.get('text','').strip(): has_text=True
                break

        if has_listen and audio_count>0: state="SPEAK_TAIL"
        elif audio_count>0 and not has_listen: state="SPEAK_GENERATION"
        elif has_listen and audio_count==0: state="LISTEN"

        results.append({'chunk':i,'state':state,'audio_count':audio_count,'has_text':has_text,
            'wall_first_audio_ms':(t_first_audio-t_send)/1e6 if t_first_audio else None,
            'wall_last_audio_ms':(t_last_audio-t_send)/1e6 if t_last_audio else None,
            'wall_done_ms':(t_done-t_send)/1e6 if t_done else None})

        if i%10==0 or i==tc-1:
            sg=[r for r in results if r['state']=='SPEAK_GENERATION']
            l=[r for r in results if r['state']=='LISTEN']
            dw=[r['wall_done_ms'] for r in sg if r['wall_done_ms']]
            law=[r['wall_last_audio_ms'] for r in sg if r['wall_last_audio_ms']]
            print(f"  [{i+1}/{tc}] SPEAK={len(sg)} LISTEN={len(l)} done_p50={statistics.median(dw):.0f}ms last_audio_p50={statistics.median(law):.0f}ms" if dw else f"  [{i+1}/{tc}] SPEAK={len(sg)} LISTEN={len(l)}")

    await ws.close()
    return results

async def main():
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument("--pipeline",type=int,default=1,choices=[0,1]); args=ap.parse_args()
    os.makedirs(OUTDIR,exist_ok=True)

    port=find_port(22610)
    env=os.environ.copy()
    env.update({"OMNI_T2W_DEVICE":"cann-flow-only","OMNI_T2W_PIPELINE_OVERLAP":str(args.pipeline),"OMNI_T2W_DRAIN_TIMEOUT_MS":"5000","OMNI_T2W_QUEUE_DIAG":"1"})

    sl=open(f"/tmp/p2v2_server.log","wb")
    proc=subprocess.Popen([SERVER_BIN,"-m",MODEL_PATH,"--host","127.0.0.1","--port",str(port),
        "-ngl","999","--device","CANN0","-c","4096","-b","512","-ub","512","--split-mode","layer","-fa","off","-n","128","-t","4"],
        stdout=subprocess.DEVNULL,stderr=sl,env=env)

    import urllib.request
    for i in range(180):
        if proc.poll() is not None: print(f"Died rc={proc.returncode}"); return 1
        try:
            if json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/health",timeout=2).read()).get('status')=='ok': break
        except: pass
        time.sleep(2)
    print(f"Server ready on {port}")

    results=await run(port,args.pipeline)

    proc.send_signal(subprocess.signal.SIGTERM)
    try: proc.communicate(timeout=30)
    except: proc.kill(); proc.communicate(timeout=5)
    sl.close()

    # Analyze
    sg=[r for r in results if r['state']=='SPEAK_GENERATION']
    ln=[r for r in results if r['state']=='LISTEN']
    st=[r for r in results if r['state']=='SPEAK_TAIL']

    # Use wall_done_ms (response.done) as the full pipeline completion marker
    done_walls=[r['wall_done_ms'] for r in sg if r['wall_done_ms']]
    last_audio_walls=[r['wall_last_audio_ms'] for r in sg if r['wall_last_audio_ms']]
    first_audio_walls=[r['wall_first_audio_ms'] for r in sg if r['wall_first_audio_ms']]

    # RTF = wall_ms / audio_duration_ms (1000ms per chunk for full pipeline)
    # Actually: each chunk produces multiple audio outputs
    # SP→WAV RTF = mean wall / mean audio_duration
    audio_per_chunk=[r['audio_count']*1.0 for r in sg]  # ~1s per WAV
    total_audio_s=sum(audio_per_chunk) if audio_per_chunk else 0
    total_wall_ms=sum(done_walls) if done_walls else 0

    # Server-side timing from log
    with open("/tmp/p2v2_server.log") as f: slog=f.read()
    import re
    svc_times=[int(m.group(1))/1000 for m in re.finditer(r'service_us=(\d+)',slog)]

    print(""); print("="*60)
    print("PHASE 2 v2: LOCAL_BEST_EFFORT SPEAK→WAV RTF")
    print("="*60)
    print(f"Chunks: {len(results)} total ({len(sg)} SPEAK, {len(ln)} LISTEN, {len(st)} TAIL)")
    print(f"Pipeline: {'ON' if args.pipeline else 'OFF'}")
    print(f"")
    print(f"Client-side (response.done wall time):")
    if done_walls:
        dw=sorted(done_walls); n=len(dw)
        print(f"  wall p50={dw[n//2]:.0f}ms p90={dw[int(n*0.9)]:.0f}ms mean={sum(dw)/n:.0f}ms")
        print(f"  total_wall={total_wall_ms:.0f}ms total_audio≈{total_audio_s:.0f}s")
        rtf_val=(total_wall_ms/1000)/total_audio_s if total_audio_s>0 else 0
        print(f"  LOCAL_BEST_EFFORT_SPEAK_TO_WAV_RTF = {rtf_val:.3f}")
    print(f"")
    print(f"Client-side (last_audio wall time):")
    if last_audio_walls:
        lw=sorted(last_audio_walls); n=len(lw)
        print(f"  wall p50={lw[n//2]:.0f}ms p90={lw[int(n*0.9)]:.0f}ms")
    print(f"")
    print(f"Server-side per-window T2W service time:")
    if svc_times:
        sv=sorted(svc_times); n=len(sv)
        print(f"  n={n} p50={sv[n//2]:.1f}ms p90={sv[int(n*0.9)]:.1f}ms mean={sum(sv)/n:.1f}ms")
        # Per-window RTF = service_ms / 1000 (each window = 1s audio)
        print(f"  LOCAL_BEST_EFFORT_PER_WINDOW_RTF(p50) = {sv[n//2]/1000:.3f}")
    print(f"")
    print(f"Official references (comparison only):")
    print(f"  ALL_CHUNK_RTF = 0.618")
    print(f"  SPEAK_TO_WAV_RTF = 1.087")
    print(f"OFFICIAL_REFERENCE_COMPARABILITY = NOT_PROVEN")

    # Save
    ts=time.strftime("%Y%m%d_%H%M%S")
    out={"phase":"2_v2","pipeline":args.pipeline,"binary_sha":"768614ab","git":"051e993",
         "states":{"speak_gen":len(sg),"listen":len(ln),"speak_tail":len(st)},
         "client_done_walls":done_walls,"server_svc_times":svc_times,"total_audio_s":total_audio_s}
    with open(f"{OUTDIR}/phase2_v2_{ts}.json","w") as f: json.dump(out,f,indent=2)
    print(f"Saved: {OUTDIR}/phase2_v2_{ts}.json")

asyncio.run(main())
