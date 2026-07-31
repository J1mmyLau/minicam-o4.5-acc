# F6 W4: Independent Server and Client First-Audio Metrics

**Date:** 2026-07-31
**Purpose:** Define two independent timing systems (server-side and client-side) for first-audio latency, correlated by `request_id` but using separate monotonic clocks.

---

## Principle

> **Server time uses server monotonic clock. Client time uses client monotonic clock.**
> **Do NOT subtract absolute timestamps across processes.**
> **Correlate by `request_id`, report separately.**

This avoids clock synchronization errors, NTP jitter, and kernel scheduling artifacts that make cross-process timestamp subtraction unreliable at millisecond precision.

---

## Server-Side Metrics

### SERVER_D0_TO_W0

```
Definition:  decode_loop_begin → first valid WAV buffer ready
Clock:       server std::chrono::steady_clock (monotonic)
Thread:      HTTP handler (D0) + T2W worker (W0)
Unit:        milliseconds (integer)
Storage:     per-request E2E profile (not shared atomics)
```

**Measurement:**
- `D0`: `STAGE_decode_loop_begin`, recorded synchronously in HTTP handler at `stream_decode()` entry
- `W0`: `STAGE_wav_ready`, recorded in T2W worker when first WAV buffer is valid
- Both timestamps stored in the same per-request profile
- `SERVER_D0_TO_W0 = wav_ready_ns - decode_loop_begin_ns` (computed at profile finalization)

### SERVER_R0_TO_W0

```
Definition:  request_received → first valid WAV buffer ready
Clock:       server std::chrono::steady_clock (monotonic)
Thread:      HTTP handler (R0) + T2W worker (W0)
Unit:        milliseconds (integer)
Storage:     per-request E2E profile
```

**Measurement:**
- `R0`: `STAGE_request_received`, recorded at `stream_decode()` entry after `reset()`
- `W0`: Same as above
- `SERVER_R0_TO_W0 = wav_ready_ns - request_received_ns`

### Server Prerequisites for Valid W0

Before SERVER_D0_TO_W0 can be reported, the following must hold for the request:
1. `wav_ready` timestamp > 0 (WAV was actually produced)
2. `audio_valid` flag = true (WAV buffer contains valid PCM)
3. `wav_ready` generation_id matches request's generation (not stale, not cross-request)
4. Profile lifecycle state ≥ FIRST_WAV_READY (see W6 state machine)

---

## Client-Side Metrics

### CLIENT_REQUEST_TO_FIRST_AUDIO_FRAME

```
Definition:  client HTTP request send → first non-empty audio frame received
Clock:       client time.monotonic() or equivalent monotonic clock
Thread:      client main thread
Unit:        milliseconds (float)
Storage:     client-side measurement script
```

**Measurement:**
- `t_send`: `time.monotonic()` immediately before `requests.post()` or WebSocket send
- `t_first_frame`: `time.monotonic()` when first non-empty audio frame arrives (WebSocket message, HTTP chunk, or polling response)
- `CLIENT_REQUEST_TO_FIRST_AUDIO_FRAME = t_first_frame - t_send`
- Frame is "non-empty" if `len(audio_bytes) > 0`

### CLIENT_REQUEST_TO_FIRST_VALID_PCM

```
Definition:  client HTTP request send → first audio frame decoded as valid PCM
Clock:       client time.monotonic()
Thread:      client main thread
Unit:        milliseconds (float)
Storage:     client-side measurement script
```

**Measurement:**
- `t_send`: same as above
- `t_first_pcm`: `time.monotonic()` when first audio frame is successfully decoded (WAV header valid, sample rate matches, non-zero samples)
- `CLIENT_REQUEST_TO_FIRST_VALID_PCM = t_first_pcm - t_send`
- Frame is "valid PCM" if: WAV header parses correctly, sample_rate = 24000, channels = 1, data_bytes > 0, at least one non-zero sample

---

## Correlation Protocol

Each request is tagged with a `request_id` on both sides:

```
Server side:
  request_id = e2e_stage.request_index (integer, monotonically increasing per server session)
  Included in E2E profile JSON as "request_index" field

Client side:
  request_id = sequential counter (0, 1, 2, ...) maintained by client script
  Logged alongside each measurement

Correlation:
  SERVER_D0_TO_W0[request_id=N] paired with CLIENT_REQUEST_TO_FIRST_AUDIO_FRAME[request_id=N]
  → Two independent measurements of the same request
  → Report BOTH, do NOT subtract one from the other
```

---

## Reporting Format

For each matched pair:

```csv
request_id, prompt_id, cache_status,
server_d0_to_w0_ms, server_r0_to_w0_ms,
client_request_to_first_audio_frame_ms, client_request_to_first_valid_pcm_ms,
server_w0_present, client_audio_valid
```

**Aggregate statistics reported separately for server and client.**

---

## What We CAN Say (Without Cross-Process Subtraction)

| Statement | Valid? | Reason |
|-----------|--------|--------|
| "Server D0→W0 improved by Xms" | ✅ | Same clock, same process |
| "Client perceived latency improved by Yms" | ✅ | Same clock, same process |
| "Server→client gap is Zms" | ❌ | Different clocks — subtraction invalid |
| "Client sees X% of server improvement" | ✅ (directional) | Compare paired deltas, not absolute differences |
| "B6b saves ~133ms D2→G0, of which ~Xms reaches W0" | ✅ | All server-side, same clock |

---

## Implementation Notes

1. Server W0 requires the fix from W5-W7 (request-scoped profile lifecycle)
2. Client metrics require a measurement harness that records `time.monotonic()` at send and first-frame-receive
3. The existing `/v1/stream/decode` HTTP endpoint returns audio inline — client can measure `t_first_frame` from the response stream
4. For WebSocket or polling transports, client metric definitions adapt accordingly
5. `request_id` on the server is already `e2e_stage.request_index` (L13360); client must maintain its own counter
