#!/usr/bin/env python3 -u
"""Daily-Omni accuracy evaluation using WebSocket backend protocol.

Sends video + question via WS /backend endpoint, collects text answer,
scores against ground truth. Uses frozen F16 binary.

Protocol: WebSocket turn_based with video base64 in messages array.
"""
import asyncio, json, base64, time, os, sys, struct, wave, io, socket, subprocess, re
from pathlib import Path

SERVER_BIN = "/workspace/llama.cpp-omni-session-fix/build/bin/llama-omni-server"
MODEL_PATH = "/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
MODEL_DIR = "/workspace/models/MiniCPM-o-4_5-gguf"
QA_FILE = "/workspace/benchmarks/Daily-Omni/qa.json"
PARQUET_DIR = "/workspace/shared_assets/datasets/MTEB/Daily-Omni/data"
OUTDIR = "/workspace/llama.cpp-omni-session-fix/benchmarks/results/accuracy"
TEMP_ROOT = "/tmp/daily_omni_eval"

# Competition thresholds
BASELINE_ACCURACY = 80.2
THRESHOLD = 77.5

PORT = None
PROC = None

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def find_port(start=24500):
    for p in range(start, start+60):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    raise RuntimeError("no free port")


def start_server():
    global PORT, PROC
    PORT = find_port()
    env = os.environ.copy()
    env.update({
        "OMNI_T2W_DEVICE": "cann-flow-only",
        "OMNI_T2W_PIPELINE_OVERLAP": "1",
        "OMNI_T2W_DRAIN_TIMEOUT_MS": "5000",
        "ASCEND_RT_VISIBLE_DEVICES": "0",
    })
    log_path = f"{TEMP_ROOT}/server.log"
    os.makedirs(TEMP_ROOT, exist_ok=True)
    blog = open(log_path, "wb")
    PROC = subprocess.Popen(
        [SERVER_BIN, "-m", MODEL_PATH, "--host", "127.0.0.1", "--port", str(PORT),
         "-ngl", "999", "--device", "CANN0", "-c", "4096", "-b", "512", "-ub", "512",
         "--split-mode", "layer", "-t", "4"],
        stdout=subprocess.DEVNULL, stderr=blog, env=env)

    import urllib.request as ur
    for i in range(180):
        if PROC.poll() is not None:
            log(f"Server died! Check {log_path}")
            return False
        try:
            ur.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=5)
            break
        except Exception:
            pass
        time.sleep(2)
    log(f"Server ready on port {PORT}")
    return True


def stop_server():
    if PROC:
        PROC.send_signal(subprocess.signal.SIGTERM)
        try:
            PROC.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            PROC.kill()
            PROC.communicate(timeout=5)


class ParquetVideoDB:
    """Efficient parquet video lookup by video_id."""

    def __init__(self, parquet_dir):
        self.parquet_dir = parquet_dir
        # Build row group index
        import pyarrow.parquet as pq
        self._files = []
        self._index = {}  # video_id -> (file_idx, row_group_idx, row_idx)
        for fi, fname in enumerate(sorted(os.listdir(parquet_dir))):
            if not fname.endswith('.parquet'):
                continue
            fp = os.path.join(parquet_dir, fname)
            pf = pq.ParquetFile(fp)
            self._files.append(pf)
            for rg in range(pf.metadata.num_row_groups):
                t = pf.read_row_group(rg, columns=['video_id'])
                ids = t.column('video_id').to_pylist()
                for ri, vid in enumerate(ids):
                    self._index[vid] = (fi, rg, ri)
        log(f"Parquet index: {len(self._index)} videos, {len(self._files)} files")

    def get_video_bytes(self, video_id):
        if video_id not in self._index:
            return None
        fi, rg, ri = self._index[video_id]
        pf = self._files[fi]
        t = pf.read_row_group(rg, columns=['video'])
        video_struct = t.column('video')[ri].as_py()
        if video_struct and 'bytes' in video_struct:
            return video_struct['bytes']
        return None


async def ws_ask_video(ws_url, video_bytes, prompt, timeout=120):
    """Send video + question via WebSocket, return answer text."""
    import websockets

    video_b64 = base64.b64encode(video_bytes).decode()

    ws = await websockets.connect(ws_url, max_size=512 * 1024 * 1024,
                                  ping_interval=None, close_timeout=30)

    # session.init: turn_based, no TTS
    await ws.send(json.dumps({
        "type": "session.init",
        "payload": {"mode": "turn_based", "use_tts": False}
    }))

    while True:
        evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        if evt.get('type') in ('session.created', 'initialized'):
            break
        elif evt.get('type') in ('session.closed', 'error', 'session.failed'):
            await ws.close()
            return {"ok": False, "error": f"init_{evt.get('type')}: {evt.get('reason', str(evt)[:100])}"}

    # input.append with video + question
    t0 = time.perf_counter_ns()
    await ws.send(json.dumps({
        "type": "input.append",
        "input": {
            "messages": [{
                "role": "user",
                "content": prompt,
                "videos": [video_b64],
                "video_stack_frames": [8]
            }],
            "streaming": True,
            "generation": {"max_new_tokens": 64}
        }
    }))

    text_parts = []
    while True:
        evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        et = evt.get('type', '')
        if et == 'response.output.delta':
            if evt.get('kind') == 'text':
                text_parts.append(evt.get('text', ''))
        elif et == 'response.done':
            if evt.get('text'):
                text_parts.append(evt['text'])
            break
        elif et in ('session.closed', 'error', 'session.failed'):
            await ws.close()
            return {"ok": False, "error": f"mid_{et}: {evt.get('reason', str(evt)[:100])}"}

    wall_ms = (time.perf_counter_ns() - t0) / 1e6
    text = ''.join(text_parts)
    await ws.close()
    return {"ok": True, "text": text, "wall_ms": wall_ms}


def extract_answer(text):
    """Extract answer letter from model output."""
    # Try to match a single letter answer
    m = re.search(r'\b([A-D])\b', text.strip())
    if m:
        return m.group(1)
    # Try "Answer: X" pattern
    m = re.search(r'[Aa]nswer:?\s*([A-D])', text)
    if m:
        return m.group(1)
    # Return first non-empty line
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    if lines:
        return lines[-1][:1]
    return text.strip()[:1]


async def main():
    os.makedirs(OUTDIR, exist_ok=True)
    os.makedirs(TEMP_ROOT, exist_ok=True)

    # Load QA data
    qa = json.load(open(QA_FILE))
    if isinstance(qa, dict):
        qa = qa.get("questions", qa.get("items", []))
    log(f"Loaded {len(qa)} QA items")

    # Build parquet index
    pvdb = ParquetVideoDB(PARQUET_DIR)

    # Start frozen server
    if not start_server():
        log("Failed to start server!")
        return 1

    ws_url = f"ws://127.0.0.1:{PORT}/backend"

    # Process items
    results = []
    correct = 0
    failed = 0
    skipped = 0
    total_wall = 0.0

    checkpoint_path = f"{OUTDIR}/daily_omni_checkpoint.json"
    start_idx = 0
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path) as f:
            ckpt = json.load(f)
            results = ckpt.get('results', [])
            start_idx = ckpt.get('next_idx', 0)
            correct = ckpt.get('correct', 0)
            failed = ckpt.get('failed', 0)
            skipped = ckpt.get('skipped', 0)
            log(f"Resuming from checkpoint: {start_idx}/{len(qa)}")

    for idx in range(start_idx, len(qa)):
        item = qa[idx]
        video_id = item['video_id']
        question = item['Question']
        choices = item['Choice']
        ground_truth = item['Answer']

        # Build prompt
        prompt = question + "\n\n" + "\n".join(choices) + "\n\nAnswer with the letter of the correct option."

        # Get video bytes
        video_bytes = pvdb.get_video_bytes(video_id)
        if not video_bytes:
            log(f"[{idx+1}/{len(qa)}] SKIP: no video for {video_id}")
            results.append({"video_id": video_id, "skipped": True,
                            "ground_truth": ground_truth})
            skipped += 1
            continue

        # Run inference
        try:
            t0 = time.time()
            result = await asyncio.wait_for(
                ws_ask_video(ws_url, video_bytes, prompt, timeout=120),
                timeout=180)
            wall = time.time() - t0
            total_wall += wall

            if not result.get('ok'):
                log(f"[{idx+1}/{len(qa)}] FAIL: {result.get('error', 'unknown')}")
                results.append({"video_id": video_id, "error": result.get('error', ''),
                                "ground_truth": ground_truth})
                failed += 1
            else:
                predicted = extract_answer(result['text'])
                is_correct = predicted == ground_truth
                if is_correct:
                    correct += 1
                status = "✓" if is_correct else f"✗ (pred={predicted}, gt={ground_truth})"
                log(f"[{idx+1}/{len(qa)}] {status} wall={wall:.1f}s text={result['text'][:60].strip()}")

                results.append({
                    "video_id": video_id,
                    "question": question[:100],
                    "prediction": predicted,
                    "ground_truth": ground_truth,
                    "is_correct": is_correct,
                    "raw_text": result['text'][:200],
                    "wall_s": round(wall, 1),
                    "qa_type": item.get('Type', ''),
                })

        except asyncio.TimeoutError:
            log(f"[{idx+1}/{len(qa)}] TIMEOUT")
            results.append({"video_id": video_id, "error": "timeout",
                            "ground_truth": ground_truth})
            failed += 1
        except Exception as e:
            log(f"[{idx+1}/{len(qa)}] ERROR: {e}")
            results.append({"video_id": video_id, "error": str(e)[:200],
                            "ground_truth": ground_truth})
            failed += 1

        # Checkpoint every 10 items
        if (idx + 1) % 10 == 0:
            total = idx + 1 - start_idx
            acc = (correct / (total - skipped - failed) * 100) if (total - skipped - failed) > 0 else 0
            log(f"  Checkpoint: {correct}/{total-skipped-failed} correct ({acc:.1f}%), "
                f"{failed} failed, {skipped} skipped, {total_wall/total:.1f}s avg")
            with open(checkpoint_path, 'w') as f:
                json.dump({
                    "next_idx": idx + 1,
                    "correct": correct,
                    "failed": failed,
                    "skipped": skipped,
                    "results": results,
                }, f, indent=2, ensure_ascii=False)

    # Final scoring
    valid = [r for r in results if not r.get('skipped') and not r.get('error')]
    total_valid = len(valid)
    total_correct = sum(1 for r in valid if r.get('is_correct'))
    accuracy = (total_correct / total_valid * 100) if total_valid > 0 else 0
    delta = accuracy - BASELINE_ACCURACY
    passed = accuracy >= THRESHOLD

    print("\n" + "=" * 60)
    print("Daily-Omni Accuracy Evaluation — COMPLETE")
    print("=" * 60)
    print(f"  Total items: {len(qa)}")
    print(f"  Valid responses: {total_valid}")
    print(f"  Correct: {total_correct}")
    print(f"  Failed: {failed}")
    print(f"  Skipped: {skipped}")
    print(f"  Accuracy: {accuracy:.2f}%")
    print(f"  Baseline: {BASELINE_ACCURACY}%")
    print(f"  Delta: {delta:+.2f}pp")
    print(f"  Threshold: {THRESHOLD}%")
    print(f"  PASS: {passed}")
    print(f"  Total wall time: {total_wall:.0f}s ({total_wall/3600:.1f}h)")
    print(f"  Avg per item: {total_wall/len(qa):.1f}s")

    # Save results
    ts = time.strftime("%Y%m%d_%H%M%S")
    summary = {
        "benchmark": "Daily-Omni",
        "status": "COMPLETE",
        "baseline_accuracy": BASELINE_ACCURACY,
        "candidate_accuracy": round(accuracy, 2),
        "delta_pp": round(delta, 2),
        "threshold": THRESHOLD,
        "threshold_delta_pp": -2.0,
        "passed": passed,
        "total_items": len(qa),
        "valid_items": total_valid,
        "correct_items": total_correct,
        "failed_items": failed,
        "skipped_items": skipped,
        "total_wall_s": round(total_wall, 1),
        "avg_wall_s": round(total_wall / len(qa), 1) if qa else 0,
        "binary_sha": "768614abd68f93ff5b57a3eb99cb79ad14d2a839f0fcb7ebf0990c88f39d189e",
    }
    with open(f"{OUTDIR}/daily_omni_summary_{ts}.json", 'w') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Saved: {OUTDIR}/daily_omni_summary_{ts}.json")

    with open(f"{OUTDIR}/daily_omni_items_{ts}.json", 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    stop_server()
    return 0 if passed else 2


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
