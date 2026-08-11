"""
WebSocket adapter for benchmark_client.py.

Implements ProtocolAdapter interface, translating HTTP /v1/stream semantics
to WebSocket /backend protocol used by llama-omni-server (frozen binary bdd4550).

Status: IMPLEMENTED for turn_based TTS sessions.
Limitation: Each decode_stream() creates an independent WS session.
            Text prompt is fixed per adapter instance (no prefill-based generation).

Field mapping:
  HTTP /v1/stream/decode        →  WS /backend
  ─────────────────────────     ──────────────────
  POST /v1/stream/omni_init     →  session.init (sent per decode_stream)
  POST /v1/stream/decode        →  input.append (messages format)
  SSE data: {"content":"..."}   →  response.output.delta (kind=text)
  SSE data: {"is_listen":true}  →  response.output.delta (kind=audio)
  SSE data: [DONE]              →  response.done

Usage:
    cd /workspace/llama.cpp-omni-official-eval/competition
    PYTHONPATH=/workspace/llama.cpp-omni-session-fix/submission/adapters \
    python3 benchmark_client.py --adapter ws --url ws://localhost:8080/backend -c 1 -n 5

Author: CC auto-generated for thread-lifecycle investigation
Date: 2026-08-06
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add benchmark_client.py directory to path if needed
_bench_dir = os.environ.get(
    "BENCHMARK_DIR", "/workspace/llama.cpp-omni-official-eval/competition"
)
if _bench_dir not in sys.path:
    sys.path.insert(0, _bench_dir)

from benchmark_client import ProtocolAdapter, ChunkEvent


# ═══════════════════════════════════════════════════════════════════
# Field Mapping (auditable)
# ═══════════════════════════════════════════════════════════════════

FIELD_MAP = {
    "ws_event_type": "response.output.delta",
    "ws_audio_kind": "audio",
    "ws_audio_field": "audio",          # base64 PCM, 16-bit, 24kHz, mono
    "ws_text_field": "text",
    "ws_done_type": "response.done",
    "ws_init_type": "session.init",
    "ws_input_type": "input.append",
    "ws_created_type": "session.created",
    "chunk_type_text": "text",
    "chunk_type_audio": "audio",
    "chunk_type_done": "done",
}

TIMESTAMP_MAP = {
    "ws_send_init_ts": "request_start",
    "ws_first_text_ts": "first_text_token",
    "ws_first_audio_ts": "first_audio_chunk",
    "ws_response_done_ts": "request_end",
}


# ═══════════════════════════════════════════════════════════════════
# WebSocket Adapter Implementation
# ═══════════════════════════════════════════════════════════════════

class WebSocketAdapterV2(ProtocolAdapter):
    """WebSocket adapter for llama-omni-server /backend.

    Each decode_stream() call:
      1. Opens WS connection
      2. Sends session.init (turn_based, use_tts_template=True)
      3. Sends input.append with prompt
      4. Streams deltas as ChunkEvents
      5. Yields is_done=True on response.done
    """

    def __init__(self, url: str):
        # Normalize: benchmark passes "ws://localhost:8080" but our path is /backend
        self._url = url.rstrip("/")
        if not self._url.endswith("/backend"):
            if "/backend" not in self._url:
                self._url = self._url + "/backend"
        self._init_payload = {}
        self._debug_dir = "/tmp/competition-debug-ws"
        # Default test text — can be overridden
        self._prompt = "请用自然的中文语速说一段完整的话。"

    @property
    def name(self) -> str:
        return "websocket-v2"

    async def health(self) -> bool:
        """Check server health via HTTP."""
        import aiohttp
        health_url = self._url.replace("ws://", "http://").replace("/backend", "/health")
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data.get("status") == "ok"
        except Exception:
            pass
        return False

    async def initialize(self, payload: dict) -> bool:
        """Store init payload. Actual session init happens per decode_stream."""
        self._init_payload = payload
        if "output_dir" in payload:
            self._debug_dir = payload["output_dir"]
        return True

    async def prefill(self, cnt: int, audio_path: str = "", img_path: str = ""):
        """No-op: WS sessions don't use prefill. Each decode_stream is self-contained."""
        return True

    async def decode_stream(self, debug_dir: str):
        """Execute one TTS session via WebSocket and yield ChunkEvents."""
        import websockets

        output_dir = debug_dir or self._debug_dir
        os.makedirs(output_dir, exist_ok=True)

        seq = 0
        raw_events = []
        t_request_start = time.time_ns()

        try:
            async with websockets.connect(
                self._url, ping_interval=None, close_timeout=10
            ) as ws:
                # 1. Session init
                init_msg = {
                    "type": "session.init",
                    "payload": {
                        "mode": "turn_based",
                        "use_tts_template": True,
                        "tts_gpu_layers": self._init_payload.get("tts_gpu_layers", 99),
                    },
                }
                t_init_send = time.time_ns()
                await ws.send(json.dumps(init_msg))

                r = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                raw_events.append({
                    "ts_ns": time.time_ns(),
                    "direction": "recv",
                    "event": r,
                })
                if r.get("type") != "session.created":
                    yield ChunkEvent(
                        seq=seq, timestamp_ns=time.time_ns(),
                        chunk_type="control", is_done=True,
                    )
                    return

                session_id = r.get("session_id", "")

                # 2. Send input
                input_msg = {
                    "type": "input.append",
                    "input": {
                        "messages": [{"role": "user", "content": self._prompt}],
                        "streaming": True,
                        "use_tts_template": True,
                    },
                }
                t_input_send = time.time_ns()
                await ws.send(json.dumps(input_msg))

                # 3. Stream deltas
                while True:
                    r = json.loads(await asyncio.wait_for(ws.recv(), timeout=600))
                    now = time.time_ns()
                    raw_events.append({
                        "ts_ns": now,
                        "direction": "recv",
                        "event": r,
                    })

                    etype = r.get("type", "?")
                    if etype == "response.output.delta":
                        kind = r.get("kind", "")
                        if kind == "text":
                            text = r.get("text") or ""
                            yield ChunkEvent(
                                seq=seq, timestamp_ns=now,
                                chunk_type="text", text=text,
                            )
                            seq += 1
                        elif kind == "audio":
                            audio_b64 = r.get("audio") or ""
                            yield ChunkEvent(
                                seq=seq, timestamp_ns=now,
                                chunk_type="audio",
                                text=audio_b64,  # carry base64 in text field
                            )
                            seq += 1

                    elif etype == "response.done":
                        yield ChunkEvent(
                            seq=seq, timestamp_ns=now,
                            chunk_type="control", is_done=True,
                        )
                        break

                    elif etype in ("session.closed", "error"):
                        yield ChunkEvent(
                            seq=seq, timestamp_ns=now,
                            chunk_type="control", is_done=True,
                        )
                        break

        except Exception as e:
            yield ChunkEvent(
                seq=seq, timestamp_ns=time.time_ns(),
                chunk_type="control", is_done=True,
                text=str(e)[:200],
            )
        finally:
            # Save raw events for audit
            session_file = os.path.join(
                output_dir,
                f"ws_adapter_{time.strftime('%Y%m%d-%H%M%S')}_{os.getpid()}.jsonl",
            )
            try:
                with open(session_file, "w") as f:
                    for evt in raw_events:
                        f.write(json.dumps(evt, ensure_ascii=False) + "\n")
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════
# Registration
# ═══════════════════════════════════════════════════════════════════

# To use with benchmark_client.py:
#   python3 -c "
#   import sys; sys.path.insert(0, '.../submission/adapters')
#   from ws_adapter import WebSocketAdapterV2
#   # Then call benchmark_client.main() with this adapter
#   "
#
# Or: monkey-patch ADAPTERS dict:
#   from benchmark_client import ADAPTERS
#   from ws_adapter import WebSocketAdapterV2
#   ADAPTERS['ws'] = WebSocketAdapterV2
