#!/usr/bin/env python3
"""Isolate which modality breaks decode: vision vs audio, and audio length.

Cases (each fresh omni_init + sys prefill + user prefill + non-stream decode):
  I:  frame_15s only (no audio) + build_prompt
  AS: audio 3s only (no image) + build_prompt
  AL: audio 29.5s only (no image) + build_prompt
  IV: frame_15s + audio 3s + build_prompt
  IL: frame_15s + audio 29.5s + build_prompt
"""
import json, os, sys, time, urllib.request, subprocess, signal

REPO = "/workspace/llama.cpp-omni-f6"
SERVER = os.path.join(REPO, "build/bin/llama-omni-server")
MODEL = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
PORT = 18099
BASE = f"http://127.0.0.1:{PORT}"
LOG = "/tmp/f6_daily_omni/isolate2_srv.log"
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


def run_case(label, rid, audio, img, text):
    print(f"\n===== CASE {label} =====")
    r = post("/v1/stream/omni_init", {"media_type": 2, "use_tts": False}, timeout=300)
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
    print(f"  text={t[:220]!r}")
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
    print(f"QUESTION: {Q[:100]}")
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

    F = f"{PREP}/G_VTkkb34gw/frame_15s.jpg"
    S3 = f"{T7}/short_3s.wav"
    L29 = f"{PREP}/G_VTkkb34gw/audio_mono.wav"   # 29.5s
    try:
        i  = run_case("I  image-only + prompt", 1, "", F, P)
        as_ = run_case("AS audio-3s only + prompt", 2, S3, "", P)
        al = run_case("AL audio-29.5s only + prompt", 3, L29, "", P)
        iv = run_case("IV image + audio-3s + prompt", 4, S3, F, P)
        il = run_case("IL image + audio-29.5s + prompt", 5, L29, F, P)
        print("\n===== SUMMARY =====")
        for lbl, res in [("I", i), ("AS", as_), ("AL", al), ("IV", iv), ("IL", il)]:
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
