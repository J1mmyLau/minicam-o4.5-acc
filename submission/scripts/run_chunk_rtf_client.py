#!/usr/bin/env python3
"""run_chunk_rtf_client.py — 驱动 TTS 请求，产生逐 chunk 音频（供 run_performance.sh）

baseline 与 candidate 共用本客户端：同一请求形态 / 请求顺序 / seed / warmup / measured count。
    --seed 0     → 按字典序取文本（确定性，对称性默认）
    --seed K     → 用 seed 固定打乱文本选择（K>0）
    --warmup W   → 先发 W 个不计入测量的请求（W 与 N 均须 baseline/candidate 一致）
    --texts-out  → 落盘实际使用的文本与请求顺序（复现审计）

用法：python3 run_chunk_rtf_client.py --port 18093 --n 3 --warmup 0 --seed 0 --text-dir <dir>
无官方脚本前使用冻结候选已验证的请求形态（use_tts=True 的 /v1/stream/decode）。
"""
import argparse, glob, json, os, random, sys, time, urllib.request

DEFAULT_TEXTS = ["请用自然的中文语速说一段完整的话，介绍一下天气。"]


def post(url, body, timeout=600):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def select_texts(text_dir, seed, needed):
    """确定性选择 needed 条文本：seed=0 字典序；seed>0 固定打乱。可循环复用。"""
    pool = []
    if text_dir and os.path.isdir(text_dir):
        pool = [open(p).read().strip()
                for p in sorted(glob.glob(os.path.join(text_dir, "*.txt")))]
    if not pool:
        pool = list(DEFAULT_TEXTS)
    if seed and seed > 0:
        rng = random.Random(seed)
        rng.shuffle(pool)
    return (pool * ((needed // len(pool)) + 1))[:needed]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18093)
    ap.add_argument("--n", type=int, default=3, help="测量请求数")
    ap.add_argument("--warmup", type=int, default=0, help="预热请求数（不计入测量）")
    ap.add_argument("--seed", type=int, default=0, help="0=字典序；>0=固定打乱文本选择")
    ap.add_argument("--text-dir", default="")
    ap.add_argument("--texts-out", default="", help="写实际使用文本清单（复现审计）")
    a = ap.parse_args()

    texts = select_texts(a.text_dir, a.seed, a.warmup + a.n)

    if a.texts_out:
        out = os.path.abspath(a.texts_out)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w") as f:
            f.write(f"# seed={a.seed} warmup={a.warmup} n={a.n} text_dir={a.text_dir or 'builtin'}\n")
            for i, t in enumerate(texts):
                f.write(f"req{i}\t{'warmup' if i < a.warmup else 'measured'}\t{len(t)}\t{t}\n")

    base = f"http://127.0.0.1:{a.port}"
    for i, t in enumerate(texts):
        t0 = time.time()
        # 冻结候选已验证的 TTS 请求形态（use_tts=True）。字段名以官方 Starter Kit 到达后为准。
        resp = post(f"{base}/v1/stream/decode", {
            "prompt": t,
            "use_tts": True,
            "max_tokens": 128,
        })
        wall = (time.time() - t0) * 1000
        tag = "warmup" if i < a.warmup else "measured"
        print(f"req[{i}] {tag} wall={wall:.0f}ms text_len={len(resp.get('text', '') or '')} "
              f"wav_count={resp.get('wav_count')} stop={resp.get('stop_reason')}")
        sys.stdout.flush()
    print("CLIENT_DONE")


if __name__ == "__main__":
    main()
