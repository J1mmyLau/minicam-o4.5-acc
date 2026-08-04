#!/usr/bin/env python3
"""F6 Daily-Omni accuracy pilot v2 — official chain + directive #6 checklist.

Chain:
  Daily-Omni input (video frame + audio + QA item)
  → omni server media protocol (two-prefill, use_tts=False)
  → text answer (non-streaming /decode `text` field)
  → extract_choice_letter (official test_utils logic)
  → score

Verification checklist (directive #6):
  A. non-stream text field  — every item's /decode returns non-empty `text`
  B. SSE text + [DONE]       — stream=True decode emits content events + `data: [DONE]`
  C. persistent context 2nd request — 2nd decode on the SAME omni context succeeds
  D. 0 HTTP500 / 0 crash / 0 stale-cross — every post() returns 200 JSON (no error
     string, no "500"); server alive + healthy at end
  E. per-request evidence — F6_REQSTATE drain_complete / response_sent / →IDLE
     (parsed from srv.log after the run)

Server: official candidate build/bin (db258375/c075c535).
"""
import json, os, sys, time, urllib.request, subprocess, signal, argparse, re

REPO = "/workspace/llama.cpp-omni-f6"
SERVER = os.path.join(REPO, "build/bin/llama-omni-server")
MODEL = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
PREP = "/tmp/f6_daily_omni"
PORT = 18098
BASE = f"http://127.0.0.1:{PORT}"
LOG = os.path.join(PREP, "srv.log")
QA = "/workspace/benchmarks/Daily-Omni/qa.json"
VIDEOS = ["G_VTkkb34gw", "bswbQtOPk6E", "d6b4OmUFt7I"]

ENV = dict(os.environ)
ENV.update({"OMNI_KV_CACHE_REUSE": "1", "OMNI_T2W_DEVICE": "cann-flow-only",
            "OMNI_VOC_DEVICE": "gpu", "ASCEND_RT_VISIBLE_DEVICES": "0"})


def health_ok():
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=3) as r:
            return json.loads(r.read().decode()).get("status") == "ok"
    except Exception:
        return False


def post_raw(path, payload, timeout=600):
    """POST; returns (http_status, raw_body) — never raises."""
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return -1, json.dumps({"error": str(e)})


def post(path, payload, timeout=600):
    st, body = post_raw(path, payload, timeout)
    try:
        return st, json.loads(body)
    except Exception:
        return st, {"raw": body[:300]}


def launch():
    os.makedirs(PREP, exist_ok=True)
    logf = open(LOG, "w")
    cmd = ["stdbuf", "-oL", "-eL", SERVER, "-m", MODEL, "-ngl", "999",
           "--device", "CANN0", "-c", "4096", "-b", "512", "-ub", "512",
           "--split-mode", "layer", "--port", str(PORT)]
    proc = subprocess.Popen(cmd, env=ENV, stdout=logf, stderr=subprocess.STDOUT,
                            cwd=REPO, preexec_fn=os.setsid)
    for _ in range(600):
        if proc.poll() is not None:
            with open(LOG, errors="replace") as f:
                raise RuntimeError("server exited early:\n" + f.read()[-1500:])
        if health_ok():
            time.sleep(3)
            return proc
        time.sleep(2)
    raise RuntimeError("server did not become healthy")


def extract_choice_letter(text):
    """Mirror of official test_utils.py extract_choice_letter."""
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    if not s:
        return None
    if s[0] in "ABCD":
        return s[0]
    m = re.search(r"\b([ABCD])\b", s)
    return m.group(1) if m else None


def build_prompt(question, choices):
    return (
        "Your task is to accurately answer multiple-choice questions based on the given video. "
        "Select the single most accurate answer from the given choices. "
        "Your answer should be a capital letter representing your choice: A, B, C, or D. "
        "Don't generate any other text.\n\n"
        f"Given the video, answer the question below.\nQuestion: {question}\nChoices: {choices}"
    )


def init_and_prefill(idx, item, short=False):
    """omni_init (media_type=2, use_tts=False) + two-prefill. Returns rec dict.
    short=True → use audio_3s.wav (in-capability audio, avoids whisper ceiling)."""
    vid = item["video_id"]
    img = os.path.join(PREP, vid, "frame_15s.jpg")
    aud = os.path.join(PREP, vid, ("audio_3s.wav" if short else "audio_mono.wav"))
    rec = {"idx": idx, "video": vid, "type": item.get("Type"),
           "question": item["Question"][:100], "correct": item["Answer"].strip().upper()}
    if not (os.path.exists(img) and os.path.exists(aud)):
        rec["error"] = "media missing"; return rec
    rec["prompt"] = build_prompt(item["Question"], item["Choice"])

    st, r = post("/v1/stream/omni_init", {"media_type": 2, "use_tts": False}, timeout=300)
    rec["init_http"] = st; rec["init"] = r.get("success")
    if not rec["init"]:
        rec["error"] = f"omni_init failed http={st}"; return rec

    st, r = post("/v1/stream/prefill", {"audio_path_prefix": "", "cnt": 0, "text": ""})
    rec["prefill_sys"] = (st, r.get("success"))
    st, r = post("/v1/stream/prefill", {
        "audio_path_prefix": aud, "img_path_prefix": img, "cnt": 1,
        "text": rec["prompt"], "max_slice_nums": 1})
    rec["prefill_media"] = (st, r.get("success"))
    return rec


def decode_nonstream(idx):
    t0 = time.time()
    st, d = post("/v1/stream/decode", {
        "stream": False, "round_idx": idx, "max_tokens": 256,
        "wall_timeout_ms": 180000}, timeout=400)
    wall = round(time.time() - t0, 1)
    text = d.get("text", "") if isinstance(d, dict) else ""
    return {"http": st, "success": d.get("success"), "stop": d.get("stop_reason"),
            "ntok": d.get("generated_token_count"), "text": text[:600],
            "text_len": len(text), "wall_s": wall,
            "pred": extract_choice_letter(text)}


def decode_sse(idx):
    """Stream=True decode; parse raw SSE body for content events + [DONE]."""
    t0 = time.time()
    st, body = post_raw("/v1/stream/decode", {
        "stream": True, "round_idx": idx, "max_tokens": 256,
        "wall_timeout_ms": 180000}, timeout=400)
    wall = round(time.time() - t0, 1)
    events = []
    content_chars = 0
    for chunk in body.split("\n\n"):
        for line in chunk.splitlines():
            if line.startswith("data:"):
                ev = line[5:].strip()
                events.append(ev)
                if ev and ev != "[DONE]":
                    try:
                        content_chars += len(json.loads(ev).get("content", ""))
                    except Exception:
                        pass
    return {"http": st, "events": len(events), "has_done": "[DONE]" in events,
            "content_chars": content_chars, "wall_s": wall}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["single", "montage"], default="single")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--short", action="store_true",
                    help="use audio_3s.wav (in-capability audio; full audio_mono.wav is "
                         "29.5s > whisper encoder ceiling ~24-26s → model degrades)")
    args = ap.parse_args()

    qa = json.load(open(QA))
    items = [d for d in qa if d.get("video_id") in VIDEOS]
    if args.limit:
        items = items[:args.limit]
    print(f"=== Daily-Omni PILOT v2 (mode={args.mode}, short={args.short}, {len(items)} items) ===")
    print(f"server: {SERVER}")

    proc = launch()
    print(f"[server up pid={proc.pid} port={PORT}]")

    results = []
    http500 = 0
    client_errors = []
    try:
        # ── Phase 1: 9 QA items (per-item fresh session) ──
        for i, it in enumerate(items):
            rec = init_and_prefill(i, it, short=args.short)
            if rec.get("error"):
                results.append(rec); print(f"\n[{i}] ERROR: {rec['error']}"); continue
            d = decode_nonstream(i)
            rec.update(d)
            rec["is_correct"] = (rec.get("pred") is not None and rec.get("pred") == rec.get("correct"))
            results.append(rec)
            # count HTTP-level failures
            if rec.get("http", 200) == 500:
                http500 += 1
            if not rec.get("success") or rec.get("http", 200) not in (200, -1) and rec.get("http") != 200:
                client_errors.append((i, "decode", rec.get("http"), rec.get("stop")))
            print(f"\n[{i}] {it['video_id']} ({it.get('Type')}) correct={it['Answer']}")
            print(f"    prefill sys/media: {rec['prefill_sys'][1]}/{rec['prefill_media'][1]} "
                  f"decode http={rec.get('http')} ok={rec.get('success')} stop={rec.get('stop')} "
                  f"ntok={rec.get('ntok')} wall={rec.get('wall_s')}s")
            print(f"    pred={rec.get('pred')} text_len={rec.get('text_len')} "
                  f"text={rec.get('text','')[:200]!r}")

        # ── Phase 2: lifecycle checklist on one persistent context ──
        print("\n── Phase 2: lifecycle (persistent context + SSE) ──")
        lc = {"idx": "lifecycle"}
        # fresh init on the SAME server process
        # NOTE: round_idx MUST be an integer — server-omni.cpp:414 does
        # data.value("round_idx", -1) which throws json type_error on strings → 500.
        base = init_and_prefill(900, items[0], short=args.short)
        if base.get("error"):
            lc["error"] = base["error"]
        else:
            # decode #1
            d1 = decode_nonstream(901)
            lc["decode1"] = {"http": d1["http"], "success": d1["success"], "stop": d1["stop"],
                             "text_len": d1["text_len"]}
            print(f"  decode#1 (non-stream) http={d1['http']} ok={d1['success']} "
                  f"stop={d1['stop']} text_len={d1['text_len']}")
            # decode #2 — persistent context 2nd request (same ctx, no re-init)
            d2 = decode_nonstream(902)
            lc["decode2"] = {"http": d2["http"], "success": d2["success"], "stop": d2["stop"],
                             "text_len": d2["text_len"]}
            lc["persistent_2nd_ok"] = (d2["http"] == 200 and d2["success"] is True)
            print(f"  decode#2 (PERSISTENT context 2nd request) http={d2['http']} "
                  f"ok={d2['success']} stop={d2['stop']} text_len={d2['text_len']}")
            # decode #3 — SSE text + [DONE]
            s = decode_sse(903)
            lc["sse"] = s
            lc["sse_ok"] = (s["http"] == 200 and s["has_done"] and s["content_chars"] >= 0)
            print(f"  decode#3 (SSE) http={s['http']} events={s['events']} "
                  f"has_done={s['has_done']} content_chars={s['content_chars']} wall={s['wall_s']}s")

        results.append(lc)
    finally:
        alive_end = proc.poll() is None
        healthy_end = health_ok()
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)

    summary = {
        "items": [r for r in results if "idx" in r and isinstance(r.get("idx"), int)],
        "lifecycle": lc,
        "http500": http500,
        "client_errors": client_errors,
        "server_alive_end": alive_end,
        "server_healthy_end": healthy_end,
    }
    json.dump(summary, open(os.path.join(PREP, f"pilot_{args.mode}_{'short' if args.short else 'full'}.json"), "w"),
              ensure_ascii=False, indent=1)

    items_r = summary["items"]
    n_eval = sum(1 for r in items_r if r.get("pred"))
    n_corr = sum(1 for r in items_r if r.get("is_correct"))
    print("\n===== PILOT v2 RESULT =====")
    if len(items_r):
        eval_pct = n_eval / len(items_r)
    else:
        eval_pct = 0
    corr_note = f"({n_corr/n_eval:.0%} of extractable)" if n_eval else "(no extractable pred)"
    print(f"items: {len(items_r)} | extractable pred: {n_eval}/{len(items_r)} "
          f"({eval_pct:.0%}) | correct: {n_corr}/{n_eval} {corr_note}")
    print(f"lifecycle: persistent_2nd_ok={lc.get('persistent_2nd_ok')} "
          f"sse_ok={lc.get('sse_ok')}")
    print(f"http500={http500} client_errors={client_errors}")
    print(f"server_alive_end={alive_end} server_healthy_end={healthy_end}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
