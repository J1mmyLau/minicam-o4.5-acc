#!/usr/bin/env python3
"""
F6 E2E A/B Test Harness — Sequential Server, ABBA Ordering
==========================================================

Supports:
  - W8_CORRECTNESS_30_PLUS: 30+ request W0 correctness across 5 categories
  - W9_MATCHED_E2E_OVERHEAD: 20-pair F6_TIMING=0 vs summary matched E2E overhead
  - TRUE_D0_TO_W0_AB: 120 strict matched pairs B6b ON vs OFF
  - TRUE_CLIENT_FIRST_AUDIO_AB: client-observed first-audio A/B
  - G3→G4 compute/wait audit (timing collection only)

Architecture:
  Same binary, different env vars (OMNI_TTS_FIRST_CHUNK_STEP),
  sequential server (one NPU server at a time), ABBA block ordering.

Client-side monotonic clock:
  - request_send_ns: time.monotonic_ns() before HTTP POST /v1/stream/decode
  - first_audio_frame_ns: time.monotonic_ns() when first WAV file detected
  - first_valid_pcm_ns: time.monotonic_ns() when first valid PCM data read from WAV

Usage:
  # 30-request W0 correctness
  python3 scripts/f6_e2e_ab_harness.py w8-correctness \
    --binary ./build/bin/llama-omni-server \
    --model /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
    --output-dir /tmp/f6_w8_correctness

  # 20-pair E2E overhead gate
  python3 scripts/f6_e2e_ab_harness.py w9-overhead \
    --binary ./build/bin/llama-omni-server \
    --model /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
    --output-dir /tmp/f6_w9_overhead

  # 120-pair B6b matched A/B
  python3 scripts/f6_e2e_ab_harness.py w10-ab \
    --binary ./build/bin/llama-omni-server \
    --model /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
    --pairs 120 \
    --output-dir /tmp/f6_w10_ab
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
import shutil
import statistics
from pathlib import Path
from datetime import datetime

# ──────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────
SERVER_START_TIMEOUT = 600  # seconds to wait for server /health
REQUEST_TIMEOUT = 300       # seconds for HTTP request (5 min max per request)
SERVER_DRAIN_EXTRA = 10     # extra seconds after decode returns for T2W drain
MAX_TOKENS = "128"          # limit generation to avoid degenerate long responses

# ──────────────────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────────────────
def http_post(url: str, data: dict, timeout: int = REQUEST_TIMEOUT) -> dict:
    """POST JSON, return parsed response dict. Includes _client_ns timing."""
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    send_ns = time.monotonic_ns()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            recv_ns = time.monotonic_ns()
            result = {"_send_ns": send_ns, "_recv_ns": recv_ns, "_status": resp.status}
            if resp.status != 200:
                result["_body"] = body
                return result
            try:
                parsed = json.loads(body)
                parsed["_send_ns"] = send_ns
                parsed["_recv_ns"] = recv_ns
                return parsed
            except json.JSONDecodeError:
                result["_body"] = body
                return result
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {"_send_ns": send_ns, "_recv_ns": time.monotonic_ns(),
                "_status": e.code, "_body": body}
    except Exception as e:
        return {"_send_ns": send_ns, "_recv_ns": time.monotonic_ns(),
                "_status": -1, "_body": str(e)}


def http_get(url: str, timeout: int = 10) -> dict:
    """GET JSON, return parsed dict."""
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"_error": str(e)}


# ──────────────────────────────────────────────────────────
# WAV file helpers
# ──────────────────────────────────────────────────────────
def read_wav_params(path: str) -> dict:
    """Read WAV header and return {sample_rate, channels, num_samples, duration_s}."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        if len(data) < 44:
            return {"_error": "too_short", "_size": len(data)}
        if data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
            return {"_error": "not_wav"}
        sample_rate = int.from_bytes(data[24:28], "little")
        channels = int.from_bytes(data[22:24], "little")
        bits_per_sample = int.from_bytes(data[34:36], "little")
        data_size = int.from_bytes(data[40:44], "little")
        num_samples = data_size // (channels * bits_per_sample // 8)
        duration_s = num_samples / sample_rate if sample_rate > 0 else 0
        return {"sample_rate": sample_rate, "channels": channels,
                "bits_per_sample": bits_per_sample, "num_samples": num_samples,
                "duration_s": duration_s}
    except Exception as e:
        return {"_error": str(e)}


def find_wav_files(output_dir: str) -> list:
    """Find all .wav files in output_dir, sorted by creation time."""
    wavs = glob.glob(os.path.join(output_dir, "*.wav"))
    wavs.sort(key=lambda p: os.path.getctime(p))
    return wavs


# ──────────────────────────────────────────────────────────
# Server Manager
# ──────────────────────────────────────────────────────────
class ServerManager:
    """Launch and manage a llama-omni-server process."""

    def __init__(self, binary: str, model: str, host: str = "127.0.0.1",
                 port: int = 8080, ngl: int = 99, extra_args: list = None):
        self.binary = binary
        self.model = model
        self.host = host
        self.port = port
        self.ngl = ngl
        self.extra_args = extra_args or []
        self.process = None
        self.base_url = f"http://{host}:{port}"

    def start(self, env: dict = None, timeout: float = SERVER_START_TIMEOUT) -> bool:
        """Start server process, wait for /health. Returns True on success."""
        cmd = [
            self.binary,
            "-m", self.model,
            "--host", self.host,
            "--port", str(self.port),
            "-ngl", str(self.ngl),
            "-c", "2048",    # Explicit ctx-size (default 0 = model default, breaks max_tgt_len)
            "-n", "128",     # Max tokens to generate (keep short for consistent testing)
        ] + self.extra_args

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        print(f"[SERVER] Starting: {' '.join(cmd)}")
        for k, v in (env or {}).items():
            print(f"[SERVER]   env {k}={v}")

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=merged_env,
        )

        # Wait for /health
        print(f"[SERVER] Waiting for /health (timeout {timeout}s)...")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                print(f"[SERVER] Process exited early (rc={self.process.returncode})")
                print(f"[SERVER] STDOUT tail: {stdout[-2000:].decode('utf-8', errors='replace')}")
                print(f"[SERVER] STDERR tail: {stderr[-2000:].decode('utf-8', errors='replace')}")
                return False
            result = http_get(f"{self.base_url}/health")
            if result.get("status") == "ok":
                print(f"[SERVER] Health OK — server ready")
                return True
            time.sleep(2.0)

        print(f"[SERVER] Timeout waiting for /health")
        self.stop()
        return False

    def stop(self) -> tuple:
        """Stop server process gracefully (SIGTERM) then forcefully (SIGKILL)."""
        stdout, stderr = b"", b""
        if self.process is None:
            return stdout, stderr

        if self.process.poll() is None:
            print(f"[SERVER] Sending SIGTERM...")
            self.process.send_signal(signal.SIGTERM)
            try:
                stdout, stderr = self.process.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                print(f"[SERVER] SIGTERM timed out, sending SIGKILL...")
                self.process.kill()
                stdout, stderr = self.process.communicate(timeout=10)
        else:
            stdout, stderr = self.process.communicate()

        print(f"[SERVER] Stopped (rc={self.process.returncode})")
        self.process = None
        return stdout, stderr

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


# ──────────────────────────────────────────────────────────
# Test Session — one omni_init + decode cycle
# ──────────────────────────────────────────────────────────
class TestSession:
    """Runs a single omni_init + stream_decode cycle, collecting all artifacts."""

    def __init__(self, server_mgr: ServerManager, output_dir: str,
                 profile_dir: str, session_id: int = 0):
        self.server = server_mgr
        self.output_dir = output_dir
        self.profile_dir = profile_dir
        self.session_id = session_id
        self.result = {
            "session_id": session_id,
            "omni_init_ok": False,
            "decode_ok": False,
            "client_timings_ns": {},
            "wav_files": [],
            "audio_profile": None,
            "partial_profile": None,
            "w0_present": False,
            "w0_value_ms": 0,
            "errors": [],
        }

    def run(self, media_type: int = 2, stream: bool = False,
            debug_dir: str = None, drain_extra: float = SERVER_DRAIN_EXTRA) -> dict:
        """Run omni_init → stream_decode cycle. Returns result dict."""
        if debug_dir is None:
            debug_dir = self.output_dir

        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.profile_dir, exist_ok=True)

        # Record any existing WAV files before decode
        wavs_before = set(find_wav_files(self.output_dir))

        # Step 1: omni_init
        init_payload = {
            "media_type": media_type,
            "use_tts": True,
            "output_dir": self.output_dir,
        }
        init_url = f"{self.server.base_url}/v1/stream/omni_init"
        init_result = http_post(init_url, init_payload)
        self.result["omni_init_ok"] = init_result.get("success", False)
        self.result["omni_init_response"] = init_result

        if not self.result["omni_init_ok"]:
            self.result["errors"].append(f"omni_init failed: {init_result}")
            return self.result

        print(f"  [{self.session_id}] omni_init OK")

        # Step 2: stream_decode
        decode_payload = {
            "debug_dir": debug_dir,
            "stream": stream,
            "round_idx": -1,
        }
        decode_url = f"{self.server.base_url}/v1/stream/decode"
        decode_result = http_post(decode_url, decode_payload)

        self.result["decode_ok"] = decode_result.get("success", False)
        self.result["client_timings_ns"]["request_send"] = decode_result.get("_send_ns", 0)
        self.result["client_timings_ns"]["response_recv"] = decode_result.get("_recv_ns", 0)

        if not self.result["decode_ok"]:
            self.result["errors"].append(f"decode failed (status={decode_result.get('_status')}): "
                                         f"{decode_result.get('_body', '')[:200]}")
            return self.result

        print(f"  [{self.session_id}] decode returned OK, draining T2W...")

        # Step 3: Wait for T2W drain + WAV files
        time.sleep(drain_extra)

        # Step 4: Find new WAV files
        wavs_after = set(find_wav_files(self.output_dir))
        new_wavs = sorted(wavs_after - wavs_before, key=lambda p: os.path.getctime(p))
        self.result["wav_files"] = new_wavs

        # Step 5: Record first WAV timestamps
        if new_wavs:
            first_wav = new_wavs[0]
            self.result["client_timings_ns"]["first_wav_file_detected"] = (
                int(os.path.getctime(first_wav) * 1e9))
            wav_info = read_wav_params(first_wav)
            self.result["first_wav_info"] = wav_info
            if "num_samples" in wav_info and wav_info["num_samples"] > 0:
                self.result["client_timings_ns"]["first_valid_pcm"] = (
                    int(os.path.getmtime(first_wav) * 1e9))
                self.result["wav_valid"] = True
            else:
                self.result["wav_valid"] = False
            print(f"  [{self.session_id}] WAV: {os.path.basename(first_wav)} "
                  f"({wav_info.get('duration_s', 0):.1f}s)")
        else:
            self.result["wav_valid"] = False
            self.result["errors"].append("no WAV files produced")

        # Step 6: Collect E2E profiles
        self._collect_profiles()

        # Step 7: Compute client-observed intervals
        ct = self.result["client_timings_ns"]
        if ct.get("request_send") and ct.get("first_wav_file_detected"):
            ct["client_request_to_first_wav_file_ns"] = (
                ct["first_wav_file_detected"] - ct["request_send"])
        if ct.get("request_send") and ct.get("first_valid_pcm"):
            ct["client_request_to_first_valid_pcm_ns"] = (
                ct["first_valid_pcm"] - ct["request_send"])

        print(f"  [{self.session_id}] Complete: W0={'PRESENT' if self.result['w0_present'] else 'MISSING'}, "
              f"WAVs={len(new_wavs)}, errors={len(self.result['errors'])}")
        return self.result

    def _collect_profiles(self):
        """Collect e2e profile JSON files."""
        # Audio completion profiles
        audio_pattern = os.path.join(self.profile_dir, "e2e_*_audio.json")
        audio_files = sorted(glob.glob(audio_pattern))
        for f in audio_files:
            try:
                with open(f) as fh:
                    profile = json.load(fh)
                # Only keep profiles from this session (by creation time proximity)
                self.result["audio_profile"] = profile
                aw = profile.get("async_stages_ms", {})
                w0 = aw.get("wav_ready", 0)
                if w0 > 0:
                    self.result["w0_present"] = True
                    self.result["w0_value_ms"] = w0
                break  # Take first matching
            except Exception as e:
                self.result["errors"].append(f"Failed to parse {f}: {e}")

        # Partial profiles
        partial_pattern = os.path.join(self.profile_dir, "e2e_*.json")
        partial_files = [p for p in sorted(glob.glob(partial_pattern))
                         if not p.endswith("_audio.json")]
        for f in partial_files:
            try:
                with open(f) as fh:
                    self.result["partial_profile"] = json.load(fh)
                break
            except Exception as e:
                self.result["errors"].append(f"Failed to parse {f}: {e}")


# ──────────────────────────────────────────────────────────
# ABBA Pair Runner
# ──────────────────────────────────────────────────────────
class ABBAPairRunner:
    """Runs matched A/B pairs in ABBA block order."""

    def __init__(self, binary: str, model: str, base_output_dir: str,
                 host: str = "127.0.0.1", base_port: int = 8080,
                 ngl: int = 99, extra_args: list = None):
        self.binary = binary
        self.model = model
        self.base_output_dir = base_output_dir
        self.host = host
        self.base_port = base_port
        self.ngl = ngl
        self.extra_args = extra_args or []

    def run_pair(self, pair_idx: int, abba_block: int = 0) -> dict:
        """
        Run one ABBA block (A1, B1, B2, A2) = 4 measurements = 2 matched pairs.

        A = B6b OFF (OMNI_TTS_FIRST_CHUNK_STEP=10)
        B = B6b ON  (OMNI_TTS_FIRST_CHUNK_STEP=5)

        Returns dict with all 4 measurements.
        """
        block_dir = os.path.join(self.base_output_dir, f"abba_block_{abba_block:04d}")
        os.makedirs(block_dir, exist_ok=True)

        results = {}

        # A1: B6b OFF
        a1 = self._run_single(block_dir, "A1", abba_block * 4 + 0, b6b_on=False)
        results["A1"] = a1

        # B1: B6b ON
        b1 = self._run_single(block_dir, "B1", abba_block * 4 + 1, b6b_on=True)
        results["B1"] = b1

        # B2: B6b ON
        b2 = self._run_single(block_dir, "B2", abba_block * 4 + 2, b6b_on=True)
        results["B2"] = b2

        # A2: B6b OFF
        a2 = self._run_single(block_dir, "A2", abba_block * 4 + 3, b6b_on=False)
        results["A2"] = a2

        # Form pairs: (A1,B1) and (A2,B2)
        pair1 = {"off": a1, "on": b1, "pair_idx": pair_idx * 2}
        pair2 = {"off": a2, "on": b2, "pair_idx": pair_idx * 2 + 1}

        return {"block": abba_block, "pairs": [pair1, pair2],
                "block_dir": block_dir, "results": results}

    def _run_single(self, block_dir: str, label: str, session_id: int,
                    b6b_on: bool, drain_extra: float = SERVER_DRAIN_EXTRA) -> dict:
        """Run a single server instance with one decode cycle."""
        output_dir = os.path.join(block_dir, f"{label}_output")
        profile_dir = os.path.join(block_dir, f"{label}_profiles")
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(profile_dir, exist_ok=True)

        env = {
            "OMNI_TTS_FIRST_CHUNK_STEP": "5" if b6b_on else "10",
            "OMNI_E2E_PROFILE": "1",
            "OMNI_E2E_PROFILE_DIR": profile_dir,
        }

        server = ServerManager(
            self.binary, self.model,
            host=self.host, port=self.base_port,
            ngl=self.ngl, extra_args=self.extra_args,
        )

        print(f"\n{'='*60}")
        print(f"[{label}] B6b={'ON' if b6b_on else 'OFF'} session_id={session_id}")
        print(f"{'='*60}")

        if not server.start(env=env):
            return {"_error": "server_start_failed", "label": label,
                    "b6b_on": b6b_on}

        session = TestSession(server, output_dir, profile_dir, session_id)
        result = session.run(drain_extra=drain_extra)
        result["label"] = label
        result["b6b_on"] = b6b_on
        result["b6b_step"] = 5 if b6b_on else 10

        server.stop()
        return result


# ──────────────────────────────────────────────────────────
# W0 Correctness Validator
# ──────────────────────────────────────────────────────────
def validate_w0_correctness(results: list) -> dict:
    """
    Validate W0 correctness across all results.

    Required criteria:
      - W0 presence = 100%
      - wrong attribution = 0
      - stale accepted = 0
      - cross-request contamination = 0
      - critical global fallback = 0
      - audio_valid = 100%
    """
    total = len(results)
    if total == 0:
        return {"verdict": "NO_DATA", "checks": {}}

    w0_present = sum(1 for r in results if r.get("w0_present"))
    wav_valid = sum(1 for r in results if r.get("wav_valid"))
    errors = sum(1 for r in results if r.get("errors"))

    checks = {
        "w0_presence_pct": round(100.0 * w0_present / total, 1),
        "w0_presence_pass": w0_present == total,
        "audio_valid_pct": round(100.0 * wav_valid / total, 1),
        "audio_valid_pass": wav_valid == total,
        "error_count": errors,
        "error_free_pass": errors == 0,
        "total_requests": total,
    }

    all_pass = (checks["w0_presence_pass"] and checks["audio_valid_pass"]
                and checks["error_free_pass"])

    return {
        "verdict": "PASS" if all_pass else "FAIL",
        "checks": checks,
    }


# ──────────────────────────────────────────────────────────
# Matched Pair Statistics
# ──────────────────────────────────────────────────────────
def compute_pair_statistics(pair: dict) -> dict:
    """Compute all relevant statistics for one matched pair."""
    off = pair["off"]
    on = pair["on"]

    stats = {"pair_idx": pair.get("pair_idx", -1)}

    # Extract server-side timings
    off_ap = (off.get("audio_profile") or {}).get("async_stages_ms", {})
    on_ap = (on.get("audio_profile") or {}).get("async_stages_ms", {})
    off_pp = (off.get("partial_profile") or {}).get("sync_stages_ms", {})
    on_pp = (on.get("partial_profile") or {}).get("sync_stages_ms", {})

    # D2→G0
    off_d2 = off_pp.get("llm_first_speak_token", 0)
    off_g0 = off_pp.get("tts_wake", 0)
    on_d2 = on_pp.get("llm_first_speak_token", 0)
    on_g0 = on_pp.get("tts_wake", 0)
    if off_d2 > 0 and off_g0 > 0:
        stats["D2_to_G0_off_ms"] = off_g0 - off_d2
    if on_d2 > 0 and on_g0 > 0:
        stats["D2_to_G0_on_ms"] = on_g0 - on_d2
    if stats.get("D2_to_G0_off_ms") and stats.get("D2_to_G0_on_ms"):
        stats["D2_to_G0_delta_ms"] = stats["D2_to_G0_on_ms"] - stats["D2_to_G0_off_ms"]

    # D0→G3
    off_d0 = off_pp.get("llm_first_decode_step", off_pp.get("decode_loop_begin", 0))
    off_g3 = off_pp.get("talker_first_audio_token", 0)
    on_d0 = on_pp.get("llm_first_decode_step", on_pp.get("decode_loop_begin", 0))
    on_g3 = on_pp.get("talker_first_audio_token", 0)
    if off_d0 > 0 and off_g3 > 0:
        stats["D0_to_G3_off_ms"] = off_g3 - off_d0
    if on_d0 > 0 and on_g3 > 0:
        stats["D0_to_G3_on_ms"] = on_g3 - on_d0
    if stats.get("D0_to_G3_off_ms") and stats.get("D0_to_G3_on_ms"):
        stats["D0_to_G3_delta_ms"] = stats["D0_to_G3_on_ms"] - stats["D0_to_G3_off_ms"]

    # D0→W0
    off_w0 = off_ap.get("wav_ready", off.get("w0_value_ms", 0))
    on_w0 = on_ap.get("wav_ready", on.get("w0_value_ms", 0))
    if off_d0 > 0 and off_w0 > 0:
        stats["D0_to_W0_off_ms"] = off_w0 - off_d0
    if on_d0 > 0 and on_w0 > 0:
        stats["D0_to_W0_on_ms"] = on_w0 - on_d0
    if stats.get("D0_to_W0_off_ms") and stats.get("D0_to_W0_on_ms"):
        stats["D0_to_W0_delta_ms"] = stats["D0_to_W0_on_ms"] - stats["D0_to_W0_off_ms"]

    # R0→W0
    off_r0 = off_pp.get("request_received", 0)
    on_r0 = on_pp.get("request_received", 0)
    if off_r0 > 0 and off_w0 > 0:
        stats["R0_to_W0_off_ms"] = off_w0 - off_r0
    if on_r0 > 0 and on_w0 > 0:
        stats["R0_to_W0_on_ms"] = on_w0 - on_r0

    # Client-side: request→first_wav
    off_ct = off.get("client_timings_ns", {})
    on_ct = on.get("client_timings_ns", {})
    off_cw = off_ct.get("client_request_to_first_wav_file_ns", 0)
    on_cw = on_ct.get("client_request_to_first_wav_file_ns", 0)
    if off_cw > 0:
        stats["CLIENT_request_to_first_wav_off_ms"] = round(off_cw / 1e6, 1)
    if on_cw > 0:
        stats["CLIENT_request_to_first_wav_on_ms"] = round(on_cw / 1e6, 1)
    if off_cw > 0 and on_cw > 0:
        stats["CLIENT_request_to_first_wav_delta_ms"] = round((on_cw - off_cw) / 1e6, 1)

    # Client-side: request→first_valid_pcm
    off_cp = off_ct.get("client_request_to_first_valid_pcm_ns", 0)
    on_cp = on_ct.get("client_request_to_first_valid_pcm_ns", 0)
    if off_cp > 0:
        stats["CLIENT_request_to_first_pcm_off_ms"] = round(off_cp / 1e6, 1)
    if on_cp > 0:
        stats["CLIENT_request_to_first_pcm_on_ms"] = round(on_cp / 1e6, 1)
    if off_cp > 0 and on_cp > 0:
        stats["CLIENT_request_to_first_pcm_delta_ms"] = round((on_cp - off_cp) / 1e6, 1)

    return stats


def aggregate_pair_statistics(all_pairs: list) -> dict:
    """Aggregate statistics across all matched pairs."""
    metrics = [
        "D2_to_G0_delta_ms", "D0_to_G3_delta_ms", "D0_to_W0_delta_ms",
        "CLIENT_request_to_first_wav_delta_ms", "CLIENT_request_to_first_pcm_delta_ms",
    ]
    agg = {"num_pairs": len(all_pairs)}
    for m in metrics:
        values = [p["stats"].get(m) for p in all_pairs if p["stats"].get(m) is not None]
        if values:
            agg[f"{m}_n"] = len(values)
            agg[f"{m}_mean"] = round(statistics.mean(values), 1)
            agg[f"{m}_median"] = round(statistics.median(values), 1)
            if len(values) >= 2:
                agg[f"{m}_stdev"] = round(statistics.stdev(values), 1)
            agg[f"{m}_min"] = round(min(values), 1)
            agg[f"{m}_max"] = round(max(values), 1)
            win_count = sum(1 for v in values if v < 0)
            agg[f"{m}_win_rate_pct"] = round(100.0 * win_count / len(values), 1)
        else:
            agg[f"{m}_n"] = 0
    return agg


# ──────────────────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────────────────
def cmd_w8_correctness(args):
    """Run 30+ request W0 correctness across 5 categories."""
    print("=" * 70)
    print("W8_CORRECTNESS_30_PLUS: Multi-category W0 Correctness")
    print("=" * 70)

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    # Define workload categories
    categories = [
        {"name": "short_tts",  "count": 12, "media_type": 2, "desc": "Short TTS (text-only)"},
        {"name": "long_tts",   "count": 6,  "media_type": 2, "desc": "Long TTS (multi-round, repeated)"},
        {"name": "audio_text", "count": 6,  "media_type": 1, "desc": "Audio+text input"},
        {"name": "rapid_fire", "count": 6,  "media_type": 2, "desc": "Rapid-fire continuous"},
        # video+audio requires vision model — skip
    ]

    all_results = []
    session_counter = 0

    for cat in categories:
        print(f"\n--- Category: {cat['name']} ({cat['desc']}) — {cat['count']} requests ---")
        for i in range(cat["count"]):
            cat_dir = os.path.join(output_dir, cat["name"], f"req_{i:03d}")
            profile_dir = os.path.join(cat_dir, "profiles")
            wav_dir = os.path.join(cat_dir, "output")
            os.makedirs(profile_dir, exist_ok=True)
            os.makedirs(wav_dir, exist_ok=True)

            env = {
                "OMNI_TTS_FIRST_CHUNK_STEP": "10",  # baseline (B6b OFF)
                "OMNI_E2E_PROFILE": "1",
                "OMNI_E2E_PROFILE_DIR": profile_dir,
            }

            server = ServerManager(
                args.binary, args.model,
                host=args.host, port=args.port,
                ngl=args.ngl, extra_args=args.extra_args or [],
            )

            print(f"\n[{session_counter}] {cat['name']}/{i}: Starting server...")
            if not server.start(env=env):
                print(f"[{session_counter}] FAILED: server did not start")
                all_results.append({"_error": "server_start_failed", "session_id": session_counter})
                session_counter += 1
                continue

            # For long_tts: repeat omni_init+decode to simulate multi-round
            if cat["name"] == "long_tts":
                session = TestSession(server, wav_dir, profile_dir, session_counter)
                result = session.run(media_type=cat["media_type"], drain_extra=args.drain)
                # Multi-round: additional decodes (simulated via repeated omni_init)
                # Note: single-decode server limitation means we can't do true multi-round
                # within one server process. We do separate servers for each "round."
                result["category"] = cat["name"]
                result["category_index"] = i
                all_results.append(result)
            elif cat["name"] == "rapid_fire":
                session = TestSession(server, wav_dir, profile_dir, session_counter)
                result = session.run(media_type=cat["media_type"], stream=True,
                                     drain_extra=args.drain)
                result["category"] = cat["name"]
                result["category_index"] = i
                all_results.append(result)
            else:
                session = TestSession(server, wav_dir, profile_dir, session_counter)
                result = session.run(media_type=cat["media_type"], drain_extra=args.drain)
                result["category"] = cat["name"]
                result["category_index"] = i
                all_results.append(result)

            server.stop()
            session_counter += 1

    # Validate
    validation = validate_w0_correctness(all_results)
    print(f"\n{'='*70}")
    print(f"W8 Correctness Verdict: {validation['verdict']}")
    for k, v in validation["checks"].items():
        print(f"  {k}: {v}")

    # Save report
    report_path = os.path.join(output_dir, "w8_correctness_report.json")
    report = {
        "timestamp": datetime.now().isoformat(),
        "verdict": validation["verdict"],
        "checks": validation["checks"],
        "results": all_results,
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Report saved: {report_path}")

    return 0 if validation["verdict"] == "PASS" else 1


def cmd_w9_overhead(args):
    """Run 20-pair F6_TIMING=0 vs summary matched E2E overhead gate."""
    print("=" * 70)
    print("W9_MATCHED_E2E_OVERHEAD: F6_TIMING=0 vs summary (20 pairs)")
    print("=" * 70)

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    pairs = []
    for i in range(args.pairs or 20):
        pair_dir = os.path.join(output_dir, f"pair_{i:03d}")
        os.makedirs(pair_dir, exist_ok=True)

        pair_result = {"pair_idx": i}

        # A: profiling OFF (OMNI_E2E_PROFILE not set)
        a_dir = os.path.join(pair_dir, "A_timing_off")
        a_profile_dir = os.path.join(a_dir, "profiles")
        a_wav_dir = os.path.join(a_dir, "output")
        os.makedirs(a_profile_dir, exist_ok=True)
        os.makedirs(a_wav_dir, exist_ok=True)

        env_a = {"OMNI_TTS_FIRST_CHUNK_STEP": "10"}

        server_a = ServerManager(args.binary, args.model, host=args.host,
                                 port=args.port, ngl=args.ngl,
                                 extra_args=args.extra_args or [])
        if server_a.start(env=env_a):
            session_a = TestSession(server_a, a_wav_dir, a_profile_dir, i * 2)
            pair_result["timing_off"] = session_a.run(drain_extra=args.drain)
            server_a.stop()
        else:
            pair_result["timing_off"] = {"_error": "server_start_failed"}

        # B: profiling ON (OMNI_E2E_PROFILE=1)
        b_dir = os.path.join(pair_dir, "B_timing_full")
        b_profile_dir = os.path.join(b_dir, "profiles")
        b_wav_dir = os.path.join(b_dir, "output")
        os.makedirs(b_profile_dir, exist_ok=True)
        os.makedirs(b_wav_dir, exist_ok=True)

        env_b = {
            "OMNI_TTS_FIRST_CHUNK_STEP": "10",
            "OMNI_E2E_PROFILE": "1",
            "OMNI_E2E_PROFILE_DIR": b_profile_dir,
        }

        server_b = ServerManager(args.binary, args.model, host=args.host,
                                 port=args.port, ngl=args.ngl,
                                 extra_args=args.extra_args or [])
        if server_b.start(env=env_b):
            session_b = TestSession(server_b, b_wav_dir, b_profile_dir, i * 2 + 1)
            pair_result["timing_full"] = session_b.run(drain_extra=args.drain)
            server_b.stop()
        else:
            pair_result["timing_full"] = {"_error": "server_start_failed"}

        pairs.append(pair_result)
        print(f"  Pair {i}: OFF={pair_result.get('timing_off',{}).get('w0_present')}, "
              f"FULL={pair_result.get('timing_full',{}).get('w0_present')}")

    # Compute overhead: compare D0→W0, client first audio between OFF and FULL
    overhead_stats = []
    for p in pairs:
        off = p.get("timing_off", {})
        full = p.get("timing_full", {})
        off_ct = off.get("client_timings_ns", {})
        full_ct = full.get("client_timings_ns", {})

        stat = {"pair_idx": p["pair_idx"]}

        # Client request→first_wav difference
        off_wav = off_ct.get("client_request_to_first_wav_file_ns", 0)
        full_wav = full_ct.get("client_request_to_first_wav_file_ns", 0)
        if off_wav > 0 and full_wav > 0:
            stat["overhead_wav_ms"] = round((full_wav - off_wav) / 1e6, 1)

        # Compare W0 values
        off_w0 = off.get("w0_value_ms", 0)
        full_w0 = full.get("w0_value_ms", 0)
        if off_w0 > 0 and full_w0 > 0:
            stat["overhead_W0_ms"] = round(full_w0 - off_w0, 1)

        overhead_stats.append(stat)

    # Aggregate
    if overhead_stats:
        wav_overheads = [s["overhead_wav_ms"] for s in overhead_stats
                        if "overhead_wav_ms" in s]
        w0_overheads = [s["overhead_W0_ms"] for s in overhead_stats
                       if "overhead_W0_ms" in s]

        print(f"\nOverhead Summary:")
        if wav_overheads:
            print(f"  Client WAV overhead: mean={statistics.mean(wav_overheads):.1f}ms, "
                  f"median={statistics.median(wav_overheads):.1f}ms")
        if w0_overheads:
            print(f"  W0 overhead: mean={statistics.mean(w0_overheads):.1f}ms, "
                  f"median={statistics.median(w0_overheads):.1f}ms")

    # Save report
    report_path = os.path.join(output_dir, "w9_overhead_report.json")
    report = {
        "timestamp": datetime.now().isoformat(),
        "pairs": pairs,
        "overhead_stats": overhead_stats,
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Report saved: {report_path}")

    return 0


def cmd_w10_ab(args):
    """Run 120+ strict matched pairs B6b ON vs OFF with ABBA ordering."""
    num_pairs = args.pairs or 120
    num_blocks = (num_pairs + 1) // 2  # Each ABBA block produces 2 matched pairs

    print("=" * 70)
    print(f"TRUE_D0_TO_W0_AB + TRUE_CLIENT_FIRST_AUDIO_AB: {num_pairs} pairs "
          f"({num_blocks} ABBA blocks)")
    print("=" * 70)

    runner = ABBAPairRunner(
        binary=args.binary,
        model=args.model,
        base_output_dir=args.output_dir,
        host=args.host,
        base_port=args.port,
        ngl=args.ngl,
        extra_args=args.extra_args or [],
    )

    all_pairs = []
    for block_idx in range(num_blocks):
        print(f"\n{'#'*60}")
        print(f"# ABBA Block {block_idx}/{num_blocks}")
        print(f"{'#'*60}")

        block_result = runner.run_pair(pair_idx=block_idx, abba_block=block_idx)

        for pair in block_result["pairs"]:
            pair["stats"] = compute_pair_statistics(pair)
            all_pairs.append(pair)

        # Print block summary
        for pair in block_result["pairs"]:
            stats = pair["stats"]
            print(f"  Pair {stats.get('pair_idx')}: "
                  f"D2→G0 Δ={stats.get('D2_to_G0_delta_ms', 'N/A')}ms, "
                  f"D0→W0 Δ={stats.get('D0_to_W0_delta_ms', 'N/A')}ms, "
                  f"Client WAV Δ={stats.get('CLIENT_request_to_first_wav_delta_ms', 'N/A')}ms")

    # Aggregate
    agg = aggregate_pair_statistics(all_pairs)
    print(f"\n{'='*70}")
    print(f"Aggregate Statistics ({agg['num_pairs']} pairs)")
    print(f"{'='*70}")
    for k, v in sorted(agg.items()):
        print(f"  {k}: {v}")

    # B6B_TRUE_E2E_GATE decision
    d0w0_delta = agg.get("D0_to_W0_delta_ms_median", None)
    client_delta = agg.get("CLIENT_request_to_first_wav_delta_ms_median", None)
    d0w0_win = agg.get("D0_to_W0_delta_ms_win_rate_pct", None)
    client_win = agg.get("CLIENT_request_to_first_wav_delta_ms_win_rate_pct", None)

    gate_pass = False
    if d0w0_delta is not None and client_delta is not None:
        gate_pass = (d0w0_delta < 0 and client_delta < 0 and
                     (d0w0_win or 0) >= 95.0 and (client_win or 0) >= 95.0)
        print(f"\nB6B_TRUE_E2E_GATE: {'PASS' if gate_pass else 'NOT_REACHED'}")
        print(f"  D0→W0 median Δ = {d0w0_delta}ms (win_rate={d0w0_win}%)")
        print(f"  Client→first_wav median Δ = {client_delta}ms (win_rate={client_win}%)")
    else:
        print(f"\nB6B_TRUE_E2E_GATE: NOT_REACHED (insufficient data)")

    # Save report
    report_path = os.path.join(args.output_dir, "w10_ab_report.json")
    report = {
        "timestamp": datetime.now().isoformat(),
        "num_pairs": len(all_pairs),
        "aggregate": agg,
        "b6b_true_e2e_gate": "PASS" if gate_pass else ("NOT_REACHED" if d0w0_delta is not None else "INSUFFICIENT_DATA"),
        "pairs": all_pairs,
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Report saved: {report_path}")

    return 0 if gate_pass or d0w0_delta is not None else 1


# ──────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="F6 E2E A/B Test Harness — Sequential Server, ABBA Ordering")
    subparsers = parser.add_subparsers(dest="command", help="Test command")

    # Common args
    def add_common_args(p):
        p.add_argument("--binary", required=True, help="Path to llama-omni-server binary")
        p.add_argument("--model", required=True, help="Path to GGUF model")
        p.add_argument("--host", default="127.0.0.1", help="Server listen host")
        p.add_argument("--port", type=int, default=8080, help="Server listen port")
        p.add_argument("--ngl", type=int, default=99, help="GPU layers")
        p.add_argument("--output-dir", required=True, help="Output directory for results")
        p.add_argument("--drain", type=float, default=SERVER_DRAIN_EXTRA,
                       help="Extra seconds to wait for T2W drain after decode")
        p.add_argument("--extra-args", nargs="*", default=[],
                       help="Extra arguments to pass to server binary")

    # w8-correctness
    p_w8 = subparsers.add_parser("w8-correctness", help="30+ request W0 correctness")
    add_common_args(p_w8)

    # w9-overhead
    p_w9 = subparsers.add_parser("w9-overhead", help="E2E overhead gate (F6_TIMING=0 vs summary)")
    add_common_args(p_w9)
    p_w9.add_argument("--pairs", type=int, default=20, help="Number of pairs (default: 20)")

    # w10-ab
    p_w10 = subparsers.add_parser("w10-ab", help="120-pair B6b matched A/B")
    add_common_args(p_w10)
    p_w10.add_argument("--pairs", type=int, default=120, help="Number of pairs (default: 120)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "w8-correctness":
        return cmd_w8_correctness(args)
    elif args.command == "w9-overhead":
        return cmd_w9_overhead(args)
    elif args.command == "w10-ab":
        return cmd_w10_ab(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
