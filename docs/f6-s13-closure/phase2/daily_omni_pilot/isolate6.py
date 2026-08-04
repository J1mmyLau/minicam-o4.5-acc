#!/usr/bin/env python3
"""Test sampling overrides: does low temp + repeat penalty fix image+audio think-loop?
media_type=2, non-TTS. Cases: image+audio-3s (4 reps), audio-3s (2 reps).
Launches server with --temp/--top-k/--repeat-penalty overrides."""
import json, os, sys, time, urllib.request, subprocess, signal

REPO = "/workspace/llama.cpp-omni-f6"
SERVER = os.path.join(REPO, "build/bin/llama-omni-server")
MODEL = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
PORT = 18099
BASE = f"http://127.0.0.1:{PORT}"
LOG = "/tmp/f6_daily_omni/isolate6_srv.log"
T7 = "/tmp/f6_t7/prep"
PREP = "/tmp/f6_daily_omni"
QA = "/workspace/benchmarks/Daily-Omni/qa.json"

SAMP_ARGS = sys.argv[1:]  # e.g. --temp 0.2 --top-k 20 --repeat-penalty 1.15

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
        print(f"{label}: omni_init FAILED"); return "FAIL"
    r = post("/v1/stream/prefill", {"audio_path_prefix": "", "cnt": 0, "text": ""})
    r = post("/v1/stream/prefill", {"audio_path_prefix": audio, "img_path_prefix": img,
                                    "cnt": 1, "text": P, "max_slice_nums": 1})
    if not r.get("success"):
        print(f"{label}: prefill FAILED"); return "FAIL"
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
    print(f"{label}: tag={tag} ntok={d.get('generated_token_count')} text={t[:70]!r}")
    return tag


def main():
    global P
    qa = json.load(open(QA))
    it = next(d for d in qa if d.get("video_id") == "G_VTkkb34gw")
    P = build_prompt(it["Question"], it["Choice"])

    logf = open(LOG, "w")
    cmd = ["stdbuf", "-oL", "-eL", SERVER, "-m", MODEL, "-ngl", "999",
           "--device", "CANN0", "-c", "4096", "-b", "512", "-ub", "512",
           "--split-mode", "layer", "--port", str(PORT)] + SAMP_ARGS
    print("SERVER ARGS:", " ".join(cmd))
    proc = subprocess.Popen(cmd, env=ENV, stdout=logf, stderr=subprocess.STDOUT, cwd=REPO,
                            preexec_fn=os.setsid)
    for _ in range(600):
        if proc.poll() is not None:
            print("server exited early"); return 1
        if health_ok():
            time.sleep(2); break
        time.sleep(2)

    S3 = f"{T7}/short_3s.wav"
    F = f"{PREP}/G_VTkkb34gw/frame_15s.jpg"
    results = []
    try:
        print("== IMAGE+AUDIO 4 reps ==")
        for i in range(4):
            results.append(("IV%d" % (i + 1), run_case(f"IV{i+1}", 100 + i, S3, F)))
        print("== AUDIO-ONLY 2 reps ==")
        for i in range(2):
            results.append(("A%d" % (i + 1), run_case(f"A{i+1}", 200 + i, S3, "")))
        print("\n===== SUMMARY =====")
        for lbl, tag in results:
            print(f"{lbl}: {tag}")
    finally:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
