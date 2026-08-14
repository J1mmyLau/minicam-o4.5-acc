#!/usr/bin/env python3
"""test_analyze_chunk_rtf.py — valid_audio 真实判定 + 离线解析单测

覆盖 10 种排除原因、合法 PCM/WAV fixture、parse_log / compute_summary / --warmup CLI。
离线执行：不起服务、不占 NPU。
运行：python3 -m unittest submission/tests/test_analyze_chunk_rtf.py
"""
import io, json, os, struct, sys, tempfile, unittest, wave

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import analyze_chunk_rtf as A

CHUNK_LINE = ("T2W线程: wav_1001.wav | 0.10s audio | 25.0ms inference | RTF=0.25 "
              "| t=1234ms | queue_wait=5.0ms | req=1 gen=1\n")


def make_row(**kw):
    base = dict(
        request_id=1, generation=1, chunk_index=0,
        is_first_chunk=True, is_final_chunk=True,
        chunk_compute_ms=100.0, sample_count=2400, sample_rate=24000,
        audio_duration_ms=100.0, chunk_rtf=1.0,
        t_cumulative_ms=1234, queue_wait_ms=5.0,
        decode_to_first_audio_ms=1200, valid_audio=None, exclusion_reason="", error="",
    )
    base.update(kw)
    return base


def make_wav(path, rate=24000, frames=2400, nchannels=1, sampwidth=2, corrupt=False):
    if corrupt:
        with open(path, "wb") as f:
            f.write(b"RIFFNOTAWAVFILE" + os.urandom(32))
        return
    with wave.open(path, "wb") as w:
        w.setnchannels(nchannels)
        w.setsampwidth(sampwidth)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * (frames * nchannels))


class TestValidateChunk(unittest.TestCase):
    def test_valid(self):
        r = make_row()
        r = A.validate_chunk(r, set())
        self.assertTrue(r["valid_audio"])
        self.assertEqual(r["exclusion_reason"], "")

    def test_empty_payload_compute_none(self):
        r = A.validate_chunk(make_row(chunk_compute_ms=None), set())
        self.assertFalse(r["valid_audio"])
        self.assertIn("EMPTY_PAYLOAD", r["exclusion_reason"])

    def test_empty_payload_zero_duration(self):
        r = A.validate_chunk(make_row(audio_duration_ms=0.0, chunk_rtf=None), set())
        self.assertIn("EMPTY_PAYLOAD", r["exclusion_reason"])

    def test_zero_samples(self):
        r = A.validate_chunk(make_row(sample_count=0), set())
        self.assertIn("ZERO_SAMPLES", r["exclusion_reason"])

    def test_invalid_sample_rate(self):
        r = A.validate_chunk(make_row(sample_rate=8000), set())
        self.assertIn("INVALID_SAMPLE_RATE", r["exclusion_reason"])

    def test_nan_inf(self):
        r = A.validate_chunk(make_row(chunk_compute_ms=float("nan")), set())
        self.assertIn("NAN_INF", r["exclusion_reason"])
        r2 = A.validate_chunk(make_row(chunk_rtf=float("inf")), set())
        self.assertIn("NAN_INF", r2["exclusion_reason"])

    def test_missing_request_id(self):
        r = A.validate_chunk(make_row(request_id=None), set())
        self.assertIn("MISSING_REQUEST_ID", r["exclusion_reason"])

    def test_missing_chunk_index(self):
        r = A.validate_chunk(make_row(chunk_index=None), set())
        self.assertIn("MISSING_CHUNK_INDEX", r["exclusion_reason"])

    def test_invalid_timestamp_negative_compute(self):
        r = A.validate_chunk(make_row(chunk_compute_ms=-1.0), set())
        self.assertIn("INVALID_TIMESTAMP", r["exclusion_reason"])

    def test_invalid_timestamp_inf_t(self):
        r = A.validate_chunk(make_row(t_cumulative_ms=float("inf")), set())
        self.assertIn("INVALID_TIMESTAMP", r["exclusion_reason"])

    def test_duplicate_chunk(self):
        seen = set()
        r1 = A.validate_chunk(make_row(chunk_index=3), seen)
        self.assertTrue(r1["valid_audio"])
        r2 = A.validate_chunk(make_row(chunk_index=3), seen)
        self.assertIn("DUPLICATE_CHUNK", r2["exclusion_reason"])

    def test_truncated_chunk(self):
        r = A.validate_chunk(make_row(is_final_chunk=True, audio_duration_ms=10.0), set())
        self.assertIn("TRUNCATED_CHUNK", r["exclusion_reason"])

    def test_non_final_short_duration_not_truncated(self):
        r = A.validate_chunk(make_row(is_final_chunk=False, audio_duration_ms=10.0), set())
        self.assertTrue(r["valid_audio"])


class TestWavCrossCheck(unittest.TestCase):
    def test_valid_wav_passes(self):
        with tempfile.TemporaryDirectory() as d:
            make_wav(os.path.join(d, "wav_1001.wav"))
            r = A.validate_chunk(make_row(chunk_index=1, request_id=1), set(), wav_dir=d)
            self.assertTrue(r["valid_audio"])

    def test_wav_wrong_rate(self):
        with tempfile.TemporaryDirectory() as d:
            make_wav(os.path.join(d, "wav_1001.wav"), rate=16000)
            r = A.validate_chunk(make_row(chunk_index=1, request_id=1), set(), wav_dir=d)
            self.assertIn("INVALID_SAMPLE_RATE", r["exclusion_reason"])

    def test_wav_corrupt_decode_failure(self):
        with tempfile.TemporaryDirectory() as d:
            make_wav(os.path.join(d, "wav_1001.wav"), corrupt=True)
            r = A.validate_chunk(make_row(chunk_index=1, request_id=1), set(), wav_dir=d)
            self.assertIn("DECODE_FAILURE", r["exclusion_reason"])

    def test_wav_missing_not_fail(self):
        with tempfile.TemporaryDirectory() as d:
            r = A.validate_chunk(make_row(chunk_index=1, request_id=1), set(), wav_dir=d)
            self.assertTrue(r["valid_audio"])


class TestParseLog(unittest.TestCase):
    def test_parse_and_final_chunk(self):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
            f.write("🎉 首响时间 (First Audio Response): 1269ms (decode_to_first_audio) | 0ms (request_to_first_audio) | req=1 gen=1\n")
            f.write("T2W线程: wav_1000.wav | 0.10s audio | 25.0ms inference | RTF=0.25 | t=1234ms | queue_wait=5.0ms | req=1 gen=1\n")
            f.write("T2W线程: wav_1001.wav | 0.20s audio | 40.0ms inference | RTF=0.20 | t=2000ms | queue_wait=5.0ms | req=1 gen=1\n")
            f.write("T2W drain: complete (wav_count=2, notify=1 poll=0 fast=0 gen=1)\n")
            path = f.name
        try:
            rows = A.parse_log(path)
            self.assertEqual(len(rows), 2)
            self.assertTrue(rows[0]["is_first_chunk"])    # wav_1000 → chunk 0
            self.assertFalse(rows[0]["is_final_chunk"])
            self.assertTrue(rows[1]["is_final_chunk"])    # per (req,gen) max idx
            self.assertEqual(rows[0]["decode_to_first_audio_ms"], 1269)
            self.assertEqual(rows[0]["chunk_index"], 0)   # wav_1000 % 1000
            self.assertEqual(rows[1]["chunk_index"], 1)
            self.assertEqual(rows[0]["chunk_rtf"], round(25.0 / 100.0, 6))
        finally:
            os.unlink(path)

    def test_no_chunk_lines(self):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
            f.write("just noise\n")
            path = f.name
        try:
            self.assertEqual(A.parse_log(path), [])
        finally:
            os.unlink(path)


class TestSummary(unittest.TestCase):
    def test_reason_counts(self):
        rows = [
            A.validate_chunk(make_row(request_id=1, chunk_index=0, audio_duration_ms=200.0), set()),
            A.validate_chunk(make_row(request_id=1, chunk_index=1, sample_rate=8000), set()),
            A.validate_chunk(make_row(request_id=2, chunk_index=0, chunk_compute_ms=None), set()),
        ]
        s = A.compute_summary(rows, "r1", "src")
        self.assertEqual(s["chunks_total"], 3)
        self.assertEqual(s["chunks_valid"], 1)
        self.assertEqual(s["chunks_invalid"], 2)
        self.assertAlmostEqual(s["exclusion_rate"], 2 / 3, places=6)
        self.assertEqual(s["exclusion_reason_counts"]["INVALID_SAMPLE_RATE"], 1)
        self.assertEqual(s["exclusion_reason_counts"]["EMPTY_PAYLOAD"], 1)


class TestCliWarmup(unittest.TestCase):
    def test_warmup_filters_first_request(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "server.log")
            with open(log, "w") as f:
                # 预热：req=1；测量：req=2,3
                for req, dur, infer in ((1, "0.10", "25.0"), (2, "0.10", "25.0"), (3, "0.10", "25.0")):
                    f.write(f"T2W线程: wav_{req * 1000 + 1}.wav | {dur}s audio | {infer}ms inference | RTF=0.25 | t=1234ms | queue_wait=5.0ms | req={req} gen=1\n")
            out = os.path.join(d, "out")
            sys.argv = ["analyze_chunk_rtf.py", log, "run_x", "--out", out, "--warmup", "1"]
            A.main()
            with open(os.path.join(out, "chunk_rtf_summary.json")) as f:
                s = json.load(f)
            self.assertEqual(s["chunks_total"], 2)
            self.assertEqual(s["requests"], 2)


if __name__ == "__main__":
    unittest.main()
