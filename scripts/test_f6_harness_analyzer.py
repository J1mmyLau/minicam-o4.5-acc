#!/usr/bin/env python3
"""
Unit tests for f6_e2e_ab_harness.py — compute_pair_statistics and schema validation.

Tests cover:
  1. FULL_VALID_PAIR: Both OFF/ON have all canonical fields → no exclusions
  2. MISSING_WAV_READY: Audio profile missing → D0→W0 excluded with reason
  3. NEGATIVE_DURATION: Anomalous negative duration detected and flagged
  4. INCONSISTENT_IDS: request_index mismatch between OFF and ON
"""

import json
import sys
import os

# Make harness importable
sys.path.insert(0, os.path.dirname(__file__))

# Import functions under test from the harness
from f6_e2e_ab_harness import (
    compute_pair_statistics,
    aggregate_pair_statistics,
    CANONICAL_STAGE_KEYS,
    CANONICAL_METRICS,
    _resolve_stage_value,
    _check_consistency,
)


# ──────────────────────────────────────────────────────────
# Fixture 1: FULL_VALID_PAIR
# ──────────────────────────────────────────────────────────
FIXTURE_FULL_VALID_OFF = {
    "partial_profile": {
        "request_index": 0,
        "generation_id": 1,
        "stages_ms": {
            "request_received": 100,
            "llm_first_decode_step": 2500,
            "llm_first_token": 4200,
            "tts_wake": 20500,
            "talker_first_audio_token": 21000,
        },
    },
    "audio_profile": {
        "request_index": 0,
        "generation_id": 1,
        "profile_status": "audio_complete",
        "async_stages_ms": {
            "wav_ready": 28000,
        },
    },
    "client_timings_ns": {
        "request_send": 1000000000,
        "first_wav_file_detected": 32000000000,
        "first_valid_pcm": 32000000000,
        "client_request_to_first_wav_file_ns": 31000000000,
        "client_request_to_first_valid_pcm_ns": 31000000000,
    },
    "w0_present": True,
    "w0_value_ms": 25500,
}

FIXTURE_FULL_VALID_ON = {
    "partial_profile": {
        "request_index": 0,
        "generation_id": 1,
        "stages_ms": {
            "request_received": 100,
            "llm_first_decode_step": 2500,
            "llm_first_token": 4200,
            "tts_wake": 20300,
            "talker_first_audio_token": 20800,
        },
    },
    "audio_profile": {
        "request_index": 0,
        "generation_id": 1,
        "profile_status": "audio_complete",
        "async_stages_ms": {
            "wav_ready": 27000,
        },
    },
    "client_timings_ns": {
        "request_send": 5000000000,
        "first_wav_file_detected": 34000000000,
        "first_valid_pcm": 34000000000,
        "client_request_to_first_wav_file_ns": 29000000000,
        "client_request_to_first_valid_pcm_ns": 29000000000,
    },
    "w0_present": True,
    "w0_value_ms": 24500,
}


# ──────────────────────────────────────────────────────────
# Fixture 2: MISSING_WAV_READY (audio profile missing)
# ──────────────────────────────────────────────────────────
FIXTURE_MISSING_WAV_OFF = {
    "partial_profile": {
        "request_index": 1,
        "generation_id": 1,
        "stages_ms": {
            "request_received": 200,
            "llm_first_decode_step": 3000,
            "llm_first_token": 5000,
            "tts_wake": 21000,
            "talker_first_audio_token": 21500,
        },
    },
    # audio_profile is missing entirely
    "client_timings_ns": {
        "request_send": 1000000000,
        "client_request_to_first_wav_file_ns": 35000000000,
    },
    "w0_present": False,
    "w0_value_ms": 0,
}

FIXTURE_MISSING_WAV_ON = {
    "partial_profile": {
        "request_index": 1,
        "generation_id": 1,
        "stages_ms": {
            "request_received": 200,
            "llm_first_decode_step": 3000,
            "llm_first_token": 5000,
            "tts_wake": 20900,
            "talker_first_audio_token": 21400,
        },
    },
    # audio_profile missing
    "client_timings_ns": {
        "request_send": 5000000000,
        "client_request_to_first_wav_file_ns": 32000000000,
    },
    "w0_present": False,
    "w0_value_ms": 0,
}


# ──────────────────────────────────────────────────────────
# Fixture 3: NEGATIVE_DURATION (corrupt timestamps)
# ──────────────────────────────────────────────────────────
FIXTURE_NEGATIVE_OFF = {
    "partial_profile": {
        "request_index": 2,
        "generation_id": 1,
        "stages_ms": {
            "request_received": 100,
            "llm_first_decode_step": 28000,   # D0 is AFTER W0 — corrupt
            "llm_first_token": 29000,
            "tts_wake": 30000,
            "talker_first_audio_token": 31000,
        },
    },
    "audio_profile": {
        "request_index": 2,
        "generation_id": 1,
        "profile_status": "audio_complete",
        "async_stages_ms": {
            "wav_ready": 26000,    # wav_ready is BEFORE llm_first_decode_step
        },
    },
    "client_timings_ns": {
        "request_send": 1000000000,
        "client_request_to_first_wav_file_ns": 30000000000,
    },
    "w0_present": True,
    "w0_value_ms": 25900,
}

FIXTURE_NEGATIVE_ON = {
    "partial_profile": {
        "request_index": 2,
        "generation_id": 1,
        "stages_ms": {
            "request_received": 100,
            "llm_first_decode_step": 29000,
            "llm_first_token": 30000,
            "tts_wake": 31000,
            "talker_first_audio_token": 32000,
        },
    },
    "audio_profile": {
        "request_index": 2,
        "generation_id": 1,
        "profile_status": "audio_complete",
        "async_stages_ms": {
            "wav_ready": 27000,
        },
    },
    "client_timings_ns": {
        "request_send": 5000000000,
        "client_request_to_first_wav_file_ns": 31000000000,
    },
    "w0_present": True,
    "w0_value_ms": 26900,
}


# ──────────────────────────────────────────────────────────
# Fixture 4: INCONSISTENT_IDS (request_index mismatch)
# ──────────────────────────────────────────────────────────
FIXTURE_INCONSISTENT_OFF = {
    "partial_profile": {
        "request_index": 5,
        "generation_id": 3,
        "stages_ms": {
            "request_received": 100,
            "llm_first_decode_step": 2000,
            "llm_first_token": 4000,
            "tts_wake": 19000,
            "talker_first_audio_token": 19500,
        },
    },
    "audio_profile": {
        "request_index": 5,
        "generation_id": 3,
        "profile_status": "audio_complete",
        "async_stages_ms": {
            "wav_ready": 26000,
        },
    },
    "client_timings_ns": {
        "request_send": 1000000000,
        "client_request_to_first_wav_file_ns": 28000000000,
    },
    "w0_present": True,
    "w0_value_ms": 25000,
}

FIXTURE_INCONSISTENT_ON = {
    "partial_profile": {
        "request_index": 7,     # MISMATCH: should be 5
        "generation_id": 4,     # MISMATCH: should be 3
        "stages_ms": {
            "request_received": 100,
            "llm_first_decode_step": 2000,
            "llm_first_token": 4000,
            "tts_wake": 18800,
            "talker_first_audio_token": 19300,
        },
    },
    "audio_profile": {
        "request_index": 7,
        "generation_id": 4,
        "profile_status": "audio_complete",
        "async_stages_ms": {
            "wav_ready": 25500,
        },
    },
    "client_timings_ns": {
        "request_send": 5000000000,
        "client_request_to_first_wav_file_ns": 27000000000,
    },
    "w0_present": True,
    "w0_value_ms": 24500,
}


# ──────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────
def test_fixture1_full_valid_pair():
    """Fixture 1: All canonical fields present → 0 exclusions, valid deltas."""
    pair = {"off": FIXTURE_FULL_VALID_OFF, "on": FIXTURE_FULL_VALID_ON, "pair_idx": 0}
    stats = compute_pair_statistics(pair)

    # No exclusions
    assert stats["exclusion_reasons"] == [], f"Expected 0 exclusions, got: {stats['exclusion_reasons']}"
    assert stats["anomalies"] == [], f"Expected 0 anomalies, got: {stats['anomalies']}"
    assert stats["schema_issues"] == [], f"Expected 0 schema issues, got: {stats['schema_issues']}"

    # D2→G0
    assert stats["D2_to_G0_off_ms"] > 0, "D2→G0 off should be positive"
    assert stats["D2_to_G0_on_ms"] > 0, "D2→G0 on should be positive"
    assert stats["D2_to_G0_delta_ms"] == stats["D2_to_G0_on_ms"] - stats["D2_to_G0_off_ms"]

    # D0→W0 (B6b should reduce this)
    assert "D0_to_W0_off_ms" in stats
    assert "D0_to_W0_on_ms" in stats
    assert "D0_to_W0_delta_ms" in stats

    # Client timing
    assert "CLIENT_request_to_first_wav_delta_ms" in stats

    print("PASS: test_fixture1_full_valid_pair")
    return True


def test_fixture2_missing_wav_ready():
    """Fixture 2: Audio profile missing → D0→W0 excluded, D2→G0 still valid."""
    pair = {"off": FIXTURE_MISSING_WAV_OFF, "on": FIXTURE_MISSING_WAV_ON, "pair_idx": 1}
    stats = compute_pair_statistics(pair)

    # D2→G0 should still work (doesn't need audio profile)
    assert "D2_to_G0_off_ms" in stats, "D2→G0 off should be present"
    assert "D2_to_G0_on_ms" in stats, "D2→G0 on should be present"

    # D0→W0 should NOT be present (wav_ready is missing)
    assert "D0_to_W0_off_ms" not in stats, "D0→W0 off should be MISSING (no audio profile)"

    # Should have exclusion reasons
    assert len(stats["exclusion_reasons"]) > 0, "Should have exclusion reasons for missing fields"
    print(f"  Exclusion reasons: {stats['exclusion_reasons']}")

    # D0→G3 should work
    assert "D0_to_G3_off_ms" in stats
    assert "D0_to_G3_on_ms" in stats

    # Client wav should be present (from client_timings_ns)
    assert "CLIENT_request_to_first_wav_delta_ms" in stats

    print("PASS: test_fixture2_missing_wav_ready")
    return True


def test_fixture3_negative_duration():
    """Fixture 3: Corrupt timestamps → D0→W0 flagged as negative duration."""
    pair = {"off": FIXTURE_NEGATIVE_OFF, "on": FIXTURE_NEGATIVE_ON, "pair_idx": 2}
    stats = compute_pair_statistics(pair)

    # Should have anomalies
    assert len(stats["anomalies"]) > 0, f"Should have anomalies for negative duration, got: {stats['anomalies']}"
    print(f"  Anomalies: {stats['anomalies']}")

    # Exclusion reasons should include the anomaly
    assert len(stats["exclusion_reasons"]) > 0, "Should exclude pair due to negative duration"

    # D0→W0 off should be negative
    if "D0_to_W0_off_ms" in stats:
        assert stats["D0_to_W0_off_ms"] < 0, f"D0→W0 off should be negative, got: {stats['D0_to_W0_off_ms']}"

    print("PASS: test_fixture3_negative_duration")
    return True


def test_fixture4_inconsistent_ids():
    """Fixture 4: request_index mismatch → schema issues detected, not excluded."""
    pair = {"off": FIXTURE_INCONSISTENT_OFF, "on": FIXTURE_INCONSISTENT_ON, "pair_idx": 3}
    stats = compute_pair_statistics(pair)

    # Should have schema issues for inconsistency
    id_issues = [i for i in stats["schema_issues"] if "INCONSISTENT" in i]
    assert len(id_issues) > 0, f"Should detect inconsistent IDs, got: {stats['schema_issues']}"
    print(f"  Schema issues: {stats['schema_issues']}")

    # Metrics should still be computed (consistency issues are warnings, not blockers)
    # D2→G0 should still work
    assert "D2_to_G0_off_ms" in stats
    assert "D2_to_G0_on_ms" in stats

    print("PASS: test_fixture4_inconsistent_ids")
    return True


def test_resolve_stage_value_missing_field():
    """_resolve_stage_value returns None+MISSING_FIELD for absent keys, NEVER 0."""
    result = {
        "partial_profile": {
            "stages_ms": {
                "llm_first_token": 4000,
                # tts_wake is MISSING
            },
        },
    }
    # llm_first_token should resolve
    val, src, err = _resolve_stage_value(result, "llm_first_token")
    assert val == 4000, f"Expected 4000, got {val}"
    assert err is None, f"Expected no error, got {err}"

    # tts_wake should fail with MISSING_FIELD
    val, src, err = _resolve_stage_value(result, "tts_wake")
    assert val is None, f"Expected None for missing field, got {val}"
    assert err and "MISSING_FIELD" in err, f"Expected MISSING_FIELD error, got {err}"

    # wav_ready requires audio_profile — should fail
    val, src, err = _resolve_stage_value(result, "wav_ready")
    assert val is None, f"Expected None (no audio profile), got {val}"
    assert err and "MISSING_PROFILE" in err, f"Expected MISSING_PROFILE, got {err}"

    print("PASS: test_resolve_stage_value_missing_field")
    return True


def test_check_consistency():
    """_check_consistency detects request_index and generation_id mismatches."""
    issues = _check_consistency(
        FIXTURE_INCONSISTENT_OFF, FIXTURE_INCONSISTENT_ON)
    assert len(issues) >= 2, f"Expected at least 2 inconsistency issues, got {len(issues)}"
    print(f"  Consistency issues: {issues}")

    # Valid pair should have 0 issues
    issues = _check_consistency(FIXTURE_FULL_VALID_OFF, FIXTURE_FULL_VALID_ON)
    assert len(issues) == 0, f"Expected 0 issues, got {issues}"

    print("PASS: test_check_consistency")
    return True


def test_aggregate_with_exclusions():
    """aggregate_pair_statistics correctly handles excluded pairs."""
    pairs = [
        {"stats": compute_pair_statistics({"off": FIXTURE_FULL_VALID_OFF, "on": FIXTURE_FULL_VALID_ON, "pair_idx": 0})},
        {"stats": compute_pair_statistics({"off": FIXTURE_MISSING_WAV_OFF, "on": FIXTURE_MISSING_WAV_ON, "pair_idx": 1})},
        {"stats": compute_pair_statistics({"off": FIXTURE_NEGATIVE_OFF, "on": FIXTURE_NEGATIVE_ON, "pair_idx": 2})},
    ]
    agg = aggregate_pair_statistics(pairs)

    assert agg["num_pairs_total"] == 3
    assert agg["num_pairs_excluded"] == 2, f"Expected 2 excluded pairs, got {agg['num_pairs_excluded']}"
    assert agg["num_pairs_valid"] == 1
    assert len(agg["exclusion_summary"]) > 0

    print(f"  Total: {agg['num_pairs_total']}, Excluded: {agg['num_pairs_excluded']}, Valid: {agg['num_pairs_valid']}")
    print(f"  Exclusion summary: {agg['exclusion_summary']}")
    print("PASS: test_aggregate_with_exclusions")
    return True


def test_zero_is_never_substituted():
    """Regression: a stage value of 0 is NOT a missing field — it's a valid timestamp at time 0."""
    result = {
        "partial_profile": {
            "stages_ms": {
                "request_received": 0,  # Valid — request_received can be 0 at the start
                "llm_first_decode_step": 2000,
                "llm_first_token": 4000,
                "tts_wake": 20000,
                "talker_first_audio_token": 20500,
            },
        },
        "audio_profile": {
            "profile_status": "audio_complete",
            "async_stages_ms": {
                "wav_ready": 26000,
            },
        },
    }

    # request_received=0 is valid — should NOT fail
    val, src, err = _resolve_stage_value(result, "request_received")
    assert val == 0, f"request_received=0 is valid, got val={val}, err={err}"
    assert err is None, f"Expected no error for valid 0, got {err}"

    print("PASS: test_zero_is_never_substituted")
    return True


# ──────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────
def run_all():
    tests = [
        ("Fixture 1: Full Valid Pair", test_fixture1_full_valid_pair),
        ("Fixture 2: Missing WAV Ready", test_fixture2_missing_wav_ready),
        ("Fixture 3: Negative Duration", test_fixture3_negative_duration),
        ("Fixture 4: Inconsistent IDs", test_fixture4_inconsistent_ids),
        ("Resolve Stage Value (Missing Field)", test_resolve_stage_value_missing_field),
        ("Check Consistency", test_check_consistency),
        ("Aggregate with Exclusions", test_aggregate_with_exclusions),
        ("Zero is Valid Timestamp (Not Missing)", test_zero_is_never_substituted),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        print(f"\n{'─'*50}")
        print(f"TEST: {name}")
        print(f"{'─'*50}")
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"RESULTS: {passed}/{passed+failed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
