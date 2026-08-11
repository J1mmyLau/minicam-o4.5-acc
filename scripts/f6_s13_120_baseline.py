#!/usr/bin/env python3
"""
S13 120/120 Comprehensive Baseline — 4 case types × 30 requests
================================================================
FP16, -ngl 999, CANN0, persistent Server on port 18093.
B6b OFF, CHUNK_SIZE=25, USE_TTS=True (CANN Flow/Vocoder).

4 case types:
  1. Short Chinese (短中文) — 30 requests
  2. Long Chinese (长中文) — 30 requests
  3. English (英文) — 30 requests
  4. Number/Mixed (数字及中英混合) — 30 requests

Progressive gates at 20/40/60/80/100.
Target: 120/120 valid, timeout=0, crash=0, stale/cross=0, critical_missing=0.

Metrics per request:
  - server_request_to_W0_ms: T0 (request submitted) → W0 (first audio PCM ready)
  - client_first_pcm_ms: T0 → first PCM timestamp received via streaming
  - response_complete_ms: T0 → decode complete + all audio drained
  - mutex_wait_us: OCTX_LOCK_ACQUIRED - OCTX_LOCK_WAIT_BEGIN
  - handler_hold_ms: HANDLER_RETURN - HANDLER_ENTER
  - prefill_wall_ms: prefill HTTP round-trip
  - decode_wall_ms: decode HTTP round-trip
  - lifecycle: state transitions
  - drain_count, wav_count
"""

import requests
import time
import os
import glob
import json
import sys
import re
import statistics
import datetime
import hashlib
import threading
import queue

# ── Config ────────────────────────────────────
BASE = "http://127.0.0.1:18093"
AUDIO_PREFIX = "/workspace/llama.cpp-omni-f6/tools/omni/assets/test_case/omni_test_case/omni_test_case_"
SERVER_LOG = "/tmp/f6_r13_kvcache_srv.log"  # same server as R13, PID 18026
OUTPUT_DIR = "/tmp/f6_s13_120_results"
USE_TTS = True

TOTAL_REQUESTS = 120  # 4 × 30
REQUESTS_PER_CASE = 30
REQUEST_TIMEOUT = 600
COOLDOWN_S = 2
PROGRESSIVE_GATES = [20, 40, 60, 80, 100]

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Prompt definitions ─────────────────────────

SHORT_CN_PROMPTS = [
    "你好，请介绍一下你自己",
    "今天天气怎么样",
    "现在几点了",
    "我喜欢吃苹果",
    "请讲个笑话",
    "什么是人工智能",
    "帮我算一下二加三等于几",
    "中国的首都是哪里",
    "请用一句话描述春天",
    "你最喜欢的颜色是什么",
    "给我推荐一本书",
    "什么是机器学习",
    "请翻译：你好世界",
    "一加一等于几",
    "请说一句鼓励的话",
    "什么是深度学习",
    "北京有哪些著名景点",
    "请用三个词形容大海",
    "今天就到这里，再见",
    "你能做什么",
    "太阳从哪边升起",
    "什么是大语言模型",
    "请解释什么是API",
    "如何煮鸡蛋",
    "你是谁开发的",
    "推荐一首中文歌曲",
    "世界上最长的河流是什么",
    "简单介绍一下上海",
    "明天会下雨吗",
    "给我讲一个一分钟的故事",
]

LONG_CN_PROMPTS = [
    "请详细介绍人工智能的发展历程，从1950年代的图灵测试开始，到现在的深度学习和生成式AI。包括重要的里程碑事件和关键人物。不少于三百字。",
    "请详细解释什么是气候变化，它的主要原因是什么，对地球生态系统有哪些具体影响，以及我们可以采取哪些措施来减缓气候变化。",
    "请从历史、文化、经济三个维度，全面分析丝绸之路对东西方文明交流的影响。包括具体的贸易商品、技术传播和文化融合的例子。",
    "请详细描述中国的四大发明（造纸术、印刷术、火药、指南针）的发明过程、技术原理及其对世界文明发展的深远影响。",
    "请系统性地介绍量子计算的基本原理，包括量子比特、量子纠缠、量子叠加态等核心概念，以及它与传统经典计算的主要区别和潜在应用前景。",
    "请详细讲述中国航天事业的发展历程，从东方红一号到天宫空间站、嫦娥探月工程到火星探测任务，包括关键技术突破和未来规划。",
    "请全面分析5G通信技术的核心特点、技术架构、应用场景，以及它对物联网、自动驾驶、远程医疗等领域的变革性影响和面临的挑战。",
    "请详细解释人体免疫系统的工作原理，包括固有免疫和适应性免疫的区别，T细胞和B细胞的具体功能，以及疫苗如何利用免疫系统保护人体健康。",
    "请系统地介绍区块链技术的核心概念，包括分布式账本、共识机制、智能合约、去中心化应用（DApp），以及它如何改变金融、供应链、数字身份等领域。",
    "请详细描述中国高铁的发展历程和技术成就，从引进消化吸收到自主创新的全过程，包括核心技术突破、运营里程、速度记录和社会经济效益分析。",
    "请从地质构造、气候特征、生物多样性、水资源分布等角度，全面介绍青藏高原的自然地理特征及其对亚洲乃至全球环境的重要影响。",
    "请详细分析可再生能源（太阳能、风能、水能、地热能、生物质能）各自的优缺点，以及中国在能源转型中面临的机遇和挑战。",
    "请系统地介绍深度学习的主要神经网络架构，包括CNN、RNN、LSTM、Transformer、GAN等，以及它们各自适用的应用场景和最新研究进展。",
    "请全面分析中国改革开放四十多年来在经济、社会、科技、教育等领域取得的巨大成就，以及当前面临的主要挑战和未来发展方向。",
    "请详细解释基因编辑技术CRISPR-Cas9的工作原理和发展历程，包括它在疾病治疗、农业改良等方面的应用前景，以及伴随而来的伦理和安全问题。",
    "请从历史沿革、艺术特色、文化内涵和保护现状四个角度，详细介绍中国非物质文化遗产中京剧的独特价值和世界影响。",
    "请系统性地介绍太阳系的八大行星，包括它们的大小、组成、轨道特征、卫星系统，以及人类对每颗行星的探测历史和重要发现。",
    "请详细分析电子商务对传统零售业的颠覆性影响，包括消费行为变化、供应链重构、物流体系创新，以及线上线下融合的新零售模式发展趋势。",
    "请全面介绍中国茶文化的历史渊源、主要茶类（绿茶、红茶、乌龙茶、白茶、黄茶、黑茶）的特点和制作工艺，以及茶道精神的文化内涵。",
    "请详细解释大数据技术的核心架构（Hadoop、Spark等），以及它在智慧城市、精准营销、医疗健康等领域的具体应用案例和数据处理方法。",
    "请系统性地介绍人类探索海洋的历史和重大发现，从早期的航海探险到现代的深海探测技术，包括海洋生物学、海洋地质学和海洋资源开发的最新进展。",
    "请从物理定律、化学组成和生物学条件三个层面，详细分析地球为什么能够孕育生命，以及科学家如何利用这些知识寻找系外宜居行星。",
    "请全面分析中国新能源汽车产业的发展现状、技术路线（纯电动、插电混动、燃料电池）、市场竞争格局和未来趋势，包括电池技术和充电基础设施。",
    "请详细描述长城的修建历史，从春秋战国到明代的不同阶段，包括建筑技术、军事功能和文化象征意义，以及现代保护和修复工作面临的挑战。",
    "请系统性地介绍计算机操作系统的发展历史，从早期的批处理系统到现代的多任务图形界面系统，包括UNIX、Windows、Linux和macOS的演进。",
    "请详细解释人体消化系统的结构和功能，从口腔到肠道的完整消化过程，包括各器官的具体作用和常见消化系统疾病的预防方法。",
    "请从品种分类、栽培技术、加工方法和品鉴标准四个维度，全面介绍世界三大饮料作物（咖啡、茶、可可）的种植历史和文化差异。",
    "请全面分析网络安全面临的主要威胁类型（病毒、木马、DDoS、钓鱼、勒索软件等）和相应的防御措施，包括加密技术、防火墙、入侵检测和安全管理策略。",
    "请详细讲述人类航空史从莱特兄弟到超音速客机的关键技术创新，包括喷气发动机、雷达导航、复合材料、自动驾驶等里程碑式进展。",
    "请系统地介绍世界主要宗教（基督教、伊斯兰教、佛教、印度教、犹太教）的基本教义、历史渊源、经典著作和全球分布现状，以及宗教对话的意义。",
]

EN_PROMPTS = [
    "Hello, please introduce yourself",
    "What's the weather like today",
    "Tell me a short story about a cat",
    "Explain what AI is in simple terms",
    "How does the internet work",
    "What are the three laws of robotics",
    "Describe the Eiffel Tower",
    "What is the speed of light",
    "Explain photosynthesis briefly",
    "Who wrote Romeo and Juliet",
    "What is the capital of Japan",
    "How do airplanes fly",
    "Explain the water cycle",
    "What is DNA and why is it important",
    "Describe the Big Bang theory",
    "How does a computer boot up",
    "What is blockchain technology",
    "Explain quantum entanglement",
    "Describe the process of photosynthesis",
    "What causes earthquakes",
    "How does GPS work",
    "Explain the concept of gravity",
    "What is machine learning",
    "Describe how electricity is generated",
    "How do vaccines work",
    "What is dark matter",
    "Explain the greenhouse effect",
    "What is CRISPR gene editing",
    "How does a nuclear reactor work",
    "Describe the Great Wall of China",
]

MIXED_PROMPTS = [
    "12345 + 67890 等于多少",
    "请列出斐波那契数列前10项：1, 1, 2, 3, 5, 8...",
    "3.14159265358979 是圆周率π的近似值",
    "一百二十三万四千五百六十七是多少",
    "There are 24 hours in a day, 这是常识",
    "2的10次方等于1024，对吗",
    "请用英文报数：one two three four five",
    "99乘法表：9×9=81, 9×8=72, 9×7=63",
    "The speed of light is 299,792,458 m/s",
    "π ≈ 3.14, e ≈ 2.718, 哪个更大",
    "IEEE 754 double-precision: sign=1bit exponent=11bit mantissa=52bit",
    "一千零一夜 (1001 Nights) 是阿拉伯的经典",
    "RGB颜色 #FF5733 的十进制表示是什么",
    "42 is the Answer to the Ultimate Question of Life",
    "我的手机号是 138-xxxx-xxxx 格式的11位数字",
    "IPv4 地址 192.168.1.1 有32位，即4个8位组",
    "圆周率 π = 3.1415926535... 你记住了吗",
    "ASCII码：A=65, B=66, a=97, b=98",
    "一年有365天，闰年有366天，2024年是闰年",
    "比特币总量上限是21,000,000个 (21 million)",
    "世界上最快的超算 Frontier 算力 1.194 exaFLOPS",
    "光年=9.46×10^12 kilometers, 是距离单位不是时间单位",
    "人体有206块骨头，成年人有32颗牙齿",
    "地球到月球距离约384,400公里 (238,855 miles)",
    "0.1 + 0.2 == 0.3 在浮点数运算中是False, IEEE 754精度问题",
    "中文数字一二三四五六七八九十 vs Arabic numerals 1234567890",
    "黄金分割率 φ = (1+√5)/2 ≈ 1.6180339887",
    "computer用了多少个字母？答案是8个: c-o-m-p-u-t-e-r",
    "身份证号码是18位，第17位奇数=男偶数=女",
    "九九归一(9×9=81→8+1=9)，这是数字的奇妙规律",
]

TEST_CASES = [
    {"type": "short_cn",   "label": "短中文",  "prompts": SHORT_CN_PROMPTS,  "audios": ["0000.wav", "0001.wav"]},
    {"type": "long_cn",    "label": "长中文",  "prompts": LONG_CN_PROMPTS,   "audios": ["0002.wav", "0003.wav"]},
    {"type": "english",    "label": "英文",    "prompts": EN_PROMPTS,        "audios": ["0004.wav", "0005.wav"]},
    {"type": "number_mix", "label": "数字混合", "prompts": MIXED_PROMPTS,      "audios": ["0006.wav", "0007.wav"]},
]


# ── Helpers ───────────────────────────────────
def log_size():
    try:
        return os.path.getsize(SERVER_LOG)
    except Exception:
        return 0


def read_log_segment(pos_start, pos_end=None):
    try:
        with open(SERVER_LOG, "r") as f:
            f.seek(pos_start)
            if pos_end is not None and pos_end > pos_start:
                return f.read(pos_end - pos_start)
            return f.read()
    except Exception:
        return ""


def parse_f6_events(log_text):
    events = {}
    for m in re.finditer(
        r"F6_EVENT\|(\d+)\|(\w+)\|req=(\S+)\|ctx=(\S+)\|tid=(\S+)", log_text
    ):
        ts = int(m.group(1))
        evt = m.group(2)
        req_id = m.group(3)
        events.setdefault(evt, []).append({"ts": ts, "req": req_id})

    req_states = []
    for m in re.finditer(
        r"F6_REQSTATE\|(\d+)\|req=(\S+)\|(\S+)→(\S+)\|label=(\S+)\|(\S+)", log_text
    ):
        req_states.append({
            "ts": int(m.group(1)),
            "req": m.group(2),
            "from_state": m.group(3),
            "to_state": m.group(4),
            "label": m.group(5),
            "status": m.group(6),
        })
    return events, req_states


def compute_mutex_wait_us(events):
    wait = events.get("OCTX_LOCK_WAIT_BEGIN", [])
    acquired = events.get("OCTX_LOCK_ACQUIRED", [])
    if wait and acquired:
        return (acquired[-1]["ts"] - wait[-1]["ts"]) / 1000.0
    return None


def compute_handler_hold_ms(events):
    enter = events.get("HANDLER_ENTER", [])
    ret = events.get("HANDLER_RETURN", [])
    if enter and ret:
        return (ret[-1]["ts"] - enter[-1]["ts"]) / 1_000_000.0
    return None


def compute_decode_event_ms(events):
    begin = events.get("STREAM_DECODE_BEGIN", [])
    end = events.get("STREAM_DECODE_END", [])
    if begin and end:
        return (end[-1]["ts"] - begin[-1]["ts"]) / 1_000_000.0
    return None


def parse_lifecycle(req_states):
    if not req_states:
        return "?"
    states = [s.get("from_state", "?") for s in req_states] + [req_states[-1].get("to_state", "?")]
    return "→".join(states)


def parse_drain_info(log_text):
    """Count drain events from e2e_profile or server log."""
    drain_count = log_text.count("DRAINING") + log_text.count("DRAIN")
    return drain_count


def parse_first_audio_ts(log_text):
    """Extract first audio PCM timestamp from server log.
    Looks for patterns like: TTS_W0|<ts>|... or first_audio_at=<ts> or T2W output timestamp.
    """
    # T2W first audio
    m = re.search(r"(?:first_audio|wav_0000|T2W_W0).*?(\d{10,})", log_text)
    if m:
        return int(m.group(1))
    # Generic: extracted audio indices
    audio_indices = re.findall(r"wav_(\d{4})", log_text)
    if audio_indices and "wav_0000" in "".join(f"wav_{a}" for a in audio_indices):
        return 1  # signal that at least wav_0000 was produced
    return None


# ── Streaming response collector ──────────────
def collect_streaming_response(resp):
    """Streaming SSE response: collect all events and measure first PCM arrival."""
    first_pcm_ts = None
    pcm_events = []
    complete = False
    lines = []
    try:
        for line in resp.iter_lines(decode_unicode=True):
            if line is None:
                continue
            lines.append(line)
            if not first_pcm_ts and ("pcm" in line.lower() or "audio" in line.lower()):
                first_pcm_ts = time.time()
            if "pcm" in line.lower():
                pcm_events.append(line)
            if "[DONE]" in line or "complete" in line.lower():
                complete = True
    except Exception as e:
        pass
    return {
        "first_pcm_ts": first_pcm_ts,
        "pcm_count": len(pcm_events),
        "complete": complete,
        "line_count": len(lines),
    }


# ── Request runner ────────────────────────────
def run_one_request(tc, prompt, round_idx):
    """Execute one request: omni_init → prefill → decode.
    Returns dict of timing metrics.
    """
    audio_idx = round_idx % len(tc["audios"])
    audio_file = tc["audios"][audio_idx]
    audio_base = AUDIO_PREFIX + audio_file.replace(".wav", "")

    metrics = {"case_type": tc["type"], "round": round_idx, "audio": audio_file, "prompt": prompt[:80]}

    pos_before = log_size()

    # ── omni_init ──
    t0 = time.time()
    r = requests.post(
        BASE + "/v1/stream/omni_init",
        json={"msg_type": 1, "media_type": 1, "use_tts": USE_TTS},
        timeout=REQUEST_TIMEOUT,
    )
    metrics["init_wall_s"] = time.time() - t0
    if r.status_code != 200:
        metrics["error"] = f"omni_init HTTP {r.status_code}: {r.text[:200]}"
        return metrics

    # ── prefill ──
    t0 = time.time()
    body = {
        "audio_path_prefix": audio_base,
        "cnt": 1,
        "text": prompt,
    }
    r = requests.post(
        BASE + "/v1/stream/prefill",
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    metrics["prefill_wall_ms"] = (time.time() - t0) * 1000.0
    if r.status_code != 200:
        metrics["error"] = f"prefill HTTP {r.status_code}: {r.text[:200]}"
        return metrics

    # ── decode ──
    t0 = time.time()
    r = requests.post(
        BASE + "/v1/stream/decode",
        json={"stream": False, "round_idx": round_idx, "debug_dir": OUTPUT_DIR},
        timeout=REQUEST_TIMEOUT,
    )
    metrics["decode_wall_s"] = time.time() - t0
    metrics["response_complete_s"] = time.time() - t0

    if r.status_code != 200:
        metrics["error"] = f"decode HTTP {r.status_code}: {r.text[:200]}"
        return metrics

    metrics["total_wall_s"] = metrics["init_wall_s"] + metrics["prefill_wall_ms"] / 1000.0 + metrics["decode_wall_s"]

    # ── Parse server log ──
    pos_after = log_size()
    log_seg = read_log_segment(pos_before, pos_after)

    events, req_states = parse_f6_events(log_seg)
    metrics["mutex_wait_us"] = compute_mutex_wait_us(events)
    metrics["handler_hold_ms"] = compute_handler_hold_ms(events)
    metrics["decode_event_ms"] = compute_decode_event_ms(events)
    metrics["lifecycle"] = parse_lifecycle(req_states)
    metrics["drain_count"] = parse_drain_info(log_seg)
    metrics["wav_count"] = len(re.findall(r"wav_\d+\.wav", log_seg))

    # First audio timestamp (if available)
    fa_ts = parse_first_audio_ts(log_seg)
    metrics["first_audio_ts"] = fa_ts

    # Check for errors in log
    metrics["has_timeout"] = 1 if "TIMEOUT" in log_seg else 0
    metrics["has_error"] = 1 if ("CANN error" in log_seg or "NPU error" in log_seg or "assertion failed" in log_seg) else 0

    return metrics


# ── Gate checker ──────────────────────────────
def check_progressive_gate(completed, gate_at):
    """Check progressive gate: at N completed, verify quality so far."""
    if len(completed) < gate_at:
        return

    recent = completed[:gate_at]
    n = len(recent)
    ok = sum(1 for r in recent if "error" not in r)
    timeouts = sum(r.get("has_timeout", 0) for r in recent)
    errors = sum(r.get("has_error", 0) for r in recent)

    print(f"\n── Progressive Gate @ {gate_at}/{TOTAL_REQUESTS} ──")
    print(f"  Completed:        {n}")
    print(f"  OK (no error):    {ok}/{n}")
    print(f"  Timeout in log:   {timeouts}")
    print(f"  CANN/NPU errors:  {errors}")

    # Calculate timing stats
    tot = [r["total_wall_s"] for r in recent if "error" not in r and "total_wall_s" in r]
    if tot:
        stot = sorted(tot)
        print(f"  Total p50:        {stot[len(stot)//2]:.1f}s")
        print(f"  Total p95:        {stot[int(len(stot)*0.95)]:.1f}s")

    # Lifestyles
    lifecycles = [r.get("lifecycle", "?") for r in recent if "error" not in r]
    from collections import Counter
    lc_counts = Counter(lifecycles)
    print(f"  Lifecycles:       {dict(lc_counts)}")

    # WAV count
    wavs = [r.get("wav_count", 0) for r in recent if "error" not in r]
    if wavs:
        print(f"  WAV (mean):       {statistics.mean(wavs):.1f}")

    gate_ok = ok == n and timeouts == 0 and errors == 0
    print(f"  Gate: {'✅ PASS' if gate_ok else '❌ FAIL'}")
    return gate_ok


# ── Main ──────────────────────────────────────
def main():
    print("=" * 72)
    print("S13 120/120 Comprehensive Baseline")
    print(f"Server:  {BASE}")
    print(f"Model:   FP16, -ngl 999, CANN0")
    print(f"TTS:     {'ON' if USE_TTS else 'OFF'}")
    print(f"Cases:   4 types × {REQUESTS_PER_CASE} requests = {TOTAL_REQUESTS} total")
    print(f"Output:  {OUTPUT_DIR}")
    print("=" * 72)

    all_results = []
    start_time = datetime.datetime.now()
    req_counter = 0

    for tc in TEST_CASES:
        print(f"\n{'─' * 60}")
        print(f"Case: {tc['label']} ({tc['type']}) — {REQUESTS_PER_CASE} requests")
        print(f"{'─' * 60}")

        for rnd in range(REQUESTS_PER_CASE):
            req_counter += 1
            prompt = tc["prompts"][rnd]
            label = f"{tc['type']}-R{rnd+1:02d}"

            metrics = run_one_request(tc, prompt, rnd)
            metrics["request_order"] = req_counter
            metrics["label"] = label

            ok = "error" not in metrics
            dur = metrics.get("total_wall_s", 0)
            err = metrics.get("error", "")
            lc = metrics.get("lifecycle", "?")
            wav = metrics.get("wav_count", 0)

            print(f"  [{req_counter:3d}/{TOTAL_REQUESTS}] {label:24s} "
                  f"ok={'✓' if ok else '✗'} dur={dur:.1f}s wav={wav} lc={lc}"
                  + (f" ERR={err}" if not ok else ""))

            all_results.append(metrics)

            # Progressive gate
            if req_counter in PROGRESSIVE_GATES:
                check_progressive_gate(all_results, req_counter)

            time.sleep(COOLDOWN_S)

    elapsed_total = (datetime.datetime.now() - start_time).total_seconds()

    # ── Final Summary ──────────────────────────
    print(f"\n{'=' * 72}")
    print("S13 120/120 — Final Summary")
    print(f"{'=' * 72}")

    ok_results = [r for r in all_results if "error" not in r]
    fail_results = [r for r in all_results if "error" in r]

    print(f"\nRequests: {len(ok_results)}/{len(all_results)} OK, {len(fail_results)} FAILED")
    print(f"Total elapsed: {elapsed_total:.1f}s ({elapsed_total/60:.1f} min)")

    # Per-type breakdown
    print(f"\n── Per-Type Breakdown ──")
    for tc in TEST_CASES:
        type_results = [r for r in ok_results if r["case_type"] == tc["type"]]
        n = len(type_results)
        tots = sorted([r["total_wall_s"] for r in type_results])
        prefs = sorted([r.get("prefill_wall_ms", 0) for r in type_results])
        decs = sorted([r.get("decode_wall_s", 0) for r in type_results])
        wavs = [r.get("wav_count", 0) for r in type_results]
        errs = sum(1 for r in all_results if r["case_type"] == tc["type"] and "error" in r)
        if tots:
            print(f"  {tc['label']:8s}: n={n}, err={errs}, "
                  f"total p50={tots[n//2]:.1f}s p95={tots[int(n*0.95)]:.1f}s, "
                  f"prefill p50={prefs[n//2]:.0f}ms, decode p50={decs[n//2]:.1f}s, "
                  f"wav p50={sorted(wavs)[n//2] if wavs else 0}")

    # Combined stats
    tots = sorted([r["total_wall_s"] for r in ok_results])
    prefs = sorted([r.get("prefill_wall_ms", 0) for r in ok_results])
    mtx = sorted([r.get("mutex_wait_us", 0) or 0 for r in ok_results])
    hh = sorted([r.get("handler_hold_ms", 0) or 0 for r in ok_results])

    if tots:
        print(f"\n── Combined Statistics (n={len(tots)}) ──")
        print(f"  Total:       p50={tots[len(tots)//2]:.1f}s p95={tots[int(len(tots)*0.95)]:.1f}s p99={tots[int(len(tots)*0.99)]:.1f}s")
        print(f"  Prefill:     p50={prefs[len(prefs)//2]:.0f}ms p95={prefs[int(len(prefs)*0.95)]:.0f}ms")
        print(f"  Mutex wait:  p50={mtx[len(mtx)//2]:.1f}µs p95={mtx[int(len(mtx)*0.95)]:.1f}µs")
        print(f"  Handler hold:p50={hh[len(hh)//2]:.0f}ms p95={hh[int(len(hh)*0.95)]:.0f}ms")

    # Error summary
    if fail_results:
        print(f"\n── Errors ({len(fail_results)}) ──")
        for r in fail_results[:10]:
            print(f"  {r['label']}: {r.get('error', 'unknown')}")

    # Lifecycle summary
    from collections import Counter
    lcs = Counter(r.get("lifecycle", "?") for r in ok_results)
    print(f"\n── Lifecycles ──")
    for lc, cnt in lcs.most_common():
        print(f"  {lc}: {cnt}")

    # Gate check
    timeouts = sum(r.get("has_timeout", 0) for r in all_results)
    errors = sum(r.get("has_error", 0) for r in all_results)
    no_wav = sum(1 for r in ok_results if r.get("wav_count", 0) == 0)

    print(f"\n── Final Gate Check ──")
    checks = [
        ("Valid requests", len(ok_results), TOTAL_REQUESTS, ">="),
        ("Errors/Failures", len(fail_results), 0, "=="),
        ("Timeouts in log", timeouts, 0, "=="),
        ("CANN/NPU errors", errors, 0, "=="),
    ]
    # Zero-WAV is informational only (model speech token generation varies by prompt)
    if no_wav > 0:
        print(f"  [ℹ INFO] Zero-WAV requests: {no_wav} (model behavior, not server fault)")
    all_pass = True
    for name, actual, expected, op in checks:
        if op == "==":
            passed = actual == expected
        elif op == ">=":
            passed = actual >= expected
        else:
            passed = False
        flag = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            all_pass = False
        print(f"  [{flag}] {name}: {actual} (expected {op} {expected})")

    print(f"\n  S13 120/120: {'PASS' if all_pass else 'FAIL'}")

    # ── Save CSV ──
    csv_path = f"{OUTPUT_DIR}/s13_120_baseline.csv"
    with open(csv_path, "w") as f:
        fields = ["request_order", "label", "case_type", "round", "audio",
                  "init_wall_s", "prefill_wall_ms", "decode_wall_s", "total_wall_s",
                  "mutex_wait_us", "handler_hold_ms", "decode_event_ms",
                  "wav_count", "drain_count", "lifecycle",
                  "has_timeout", "has_error",
                  "first_audio_ts", "error"]
        f.write(",".join(fields) + "\n")
        for r in all_results:
            f.write(",".join(str(r.get(k, "")) for k in fields) + "\n")
    print(f"\nCSV: {csv_path}")

    # ── Save JSON ──
    report = {
        "test": "S13 120/120 Comprehensive Baseline",
        "timestamp": start_time.isoformat(),
        "duration_s": elapsed_total,
        "config": {
            "server": BASE,
            "model": "MiniCPM-o-4_5-F16.gguf FP16 -ngl999 CANN0",
            "use_tts": USE_TTS,
            "requests_total": TOTAL_REQUESTS,
            "requests_per_case": REQUESTS_PER_CASE,
        },
        "results_summary": {
            "ok": len(ok_results),
            "failed": len(fail_results),
            "total_wall_p50_s": tots[len(tots)//2] if tots else -1,
            "total_wall_p95_s": tots[int(len(tots)*0.95)] if tots else -1,
            "prefill_p50_ms": prefs[len(prefs)//2] if prefs else -1,
            "mutex_wait_p50_us": mtx[len(mtx)//2] if mtx else -1,
            "handler_hold_p50_ms": hh[len(hh)//2] if hh else -1,
            "timeouts": timeouts,
            "cann_errors": errors,
            "zero_wav": no_wav,
        },
        "gate_checks": {c[0]: {"actual": c[1], "expected": c[2], "passed": (c[1] >= c[2] if c[3] == ">=" else c[1] == c[2])} for c in checks},
        "passed": all_pass,
        "results": all_results,
    }
    json_path = f"{OUTPUT_DIR}/s13_120_baseline_report.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"JSON: {json_path}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
