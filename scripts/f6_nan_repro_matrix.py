#!/usr/bin/env python3
"""
Phase 4: Minimal NaN Repro Matrix with OMNI_NAN_DIAG=1

Corrected WS protocol:
  - session.init: {type, payload: {mode, use_tts, system_prompt}}
  - input.append: {type, input: {messages: [...]}}

4 cases:
  1. text-only      → expected CLEAN
  2. image-only     → expected CLEAN
  3. audio-only     → expected NaN (all ?)
  4. video-no-audio → expected NaN (all ?)

Server must be started with OMNI_NAN_DIAG=1 env var.
"""
import asyncio, json, base64, sys, os, subprocess
import websockets

SERVER_WS = os.environ.get("OMNI_WS_URL", "ws://127.0.0.1:18094/backend")

def b64_file(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def make_init(mode="turn_based", use_tts=False, system_prompt="You are a helpful assistant."):
    return {
        "type": "session.init",
        "payload": {
            "mode": mode,
            "use_tts": use_tts,
            "system_prompt": system_prompt
        }
    }

def make_input(messages):
    """Wrap messages array in input.append protocol."""
    return {
        "type": "input.append",
        "input": {"messages": messages}
    }

def text_only_input():
    return make_input([
        {"role": "user", "content": "What is 2+2? Answer with just the number."}
    ])

def image_only_input(img_path):
    return make_input([
        {"role": "user", "content": [
            {"type": "text", "text": "Describe this image briefly."},
            {"type": "image", "data": b64_file(img_path)}
        ]}
    ])

def audio_only_input(audio_path):
    return make_input([
        {"role": "user", "content": [
            {"type": "text", "text": "What do you hear? Answer briefly."},
            {"type": "audio", "data": b64_file(audio_path)}
        ]}
    ])

def video_no_audio_input(video_path):
    return make_input([
        {"role": "user", "content": [
            {"type": "text", "text": "Describe this video briefly."},
            {"type": "video", "data": b64_file(video_path), "stack_frames": 4}
        ]}
    ])

async def run_case(name, init_msg, input_msg, timeout=90):
    text_output = ""

    try:
        async with websockets.connect(SERVER_WS, ping_interval=None, close_timeout=5) as ws:
            # Init session
            await ws.send(json.dumps(init_msg))
            init_resp = await asyncio.wait_for(ws.recv(), timeout=15)
            print(f"  Init response type: {json.loads(init_resp).get('type', '?')}")

            # Send input.append
            await ws.send(json.dumps(input_msg))

            # Collect response events
            done = False
            while not done:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    resp = json.loads(raw)
                    t = resp.get("type", "")

                    if t == "response.text.delta":
                        text_output += resp.get("delta", "")
                    elif t == "response.text.done":
                        text_output += resp.get("text", "")
                    elif t == "response.done":
                        done = True
                    elif t == "response.created":
                        pass  # ack
                    elif t == "session.closed":
                        done = True
                    elif t == "session.error":
                        text_output = f"ERROR: {resp}"
                        done = True
                    elif t == "error":
                        text_output = f"ERROR: {resp}"
                        done = True
                except asyncio.TimeoutError:
                    done = True
    except Exception as e:
        text_output = f"EXCEPTION: {e}"

    return text_output.strip()

async def main():
    img = "/tmp/daily_omni_20/frame_0.jpg"
    audio = "/tmp/silence_0.5s.wav"
    video_no_audio = "/tmp/omni_duplex1_no_audio.mp4"

    cases = [
        ("1_text_only",      text_only_input(),               "CLEAN"),
        ("2_image_only",     image_only_input(img),            "CLEAN"),
        ("3_audio_only",     audio_only_input(audio),          "NaN"),
        ("4_video_no_aud",   video_no_audio_input(video_no_audio), "NaN"),
    ]

    results = []
    for name, input_msg, expected in cases:
        print(f"\n{'='*60}")
        print(f"Case: {name} (expected: {expected})")
        print(f"{'='*60}")

        init_msg = make_init(use_tts=False, system_prompt="You are a helpful assistant.")
        text = await run_case(name, init_msg, input_msg)

        # Check for NaN indicator (all ? characters)
        stripped = text.strip()
        all_q = len(stripped) > 0 and all(c == '?' or c == '�' for c in stripped)
        has_text = len(stripped) > 0 and not all_q

        if expected == "CLEAN":
            status = "PASS" if has_text else "FAIL"
        else:
            status = "PASS" if (all_q or len(stripped) == 0) else "FAIL"

        preview = text[:200].replace('\n', '\\n')
        print(f"  Text: {preview}")
        print(f"  All '?': {all_q}, Has text: {has_text}")
        print(f"  Status: {status}")

        results.append((name, status, text[:200], all_q, has_text))

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    all_pass = True
    for name, status, text, all_q, has_text in results:
        print(f"  {name}: {status} (all_?={all_q}, has_text={has_text})")
        if status != "PASS":
            all_pass = False

    print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAIL'}")
    print(f"\nCheck server stderr for [nan_diag] lines to find first NaN boundary.")
    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
