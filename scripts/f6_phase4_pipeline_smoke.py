#!/usr/bin/env python3
"""F6 Phase 4: Flow ∥ Vocoder Pipeline — Smoke Test

Tests:
  1. Serial mode (OMNI_T2W_PIPELINE_OVERLAP=0) — 1 session, verify WAV output
  2. Pipeline mode (OMNI_T2W_PIPELINE_OVERLAP=1) — 1 session, verify WAV output
  3. Compare window counts, WAV file lists, drain logs

Model: Q4_K_M (5GB, fast loading) or Q8_0 (8.7GB)
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
import glob
from datetime import datetime

# ── Constants ──
SERVER_START_TIMEOUT = 300
REQUEST_TIMEOUT = 180
AUDIO_PATH = "tools/omni/assets/test_case/omni_test_case/omni_test_case_0006"
TEST_PROMPT = "你好，请介绍一下人工智能的发展历程"
MAX_TOKENS = 64
SERVER_PORT = 18094  # Avoid collision with other test servers

# ── Helpers ──
def http_post(url, data, timeout=REQUEST_TIMEOUT):
    req = urllib.request.Request(url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            result = {"_status": resp.status, "_body": body}
            try:
                result.update(json.loads(body))
            except json.JSONDecodeError:
                pass
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {"_status": e.code, "_body": body}
    except Exception as e:
        return {"_status": -1, "_body": str(e)}

def http_get(url, timeout=10):
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"_error": str(e)}

def find_free_port(start=18094):
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    raise RuntimeError("No free port found")

def read_wav_header(path):
    """Return (sample_rate, num_samples, duration_s)."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 44 or data[:4] != b"RIFF":
        return None
    sample_rate = int.from_bytes(data[24:28], 'little')
    num_channels = int.from_bytes(data[22:24], 'little')
    bits_per_sample = int.from_bytes(data[34:36], 'little')
    data_size = int.from_bytes(data[40:44], 'little')
    bytes_per_sample = bits_per_sample // 8
    num_samples = data_size // (num_channels * bytes_per_sample)
    duration_s = num_samples / sample_rate
    return {"sample_rate": sample_rate, "num_channels": num_channels,
            "num_samples": num_samples, "duration_s": duration_s,
            "data_bytes": data_size}

def read_wav_pcm(path):
    """Return list of int16 PCM samples."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 44 or data[:4] != b"RIFF":
        return None
    data_size = int.from_bytes(data[40:44], 'little')
    pcm_start = data.index(b'data') + 4
    # data chunk may not start at offset 44 if there are extra chunks
    pcm_bytes = data[pcm_start:pcm_start + data_size]
    import struct
    return struct.unpack('<' + 'h' * (len(pcm_bytes) // 2), pcm_bytes)

# ── Server manager ──
class Server:
    def __init__(self, binary, model, port, env=None):
        self.binary = binary
        self.model = model
        self.port = port
        self.env = env or {}
        self.process = None
        self.base_url = f"http://127.0.0.1:{port}"

    def start(self):
        cmd = [
            self.binary,
            "-m", self.model,
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "-ngl", "99",
            "-c", "4096",
            "-b", "512", "-ub", "512",
            "--split-mode", "layer",
            "-fa", "off",
            "-n", "128",
            "-t", "4",
        ]
        merged_env = os.environ.copy()
        merged_env.update(self.env)

        print(f"\n[SERVER] Starting: {' '.join(cmd)}")
        for k, v in self.env.items():
            print(f"[SERVER]   env {k}={v}")

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=merged_env,
        )

        print(f"[SERVER] PID={self.process.pid}, waiting for /health...")
        deadline = time.monotonic() + SERVER_START_TIMEOUT
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                print(f"[SERVER] EXITED early rc={self.process.returncode}")
                print(f"[SERVER] STDOUT tail: {stdout[-4000:].decode('utf-8', errors='replace')}")
                print(f"[SERVER] STDERR tail: {stderr[-4000:].decode('utf-8', errors='replace')}")
                return False
            result = http_get(f"{self.base_url}/health")
            if result.get("status") == "ok":
                print(f"[SERVER] /health OK")
                return True
            time.sleep(1)
        print(f"[SERVER] TIMEOUT waiting for /health")
        return False

    def stop(self):
        if self.process is None or self.process.poll() is not None:
            return
        print(f"\n[SERVER] Stopping PID={self.process.pid}...")
        self.process.send_signal(signal.SIGTERM)
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            print(f"[SERVER] SIGTERM timeout, sending SIGKILL...")
            self.process.kill()
            self.process.wait(timeout=10)
        print(f"[SERVER] Stopped (rc={self.process.returncode})")

    def collect_logs(self, prefix):
        """Save server stderr/stdout to files for analysis."""
        if self.process is None:
            return
        try:
            self.process.send_signal(signal.SIGTERM)
            stdout, stderr = self.process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            stdout, stderr = self.process.communicate(timeout=5)
        except Exception:
            stdout, stderr = b"", b""

        os.makedirs("/tmp/f6_phase4_test", exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(f"/tmp/f6_phase4_test/{prefix}_{ts}_stdout.log", "wb") as f:
            f.write(stdout)
        with open(f"/tmp/f6_phase4_test/{prefix}_{ts}_stderr.log", "wb") as f:
            f.write(stderr)
        print(f"[LOGS] Saved to /tmp/f6_phase4_test/{prefix}_{ts}_*.log")
        return stdout.decode('utf-8', errors='replace'), stderr.decode('utf-8', errors='replace')

# ── Test runner ──
def run_one_session(server, label):
    """Run omni_init → prefill → decode. Return result dict."""
    result = {"label": label}

    # 1. omni_init
    t0 = time.monotonic()
    r = http_post(f"{server.base_url}/v1/stream/omni_init",
                  {"msg_type": 1, "media_type": 1, "use_tts": True})
    result["init_ms"] = (time.monotonic() - t0) * 1000
    if r.get("_status") != 200:
        result["error"] = f"omni_init failed: {r}"
        return result
    result["init_ok"] = True

    # 2. prefill
    t0 = time.monotonic()
    r = http_post(f"{server.base_url}/v1/stream/prefill",
                  {"audio_path_prefix": AUDIO_PATH, "cnt": 1, "text": TEST_PROMPT})
    result["prefill_ms"] = (time.monotonic() - t0) * 1000
    if r.get("_status") != 200:
        result["error"] = f"prefill failed: {r}"
        return result
    result["prefill_ok"] = True

    # 3. decode
    t0 = time.monotonic()
    r = http_post(f"{server.base_url}/v1/stream/decode",
                  {"debug_dir": "./", "stream": False, "round_idx": 0,
                   "max_tokens": MAX_TOKENS, "wall_timeout_ms": 120000})
    result["decode_ms"] = (time.monotonic() - t0) * 1000
    if r.get("_status") != 200:
        result["error"] = f"decode failed: {r}"
        return result

    result["success"] = r.get("success", False)
    result["stop_reason"] = r.get("stop_reason", "?")
    result["sliding_window_count"] = r.get("sliding_window_count", -1)
    result["generated_token_count"] = r.get("generated_token_count", -1)
    result["decode_ok"] = True

    return result

def collect_wav_files():
    """Find all WAV files produced by the test."""
    output_dir = "tools/omni/output"
    wav_files = []
    for root, dirs, files in os.walk(output_dir):
        for f in sorted(files):
            if f.endswith('.wav'):
                wav_files.append(os.path.join(root, f))
    return wav_files

# ── Main ──
def main():
    parser = argparse.ArgumentParser(description="F6 Phase 4 Pipeline Smoke Test")
    parser.add_argument("--binary", default="./build/bin/llama-omni-server")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output-dir", default="/tmp/f6_phase4_test")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Clean old WAV files
    old_wavs = collect_wav_files()
    if old_wavs and os.path.exists("tools/omni/output"):
        import shutil
        shutil.rmtree("tools/omni/output", ignore_errors=True)

    port = find_free_port(SERVER_PORT)

    results = {}

    # ── Test 1: Serial mode (default) ──
    print("\n" + "=" * 70)
    print("TEST 1: Serial mode (OMNI_T2W_PIPELINE_OVERLAP unset)")
    print("=" * 70)

    env_serial = {
        "OMNI_T2W_DEVICE": "cann-flow-only",
        "OMNI_T2W_QUEUE_DIAG": "1",
    }
    server = Server(args.binary, args.model, port, env_serial)
    if not server.start():
        print("FAIL: Server failed to start (serial mode)")
        sys.exit(1)

    result_serial = run_one_session(server, "serial")
    print(f"\n[RESULT serial] {json.dumps(result_serial, indent=2, ensure_ascii=False)}")
    results["serial"] = result_serial

    stdout_s, stderr_s = server.collect_logs("serial")
    server.stop()

    # Count WAV files from serial run
    wavs_serial = collect_wav_files()
    print(f"\n[WAV serial] {len(wavs_serial)} files: {[os.path.basename(w) for w in wavs_serial]}")

    # ── Test 2: Pipeline mode ──
    print("\n" + "=" * 70)
    print("TEST 2: Pipeline mode (OMNI_T2W_PIPELINE_OVERLAP=1)")
    print("=" * 70)

    # Clean output again
    if os.path.exists("tools/omni/output"):
        import shutil
        shutil.rmtree("tools/omni/output", ignore_errors=True)

    port2 = find_free_port(port + 1)

    env_pipeline = {
        "OMNI_T2W_DEVICE": "cann-flow-only",
        "OMNI_T2W_PIPELINE_OVERLAP": "1",
        "OMNI_T2W_QUEUE_DIAG": "1",
    }
    server2 = Server(args.binary, args.model, port2, env_pipeline)
    if not server2.start():
        print("FAIL: Server failed to start (pipeline mode)")
        results["pipeline"] = {"error": "server start failed"}
    else:
        result_pipeline = run_one_session(server2, "pipeline")
        print(f"\n[RESULT pipeline] {json.dumps(result_pipeline, indent=2, ensure_ascii=False)}")
        results["pipeline"] = result_pipeline

        stdout_p, stderr_p = server2.collect_logs("pipeline")
        server2.stop()

        wavs_pipeline = collect_wav_files()
        print(f"\n[WAV pipeline] {len(wavs_pipeline)} files: {[os.path.basename(w) for w in wavs_pipeline]}")

    # ── Summary ──
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for mode, r in results.items():
        status = "PASS" if r.get("success") else ("FAIL" if "error" in r else "INCOMPLETE")
        print(f"  {mode:12s}: {status} | windows={r.get('sliding_window_count', '?')} "
              f"| tokens={r.get('generated_token_count', '?')} "
              f"| decode={r.get('decode_ms', '?'):.0f}ms "
              f"| err={r.get('error', 'none')[:80]}")

    # Check WAV file sanity
    all_wavs = collect_wav_files()
    if all_wavs:
        print(f"\n  Total WAV files: {len(all_wavs)}")
        for w in all_wavs:
            hdr = read_wav_header(w)
            if hdr:
                pcm = read_wav_pcm(w)
                rms = (sum(s*s for s in pcm) / len(pcm)) ** 0.5 if pcm else 0
                has_nan = any(s != s for s in pcm) if pcm else False
                print(f"    {os.path.basename(w)}: {hdr['duration_s']:.3f}s "
                      f"{hdr['num_samples']}samples rms={rms:.1f} NaN={has_nan}")
            else:
                print(f"    {os.path.basename(w)}: INVALID WAV")

    # Final verdict
    serial_ok = results.get("serial", {}).get("success", False)
    pipeline_ok = results.get("pipeline", {}).get("success", False)

    print(f"\n  Serial non-regression: {'PASS' if serial_ok else 'FAIL'}")
    print(f"  Pipeline mode:         {'PASS' if pipeline_ok else 'FAIL'}")

    return 0 if serial_ok else 1

if __name__ == "__main__":
    sys.exit(main())
