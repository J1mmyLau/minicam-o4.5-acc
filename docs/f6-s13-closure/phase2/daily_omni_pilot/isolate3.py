#!/usr/bin/env python3
"""Does media_type=1 (audio mode) produce real text from user audio, unlike media_type=2?

Cases:
  M1F: media_type=1, use_tts=False, short_3s audio + prompt
  M1T: media_type=1, use_tts=True,  short_3s audio + prompt
  M2F: media_type=2, use_tts=False, short_3s audio + prompt (control)
  M1F29: media_type=1, use_tts=False, 29.5s audio + prompt
"""
import json, os, sys, time, urllib.request, subprocess, signal

REPO = "/workspace/llama.cpp-omni-f6"
SERVER = os.path.join(REPO, "build/bin/llama-omni-server")
MODEL = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
PORT = 18099
BASE = f"http://127.0.0.1:{PORT}"
LOG = "/tmp/f6_daily_omni/isolate3_srv.log"
T7 = "/tmp/f6_t7/prep"
PREP = "/tmp/f6_daily_omni"
QA = "/workspace/benchmarks/Daily-Omni/qa.json"

ENV = dict(os.environ)
ENV.update({"OMNI_KV_CACHE_REUSE": "1", "OMNI_T2W_DEVICE": "cann-flow-only",
            "OMNI_VOC_DEVICE": "gpu", "ASCEND_RT_VISIBLE_DEVICES": "0"})


def health_ok():
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=3) as r:
            return json.loads(r.read().decode()).get("status") == "ok"
    except Exception:
        return False


def post(path, payload, timeout=400):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"http": e.code, "error": e.read().decode()[:200]}
    except Exception as e:
        return {"error": str(e)}


def run_case(label, rid, mt, utts, audio, img, text):
    print(f"\n===== CASE {label} (media_type={mt}, use_tts={utts}) =====")
    r = post("/v1/stream/omni_init", {"media_type": mt, "use_tts": utts}, timeout=300)
    if not r.get("success"):
        print("  omni_init FAILED:", json.dumps(r)[:150]); return None
    r = post("/v1/stream/prefill", {"audio_path_prefix": "", "cnt": 0, "text": ""})
    r = post("/v1/stream/prefill", {"audio_path_prefix": audio, "img_path_prefix": img,
                                    "cnt": 1, "text": text, "max_slice_nums": 1})
    if not r.get("success"):
        print("  prefill FAILED:", json.dumps(r)[:150]); return None
    t0 = time.time()
    d = post("/v1/stream/decode", {"stream": False, "round_idx": rid,
                                   "max_tokens": 256, "wall_timeout_ms": 120000}, timeout=400)
    wall = round(time.time() - t0, 1)
    t = d.get("text", "") if isinstance(d, dict) else ""
    print(f"  http={d.get('http')} ok={d.get('success')} stop={d.get('stop_reason')} "
          f"ntok={d.get('generated_token_count')} wall={wall}s text_len={len(t)}")
    print(f"  text={t[:200]!r}")
    return t


def build_prompt(question, choices):
    return (
        "Your task is to accurately answer multiple-choice questions based on the given video. "
        "Select the single most accurate answer from the given choices. "
        "Your answer should be a capital letter representing your choice: A, B, C, or D. "
        "Don't generate any other text.\n\n"
        f"Given the video, answer the question below.\nQuestion: {question}\nChoices: {choices}"
    )


def main():
    qa = json.load(open(QA))
    it = next(d for d in qa if d.get("video_id") == "G_VTkkb34gw")
    Q, CH = it["Question"], it["Choice"]
    P = build_prompt(Q, CH)

    logf = open(LOG, "w")
    proc = subprocess.Popen(["stdbuf", "-oL", "-eL", SERVER, "-m", MODEL, "-ngl", "999",
                             "--device", "CANN0", "-c", "4096", "-b", "512", "-ub", "512",
                             "--split-mode", "layer", "--port", str(PORT)],
                            env=ENV, stdout=logf, stderr=subprocess.STDOUT, cwd=REPO,
                            preexec_fn=os.setsid)
    for _ in range(600):
        if proc.poll() is not None:
            print("server exited early"); return 1
        if health_ok():
            time.sleep(2); break
        time.sleep(2)

    S3 = f"{T7}/short_3s.wav"
    L29 = f"{PREP}/G_VTkkb34gw/audio_mono.wav"
    try:
        m1f  = run_case("M1F media1 no-tts 3s", 1, 1, False, S3, "", P)
        m1t  = run_case("M1T media1 tts 3s", 2, 1, True, S3, "", P)
        m2f  = run_case("M2F media2 no-tts 3s", 3, 2, False, S3, "", P)
        m1f29= run_case("M1F29 media1 no-tts 29.5s", 4, 1, False, L29, "", P)
        print("\n===== SUMMARY =====")
        for lbl, res in [("M1F", m1f), ("M1T", m1t), ("M2F", m2f), ("M1F29", m1f29)]:
            if res is None:
                tag = "FAIL"
            elif not res:
                tag = "EMPTY"
            elif res.startswith("?" * 8):
                tag = "?×N"
            elif res.strip().replace("\n", "").replace(" ", "") == "":
                tag = "WS_ONLY"
            else:
                tag = "REAL"
            print(f"{lbl}: {tag} len={len(res) if res else 0}")
    finally:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
