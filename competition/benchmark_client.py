#!/usr/bin/env python3
"""
Official benchmark client for llama-omni-server.

Status: PROVISIONAL — official adapter pending starter kit.

Architecture:
    Benchmark orchestration (this file)
    ├── HTTP/SSE adapter   — provisional, based on known /v1/stream API
    ├── WebSocket adapter  — placeholder, for /backend duplex mode
    └── Official adapter   — pending starter kit

Metrics logic is independent of protocol adapter.

Usage:
    python3 benchmark_client.py --adapter http --url http://localhost:9060 -c 4 -n 100
    python3 benchmark_client.py --adapter ws   --url ws://localhost:9060  -c 1 -n 10

Output: JSONL file with per-request timing data.
"""

import abc
import argparse
import asyncio
import json
import os
import signal
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════
# Data structures (protocol-independent)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ChunkEvent:
    """Single chunk from server stream. Protocol adapters produce these."""
    seq: int
    timestamp_ns: int
    chunk_type: str = "text"       # "text" | "audio" | "control" | "done"
    text: str = ""
    is_listen: bool = False
    is_done: bool = False


@dataclass
class RequestResult:
    """Per-request timing result. Computed from ChunkEvents."""
    session_id: str
    adapter: str
    request_start_ns: int = 0
    request_end_ns: int = 0
    first_text_token_ns: int = 0
    first_audio_chunk_ns: int = 0
    chunks: list = field(default_factory=list)
    ttft_ms: float = 0.0
    first_audio_ms: float = 0.0
    chunk_intervals_ms: list = field(default_factory=list)
    e2e_ms: float = 0.0
    success: bool = False
    error: str = ""


# ═══════════════════════════════════════════════════════════════════
# Protocol adapter interface
# ═══════════════════════════════════════════════════════════════════

class ProtocolAdapter(abc.ABC):
    """Abstract protocol adapter. Each concrete adapter handles one server protocol."""

    @abc.abstractmethod
    async def health(self) -> bool:
        ...

    @abc.abstractmethod
    async def initialize(self, payload: dict) -> bool:
        ...

    @abc.abstractmethod
    async def prefill(self, cnt: int, audio_path: str = "", img_path: str = ""):
        ...

    @abc.abstractmethod
    async def decode_stream(self, debug_dir: str):
        """Yield ChunkEvent. Must include is_done=True at end."""
        ...

    @property
    @abc.abstractmethod
    def name(self) -> str:
        ...


# ═══════════════════════════════════════════════════════════════════
# HTTP/SSE adapter (provisional — known /v1/stream API)
# ═══════════════════════════════════════════════════════════════════

class HTTPSSEAdapter(ProtocolAdapter):
    """HTTP SSE adapter for llama-omni-server /v1/stream endpoints.

    Status: PROVISIONAL. Works with current server but official protocol
    may differ. Validate against starter kit before claiming ready.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    @property
    def name(self) -> str:
        return "http-sse"

    async def health(self) -> bool:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{self.base_url}/health") as r:
                return r.status == 200

    async def initialize(self, payload: dict) -> bool:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{self.base_url}/v1/stream/omni_init",
                json=payload, timeout=aiohttp.ClientTimeout(total=120)
            ) as r:
                return r.status == 200

    async def prefill(self, cnt: int, audio_path: str = "", img_path: str = ""):
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{self.base_url}/v1/stream/prefill",
                json={"cnt": cnt, "audio_path_prefix": audio_path, "img_path_prefix": img_path},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                return r.status == 200

    async def decode_stream(self, debug_dir: str):
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{self.base_url}/v1/stream/decode",
                json={"debug_dir": debug_dir, "stream": True},
                timeout=aiohttp.ClientTimeout(total=300)
            ) as r:
                seq = 0
                async for line in r.content:
                    line = line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        yield ChunkEvent(seq=seq, timestamp_ns=time.time_ns(),
                                         chunk_type="control", is_done=True)
                        return
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    text = data.get("content", "")
                    is_listen = data.get("is_listen", False)
                    stop = data.get("stop", False)
                    ct = "audio" if is_listen else "text"
                    yield ChunkEvent(seq=seq, timestamp_ns=time.time_ns(),
                                     chunk_type=ct, text=text,
                                     is_listen=is_listen, is_done=stop)
                    seq += 1
                    if stop:
                        return


# ═══════════════════════════════════════════════════════════════════
# WebSocket adapter (placeholder — for /backend duplex mode)
# ═══════════════════════════════════════════════════════════════════

class WebSocketAdapter(ProtocolAdapter):
    """WebSocket adapter for llama-omni-server /backend duplex mode.

    Status: PLACEHOLDER. Not yet implemented. Official protocol may differ.
    """

    def __init__(self, url: str):
        self._url = url

    @property
    def name(self) -> str:
        return "websocket"

    async def health(self) -> bool:
        raise NotImplementedError("WebSocket adapter: health check not implemented")

    async def initialize(self, payload: dict) -> bool:
        raise NotImplementedError("WebSocket adapter: initialize not implemented")

    async def prefill(self, cnt: int, audio_path: str = "", img_path: str = ""):
        raise NotImplementedError("WebSocket adapter: prefill not implemented")

    async def decode_stream(self, debug_dir: str):
        raise NotImplementedError("WebSocket adapter: decode not implemented")
        yield  # type hint


# ═══════════════════════════════════════════════════════════════════
# Official starter-kit adapter (placeholder)
# ═══════════════════════════════════════════════════════════════════

class OfficialAdapter(ProtocolAdapter):
    """Official starter-kit adapter.

    Status: PENDING. Will be implemented when starter kit is available.
    Must validate against METRIC_CONTRACT.md and STARTER_KIT_CHECKLIST.md.
    """

    def __init__(self, url: str):
        self._url = url

    @property
    def name(self) -> str:
        return "official"

    async def health(self) -> bool:
        raise NotImplementedError("Official adapter: pending starter kit")

    async def initialize(self, payload: dict) -> bool:
        raise NotImplementedError("Official adapter: pending starter kit")

    async def prefill(self, cnt: int, audio_path: str = "", img_path: str = ""):
        raise NotImplementedError("Official adapter: pending starter kit")

    async def decode_stream(self, debug_dir: str):
        raise NotImplementedError("Official adapter: pending starter kit")
        yield


# ═══════════════════════════════════════════════════════════════════
# Adapter factory
# ═══════════════════════════════════════════════════════════════════

ADAPTERS = {
    "http": HTTPSSEAdapter,
    "ws": WebSocketAdapter,
    "official": OfficialAdapter,
}


# ═══════════════════════════════════════════════════════════════════
# Benchmark runner (protocol-independent)
# ═══════════════════════════════════════════════════════════════════

async def run_one_request(
    adapter: ProtocolAdapter,
    session_id: str,
    output_dir: str,
    timeout_s: int = 300,
) -> RequestResult:
    """Run a single decode request and collect timing data."""
    result = RequestResult(session_id=session_id, adapter=adapter.name)
    result.request_start_ns = time.time_ns()

    try:
        async with asyncio.timeout(timeout_s):
            text_started = False
            audio_started = False
            prev_chunk_ns = 0

            async for chunk in adapter.decode_stream(output_dir):
                now = chunk.timestamp_ns

                if chunk.is_done:
                    break

                if not text_started and chunk.chunk_type == "text" and chunk.text:
                    result.first_text_token_ns = now
                    text_started = True

                if not audio_started and chunk.chunk_type == "audio":
                    result.first_audio_chunk_ns = now
                    audio_started = True

                if prev_chunk_ns > 0:
                    interval_ms = (now - prev_chunk_ns) / 1_000_000
                    result.chunk_intervals_ms.append(interval_ms)

                prev_chunk_ns = now
                result.chunks.append({
                    "seq": chunk.seq, "ts_ns": now, "type": chunk.chunk_type,
                    "text": chunk.text, "is_listen": chunk.is_listen,
                })

        result.request_end_ns = time.time_ns()
        result.success = True

    except asyncio.TimeoutError:
        result.request_end_ns = time.time_ns()
        result.error = "timeout"
    except Exception as e:
        result.request_end_ns = time.time_ns()
        result.error = str(e)

    if result.success:
        result.ttft_ms = (result.first_text_token_ns - result.request_start_ns) / 1_000_000 if result.first_text_token_ns else 0.0
        result.first_audio_ms = (result.first_audio_chunk_ns - result.request_start_ns) / 1_000_000 if result.first_audio_chunk_ns else 0.0
        result.e2e_ms = (result.request_end_ns - result.request_start_ns) / 1_000_000

    return result


async def run_benchmark(
    adapter: ProtocolAdapter,
    concurrency: int,
    num_requests: int,
    warmup_requests: int = 3,
    output_dir: str = "results",
    debug_dir: str = "/tmp/competition-debug",
) -> list[RequestResult]:
    """Run concurrent benchmark with given adapter."""

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(debug_dir, exist_ok=True)

    print(f"Benchmark: adapter={adapter.name}, concurrency={concurrency}, requests={num_requests}")

    healthy = await adapter.health()
    if not healthy:
        print("ERROR: Server not healthy")
        return []
    print("Server healthy.")

    print("Initializing...")
    ok = await adapter.initialize({
        "media_type": 2,
        "use_tts": True,
        "duplex_mode": False,
        "model_dir": os.environ.get("MODEL_DIR", "/workspace/models/MiniCPM-o-4_5-gguf"),
        "tts_bin_dir": os.environ.get("TTS_BIN_DIR", "/workspace/models/MiniCPM-o-4_5-gguf/tts"),
        "tts_gpu_layers": int(os.environ.get("TTS_GPU_LAYERS", "0")),
        "output_dir": debug_dir,
    })
    if not ok:
        print("ERROR: omni_init failed")
        return []
    print("Initialized.")

    results: list[RequestResult] = []

    # Warmup
    print(f"Warmup: {warmup_requests} requests...")
    for i in range(warmup_requests):
        r = await run_one_request(adapter, f"warmup-{i}", debug_dir)
        results.append(r)

    # Measured
    print(f"Measured: {num_requests} requests, concurrency={concurrency}...")
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(idx: int):
        async with semaphore:
            r = await run_one_request(adapter, f"measured-{idx}", debug_dir)
            status = "OK" if r.success else f"FAIL({r.error})"
            print(f"  [{idx+1}/{num_requests}] {status} ttft={r.ttft_ms:.0f}ms e2e={r.e2e_ms:.0f}ms")
            return r

    tasks = [bounded(i) for i in range(num_requests)]
    measured = await asyncio.gather(*tasks)
    results.extend(measured)

    # Save
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = os.path.join(output_dir, f"benchmark_{adapter.name}_c{concurrency}_n{num_requests}_{ts}.jsonl")
    with open(out, "w") as f:
        for r in results:
            f.write(json.dumps({
                "session_id": r.session_id,
                "adapter": r.adapter,
                "success": r.success,
                "error": r.error,
                "ttft_ms": round(r.ttft_ms, 2),
                "first_audio_ms": round(r.first_audio_ms, 2),
                "e2e_ms": round(r.e2e_ms, 2),
                "chunk_intervals_ms": [round(x, 2) for x in r.chunk_intervals_ms],
                "chunk_count": len(r.chunks),
                "request_start_ns": r.request_start_ns,
                "request_end_ns": r.request_end_ns,
            }) + "\n")

    print(f"\nSaved: {out}")
    return results


def main():
    parser = argparse.ArgumentParser(description="llama-omni-server benchmark client")
    parser.add_argument("--adapter", choices=sorted(ADAPTERS), default="http",
                        help="Protocol adapter (default: http)")
    parser.add_argument("--url", default="http://localhost:9060", help="Server URL")
    parser.add_argument("-c", "--concurrency", type=int, default=1)
    parser.add_argument("-n", "--requests", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("-o", "--output-dir", default="results")
    parser.add_argument("--debug-dir", default="/tmp/competition-debug")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(1))

    adapter_cls = ADAPTERS[args.adapter]
    adapter = adapter_cls(args.url)

    asyncio.run(run_benchmark(
        adapter=adapter,
        concurrency=args.concurrency,
        num_requests=args.requests,
        warmup_requests=args.warmup,
        output_dir=args.output_dir,
        debug_dir=args.debug_dir,
    ))


if __name__ == "__main__":
    main()
