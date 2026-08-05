#!/usr/bin/env python3
"""run_chunk_rtf_client.py — 驱动 N 个 TTS 请求，产生逐 chunk 音频（供 run_performance.sh）

用法：python3 run_chunk_rtf_client.py --port 18093 --n 3 --text-dir <dir>
无官方脚本前使用冻结候选已验证的请求形态（use_tts=True 的 /v1/stream/decode）。
"""
import argparse, glob, json, os, sys, time, urllib.request

def post(url, body, timeout=600):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18093)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--text-dir", default="")
    a = ap.parse_args()

    base = f"http://127.0.0.1:{a.port}"
    texts = []
    if a.text_dir and os.path.isdir(a.text_dir):
        for p in sorted(glob.glob(os.path.join(a.text_dir, "*.txt")))[: a.n]:
            texts.append(open(p).read().strip())
    if len(texts) < a.n:
        texts += ["请用自然的中文语速说一段完整的话，介绍一下天气。"] * (a.n - len(texts))

    for i, t in enumerate(texts):
        t0 = time.time()
        # 冻结候选已验证的 TTS 请求形态（use_tts=True）。字段名以官方 Starter Kit 到达后为准。
        resp = post(f"{base}/v1/stream/decode", {
            "prompt": t,
            "use_tts": True,
            "max_tokens": 128,
        })
        wall = (time.time() - t0) * 1000
        print(f"req[{i}] wall={wall:.0f}ms text_len={len(resp.get('text', '') or '')} "
              f"wav_count={resp.get('wav_count')} stop={resp.get('stop_reason')}")
        sys.stdout.flush()
    print("CLIENT_DONE")

if __name__ == "__main__":
    main()
