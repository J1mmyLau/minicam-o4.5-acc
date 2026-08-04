#!/usr/bin/env python3
"""Comprehensive pilot-input verification at deterministic sampling (temp 0.2):
  I:   image-only
  IV3: image + short_3s
  IV24: image + trim_24s   (within whisper encoder limit)
  IVL: image + 29.5s        (actual Daily-Omni audio)
  AL:  audio-29.5s only     (control)
"""
import json, os, sys, time, urllib.request, subprocess, signal

REPO = "/workspace/llama.cpp-omni-f6"
SERVER = os.path.join(REPO, "build/bin/llama-omni-server")
MODEL = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
PORT = 18099
BASE = f"http://127.0.0.1:{PORT}"
LOG = "/tmp/f6_daily_omni/isolate7_srv.log"
T7 = "/tmp/f6_t7/prep"
PREP = "/tmp/f6_daily_omni"
QA = "/workspace/benchmarks/Daily-Omni/qa.json"
SAMP_ARGS = ["--temp", "0.2", "--top-k", "20", "--repeat-penalty", "1.15"]

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


def build_prompt(question, choices):
    return (
        "Your task is to accurately answer multiple-choice questions based on the given video. "
        "Select the single most accurate answer from the given choices. "
        "Your answer should be a capital letter representing your choice: A, B, C, or D. "
        "Don't generate any other text.\n\n"
        f"Given the video, answer the question below.\nQuestion: {question}\nChoices: {choices}"
    )


def run_case(label, rid, audio, img):
    r = post("/v1/stream/omni_init", {"media_type": 2, "use_tts": False}, timeout=300)
    if not r.get("success"):
        print(f"{label}: omni_init FAILED"); return None
    r = post("/v1/stream/prefill", {"audio_path_prefix": "", "cnt": 0, "text": ""})
    r = post("/v1/stream/prefill", {"audio_path_prefix": audio, "img_path_prefix": img,
                                    "cnt": 1, "text": P, "max_slice_nums": 1})
    if not r.get("success"):
        print(f"{label}: prefill FAILED"); return None
    d = post("/v1/stream/decode", {"stream": False, "round_idx": rid,
                                   "max_tokens": 256, "wall_timeout_ms": 120000}, timeout=400)
    t = d.get("text", "") if isinstance(d, dict) else ""
    if t.startswith("?" * 8):
        tag = "?×N"
    elif not t.strip():
        tag = "EMPTY"
    elif t.strip().replace("\n", "").replace(" ", "") == "":
        tag = "WS_ONLY"
    else:
        tag = "REAL"
    print(f"{label}: tag={tag} ntok={d.get('generated_token_count')} stop={d.get('stop_reason')} text={t[:60]!r}")
    return (tag, d.get("generated_token_count"), d.get("stop_reason"), t[:120])


def main():
    global P
    qa = json.load(open(QA))
    it = next(d for d in qa if d.get("video_id") == "G_VTkkb34gw")
    P = build_prompt(it["Question"], it["Choice"])
    print("Q:", it["Question"][:80])
    print("Expected answer:", it.get("Answer"))

    logf = open(LOG, "w")
    cmd = ["stdbuf", "-oL", "-eL", SERVER, "-m", MODEL, "-ngl", "999",
           "--device", "CANN0", "-c", "4096", "-b", "512", "-ub", "512",
           "--split-mode", "layer", "--port", str(PORT)] + SAMP_ARGS
    proc = subprocess.Popen(cmd, env=ENV, stdout=logf, stderr=subprocess.STDOUT, cwd=REPO,
                            preexec_fn=os.setsid)
    for _ in range(600):
        if proc.poll() is not None:
            print("server exited early"); return 1
        if health_ok():
            time.sleep(2); break
        time.sleep(2)

    F = f"{PREP}/G_VTkkb34gw/frame_15s.jpg"
    S3 = f"{T7}/short_3s.wav"
    T24 = f"{PREP}/trims/trim_24s.wav"
    L29 = f"{PREP}/G_VTkkb34gw/audio_mono.wav"
    results = []
    try:
        results.append(("I",   run_case("I   image-only", 1, "", F)))
        results.append(("IV3", run_case("IV3 image+3s", 2, S3, F)))
        results.append(("IV24", run_case("IV24 image+24s", 3, T24, F)))
        results.append(("IVL", run_case("IVL image+29.5s", 4, L29, F)))
        results.append(("AL",  run_case("AL audio-29.5s-only", 5, L29, "")))
        print("\n===== SUMMARY =====")
        for lbl, r in results:
            if r:
                print(f"{lbl}: {r[0]} ntok={r[1]} text={r[3][:60]!r}")
            else:
                print(f"{lbl}: FAIL")
        json.dump([{"case": lbl, "tag": r[0], "ntok": r[1], "stop": r[2], "text": r[3]}
                   for lbl, r in results if r],
                  open(f"{PREP}/isolate7.json", "w"), ensure_ascii=False, indent=1)
    finally:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
