#!/usr/bin/env python3
"""Demo D4-D12 test harness — corrected protocol.

Key protocol findings:
  - session.init: {"mode":"turn_based","use_tts":true}  (use_tts defaults true)
  - input.append: input.use_tts_template=true for TTS, input.tts.enabled=true also works
  - Messages content[]: type=image/audio with data=B64 field (extract_*_b64 reads data/base64 keys)
  - Streaming: input.streaming=true (defaults true)
"""

import asyncio
import json
import sys
import os
import time
import hashlib
import base64
import wave
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    import websockets
except ImportError:
    print("pip install websockets", file=sys.stderr)
    sys.exit(1)

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("harness")

# ── Config ──
GATEWAY_URL = "ws://127.0.0.1:18006/v1/realtime"
GATEWAY_HTTP = "http://127.0.0.1:18006"
WORKER_URL = "http://127.0.0.1:22400"
CASES_DIR = Path("/workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/cases")
OUTPUT_DIR = Path("/workspace/llama.cpp-omni-session-fix/demo_runs/demo_d4_d12")
COMMON_DIR = CASES_DIR / "common"
REF_AUDIO_PATH = COMMON_DIR / "ref_audio/BH-Ref-HT-F224-Ref06_82_U001_话题_3_348s-355s.wav"

TIMEOUT_S = 180
SAMPLE_RATE = 24000

# ── Helpers ──

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

def load_media_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")

def pcm_duration_s(pcm_bytes: bytes) -> float:
    return len(pcm_bytes) / (SAMPLE_RATE * 2)

def save_wav(path: str, pcm_bytes: bytes):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)

# ── Wait for idle ──

async def wait_worker_idle(timeout: float = 30):
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient() as client:
        while time.monotonic() < deadline:
            try:
                r = await client.get(f"{WORKER_URL}/health", timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("worker_status") == "idle":
                        r2 = await client.get(f"{GATEWAY_HTTP}/status", timeout=5)
                        if r2.status_code == 200:
                            gs = r2.json()
                            if gs.get("busy_workers", 0) == 0 and gs.get("queue_length", 0) == 0:
                                return True
            except Exception:
                pass
            await asyncio.sleep(1)
    log.warning("Timeout waiting for worker idle")
    return False


# ── GatewaySession ──

class GatewaySession:
    def __init__(self, mode: str = "chat"):
        self.mode = mode
        self.events: List[Dict[str, Any]] = []
        self.audio_chunks: List[bytes] = []
        self.text_chunks: List[str] = []
        self.ws: Optional[Any] = None
        self.started_at: float = 0
        self.ended_at: float = 0

    async def connect(self):
        self.started_at = time.monotonic()
        url = f"{GATEWAY_URL}?mode={self.mode}"
        self.ws = await websockets.connect(url, max_size=128 * 1024 * 1024)
        # Drain queue messages
        while True:
            try:
                msg = await asyncio.wait_for(self.ws.recv(), timeout=2)
                evt = json.loads(msg)
                self.events.append(evt)
                if evt.get("type") in ("session.queue_done", "error"):
                    break
            except asyncio.TimeoutError:
                break
        return self

    async def send_init(self, init_payload: dict):
        """Send session.init (always first message)."""
        await self.ws.send(json.dumps({
            "type": "session.init",
            "payload": init_payload,
        }))
        # Wait for session.created
        evt = await self.recv()
        ctype = evt.get("type", "")
        inner = evt.get("event", {}) if isinstance(evt.get("event"), dict) else {}
        itype = inner.get("type", "")
        if not (ctype.startswith("session.") or itype.startswith("session.")):
            log.warning(f"  Expected session.created, got: type={ctype}, inner={itype}")

    async def send_input(self, input_data: dict):
        await self.ws.send(json.dumps({
            "type": "input.append",
            "input": input_data,
        }))

    async def recv(self) -> dict:
        raw = await asyncio.wait_for(self.ws.recv(), timeout=TIMEOUT_S)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        event = json.loads(raw)
        self.events.append(event)
        self._collect_media(event)
        return event

    def _collect_media(self, event: dict):
        # Direct format
        etype = event.get("type", "")
        if etype == "response.output.delta":
            kind = event.get("kind", "")
            if kind == "audio":
                b64 = event.get("audio") or event.get("data") or ""
                if b64:
                    self.audio_chunks.append(base64.b64decode(b64))
            elif kind == "text":
                delta = event.get("delta") or event.get("text") or ""
                if delta:
                    self.text_chunks.append(delta)

        # Nested format
        inner = event.get("event", {})
        if isinstance(inner, dict):
            itype = inner.get("type", "")
            if itype == "response.output.delta":
                ikind = inner.get("kind", "")
                if ikind == "audio":
                    b64 = inner.get("audio") or inner.get("data") or ""
                    if b64:
                        self.audio_chunks.append(base64.b64decode(b64))
                elif ikind == "text":
                    delta = inner.get("delta") or inner.get("text") or ""
                    if delta:
                        self.text_chunks.append(delta)

        # Flat text
        if not self.text_chunks:
            for k in ("text", "content"):
                t = event.get(k, "")
                if isinstance(t, str) and t:
                    self.text_chunks.append(t)
                    break

    async def recv_until(self, stop_types: set, timeout: float = TIMEOUT_S) -> List[dict]:
        results = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                evt = await asyncio.wait_for(self.recv(), timeout=min(remaining, 60))
                results.append(evt)
                etype = evt.get("type", "")
                if etype in stop_types:
                    break
                inner = evt.get("event", {})
                if isinstance(inner, dict) and inner.get("type") in stop_types:
                    break
            except (asyncio.TimeoutError, Exception):
                break
        return results

    async def close(self):
        self.ended_at = time.monotonic()
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass

    @property
    def elapsed_s(self) -> float:
        return self.ended_at - self.started_at

    @property
    def combined_audio(self) -> bytes:
        return b"".join(self.audio_chunks)

    @property
    def combined_text(self) -> str:
        return "".join(self.text_chunks)

    @property
    def audio_duration_s(self) -> float:
        if not self.audio_chunks:
            return 0.0
        return pcm_duration_s(self.combined_audio)


# ── Test Procs ──

async def _chat_turn(s: GatewaySession, prompt: str, use_tts: bool = False, max_tokens: int = 80) -> dict:
    """Single turn in an existing chat session."""
    inp: Dict[str, Any] = {
        "messages": [{"role": "user", "content": prompt}],
        "streaming": True,
        "generation": {"max_new_tokens": max_tokens},
    }
    if use_tts:
        inp["use_tts_template"] = True

    await s.send_input(inp)
    _ = await s.recv_until({"session.closed", "response.done", "error", "response.completed"})
    return {
        "text": s.combined_text[-300:],
        "text_len": len(s.combined_text),
        "audio_chunks": len(s.audio_chunks),
    }


async def test_text_chat(gate: str, prompt: str) -> dict:
    await wait_worker_idle()
    s = GatewaySession(mode="chat")
    await s.connect()
    await s.send_init({"mode": "turn_based", "use_tts": False})
    await s.send_input({
        "messages": [{"role": "user", "content": prompt}],
        "streaming": True,
        "generation": {"max_new_tokens": 80},
    })
    _ = await s.recv_until({"session.closed", "response.done", "error"})
    await s.close()
    return {
        "gate": gate, "text": s.combined_text, "text_len": len(s.combined_text),
        "events": len(s.events), "elapsed_s": round(s.elapsed_s, 2),
        "success": len(s.combined_text) > 0,
    }


async def test_image_understanding() -> dict:
    img_path = COMMON_DIR / "images/image.png"
    if not img_path.exists():
        return {"gate": "D4", "success": False, "error": f"Missing: {img_path}"}

    await wait_worker_idle()
    img_b64 = load_media_b64(str(img_path))
    s = GatewaySession(mode="chat")
    await s.connect()
    await s.send_init({"mode": "turn_based", "use_tts": False})
    await s.send_input({
        "messages": [{"role": "user", "content": [
            {"type": "image", "data": img_b64},
            {"type": "text", "text": "这是什么图片？简短回答。"},
        ]}],
        "streaming": True,
        "generation": {"max_new_tokens": 100},
    })
    _ = await s.recv_until({"session.closed", "response.done", "error"})
    await s.close()
    return {
        "gate": "D4", "text": s.combined_text, "text_len": len(s.combined_text),
        "events": len(s.events), "elapsed_s": round(s.elapsed_s, 2),
        "success": len(s.combined_text) > 0,
    }


async def test_audio_understanding() -> dict:
    audio_path = COMMON_DIR / "user_audio/000_user_audio0.wav"
    if not audio_path.exists():
        return {"gate": "D5", "success": False, "error": f"Missing: {audio_path}"}

    await wait_worker_idle()
    audio_b64 = load_media_b64(str(audio_path))
    s = GatewaySession(mode="chat")
    await s.connect()
    await s.send_init({"mode": "turn_based", "use_tts": False})
    await s.send_input({
        "messages": [{"role": "user", "content": [
            {"type": "audio", "data": audio_b64},
            {"type": "text", "text": "请复述用户说的话。"},
        ]}],
        "streaming": True,
        "generation": {"max_new_tokens": 200},
    })
    _ = await s.recv_until({"session.closed", "response.done", "error"})
    await s.close()
    return {
        "gate": "D5", "text": s.combined_text, "text_len": len(s.combined_text),
        "events": len(s.events), "elapsed_s": round(s.elapsed_s, 2),
        "success": len(s.combined_text) > 0,
    }


async def test_duplex_basic() -> dict:
    """D6: Duplex (mode=video) with audio input."""
    audio_path = COMMON_DIR / "user_audio/000_user_audio0.wav"
    if not audio_path.exists():
        return {"gate": "D6", "success": False, "error": f"Missing: {audio_path}"}

    await wait_worker_idle()
    audio_b64 = load_media_b64(str(audio_path))
    ref_b64 = load_media_b64(str(REF_AUDIO_PATH)) if REF_AUDIO_PATH.exists() else None

    s = GatewaySession(mode="video")
    await s.connect()

    init_payload: Dict[str, Any] = {
        "mode": "full_duplex",
        "use_tts": True,
        "system_prompt": "You are a helpful voice assistant. Keep responses short.",
        "config": {"force_listen_count": 0},  # Disable force-listen for single-turn test
    }
    if ref_b64:
        init_payload["voice"] = {"ref_audio_base64": ref_b64}

    await s.send_init(init_payload)

    # Full-duplex uses direct audio_base64 field (NOT messages[])
    await s.send_input({
        "audio_base64": audio_b64,
        "text": "请复述用户说的话并简短回应。",
        "use_tts_template": True,
        "streaming": True,
        "generation": {"max_new_tokens": 200},
    })
    _ = await s.recv_until({"session.closed", "response.done", "error", "response.completed"}, timeout=120)
    await s.close()

    result = {
        "gate": "D6", "text": s.combined_text, "text_len": len(s.combined_text),
        "audio_chunks": len(s.audio_chunks), "audio_duration_s": round(s.audio_duration_s, 3),
        "events": len(s.events), "elapsed_s": round(s.elapsed_s, 2),
    }
    result["success"] = len(s.combined_text) > 0
    return result


async def test_tts_output(run_dir: Path) -> dict:
    """D7: TTS output completeness."""
    await wait_worker_idle()
    ref_b64 = load_media_b64(str(REF_AUDIO_PATH)) if REF_AUDIO_PATH.exists() else None

    s = GatewaySession(mode="chat")
    await s.connect()
    await s.send_init({"mode": "turn_based", "use_tts": True})

    inp: Dict[str, Any] = {
        "messages": [{"role": "user", "content": "请用中文说：今天天气真好，适合出去玩。"}],
        "use_tts_template": True,
        "streaming": True,
        "generation": {"max_new_tokens": 200},
    }
    if ref_b64:
        inp["voice"] = {"ref_audio_base64": ref_b64}

    await s.send_input(inp)
    _ = await s.recv_until({"session.closed", "response.done", "error", "response.completed"})
    await s.close()

    result = {
        "gate": "D7", "text": s.combined_text, "text_len": len(s.combined_text),
        "audio_chunks": len(s.audio_chunks), "audio_bytes": len(s.combined_audio),
        "audio_duration_s": round(s.audio_duration_s, 3),
        "events": len(s.events), "elapsed_s": round(s.elapsed_s, 2),
    }
    if s.audio_chunks:
        wav_path = run_dir / "D7_tts_output.wav"
        save_wav(str(wav_path), s.combined_audio)
        result["wav_path"] = str(wav_path)
        result["wav_sha256"] = sha256_hex(s.combined_audio)
        result["wav_size"] = len(s.combined_audio)
    result["success"] = s.audio_duration_s > 0.1
    return result


async def test_streaming_text() -> dict:
    """D8: Streaming text-only."""
    await wait_worker_idle()
    s = GatewaySession(mode="chat")
    await s.connect()
    await s.send_init({"mode": "turn_based", "use_tts": False})
    await s.send_input({
        "messages": [{"role": "user", "content": "简单介绍一下上海。"}],
        "streaming": True,
        "generation": {"max_new_tokens": 100},
    })
    _ = await s.recv_until({"session.closed", "response.done", "error", "response.completed"})
    await s.close()
    return {
        "gate": "D8", "text": s.combined_text, "text_len": len(s.combined_text),
        "text_chunks": len(s.text_chunks), "events": len(s.events),
        "elapsed_s": round(s.elapsed_s, 2),
        "success": len(s.text_chunks) > 0,
    }


async def test_streaming_with_tts(run_dir: Path) -> dict:
    """D9: Streaming with TTS audio."""
    await wait_worker_idle()
    ref_b64 = load_media_b64(str(REF_AUDIO_PATH)) if REF_AUDIO_PATH.exists() else None

    s = GatewaySession(mode="chat")
    await s.connect()
    await s.send_init({"mode": "turn_based", "use_tts": True})

    inp: Dict[str, Any] = {
        "messages": [{"role": "user", "content": "请用中文说：欢迎使用语音助手。"}],
        "use_tts_template": True,
        "streaming": True,
        "generation": {"max_new_tokens": 100},
    }
    if ref_b64:
        inp["voice"] = {"ref_audio_base64": ref_b64}

    await s.send_input(inp)
    _ = await s.recv_until({"session.closed", "response.done", "error", "response.completed"})
    await s.close()

    result = {
        "gate": "D9", "text": s.combined_text, "text_len": len(s.combined_text),
        "audio_chunks": len(s.audio_chunks), "audio_duration_s": round(s.audio_duration_s, 3),
        "events": len(s.events), "elapsed_s": round(s.elapsed_s, 2),
    }
    if s.audio_chunks:
        wav_path = run_dir / "D9_streaming_tts.wav"
        save_wav(str(wav_path), s.combined_audio)
        result["wav_path"] = str(wav_path)
        result["wav_sha256"] = sha256_hex(s.combined_audio)
    result["success"] = len(s.audio_chunks) > 0
    return result


async def test_streaming_audio_input(run_dir: Path) -> dict:
    """D10: Audio input → streaming TTS response."""
    audio_path = COMMON_DIR / "user_audio/当出现植物大战僵尸的时候提醒我.wav"
    if not audio_path.exists():
        audio_path = COMMON_DIR / "user_audio/000_user_audio0.wav"

    await wait_worker_idle()
    audio_b64 = load_media_b64(str(audio_path))
    ref_b64 = load_media_b64(str(REF_AUDIO_PATH)) if REF_AUDIO_PATH.exists() else None

    s = GatewaySession(mode="chat")
    await s.connect()
    await s.send_init({"mode": "turn_based", "use_tts": True})

    inp: Dict[str, Any] = {
        "messages": [{"role": "user", "content": [
            {"type": "audio", "data": audio_b64},
            {"type": "text", "text": "请复述然后简短回应。"},
        ]}],
        "use_tts_template": True,
        "streaming": True,
        "generation": {"max_new_tokens": 200},
    }
    if ref_b64:
        inp["voice"] = {"ref_audio_base64": ref_b64}

    await s.send_input(inp)
    _ = await s.recv_until({"session.closed", "response.done", "error", "response.completed"})
    await s.close()

    result = {
        "gate": "D10", "text": s.combined_text, "text_len": len(s.combined_text),
        "audio_chunks": len(s.audio_chunks), "audio_duration_s": round(s.audio_duration_s, 3),
        "events": len(s.events), "elapsed_s": round(s.elapsed_s, 2),
    }
    if s.audio_chunks:
        wav_path = run_dir / "D10_audio_input_tts.wav"
        save_wav(str(wav_path), s.combined_audio)
        result["wav_path"] = str(wav_path)
        result["wav_sha256"] = sha256_hex(s.combined_audio)
    result["success"] = len(s.audio_chunks) > 0 and len(s.combined_text) > 0
    return result


async def test_multi_turn() -> dict:
    """D11: Multi-turn conversation (3 turns in one session)."""
    await wait_worker_idle()
    s = GatewaySession(mode="chat")
    await s.connect()
    await s.send_init({"mode": "turn_based", "use_tts": False})

    turns = [
        ("你好，今天天气怎么样？", False),
        ("那适合出门吗？", False),
        ("谢谢你的建议。", False),
    ]

    turn_results = []
    for i, (text, use_tts) in enumerate(turns):
        inp: Dict[str, Any] = {
            "messages": [{"role": "user", "content": text}],
            "streaming": True,
            "generation": {"max_new_tokens": 80},
        }
        if use_tts:
            inp["use_tts_template"] = True

        await s.send_input(inp)
        _ = await s.recv_until({"session.closed", "response.done", "error", "response.completed"})
        current_text = s.combined_text
        turn_results.append({
            "turn": i + 1, "input": text,
            "output": current_text[-300:],
            "success": len(current_text) > 0,
        })

        # Stop if session closed
        if any(
            e.get("type") == "session.closed" or
            (isinstance(e.get("event"), dict) and e["event"].get("type") == "session.closed")
            for e in s.events[-3:]
        ):
            break

    await s.close()
    return {
        "gate": "D11", "turns_total": len(turns),
        "turns_completed": len(turn_results),
        "turn_results": turn_results,
        "text_total": len(s.combined_text),
        "elapsed_s": round(s.elapsed_s, 2),
        "success": all(r["success"] for r in turn_results),
    }


# ── D12 Continuous Stability ──

async def test_continuous_stability(duration_m: int = 30) -> dict:
    """D12: Continuous sequential sessions for N minutes."""
    start = time.monotonic()
    deadline = start + duration_m * 60
    sessions_ok = 0
    sessions_fail = 0
    session_results = []
    consecutive_fails = 0

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining < 15:
            break

        # Wait for worker idle with cooldown — ensure server session fully released
        cooled_down = await wait_worker_idle(timeout=30)
        if not cooled_down:
            # Worker stuck — wait extra and retry
            await asyncio.sleep(10)
            continue

        # Extra cooldown to let server release session resources
        await asyncio.sleep(3)

        s = GatewaySession(mode="chat")
        try:
            await s.connect()
            await s.send_init({"mode": "turn_based", "use_tts": False})
            await s.send_input({
                "messages": [{"role": "user", "content": "说：你好。"}],
                "streaming": True,
                "generation": {"max_new_tokens": 20},
            })
            _ = await s.recv_until({"session.closed", "response.done", "error"}, timeout=90)
            ok = len(s.combined_text) > 0
            if ok:
                sessions_ok += 1
                consecutive_fails = 0
            else:
                sessions_fail += 1
                consecutive_fails += 1
            session_results.append({
                "n": sessions_ok + sessions_fail, "ok": ok,
                "text": s.combined_text[:80],
                "elapsed_s": round(s.elapsed_s, 2),
                "remaining_s": round(deadline - time.monotonic(), 0),
            })
        except Exception as e:
            sessions_fail += 1
            consecutive_fails += 1
            session_results.append({
                "n": sessions_ok + sessions_fail, "ok": False,
                "error": str(e)[:200],
                "remaining_s": round(deadline - time.monotonic(), 0),
            })
        finally:
            try:
                await s.close()
            except Exception:
                pass

        # Abort early if repeated failures indicate systemic issue
        if consecutive_fails >= 5:
            log.error(f"D12: {consecutive_fails} consecutive failures — aborting stability test")
            break

        # Cooldown between sessions
        await asyncio.sleep(5)

    return {
        "gate": "D12", "duration_m": duration_m,
        "total": sessions_ok + sessions_fail, "ok": sessions_ok, "fail": sessions_fail,
        "success_rate": f"{sessions_ok}/{sessions_ok + sessions_fail}",
        "sessions": session_results,
    }


# ── Main ──

async def run_all(include_d12: bool = True, d12_minutes: int = 30, gates: str = "all"):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"run_id": run_id, "started": ts(), "results": {}}

    requested = set(g.strip() for g in gates.split(",")) if gates != "all" else None

    async def run_if(name, fn, *args):
        if requested is None or name in requested:
            log.info(f"── {name} ──")
            try:
                r = await fn(*args)
                manifest["results"][name] = r
                icon = "✅" if r.get("success") else "❌"
                xtra = ""
                if r.get("text"):
                    xtra = f" text={r['text'][:60]}..."
                if r.get("audio_chunks"):
                    xtra += f" audio={r['audio_chunks']}ch/{r.get('audio_duration_s','?')}s"
                log.info(f"  {icon} {name} {xtra}")
            except Exception as e:
                log.error(f"  ❌ {name}: {e}")
                manifest["results"][name] = {"gate": name, "success": False, "error": str(e)[:300]}
        else:
            log.info(f"── {name} (skipped) ──")

    # Run turn_based gates first (shared context reuse), then duplex (creates new context).
    # D6 duplex mode switches the shared context; subsequent turn_based would need
    # a new model load. Run D6 last to avoid mode-switch overhead.
    await run_if("D1-D3", test_text_chat, "D1-D3", "用一句话介绍北京。")
    await run_if("D4", test_image_understanding)
    await run_if("D5", test_audio_understanding)
    await run_if("D7", test_tts_output, run_dir)
    await run_if("D8", test_streaming_text)
    await run_if("D9", test_streaming_with_tts, run_dir)
    await run_if("D10", test_streaming_audio_input, run_dir)
    await run_if("D11", test_multi_turn)
    # Duplex last — creates its own omni context (different mode)
    await run_if("D6", test_duplex_basic)

    if include_d12:
        await run_if("D12", test_continuous_stability, d12_minutes)

    manifest["finished"] = ts()
    passed = sum(1 for v in manifest["results"].values() if isinstance(v, dict) and v.get("success"))
    total = len(manifest["results"])
    manifest["summary"] = {"passed": passed, "total": total, "pass_rate": f"{passed}/{total}"}

    manifest_path = run_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)

    log.info(f"{'='*60}")
    log.info(f"Results: {run_dir}   Pass: {passed}/{total}")
    for gate, r in manifest["results"].items():
        icon = "✅" if r.get("success") else "❌"
        xtra = ""
        if r.get("text"):
            xtra = f" text={r['text'][:60]}"
        if r.get("audio_chunks"):
            xtra += f" audio={r['audio_chunks']}ch/{r.get('audio_duration_s','?')}s"
        log.info(f"  {icon} {gate}{xtra}")
    log.info(f"{'='*60}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-d12", action="store_true")
    parser.add_argument("--d12-minutes", type=int, default=30)
    parser.add_argument("--gates", type=str, default="all")
    args = parser.parse_args()
    asyncio.run(run_all(include_d12=not args.no_d12, d12_minutes=args.d12_minutes, gates=args.gates))
